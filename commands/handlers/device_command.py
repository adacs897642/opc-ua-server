# commands/handlers/device_command.py
# -*- coding: utf-8 -*-
"""
Универсальный обработчик для команд с device_command

Используется для: RESET, REBOOT, CLEAR_ALARM, DIAGNOSTIC, etc.
"""

import logging
from commands.base import CommandHandler

logger = logging.getLogger(__name__)


class DeviceCommandHandler(CommandHandler):
    """
    Универсальный обработчик для команд с device_command

    ВАЖНО: COMMAND_CODE должен быть установлен при создании!
    """

    COMMAND_CODE = None  # ← ← ← Будет установлен в __init__

    def __init__(self, db, config: dict = None, command_code: str = None):
        super().__init__(db, config)

        # ✅ Устанавливаем COMMAND_CODE динамически
        if command_code:
            self.COMMAND_CODE = command_code
            # ✅ Обновляем логгер для правильного именования
            self.logger = logging.getLogger(f'commands.{command_code}')
        else:
            raise ValueError("command_code обязателен для DeviceCommandHandler!")

    def execute(self, params: dict, sim: str) -> dict:
        """
        Выполняет команду с device_command

        Пользователь вызывает команду без параметров (или с параметрами),
        устройство получает внутренний код из _meta
        """
        self.logger.info(f"🔄 Выполнение {self.COMMAND_CODE} для устройства {sim}")
        self.logger.info(f"   Параметры: {params}")

        # ✅ Получаем внутренний код команды из БД
        device_cmd = self.get_device_command()

        # ✅ Получаем тип команды (text/hex/json)
        cmd_type = self.get_device_command_type()

        self.logger.info(f"🔍 device_command: {device_cmd}")
        self.logger.info(f"🔍 device_command_type: {cmd_type}")

        # ✅ Валидация: device_command обязателен
        if not device_cmd:
            return self.error_response(
                message=f"Для команды {self.COMMAND_CODE} не указан device_command",
                sim=sim
            )

        self.logger.info(f"📤 Отправка на устройство: {device_cmd} (type={cmd_type})")

        try:
            # ✅ Создаём файл команды через CommandFileBuilder (из базового класса)
            command_info = self.build_command_file(
                sim=sim,
                command_code=device_cmd,
                command_type=cmd_type,
                params=params,
                priority=2
            )

            self.logger.info(f"✅ Файл команды создан: {command_info['filepath']}")

            # ✅ Записываем в очередь для отправки
            self._write_to_device_queue(
                sim=sim,
                command_code=device_cmd,
                command_type=cmd_type,
                filepath=command_info['filepath'],
                command_data=command_info.get('command_data')
            )

            return self.success_response(
                message=f'Команда {self.COMMAND_CODE} отправлена',
                sim=sim,
                device_command=device_cmd,
                device_command_type=cmd_type,
                filepath=command_info['filepath']
            )

        except Exception as e:
            self.logger.error(f"❌ Ошибка выполнения {self.COMMAND_CODE}: {e}", exc_info=True)
            return self.error_response(
                message=f'Ошибка {self.COMMAND_CODE}: {str(e)}',
                sim=sim
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

        Args:
            sim: SIM устройства
            command_code: Внутренний код команды
            command_type: Тип команды (text/hex/json)
            filepath: Путь к файлу команды
            command_data: Данные команды (опционально)
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
            # Не пробрасываем исключение — команда всё равно отправлена в файл