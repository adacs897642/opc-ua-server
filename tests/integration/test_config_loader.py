# tests/unit/test_config_loader.py

import pytest
import json
from pathlib import Path
from unittest.mock import patch, mock_open

from config.loader import ConfigLoader


class TestConfigLoader:
    """Тесты загрузчика конфигурации"""

    @pytest.mark.unit
    def test_load_config_success(self, tmp_path, test_config):
        """Успешная загрузка конфигурации"""
        config_file = tmp_path / 'config.json'
        with config_file.open('w') as f:
            json.dump(test_config, f)

        loader = ConfigLoader(str(config_file))
        config = loader.load()

        assert config['app']['name'] == 'Test OPC Server'
        assert config['server']['endpoint'] == 'opc.tcp://0.0.0.0:4841/'

    @pytest.mark.unit
    def test_load_config_file_not_found(self):
        """Ошибка при отсутствии файла"""
        loader = ConfigLoader('/nonexistent/path/config.json')

        with pytest.raises(FileNotFoundError):
            loader.load()

    @pytest.mark.unit
    def test_load_config_invalid_json(self, tmp_path):
        """Ошибка при невалидном JSON"""
        config_file = tmp_path / 'config.json'
        with config_file.open('w') as f:
            f.write('{invalid json}')

        loader = ConfigLoader(str(config_file))

        with pytest.raises(json.JSONDecodeError):
            loader.load()

    @pytest.mark.unit
    def test_get_nested_value(self, test_config):
        """Получение вложенных значений"""
        loader = ConfigLoader()
        loader._config = test_config

        assert loader.get('app.name') == 'Test OPC Server'
        assert loader.get('server.endpoint') == 'opc.tcp://0.0.0.0:4841/'
        assert loader.get('nonexistent.key', 'default') == 'default'

    @pytest.mark.unit
    def test_get_missing_value_with_default(self, test_config):
        """Получение отсутствующего значения с дефолтом"""
        loader = ConfigLoader()
        loader._config = test_config

        assert loader.get('missing.key', 'default_value') == 'default_value'
        assert loader.get('app.missing', None) is None