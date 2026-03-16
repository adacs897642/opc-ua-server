# tests/conftest.py

import pytest
import sys
import os
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import json

# Добавляем корень проекта в path
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


# ============================================================================
# Фикстуры конфигурации
# ============================================================================

@pytest.fixture
def test_config():
    """Тестовая конфигурация"""
    return {
        'app': {
            'name': 'Test OPC Server',
            'version': '1.0.0',
            'namespace_uri': 'http://test.server'
        },
        'server': {
            'endpoint': 'opc.tcp://0.0.0.0:4841/',  # Другой порт для тестов
            'security': {'enable_encryption': False}
        },
        'database': {
            'default': {
                'dbname': 'test_systemx',
                'host': 'localhost',
                'user': 'test_user',
                'password': 'test_password',
                'port': 5432
            }
        },
        'polling': {
            'notify_timeout_sec': 1,
            'update_interval_sec': 1,
            'default_period_min': 60
        },
        'hot_reload': {
            'enabled': True,
            'interval_sec': 5
        },
        'logging': {
            'level': 'DEBUG',
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        }
    }


@pytest.fixture
def test_config_file(tmp_path, test_config):
    """Создаёт временный файл конфигурации"""
    config_file = tmp_path / 'test_config.json'
    with config_file.open('w', encoding='utf-8') as f:
        json.dump(test_config, f, indent=2)
    return str(config_file)


# ============================================================================
# Фикстуры базы данных (мок)
# ============================================================================

@pytest.fixture
def mock_db_connection():
    """Мок подключения к базе данных"""
    mock_conn = MagicMock()
    mock_conn.autocommit = True
    mock_conn.notifies = []
    mock_conn.poll = MagicMock()
    mock_conn.close = MagicMock()
    return mock_conn


@pytest.fixture
def mock_db_cursor():
    """Мок курсора базы данных"""
    mock_cursor = MagicMock()
    mock_cursor.description = None
    mock_cursor.fetchall = MagicMock(return_value=[])
    mock_cursor.rowcount = 0
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    return mock_cursor


@pytest.fixture
def mock_db(mock_db_connection, mock_db_cursor):
    """Мок объекта Database"""
    mock_db_connection.cursor = MagicMock(return_value=mock_db_cursor)

    with patch('db.connection.psycopg2.connect', return_value=mock_db_connection):
        from db.connection import Database
        db = Database({
            'dbname': 'test_db',
            'host': 'localhost',
            'user': 'test',
            'password': 'test'
        })
        yield db


# ============================================================================
# Фикстуры OPC UA (мок)
# ============================================================================

@pytest.fixture
def mock_opc_node():
    """Мок OPC UA узла"""
    node = MagicMock()
    node.nodeid = MagicMock()
    node.set_value = MagicMock()
    node.set_display_name = MagicMock()
    node.set_description = MagicMock()
    node.set_writable = MagicMock()
    node.get_display_name = MagicMock(return_value=MagicMock(Text='Test'))
    node.get_description = MagicMock(return_value=MagicMock(Text='Test'))
    node.delete = MagicMock()
    node.add_variable = MagicMock(return_value=node)
    node.add_method = MagicMock(return_value=node)
    node.add_object = MagicMock(return_value=node)
    return node


@pytest.fixture
def mock_opc_server(mock_opc_node):
    """Мок OPC UA сервера"""
    server = MagicMock()
    server.set_endpoint = MagicMock()
    server.set_server_name = MagicMock()
    server.register_namespace = MagicMock(return_value=2)
    server.start = MagicMock()
    server.stop = MagicMock()
    server.get_objects_node = MagicMock(return_value=mock_opc_node)
    server.get_node = MagicMock(return_value=mock_opc_node)
    return server


# ============================================================================
# Фикстуры для реальных тестов (интеграционные)
# ============================================================================

@pytest.fixture(scope='session')
def docker_compose_file():
    """Путь к docker-compose для тестовой БД"""
    return str(ROOT_DIR / 'docker-compose.test.yml')


@pytest.fixture(scope='session')
def test_db_container(docker_compose_file):
    """Запускает PostgreSQL в Docker для тестов"""
    import subprocess
    import time

    # Запуск контейнера
    subprocess.run(
        ['docker-compose', '-f', docker_compose_file, 'up', '-d', 'postgres'],
        check=True
    )

    # Ждём готовности БД
    time.sleep(5)

    yield

    # Остановка контейнера
    subprocess.run(
        ['docker-compose', '-f', docker_compose_file, 'down', '-v'],
        check=True
    )


@pytest.fixture
def real_db(test_db_container):
    """Реальное подключение к тестовой БД"""
    from db.connection import Database

    db = Database({
        'dbname': 'test_systemx',
        'host': 'localhost',
        'user': 'test_user',
        'password': 'test_password',
        'port': 5432
    })

    # Создаём тестовые таблицы
    setup_test_schema(db)

    yield db

    # Очистка после теста
    teardown_test_schema(db)
    db.close()


def setup_test_schema(db):
    """Создаёт тестовую схему БД"""
    db.execute("""
        CREATE TABLE IF NOT EXISTS commands_catalog (
            id SERIAL PRIMARY KEY,
            code VARCHAR(50) UNIQUE NOT NULL,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            has_params BOOLEAN DEFAULT FALSE,
            param_schema JSONB DEFAULT '[]'::jsonb,
            is_active BOOLEAN DEFAULT TRUE,
            version INT DEFAULT 1,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS commands_queue (
            id SERIAL PRIMARY KEY,
            command_id INT,
            params JSONB,
            status VARCHAR(20) DEFAULT 'pending',
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)


def teardown_test_schema(db):
    """Очищает тестовую схему БД"""
    db.execute("DROP TABLE IF EXISTS commands_queue CASCADE")
    db.execute("DROP TABLE IF EXISTS commands_catalog CASCADE")


# ============================================================================
# Утилиты для тестов
# ============================================================================

@pytest.fixture
def sample_command_data():
    """Пример данных команды для тестов"""
    return {
        'code': 'TEST_COMMAND',
        'name': 'Тестовая команда',
        'description': 'Команда для тестирования',
        'has_params': True,
        'param_schema': [
            {'name': 'value', 'type': 'float', 'min': 0, 'max': 100},
            {'name': 'priority', 'type': 'int', 'min': 1, 'max': 5}
        ]
    }


@pytest.fixture
def sample_telemetry_data():
    """Пример данных телеметрии для тестов"""
    return {
        'alias': 'test_sensor_1',
        'name': 'Датчик температуры',
        'value': 25.5,
        'type': 'float',
        'unit': '°C'
    }