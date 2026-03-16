# tests/fixtures/db.py
# -*- coding: utf-8 -*-
"""
Специализированные фикстуры для базы данных
"""

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def db_with_commands(mock_db):
    """БД с предзагруженными командами"""
    mock_db.query.return_value = [
        (1, 'REBOOT', 'Перезагрузка', '', False, '[]', True),
        (2, 'SET_CONFIG', 'Настройка', '', True, '[{"name": "key"}]', True),
    ]
    return mock_db


@pytest.fixture
def db_with_empty_commands(mock_db):
    """БД без команд"""
    mock_db.query.return_value = []
    return mock_db


@pytest.fixture
def db_with_error(mock_db):
    """БД которая выбрасывает ошибку"""
    import psycopg2
    mock_db.query.side_effect = psycopg2.Error("Connection failed")
    return mock_db


@pytest.fixture
def db_notification(mock_db):
    """БД с NOTIFY уведомлением"""
    mock_db.conn.notifies = [MagicMock(channel='test_alias', payload='')]
    return mock_db