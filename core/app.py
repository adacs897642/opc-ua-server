# core/app.py
# -*- coding: utf-8 -*-
"""
Главный класс приложения OPC UA
"""

import logging
import signal
from typing import Optional

from config.loader import ConfigLoader
from db.connection import Database
from opc.server import OPCServer
from opc.commands.registry import CommandRegistry
from opc.commands.executor import CommandExecutor
from opc.commands.hot_reload import CommandHotReload


class OPCApp:
    """Главный класс приложения"""

    def __init__(self, config_path: str):
        self.config = ConfigLoader(config_path)
        self.logger = logging.getLogger('app')

        self.db: Optional[Database] = None
        self.opc_server: Optional[OPCServer] = None
        self.command_registry: Optional[CommandRegistry] = None
        self.command_executor: Optional[CommandExecutor] = None
        self.command_reload: Optional[CommandHotReload] = None

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
            self._main_loop()
        except Exception as e:
            self.logger.exception(f"Ошибка в главном цикле: {e}")
        finally:
            self._shutdown()

    def _initialize(self) -> None:
        """Инициализирует компоненты"""
        self.logger.info("Инициализация компонентов...")

        # ✅ База данных (исправлено!)
        self.db = Database(self.config.db_config)

        # OPC UA сервер (внутри создаётся вся структура)
        self.opc_server = OPCServer(self.config._config, self.db)
        self.opc_server.start()  # ← Здесь вызывается create_address_space()

        # 3. Получаем Objects node ПОСЛЕ старта
        objects_node = self.opc_server.server.get_objects_node()
        self.logger.info(f"Objects node: {objects_node.nodeid if objects_node else 'None'}")
        # Реестр команд
        self.command_registry = CommandRegistry(self.db)

        # Исполнитель команд
        self.command_executor = CommandExecutor(
            db=self.db,
            command_handlers=self._get_command_handlers(),
            queue_size=self.config.get('commands.queue_size', 100),
            poll_interval_sec=self.config.get('commands.poll_interval_sec', 2),
            worker_threads=self.config.get('commands.worker_threads', 1)
        )

        # Hot-reload
        self.command_reload = CommandHotReload(
            db=self.db,
            opc_server=self.opc_server,
            registry=self.opc_server.command_registry,
            check_interval_sec=self.config.get('hot_reload.interval_sec', 30)
        )

        # Первоначальная загрузка команд
        self._load_commands_initial()

        # Запуск исполнителя и hot-reload
        if self.config.get('commands.executor_enabled', True):
            self.command_executor.start()

        if self.config.get('hot_reload.enabled', False):
            self.command_reload.start()

        self.logger.info("Инициализация завершена")

    def _get_command_handlers(self) -> dict:
        """Возвращает словарь обработчиков команд"""
        return {
            'REBOOT': self._handle_reboot,
            'SET_CONFIG': self._handle_set_config,
            'CLEAR_ALARM': self._handle_clear_alarm,
        }

    def _handle_reboot(self, params: dict, sim: str) -> dict:
        """
        Обработчик команды перезагрузки

        Args:
            params: Параметры команды
            sim: SIM устройства
        """
        self.logger.info(f"🔄 Перезагрузка устройства {sim}...")

        # Здесь ваша логика перезагрузки
        # Например: отправка через MQTT, Modbus, HTTP API

        return {
            'status': 'ok',
            'message': f'Перезагрузка инициирована для {sim}',
            'sim': sim,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

    def _handle_set_config(self, params: dict, sim: str) -> dict:
        """
        Обработчик команды настройки

        Args:
            params: Параметры команды
            sim: SIM устройства
        """
        self.logger.info(f"⚙️ Настройка устройства {sim}: {params}")

        # Логика настройки устройства

        return {
            'status': 'ok',
            'message': f'Конфигурация обновлена для {sim}',
            'sim': sim,
            'params': params
        }

    def _handle_clear_alarm(self, params: dict, sim: str) -> dict:
        """
        Обработчик команды сброса аварии

        Args:
            params: Параметры команды
            sim: SIM устройства
        """
        self.logger.info(f"🔕 Сброс аварии на устройстве {sim}")

        # Логика сброса аварии

        return {
            'status': 'ok',
            'message': f'Авария сброшена для {sim}',
            'sim': sim
        }

    def _load_commands_initial(self) -> None:
        """Первоначальная загрузка команд"""
        # ... существующий код ...
        pass

    def _main_loop(self) -> None:
        """Главный цикл обработки событий"""
        import select
        import time

        poll_timeout = self.config.get('polling.notify_timeout_sec', 5)
        update_interval = self.config.get('polling.update_interval_sec', 5)

        while self._running:
            try:
                if select.select([self.db.conn], [], [], poll_timeout)[0]:
                    self.db.poll_notifications()
                    for channel in self.db.conn.notifies:
                        self.db.conn.notifies.remove(channel)
                        self._handle_notification(channel)
                else:
                    self.opc_server.update_telemetry()
                    time.sleep(update_interval)
            except Exception as e:
                self.logger.error(f"Ошибка в главном цикле: {e}")

    def _handle_notification(self, channel: str) -> None:
        """Обрабатывает уведомление от БД"""
        self.logger.debug(f"NOTIFY: {channel}")
        self.opc_server.update_parameter(channel)

    def _shutdown(self) -> None:
        """Корректное завершение работы"""
        self.logger.info("Завершение работы...")

        if self.command_executor:
            self.command_executor.stop()

        if self.command_reload:
            self.command_reload.stop()

        if self.opc_server:
            self.opc_server.stop()

        if self.db:
            self.db.close()

        self.logger.info("Работа завершена")