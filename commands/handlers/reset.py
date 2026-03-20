# commands/handlers/reset.py
# -*- coding: utf-8 -*-
"""
Обработчик команды RESET
"""

import logging
from commands.base import CommandHandler

logger = logging.getLogger(__name__)


class ResetHandler(CommandHandler):
    """Обработчик команды сброса"""

    COMMAND_CODE = 'RESET'  # ← ← ← Обязательно!

    def execute(self, params: dict, sim: str) -> dict:
        """Выполняет команду сброса"""
        self.logger.info(f"🔄 Сброс устройства {sim}")

        # ✅ Получаем внутренний код команды из БД
        device_cmd = self.get_device_command()

        # ✅ ПОЛУЧАЕМ ТИП КОМАНДЫ (этой строки не хватало!)
        cmd_type = self.get_device_command_type()

        self.logger.info(f"🔍 device_command: {device_cmd}")
        self.logger.info(f"🔍 device_command_type: {cmd_type}")

        if not device_cmd:
            return self.error_response(
                message=f"Для команды RESET не указан device_command",
                sim=sim
            )

        self.logger.info(f"📤 Отправка на устройство: {device_cmd} (type={cmd_type})")

        try:
            # ✅ Создаём файл команды через CommandFileBuilder
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
                filepath=command_info['filepath']
            )

            return self.success_response(
                message=f'Команда сброса отправлена',
                sim=sim,
                device_command=device_cmd,
                device_command_type=cmd_type,
                filepath=command_info['filepath']
            )

        except Exception as e:
            self.logger.error(f"❌ Ошибка сброса: {e}", exc_info=True)
            return self.error_response(
                message=f'Ошибка сброса: {str(e)}',
                sim=sim
            )

    def _write_to_device_queue(
            self,
            sim: str,
            command_code: str,
            command_type: str,
            filepath: str
    ) -> None:
        """Записывает команду в очередь для отправки"""
        try:
            self.db.execute("""
                INSERT INTO device_command_queue 
                (sim, command_code, command_type, filepath, status, created_at)
                VALUES (%s, %s, %s, %s, 'pending', NOW())
            """, (sim, command_code, command_type, filepath))

            self.logger.info(f"✅ Команда {command_code} записана в очередь для {sim}")

        except Exception as e:
            self.logger.error(f"❌ Ошибка записи в очередь: {e}")