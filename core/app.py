# core/app.py
# -*- coding: utf-8 -*-
"""
Главный класс приложения OPC UA
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path
import signal
from typing import Optional
import asyncio

from config.loader import ConfigLoader
from db.connection import Database
from db.schema import SchemaValidator
from opc.server import OPCServer
from opc.commands.registry import OpcCommandRegistry
from opc.commands.executor import OpcCommandReceiver
from opc.commands.hot_reload import CommandHotReload
from commands.executor import CommandExecutor as BusinessCommandExecutor  # ← ← ← Исполнение


def setup_logging(config: dict) -> None:
    """
    Настраивает логирование в файл и консоль

    Args:
        config: Конфигурация из config.json
    """
    # ✅ Параметры из конфига
    log_level = config.get('logging', {}).get('level', 'INFO').upper()
    log_file = config.get('logging', {}).get('file', '/var/log/opc_server/app.log')
    log_max_bytes = config.get('logging', {}).get('max_bytes', 10 * 1024 * 1024)  # 10 MB
    log_backup_count = config.get('logging', {}).get('backup_count', 5)
    log_format = config.get('logging', {}).get('format', '%(asctime)s [%(levelname)s] %(name)s: %(message)s')

    # ✅ Создаём директорию для логов
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    # ✅ Корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))

    # ✅ Очищаем старые хендлеры (для перезапуска)
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # ✅ Форматтер
    formatter = logging.Formatter(log_format, datefmt='%Y-%m-%d %H:%M:%S')

    # ✅ File Handler с ротацией
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_file,
        maxBytes=log_max_bytes,
        backupCount=log_backup_count,
        encoding='utf-8',
        delay=True  # Не создавать файл пока не будет первая запись
    )
    file_handler.setLevel(getattr(logging, log_level, logging.INFO))
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # ✅ Console Handler (для отладки)
    if config.get('logging', {}).get('console', True):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level, logging.INFO))
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # ✅ Логирование ошибок в отдельный файл
    error_file = log_file.replace('.log', '.error.log')
    error_handler = logging.handlers.RotatingFileHandler(
        filename=error_file,
        maxBytes=log_max_bytes,
        backupCount=log_backup_count,
        encoding='utf-8',
        delay=True
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)

    # ✅ Подавить шумные библиотеки
    logging.getLogger('opcua').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)

    logging.info(f"✅ Логирование настроено: {log_file} (level={log_level})")


class OPCApp:
    """Главный класс приложения"""

    def __init__(self, config_path: str):
        self.config = ConfigLoader(config_path)
        # Загрузить конфиг
        setup_logging(self.config._config)

        self.logger = logging.getLogger('app')

        self.db: Optional[Database] = None
        self.opc_server: Optional[OPCServer] = None
        self.opc_command_registry: Optional[OpcCommandRegistry] = None
        self.opc_command_receiver: Optional[OpcCommandReceiver] = None
        self.command_reload: Optional[CommandHotReload] = None
        self.command_executor = None  # ← ← ← Бизнес-исполнитель

        self._running = False
        self._setup_signals()

    def _setup_signals(self) -> None:
        """Регистрирует обработчики сигналов"""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame) -> None:
        """Обработчик сигналов завершения"""
        self.logger.info(f"Получен сигнал {signum}, завершение...")
        self._running = False

    def run(self) -> None:
        """Запускает приложение"""
        try:
            self._initialize()
            self._running = True
            self.logger.info("✅ Инициализация завершена, запуск цикла...")
            self._main_loop()
        except Exception as e:
            self.logger.exception(f"Ошибка в главном цикле: {e}")
        finally:
            self._shutdown()

    # core/app.py

    def _initialize(self) -> None:
        """Инициализирует компоненты"""
        self.logger.info("Инициализация компонентов...")

        # ✅ База данных
        self.db = Database(self.config.db_config)

        self.logger.info("✅ База данных готова к работе")

        # ✅ OPC UA сервер (внутри: OpcCommandRegistry + OpcCommandReceiver)
        self.opc_server = OPCServer(self.config._config, self.db)
        self.opc_server.start()

        # ✅ Hot-reload (опционально)
        self.command_reload = CommandHotReload(
            db=self.db,
            opc_server=self.opc_server,
            registry=self.opc_server.opc_command_registry,
            check_interval_sec=self.config.get('hot_reload.interval_sec', 30)
        )

        # ✅ Исполнитель команд (бизнес-логика)
        self.command_executor = BusinessCommandExecutor(
            db=self.db,
            config=self.config or {}
            # .get('commands', {})
        )
        self.command_executor.start()

        # ✅ Запуск hot-reload
        if self.config.get('hot_reload.enabled', False):
            self.command_reload.start()
        else:
            self.logger.info("ℹ️ Hot Reload отключен")

        self.logger.info("Инициализация завершена")

    def _shutdown(self) -> None:
        """Корректное завершение"""
        self.logger.info("Завершение работы...")

        # ✅ Порядок остановки: сначала бизнес-логика, потом OPC
        if self.command_executor:
            self.command_executor.stop()

        if self.command_reload:
            self.command_reload.stop()

        if self.opc_server:
            self.opc_server.stop()

        if self.db:
            self.db.close()

        self.logger.info("Работа завершена")

    # def _initialize(self) -> None:
    #     """Инициализирует компоненты"""
    #     self.logger.info("Инициализация компонентов...")
    #
    #     # ✅ База данных (исправлено!)
    #     self.db = Database(self.config.db_config)
    #
    #     # OPC UA сервер (внутри создаётся вся структура)
    #     self.opc_server = OPCServer(self.config._config, self.db)
    #     self.opc_server.start()  # ← Здесь вызывается create_address_space()
    #
    #     # 3. Получаем Objects node ПОСЛЕ старта
    #     objects_node = self.opc_server.server.get_objects_node()
    #     self.logger.info(f"Objects node: {objects_node.nodeid if objects_node else 'None'}")
    #     # Реестр команд
    #     self.opc_command_registry = OpcCommandRegistry(self.db)
    #
    #     # # Исполнитель команд
    #     self.opc_command_receiver = OpcCommandReceiver(
    #         db=self.db,
    #         command_handlers=self._get_command_handlers(),
    #         queue_size=self.config.get('commands.queue_size', 100),
    #         poll_interval_sec=self.config.get('commands.poll_interval_sec', 2),
    #         worker_threads=self.config.get('commands.worker_threads', 1)
    #     )
    #
    #
    #     # Hot-reload
    #     self.command_reload = CommandHotReload(
    #         db=self.db,
    #         opc_server=self.opc_server,
    #         registry=self.opc_server.opc_command_registry,
    #         check_interval_sec=self.config.get('hot_reload.interval_sec', 30)
    #     )
    #
    #     # Первоначальная загрузка команд
    #     self._load_commands_initial()
    #
    #     self.opc_command_receiver.start()
    #
    #     if self.config.get('hot_reload.enabled', False):
    #         self.command_reload.start()
    #     else:
    #         self.logger.info("ℹ️ Hot Reload отключен в конфигурации")
    #
    #     self.logger.info("Инициализация завершена")

    # def _get_command_handlers(self) -> dict:
    #     """Возвращает словарь обработчиков команд"""
    #     return {
    #         'REBOOT': self._handle_reboot,
    #         'SET_CONFIG': self._handle_set_config,
    #         'CLEAR_ALARM': self._handle_clear_alarm,
    #     }

    def _load_commands_initial(self) -> None:
        """Первоначальная загрузка команд"""
        # ✅ Исполнитель команд (бизнес-логика)
        self.command_executor = BusinessCommandExecutor(
            db=self.db,
            config=self.config.get('commands', {})
        )
        self.command_executor.start()
        # pass

    def _main_loop(self) -> None:
        """Главный цикл обработки событий"""
        import select
        import time

        poll_timeout = self.config.get('polling.notify_timeout_sec', 5)
        update_interval = self.config.get('polling.update_interval_sec', 5)

        while self._running:
            try:
                # ✅ Проверить состояние сервера
                if select.select([self.db.conn], [], [], poll_timeout)[0]:
                    self.db.poll_notifications()
                    for channel in self.db.conn.notifies:
                        self.db.conn.notifies.remove(channel)
                        self._handle_notification(channel)
                else:
                    self.opc_server.update_telemetry()
                    time.sleep(0.1)
            except Exception as e:
                self.logger.error(f"Ошибка в главном цикле: {e}")
                # ✅ Пауза
                time.sleep(1)

    def _handle_notification(self, notify) -> None:
        """
        Обрабатывает уведомление от БД (PostgreSQL LISTEN/NOTIFY)

        Args:
            notify: psycopg2.extensions.notify объект
        """
        # ✅ Извлечь alias из канала уведомления
        alias = notify.channel  # ← ← ← Это строка '79215851634-LV1'
        payload = notify.payload

        self.logger.debug(f"📬 NOTIFY: alias={alias}, payload={payload}")

        # ✅ Если payload содержит данные (например, JSON)
        if payload:
            import json
            try:
                data = json.loads(payload)
                self.logger.debug(f"📊 Данные из payload: {data}")
                # Можно использовать data для чего-то
            except json.JSONDecodeError:
                self.logger.debug(f"📝 Payload не JSON: {payload}")

        # # ✅ Передать alias в update_parameter
        # self.opc_server.update_parameter(alias)
        # ✅ НЕ вызывать update_parameter() напрямую!
        # Вместо этого — добавить в очередь
        self.opc_server.request_update(alias)  # ← ← ← Безопасно!
    # def _shutdown(self) -> None:
    #     """Корректное завершение работы"""
    #     self.logger.info("Завершение работы...")
    #
    #     if self.opc_command_receiver:
    #         self.opc_command_receiver.stop()
    #
    #     if self.command_reload:
    #         self.command_reload.stop()
    #
    #     if self.opc_server:
    #         self.opc_server.stop()
    #
    #     if self.db:
    #         self.db.close()
    #
    #     if self.command_executor:
    #         self.command_executor.stop()
    #
    #     self.logger.info("Работа завершена")