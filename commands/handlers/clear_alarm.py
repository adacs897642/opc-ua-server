# commands/handlers/clear_alarm.py
# -*- coding: utf-8 -*-
"""
Обработчик команды CLEAR_ALARM
"""

import logging
from commands.base import CommandHandler

logger = logging.getLogger(__name__)


class ClearAlarmHandler(CommandHandler):
    """Обработчик команды сброса аварии"""

    COMMAND_CODE = 'CLEAR_ALARM'

    def execute(self, params: dict, sim: str) -> dict:
        """
        Выполняет команду сброса аварии

        Args:
            params: Параметры команды (пустые для этой команды)
            sim: SIM устройства
        """
        self.logger.info(f"🔕 Сброс аварии для устройства {sim}")

        try:
            # ✅ Ваша логика сброса аварии
            # Пример: отправка через MQTT
            # self.mqtt_client.publish(f"device/{sim}/alarm", "clear")

            # Пример: запись в БД
            # self.db.execute("""
            #     UPDATE device_alarms 
            #     SET status = 'cleared', cleared_at = NOW()
            #     WHERE sim = %s AND status = 'active'
            # """, (sim,))

            return self.success_response(
                message=f'Авария сброшена для устройства {sim}',
                sim=sim
            )

        except Exception as e:
            self.logger.error(f"❌ Ошибка сброса аварии: {e}", exc_info=True)
            return self.error_response(
                message=f'Ошибка сброса аварии: {str(e)}',
                sim=sim
            )