# commands/handlers/set_config.py
# -*- coding: utf-8 -*-
"""
Обработчик команды SET_CONFIG
"""

import os
import random
import string
import logging
from typing import Any
from datetime import datetime, timezone
from commands.base import CommandHandler

logger = logging.getLogger(__name__)


class SetConfigHandler(CommandHandler):
    """Обработчик команды настройки устройства"""

    COMMAND_CODE = 'SET_CONFIG'

    def __init__(self, db, config: dict = None):
        super().__init__(db, config)
        self.config_dir = config.get('config_dir', 'device_configs') if config else 'device_configs'
        os.makedirs(self.config_dir, exist_ok=True)

    def _generate_random_extension(self, length: int = 4) -> str:
        """
        Генерирует случайное расширение файла

        Args:
            length: Длина расширения (по умолчанию 4)

        Returns:
            str: Случайное расширение (например, '.x7k9')
        """
        # ✅ Используем буквы и цифры (без похожих символов)
        chars = string.ascii_lowercase + string.digits
        # Исключаем похожие символы: l, 1, i, o, 0
        chars = chars.replace('l', '').replace('1', '').replace('i', '').replace('o', '').replace('0', '')

        random_part = ''.join(random.choice(chars) for _ in range(length))
        return f".{random_part}"

    def execute(self, params: dict, sim: str) -> dict:
        """Выполняет команду настройки устройства"""
        self.logger.info(f"⚙️ Настройка устройства {sim}")
        self.logger.info(f"   Параметры: {params}")

        param_name = params.get('param_name', '')
        param_value = params.get('param_value')
        timeout = params.get('timeout', 30)

        # ✅ Вторичная валидация (логирование, не блокирующая)
        is_valid, errors = self._validate_params(param_name, param_value, timeout)

        if not is_valid:
            # Это не должно происходить если ранняя валидация работает
            self.logger.error(f"⚠️ Вторичная валидация не пройдена: {errors}")
            # Но всё равно продолжаем (ранняя валидация уже пропустила)

        try:
            filepath = self._save_config_file(sim, param_name, param_value, timeout)
            self.logger.info(f"✅ Файл создан: {filepath}")

            self._save_to_db(sim, param_name, param_value, timeout, filepath)

            return self.success_response(
                message=f'Конфигурация сохранена: {param_name}={param_value}',
                sim=sim,
                param_name=param_name,
                param_value=param_value,
                timeout=timeout,
                filepath=filepath
            )

        except Exception as e:
            self.logger.error(f"❌ Ошибка записи конфигурации: {e}", exc_info=True)
            return self.error_response(
                message=f'Ошибка записи конфигурации: {str(e)}',
                sim=sim
            )

    def _validate_params(self, param_name: str, param_value: Any, timeout: int) -> tuple:
        """Вторичная валидация (для логирования)"""
        errors = []

        if not param_name or not str(param_name).strip():
            errors.append("param_name пустой")

        if param_value is None or param_value == '':
            errors.append("param_value пустой")

        try:
            timeout_int = int(timeout) if timeout is not None else 0
            if timeout_int < 1 or timeout_int > 3600:
                errors.append(f"timeout={timeout} вне диапазона 1-3600")
        except:
            errors.append(f"timeout={timeout} не число")

        return len(errors) == 0, errors

    def _save_config_file(self, sim: str, param_name: str, param_value: Any, timeout: int) -> str:
        """Сохраняет конфигурацию в файл формата name=value"""
        safe_param_name = param_name.replace('/', '_').replace('\\', '_')

        # ✅ Генерируем случайное расширение
        random_ext = self._generate_random_extension(length=4)
        # ✅ Имя файла: sim.param_name.RANDOM
        filename = f"{sim}{random_ext}"
        filepath = os.path.join(self.config_dir, filename)

        # config_lines = [
        #     f"# Конфигурация устройства {sim}",
        #     f"# Создано: {self.get_timestamp()}",
        #     f"#",
        #     f"{param_name}={param_value}",
        #     f"timeout={timeout}",
        #     f"sim={sim}",
        #     f"created_at={self.get_timestamp()}",
        # ]
        config_lines = [
            f"To: {sim}",
            f"",
            f"RQWQR:{param_name}={param_value}"
        ]

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(config_lines))
            f.write('\n')

        return filepath

    def _save_to_db(self, sim: str, param_name: str, param_value: Any,
                    timeout: int, filepath: str) -> None:
        """Сохраняет конфигурацию в БД"""
        try:
            self.db.execute("""
                INSERT INTO device_config_history 
                (sim, param_name, param_value, timeout, filepath, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (sim, param_name) 
                DO UPDATE SET 
                    param_value = EXCLUDED.param_value,
                    timeout = EXCLUDED.timeout,
                    filepath = EXCLUDED.filepath,
                    updated_at = NOW()
            """, (sim, param_name, str(param_value), timeout, filepath))
        except Exception as e:
            self.logger.warning(f"⚠️ Не удалось сохранить в БД: {e}")