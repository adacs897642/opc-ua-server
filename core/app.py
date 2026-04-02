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
        """Регистрирует обработчики сигналов (кросс-платформенно)"""

        # ✅ Всегда доступные сигналы
        signal.signal(signal.SIGINT, self._signal_handler)  # Ctrl+C
        signal.signal(signal.SIGTERM, self._signal_handler)  # kill / systemd

        # ✅ Windows-специфичный сигнал
        if hasattr(signal, 'SIGBREAK'):
            signal.signal(signal.SIGBREAK, self._signal_handler)  # Ctrl+Break

        # ✅ Unix-специфичные сигналы (проверка перед использованием)
        if hasattr(signal, 'SIGHUP'):
            signal.signal(signal.SIGHUP, self._signal_handler)  # Закрытие терминала

        if hasattr(signal, 'SIGUSR1'):
            signal.signal(signal.SIGUSR1, self._signal_handler)  # Пользовательский 1

        if hasattr(signal, 'SIGUSR2'):
            signal.signal(signal.SIGUSR2, self._signal_handler)  # Пользовательский 2

        self.logger.info("✅ Обработчики сигналов зарегистрированы")

    def _signal_handler(self, signum, frame) -> None:
        """Обработчик сигналов завершения (кросс-платформенный)"""
        # ✅ Определить имя сигнала (с обработкой неизвестных)
        sig_names = {
            signal.SIGINT: 'SIGINT (Ctrl+C)',
            signal.SIGTERM: 'SIGTERM (kill)',
        }

        # Добавить платформенно-специфичные
        if hasattr(signal, 'SIGBREAK'):
            sig_names[signal.SIGBREAK] = 'SIGBREAK (Ctrl+Break)'
        if hasattr(signal, 'SIGHUP'):
            sig_names[signal.SIGHUP] = 'SIGHUP (terminal closed)'
        if hasattr(signal, 'SIGUSR1'):
            sig_names[signal.SIGUSR1] = 'SIGUSR1 (custom 1)'
        if hasattr(signal, 'SIGUSR2'):
            sig_names[signal.SIGUSR2] = 'SIGUSR2 (custom 2)'

        sig_name = sig_names.get(signum, f'signal {signum}')

        self.logger.info(f"🛑 Получен сигнал {sig_name}, завершение...")
        self._running = False

        # ✅ Дополнительно: прервать блокирующий select() если нужно
        # (опционально, если select() блокирует завершение)
        if hasattr(self.db, 'conn') and self.db.conn:
            try:
                # Отправить "пустой" запрос чтобы прервать select
                self.db.conn.cancel()
            except:
                pass  # Игнорировать если не поддерживается

    def run(self) -> None:
        """Запускает приложение"""
        try:
            self._initialize()
            self._running = True
            self.logger.info("✅ Инициализация завершена, запуск цикла...")
            self._main_loop()
        except KeyboardInterrupt:
            self.logger.info("🛑 Прервано пользователем (Ctrl+C)")
        except Exception as e:
            self.logger.exception(f"❌ Критическая ошибка: {e}")
        finally:
            # ✅ ✅ ✅ Всегда вызывать shutdown (даже при ошибке!)
            self._shutdown()
            self.logger.info("✅ Приложение завершено")

    # core/app.py

    def _initialize(self) -> None:
        """Инициализирует компоненты"""
        self.logger.info("Инициализация компонентов...")

        # ✅ База данных
        self.db = Database(self.config.db_config)

        self.logger.info("✅ База данных готова к работе")
        # ✅ ✅ ✅ Передать config в UserManager!
        from opc.user_manager import UserManager
        self.user_manager = UserManager(
            config=self.config._config,
            db_connection=self.db.conn  # ← ← ← Передать psycopg2 connection!
        )

        # ✅ OPC UA сервер (внутри: OpcCommandRegistry + OpcCommandReceiver)
        self.opc_server = OPCServer(self.config._config, self.db)

        self.opc_server.start()
        # ✅ ✅ ✅ ТОЛЬКО ПОСЛЕ start() сервер создан — назначить user_manager
        if self.opc_server.server:
            self.opc_server.server.user_manager = self.user_manager
            self.logger.info("✅ user_manager назначен серверу")
        else:
            self.logger.error("❌ self.opc_server.server всё ещё None после start()!")
            raise RuntimeError("Сервер не создан!")

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
        """Полное завершение с гарантированным выходом"""
        import threading
        import time
        import sys
        import os

        self.logger.info("🧹 Завершение работы...")

        # ✅ 1. Остановить компоненты по порядку
        components = [
            ('Command Executor', self.command_executor),
            ('Command Reload', self.command_reload),
            ('OPC Server', self.opc_server),
            ('Database', self.db),
        ]

        for name, component in components:
            if component:
                try:
                    self.logger.info(f"🔌 Остановка {name}...")
                    if hasattr(component, 'stop'):
                        component.stop()
                    elif hasattr(component, 'close'):
                        component.close()
                    self.logger.info(f"✅ {name} остановлен")
                except Exception as e:
                    self.logger.error(f"❌ Ошибка остановки {name}: {e}")

        # ✅ 2. Ожидание фоновых задач
        self.logger.info("⏳ Ожидание завершения фоновых задач (2 сек)...")
        time.sleep(2)

        # ✅ 3. Диагностика потоков
        active_threads = threading.enumerate()
        non_daemon = [t for t in active_threads if t.name != 'MainThread' and not t.daemon]

        if non_daemon:
            self.logger.warning(f"⚠️ Активные не-daemon потоки ({len(non_daemon)}):")
            for t in non_daemon:
                self.logger.warning(f"   - {t.name} (daemon={t.daemon})")
        else:
            self.logger.info("✅ Все потоки завершены")

        # ✅ 4. Очистить ссылки
        self.command_executor = None
        self.command_reload = None
        self.opc_server = None
        self.db = None

        self.logger.info("🏁 Все ресурсы освобождены")

        # ✅ 5. Принудительный выход (гарантированно завершит процесс)
        self.logger.info("🚪 Выход из процесса...")

        # Flush логов перед выходом
        for handler in self.logger.handlers:
            handler.flush()
        # noinspection PyProtectedMember
        # noinspection PyUnresolvedReferences
        # ✅ Жёсткий выход (игнорирует активные потоки)
        os._exit(0)

    def _load_commands_initial(self) -> None:
        """Первоначальная загрузка команд"""
        # ✅ Исполнитель команд (бизнес-логика)
        self.command_executor = BusinessCommandExecutor(
            db=self.db,
            config=self.config.get('commands', {})
        )
        self.command_executor.start()

    def _main_loop(self) -> None:
        """Главный цикл обработки событий"""
        import select
        import time

        # ✅ Уменьшить таймаут для быстрого реагирования на сигнал
        poll_timeout = min(
            self.config.get('polling.notify_timeout_sec', 5),
            1.0  # ← ← ← Не больше 1 секунды!
        )
        update_interval = self.config.get('polling.update_interval_sec', 5)

        last_update = 0

        while self._running:
            # self.logger.info(f"🛑 _running={self._running}")
            try:
                # ✅ Проверить уведомления (с коротким таймаутом)
                if select.select([self.db.conn], [], [], poll_timeout)[0]:
                    # ✅ Обработать ВСЕ уведомления, но с проверкой флага
                    while self._running and self.db.conn.notifies:
                        notify = self.db.conn.notifies.pop(0)
                        self._handle_notification(notify)
                else:
                    # ✅ Периодическое обновление телеметрии
                    now = time.time()
                    if now - last_update >= update_interval:
                        self.opc_server.update_telemetry()
                        last_update = now

                    # ✅ Короткий сон чтобы не грузить CPU
                    time.sleep(0.05)  # 50 мс

            except KeyboardInterrupt:
                # ← ← ← На случай если сигнал не перехвачен
                self.logger.info("🛑 Получен KeyboardInterrupt")
                break
            except select.error as e:
                # ← ← ← select() прерван сигналом
                if e.args[0] == 4:  # EINTR
                    self.logger.debug("⚠️ select() прерван сигналом, продолжаем")
                    continue
                raise
            except Exception as e:
                self.logger.error(f"❌ Ошибка в главном цикле: {e}", exc_info=True)
                # ✅ Не выходить при ошибке, продолжить работу
                time.sleep(1)

    def _handle_notification(self, notify) -> None:
        """
        Обрабатывает уведомление от БД (PostgreSQL LISTEN/NOTIFY)

        Args:
            notify: psycopg2.extensions.notify объект
        """
        # ✅ Извлечь alias из канала уведомления
        channel = notify.channel  # ← ← ← Это строка '79215851634-LV1'
        payload = notify.payload

        self.logger.debug(f"📬 NOTIFY: channel={channel}, payload={payload}")
        # ✅ 1. Уведомления телеметрии (существующая логика)
        if channel in self.opc_server._telemetry_nodes:
            # ✅ Если payload содержит данные (например, JSON)
            if payload:
                import json
                try:
                    data = json.loads(payload)
                    self.logger.debug(f"📊 Данные из payload: {data}")
                    # Можно использовать data для чего-то
                except json.JSONDecodeError:
                    self.logger.debug(f"📝 Payload не JSON: {payload}")

            self.opc_server.request_update(channel)  # ← ← ← Безопасно!
            return

        # ✅ ✅ ✅ 2. Уведомления об изменениях пользователей
        if channel == 'opc_user_change':
            self._handle_user_change(payload)
            return

        # ✅ 3. Другие каналы...
        self.logger.debug(f"⚠️ Неизвестный канал: {channel}")

    def _handle_user_change(self, payload: str) -> None:
        """
        Обработать уведомление об изменении пользователей

        Args:
            payload: JSON строка от триггера
        """
        import json

        try:
            # ✅ Распарсить payload
            data = json.loads(payload)
            action = data.get('action', 'unknown')
            username = data.get('username', 'unknown')

            self.logger.info(f"🔄 Изменение пользователей: {action.upper()} {username}")

            # ✅ Перезагрузить кэш пользователей
            if hasattr(self, 'user_manager') and self.user_manager:
                self.user_manager.reload_users()
                self.logger.info(f"✅ Кэш пользователей обновлён")
            else:
                self.logger.warning("⚠️ user_manager не доступен для reload")

        except json.JSONDecodeError as e:
            self.logger.error(f"❌ Ошибка парсинга payload: {e}")
        except Exception as e:
            self.logger.error(f"❌ Ошибка обработки user_change: {e}", exc_info=True)