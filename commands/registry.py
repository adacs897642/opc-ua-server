# commands/registry.py
# -*- coding: utf-8 -*-
"""
Реестр обработчиков команд
"""

import logging
from typing import Dict, Type
from commands.base import CommandHandler
from commands.handlers.clear_alarm import ClearAlarmHandler
from commands.handlers.reboot import RebootHandler
from commands.handlers.set_config import SetConfigHandler

logger = logging.getLogger(__name__)


class HandlerRegistry:
    """Реестр обработчиков команд"""

    # Карта обработчиков
    HANDLERS: Dict[str, Type[CommandHandler]] = {
        'CLEAR_ALARM': ClearAlarmHandler,
        'REBOOT': RebootHandler,
        'SET_CONFIG': SetConfigHandler,
    }

    def __init__(self, db, config: dict = None):
        self.db = db
        self.config = config or {}
        self.logger = logging.getLogger('commands.registry')
        self._instances: Dict[str, CommandHandler] = {}

        self._initialize_handlers()

    def _initialize_handlers(self) -> None:
        """Инициализирует все обработчики"""
        for code, handler_class in self.HANDLERS.items():
            try:
                self._instances[code] = handler_class(self.db, self.config)
                self.logger.info(f"✅ Обработчик {code} инициализирован")
            except Exception as e:
                self.logger.error(f"❌ Ошибка инициализации {code}: {e}")

    def get_handler(self, code: str) -> CommandHandler:
        """
        Получает обработчик по коду команды

        Args:
            code: Код команды

        Returns:
            CommandHandler: Экземпляр обработчика

        Raises:
            ValueError: Если обработчик не найден
        """
        handler = self._instances.get(code)

        if handler is None:
            raise ValueError(f"Обработчик для команды '{code}' не найден")

        return handler

    def get_all_handlers(self) -> Dict[str, CommandHandler]:
        """Возвращает все обработчики"""
        return self._instances.copy()

    def get_handler_codes(self) -> list:
        """Возвращает список кодов доступных команд"""
        return list(self._instances.keys())