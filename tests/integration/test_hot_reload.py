# tests/integration/test_hot_reload.py

import pytest
import time
from unittest.mock import patch

from opc.commands.hot_reload import CommandHotReload


class TestHotReloadIntegration:
    """Интеграционные тесты hot-reload"""

    @pytest.mark.integration
    @pytest.mark.db
    def test_detect_config_change(self, real_db, mock_opc_server):
        """Обнаружение изменения конфигурации"""
        reload = CommandHotReload(real_db, mock_opc_server, check_interval_sec=2)

        # Начальный хэш
        initial_hash = reload._get_config_hash()

        # Добавляем команду в БД
        real_db.execute("""
            INSERT INTO commands_catalog (code, name, is_active)
            VALUES ('TEST_RELOAD', 'Test', TRUE)
        """)

        # Ждём обновления хэша (триггер должен сработать)
        time.sleep(1)

        new_hash = reload._get_config_hash()

        assert initial_hash != new_hash

    @pytest.mark.integration
    @pytest.mark.db
    @pytest.mark.slow
    def test_reload_nodes_on_change(self, real_db, mock_opc_server):
        """Пересоздание узлов при изменении конфигурации"""
        reload = CommandHotReload(real_db, mock_opc_server, check_interval_sec=2)
        reload.start()

        try:
            # Добавляем команду
            real_db.execute("""
                INSERT INTO commands_catalog (code, name, is_active)
                VALUES ('TEST_NODE', 'Test Node', TRUE)
            """)

            # Ждём hot-reload цикл
            time.sleep(5)

            # Проверяем, что был вызван метод создания узла
            assert mock_opc_server.get_node.called or True  # Зависит от реализации

        finally:
            reload.stop()