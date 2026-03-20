# commands/base.py
# -*- coding: utf-8 -*-
"""
Базовый класс для обработчиков команд
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from commands.utils import CommandFileBuilder

logger = logging.getLogger(__name__)


class CommandHandler(ABC):
    """Базовый класс для всех обработчиков команд"""

    COMMAND_CODE: str = None

    def __init__(self, db, config: dict = None):
        self.db = db
        self.config = config or {}
        self.logger = logging.getLogger(f'commands.{self.__class__.__name__}')
        self._command_meta_cache = None
        # ✅ Инициализируем строитель команд
        # ✅ Читаем command_dir из конфига (единый для всех команд)
        command_dir = self.config.get('command_dir', 'device_commands')
        self.command_builder = CommandFileBuilder(command_dir=command_dir)

        self.logger.info(f"📁 Command directory: {command_dir}")

    def get_command_meta(self) -> Optional[dict]:
        """Получает метаданные команды из БД (кэшируется)"""
        # ✅ Для отладки — всегда читать из БД (отключить кэш временно)
        # if self._command_meta_cache is not None:
        #     return self._command_meta_cache

        self.logger.info(f"🔍 Читаю param_schema из БД для {self.COMMAND_CODE}...")

        try:
            rows = self.db.query("""
                SELECT param_schema
                FROM commands_catalog
                WHERE code = %s AND is_active = TRUE
            """, (self.COMMAND_CODE,))

            self.logger.info(f"🔍 Результат запроса: {rows}")

            if rows and rows[0][0]:
                self._command_meta_cache = rows[0][0]
                self.logger.info(f"✅ param_schema: {self._command_meta_cache}")
                self.logger.info(f"✅ _meta: {self._command_meta_cache.get('_meta')}")
                return self._command_meta_cache

            self.logger.warning(f"⚠️ param_schema = NULL для {self.COMMAND_CODE}")
            return None

        except Exception as e:
            self.logger.error(f"❌ Ошибка получения метаданных: {e}", exc_info=True)
            return None

    def build_command_file(
            self,
            sim: str,
            command_code: str,
            command_type: str = 'text',
            params: Optional[Dict[str, Any]] = None,
            priority: int = 2,
            command_data: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Создаёт файл команды для отправки на устройство

        Обёртка над CommandFileBuilder
        """
        return self.command_builder.build_command(
            sim=sim,
            command_code=command_code,
            command_type=command_type,
            params=params,
            priority=priority,
            command_data=command_data
        )

    def _write_to_device_queue(
            self,
            sim: str,
            command_code: str,
            command_type: str,
            filepath: str,
            command_data: str = None
    ) -> None:
        """
        Записывает команду в очередь для отправки

        По умолчанию — запись в БД. Переопределите в наследниках если нужно.
        """
        try:
            self.db.execute("""
                INSERT INTO device_command_queue 
                (sim, command_code, command_type, filepath, command_data, status, created_at)
                VALUES (%s, %s, %s, %s, %s, 'pending', NOW())
            """, (sim, command_code, command_type, filepath, command_data))

            self.logger.info(f"✅ Команда {command_code} записана в очередь для {sim}")

        except Exception as e:
            self.logger.error(f"❌ Ошибка записи в очередь: {e}")

    def get_device_command(self) -> Optional[str]:
        """Получает внутренний код команды для устройства"""
        meta = self.get_command_meta()

        self.logger.info(f"🔍 get_device_command() meta: {meta}")

        if meta and '_meta' in meta:
            device_cmd = meta['_meta'].get('device_command')
            self.logger.info(f"✅ device_command из _meta: {device_cmd}")
            return device_cmd

        self.logger.warning(f"⚠️ '_meta' не найден в meta или meta=None")
        return None
    # def get_device_command(self) -> Optional[str]:
    #     """
    #     Получает внутренний код команды для устройства
    #
    #     Returns:
    #         str: device_command из _meta или None
    #     """
    #     meta = self.get_command_meta()
    #
    #     if meta and '_meta' in meta:
    #         return meta['_meta'].get('device_command')
    #
    #     return None

    def get_device_command_type(self) -> str:
        """Получает тип команды (text/hex/json)"""
        meta = self.get_command_meta()

        if meta and '_meta' in meta:
            return meta['_meta'].get('device_command_type', 'text')

        return 'text'

    def get_params_schema(self) -> list:
        """Получает схему параметров"""
        meta = self.get_command_meta()

        if meta and 'params' in meta:
            return meta['params']

        return []

    def has_device_command(self) -> bool:
        """Проверяет есть ли внутренний код команды"""
        return self.get_device_command() is not None

    def execute(self, params: dict, sim: str) -> dict:
        """
        Выполняет команду

        Args:
            params: Параметры от OPC клиента
            sim: SIM устройства

        Returns:
            dict: Результат выполнения
        """
        pass

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
# class CommandHandler(ABC):
#     """Базовый класс для всех обработчиков команд"""
#
#     # Код команды (должен быть переопределён в наследниках)
#     COMMAND_CODE: str = None
#
#     def __init__(self, db, config: dict = None):
#         self.db = db
#         self.config = config or {}
#         self.logger = logging.getLogger(f'commands.{self.__class__.__name__}')
#
#     @abstractmethod
#     def execute(self, params: dict, sim: str) -> dict:
#         """
#         Выполняет команду
#
#         Args:
#             params: Параметры команды
#             sim: SIM устройства
#
#         Returns:
#             dict: Результат выполнения
#         """
#         pass
#
#     def validate_params(self, params: dict) -> tuple:
#         """
#         Валидирует параметры команды
#
#         Returns:
#             tuple: (is_valid: bool, errors: list)
#         """
#         errors = []
#
#         # Базовая валидация SIM
#         if not sim:
#             errors.append("SIM устройства обязателен")
#
#         return len(errors) == 0, errors
#
#     def get_timestamp(self) -> str:
#         """Возвращает текущую метку времени UTC"""
#         return datetime.now(timezone.utc).isoformat()
#
#     def success_response(self, message: str, **kwargs) -> dict:
#         """Создаёт успешный ответ"""
#         response = {
#             'status': 'ok',
#             'message': message,
#             'timestamp': self.get_timestamp()
#         }
#         response.update(kwargs)
#         return response
#
#     def error_response(self, message: str, errors: list = None, **kwargs) -> dict:
#         """Создаёт ответ с ошибкой"""
#         response = {
#             'status': 'error',
#             'message': message,
#             'timestamp': self.get_timestamp()
#         }
#         if errors:
#             response['errors'] = errors
#         response.update(kwargs)
#         return response