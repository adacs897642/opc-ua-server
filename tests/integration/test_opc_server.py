# tests/integration/test_opc_server.py

import pytest
import time
from opcua import Client

from opc.server import OPCServer


class TestOPCServerIntegration:
    """Интеграционные тесты OPC UA сервера"""

    @pytest.mark.integration
    @pytest.mark.opc
    def test_server_start_stop(self, test_config, mock_db):
        """Запуск и остановка сервера"""
        server = OPCServer(test_config, mock_db)

        server.start()
        assert server.server is not None
        assert server.server.is_running is True

        server.stop()
        assert server.server.is_running is False

    @pytest.mark.integration
    @pytest.mark.opc
    def test_server_endpoint_accessible(self, test_config, mock_db):
        """Проверка доступности эндпоинта"""
        # Запускаем сервер на тестовом порту
        test_config['server']['endpoint'] = 'opc.tcp://0.0.0.0:4841/'

        server = OPCServer(test_config, mock_db)
        server.start()

        try:
            # Пробуем подключиться клиентом
            client = Client('opc.tcp://localhost:4841/')
            client.connect()

            objects = client.nodes.objects
            assert objects is not None

            client.disconnect()
        finally:
            server.stop()

    @pytest.mark.integration
    @pytest.mark.opc
    @pytest.mark.slow
    def test_telemetry_update(self, test_config, real_db):
        """Обновление телеметрии в реальном времени"""
        # Добавляем тестовые данные в БД
        real_db.execute("""
            INSERT INTO objects (obj, sim, lpu) VALUES ('TestObj', '12345', 'LPU1')
        """)

        server = OPCServer(test_config, real_db)
        server.start()

        try:
            client = Client('opc.tcp://localhost:4841/')
            client.connect()

            # Ждём обновления
            time.sleep(2)

            # Проверяем наличие узлов
            objects = client.nodes.objects.get_children()
            assert len(objects) > 0

            client.disconnect()
        finally:
            server.stop()