# tests/unit/test_config_schema.py
# -*- coding: utf-8 -*-

import pytest
import json
from pathlib import Path
import jsonschema

ROOT_DIR = Path(__file__).parent.parent.parent


class TestConfigSchema:

    @pytest.fixture
    def schema(self):
        """Загружает схему"""
        schema_path = ROOT_DIR / 'config' / 'schema.json'
        with schema_path.open('r', encoding='utf-8') as f:
            return json.load(f)

    @pytest.fixture
    def valid_config(self):
        """Валидная конфигурация"""
        return {
            'app': {'name': 'Test', 'version': '1.0.0', 'namespace_uri': 'http://test'},
            'server': {'endpoint': 'opc.tcp://0.0.0.0:4840/'},
            'database': {'default': {'dbname': 'db', 'host': 'localhost', 'user': 'u', 'password': 'p'}}
        }

    def test_valid_config_passes(self, schema, valid_config):
        """Валидная конфигурация проходит проверку"""
        jsonschema.validate(instance=valid_config, schema=schema)
        # Если нет исключения - тест пройден

    def test_missing_required_field(self, schema, valid_config):
        """Отсутствие обязательного поля вызывает ошибку"""
        del valid_config['app']

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_config, schema=schema)

    def test_invalid_port_type(self, schema, valid_config):
        """Неверный тип порта вызывает ошибку"""
        valid_config['server']['port'] = '4840'  # Строка вместо числа

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_config, schema=schema)

    def test_port_out_of_range(self, schema, valid_config):
        """Порт вне диапазона вызывает ошибку"""
        valid_config['server']['port'] = 70000

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_config, schema=schema)

    def test_invalid_log_level(self, schema, valid_config):
        """Неверный уровень лога вызывает ошибку"""
        valid_config['logging'] = {'level': 'TRACE'}

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_config, schema=schema)

    def test_additional_properties_not_allowed(self, schema, valid_config):
        """Лишние поля запрещены"""
        valid_config['unknown_field'] = 'value'

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_config, schema=schema)