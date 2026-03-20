# commands/registry.py
import logging
from commands.handlers.reset import ResetHandler
from commands.handlers.reboot import RebootHandler
from commands.handlers.clear_alarm import ClearAlarmHandler
from commands.handlers.set_config import SetConfigHandler
from commands.handlers.device_command import DeviceCommandHandler

logger = logging.getLogger(__name__)


class HandlerRegistry:
    """Реестр обработчиков команд"""

    HANDLERS = {
        # ✅ Индивидуальные обработчики (если нужна спец. логика)
        # 'RESET': ResetHandler,
        'SET_CONFIG': SetConfigHandler,

        # ✅ Универсальный обработчик для команд с device_command
        'RESET': lambda db, cfg: DeviceCommandHandler(db, cfg, 'RESET'),
        'SET_POWER_MODE': lambda db, cfg: DeviceCommandHandler(db, cfg, 'SET_POWER_MODE'),
        'GET_POWER_MODE': lambda db, cfg: DeviceCommandHandler(db, cfg, 'GET_POWER_MODE'),
        'GET_CFG2': lambda db, cfg: DeviceCommandHandler(db, cfg, 'GET_CFG2'),
        'GET_REPORT': lambda db, cfg: DeviceCommandHandler(db, cfg, 'GET_REPORT'),
        'GET_CFG': lambda db, cfg: DeviceCommandHandler(db, cfg, 'GET_CFG'),
        'GET_GAS': lambda db, cfg: DeviceCommandHandler(db, cfg, 'GET_GAS'),
    }

    def __init__(self, db, config: dict = None):
        self.db = db
        # ✅ Получаем конфиг команд (вложенный)
        self.config = config.get('commands', {}) if config else {}
        self.logger = logging.getLogger('commands.registry')
        self._instances = {}

        self.logger.info(f"📁 Command dir from config: {self.config.get('command_dir', 'device_commands')}")

        self._initialize_handlers()

    def _initialize_handlers(self) -> None:
        """Инициализирует все обработчики"""
        for code, handler_ref in self.HANDLERS.items():
            try:
                if callable(handler_ref) and not isinstance(handler_ref, type):
                    # ✅ Lambda-функция для универсального обработчика
                    self._instances[code] = handler_ref(self.db, self.config)
                else:
                    # ✅ Конкретный класс
                    self._instances[code] = handler_ref(self.db, self.config)

                # ✅ Логирование с COMMAND_CODE
                handler = self._instances[code]
                cmd_code = getattr(handler, 'COMMAND_CODE', 'UNKNOWN')
                self.logger.info(f"✅ Обработчик {code} инициализирован (COMMAND_CODE={cmd_code})")

            except Exception as e:
                self.logger.error(f"❌ Ошибка инициализации {code}: {e}", exc_info=True)

    def get_handler(self, code: str):
        """Получает обработчик по коду команды"""
        handler = self._instances.get(code)
        if handler is None:
            raise ValueError(f"Обработчик для команды '{code}' не найден")
        return handler

    def get_all_handlers(self):
        """Возвращает все обработчики"""
        return self._instances.copy()

    def get_handler_codes(self):
        """Возвращает список кодов доступных команд"""
        return list(self._instances.keys())