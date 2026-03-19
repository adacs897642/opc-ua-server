# commands/handlers/reboot.py
# -*- coding: utf-8 -*-
"""
Обработчик команды REBOOT
"""

import logging
from commands.base import CommandHandler

logger = logging.getLogger(__name__)


class RebootHandler(CommandHandler):
    """Обработчик команды перезагрузки"""

    COMMAND_CODE = 'REBOOT'

    def execute(self, params: dict, sim: str) -> dict:
        """
        Выполняет команду перезагрузки

        Args:
            params: Параметры команды (пустые для этой команды)
            sim: SIM устройства
        """
        self.logger.info(f"🔄 Перезагрузка устройства {sim}")

        try:
            # ✅ Ваша логика перезагрузки
            # Пример: отправка через MQTT
            # self.mqtt_client.publish(f"device/{sim}/command", "reboot")

            # Пример: запись в БД
            # self.db.execute("""
            #     INSERT INTO device_commands_log (sim, command, status, created_at)
            #     VALUES (%s, 'reboot', 'pending', NOW())
            # """, (sim,))

            return self.success_response(
                message=f'Перезагрузка инициирована для устройства {sim}',
                sim=sim
            )

        except Exception as e:
            self.logger.error(f"❌ Ошибка перезагрузки: {e}", exc_info=True)
            return self.error_response(
                message=f'Ошибка перезагрузки: {str(e)}',
                sim=sim
            )