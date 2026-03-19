# commands/base.py
# -*- coding: utf-8 -*-
"""
Базовый класс для обработчиков команд
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class CommandHandler(ABC):
    """Базовый класс для всех обработчиков команд"""

    # Код команды (должен быть переопределён в наследниках)
    COMMAND_CODE: str = None

    def __init__(self, db, config: dict = None):
        self.db = db
        self.config = config or {}
        self.logger = logging.getLogger(f'commands.{self.__class__.__name__}')

    @abstractmethod
    def execute(self, params: dict, sim: str) -> dict:
        """
        Выполняет команду

        Args:
            params: Параметры команды
            sim: SIM устройства

        Returns:
            dict: Результат выполнения
        """
        pass

    def validate_params(self, params: dict) -> tuple:
        """
        Валидирует параметры команды

        Returns:
            tuple: (is_valid: bool, errors: list)
        """
        errors = []

        # Базовая валидация SIM
        if not sim:
            errors.append("SIM устройства обязателен")

        return len(errors) == 0, errors

    def get_timestamp(self) -> str:
        """Возвращает текущую метку времени UTC"""
        return datetime.now(timezone.utc).isoformat()

    def success_response(self, message: str, **kwargs) -> dict:
        """Создаёт успешный ответ"""
        response = {
            'status': 'ok',
            'message': message,
            'timestamp': self.get_timestamp()
        }
        response.update(kwargs)
        return response

    def error_response(self, message: str, errors: list = None, **kwargs) -> dict:
        """Создаёт ответ с ошибкой"""
        response = {
            'status': 'error',
            'message': message,
            'timestamp': self.get_timestamp()
        }
        if errors:
            response['errors'] = errors
        response.update(kwargs)
        return response