# config/loader.py
# -*- coding: utf-8 -*-
"""
Загрузка и валидация конфигурации
"""

import json
from pathlib import Path
from typing import Any, Optional
import jsonschema


class ConfigLoader:
    """Загрузка и валидация конфигурации"""

    DEFAULT_PATH = 'config.json'
    SCHEMA_PATH = 'config/schema.json'

    def __init__(self, config_path: str = None):
        self.path = Path(config_path or self.DEFAULT_PATH)
        self._config: dict = {}
        self._load()

    def _load(self) -> None:
        """Загружает конфигурацию из JSON"""
        if not self.path.exists():
            raise FileNotFoundError(f"Конфигурация не найдена: {self.path}")

        with self.path.open('r', encoding='utf-8') as f:
            self._config = json.load(f)

        self._validate()

    def _validate(self) -> None:
        """Валидирует конфигурацию по схеме"""
        schema_path = Path(self.SCHEMA_PATH)
        if schema_path.exists():
            with schema_path.open('r', encoding='utf-8') as f:
                schema = json.load(f)
            jsonschema.validate(instance=self._config, schema=schema)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Получает значение по ключу с поддержкой вложенности

        Args:
            key: Ключ в точечной нотации (например, 'database.default')
            default: Значение по умолчанию

        Returns:
            Значение конфигурации
        """
        keys = key.split('.')
        value = self._config

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default

        return value

    def set(self, key: str, value: Any) -> None:
        """
        Устанавливает значение по ключу

        Args:
            key: Ключ в точечной нотации
            value: Значение
        """
        keys = key.split('.')
        config = self._config

        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value

    @property
    def db_config(self) -> dict:
        """Конфигурация базы данных"""
        return self.get('database.default', {})

    @property
    def server_config(self) -> dict:
        """Конфигурация сервера"""
        return self.get('server', {})

    @property
    def app_config(self) -> dict:
        """Конфигурация приложения"""
        return self.get('app', {})

    @property
    def logging_config(self) -> dict:
        """Конфигурация логирования"""
        return self.get('logging', {})

    @property
    def commands_config(self) -> dict:
        """Конфигурация команд"""
        return self.get('commands', {})

    @property
    def hot_reload_config(self) -> dict:
        """Конфигурация hot-reload"""
        return self.get('hot_reload', {})

    @property
    def polling_config(self) -> dict:
        """Конфигурация опроса"""
        return self.get('polling', {})