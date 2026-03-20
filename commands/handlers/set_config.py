# commands/handlers/set_config.py
# -*- coding: utf-8 -*-
"""
Обработчик команды SET_CONFIG

Использует CommandFileBuilder (как DeviceCommandHandler)
"""

import logging
from commands.base import CommandHandler
from commands.utils.phone_validator import PhoneValidator

logger = logging.getLogger(__name__)


class SetConfigHandler(CommandHandler):
    """Обработчик команды настройки устройства"""

    COMMAND_CODE = 'SET_CONFIG'

    def execute(self, params: dict, sim: str) -> dict:
        """
        Выполняет команду настройки устройства

        Формирует команду для отправки на устройство через CommandFileBuilder
        """
        self.logger.info(f"⚙️ Настройка устройства {sim}")
        self.logger.info(f"   Параметры: {params}")

        # ✅ 1. Извлекаем параметры
        param_name = params.get('param_name', '')
        param_value = params.get('param_value')
        timeout = params.get('timeout', 30)

        # ✅ 2. Получаем тип параметра из desc_params
        param_type = self._get_param_type(param_name)
        self.logger.info(f"📋 Тип параметра: {param_type}")

        # ✅ 3. Нормализация phone
        if param_type and param_type.lower() in ('phone', 'tel', 'telephone'):
            self.logger.info(f"📱 Нормализация телефонного номера...")
            is_valid, normalized, error_msg = PhoneValidator.validate(param_value)

            if not is_valid:
                return self.error_response(
                    message=f'Ошибка валидации телефона: {error_msg}',
                    errors=[error_msg],
                    sim=sim
                )

            param_value = normalized
            self.logger.info(f"✅ Номер нормализован: {normalized}")

        # ✅ 4. Валидация
        is_valid, errors = self._validate_params(param_name, param_value, timeout, param_type)

        if not is_valid:
            self.logger.error(f"❌ Ошибки валидации: {errors}")
            return self.error_response(
                message='Ошибка валидации параметров',
                errors=errors,
                sim=sim
            )

        try:
            # ✅ 5. Получаем device_command из БД
            device_cmd = self.get_device_command()
            cmd_type = self.get_device_command_type()

            if not device_cmd:
                device_cmd = 'SET_CONFIG'
                cmd_type = 'keyvalue'  # ← ← ← По умолчанию keyvalue для SET_CONFIG

            self.logger.info(f"📤 Отправка на устройство: {device_cmd} (type={cmd_type})")

            # ✅ 6. Форматируем данные команды как key=value
            command_data = f"{param_name}={param_value}"
            self.logger.info(f"📄 Данные команды: {command_data}")

            # ✅ 7. Создаём файл команды через CommandFileBuilder (из базового класса!)
            command_info = self.build_command_file(
                sim=sim,
                command_code=device_cmd,
                command_type=cmd_type,
                params={
                    'param_name': param_name,
                    'param_value': param_value,
                    'timeout': timeout
                },
                priority=2,
                command_data=command_data  # ← ← ← Передаём готовое key=value
            )

            self.logger.info(f"✅ Файл команды создан: {command_info['filepath']}")

            # ✅ 8. Записываем в очередь
            self._write_to_device_queue(
                sim=sim,
                command_code=device_cmd,
                command_type=cmd_type,
                filepath=command_info['filepath'],
                command_data=command_data
            )

            # ✅ 9. Сохраняем в историю конфигураций
            self._save_to_config_history(
                sim=sim,
                param_name=param_name,
                param_value=param_value,
                timeout=timeout,
                filepath=command_info['filepath']
            )

            return self.success_response(
                message=f'Команда настройки отправлена: {command_data}',
                sim=sim,
                device_command=device_cmd,
                device_command_type=cmd_type,
                command_data=command_data,
                param_name=param_name,
                param_value=param_value,
                filepath=command_info['filepath']
            )

        except Exception as e:
            self.logger.error(f"❌ Ошибка настройки: {e}", exc_info=True)
            return self.error_response(
                message=f'Ошибка настройки: {str(e)}',
                sim=sim
            )

    def _get_param_type(self, param_name: str) -> str:
        """Получает тип параметра из desc_params"""
        try:
            rows = self.db.query("""
                SELECT type
                FROM desc_params
                WHERE id_dev = 1
                  AND (alias = %s OR name = %s)
                LIMIT 1
            """, (param_name, param_name))

            if rows:
                return rows[0][0]

            return None

        except Exception as e:
            self.logger.warning(f"⚠️ Не удалось получить тип параметра: {e}")
            return None

    def _validate_params(self, param_name: str, param_value: any, timeout: int, param_type: str = None) -> tuple:
        """Валидирует параметры команды"""
        errors = []

        # param_name
        if not param_name or not str(param_name).strip():
            errors.append("param_name обязателен и не может быть пустым")
        elif len(param_name) > 50:
            errors.append("param_name должен быть не более 50 символов")

        # param_value
        if param_value is None or param_value == '':
            errors.append("param_value обязателен и не может быть пустым")

        # timeout
        try:
            timeout_int = int(timeout) if timeout is not None else 0
            if timeout_int < 1 or timeout_int > 3600:
                errors.append("timeout должен быть от 1 до 3600 секунд")
        except (ValueError, TypeError):
            errors.append("timeout должен быть целым числом")

        # Валидация по типу параметра
        if param_type:
            if param_type.lower() in ('int', 'integer', 'int4'):
                try:
                    int(param_value)
                except (ValueError, TypeError):
                    errors.append(f"param_value должно быть целым числом (тип: {param_type})")

            elif param_type.lower() in ('float', 'double', 'real'):
                try:
                    float(param_value)
                except (ValueError, TypeError):
                    errors.append(f"param_value должно быть числом (тип: {param_type})")

            elif param_type.lower() in ('phone', 'tel', 'telephone'):
                if not str(param_value).startswith('+'):
                    errors.append("Номер телефона должен начинаться с +")

        return len(errors) == 0, errors

    def _write_to_device_queue(self, sim: str, command_code: str, command_type: str,
                               filepath: str, command_data: str) -> None:
        """Записывает команду в очередь"""
        try:
            self.db.execute("""
                INSERT INTO device_command_queue 
                (sim, command_code, command_type, filepath, command_data, status, created_at)
                VALUES (%s, %s, %s, %s, %s, 'pending', NOW())
            """, (sim, command_code, command_type, filepath, command_data))

            self.logger.info(f"✅ Команда {command_code} записана в очередь для {sim}")

        except Exception as e:
            self.logger.error(f"❌ Ошибка записи в очередь: {e}")

    def _save_to_config_history(self, sim: str, param_name: str, param_value: any,
                                timeout: int, filepath: str) -> None:
        """Сохраняет конфигурацию в историю"""
        try:
            self.db.execute("""
                INSERT INTO device_config_history 
                (sim, param_name, param_value, timeout, filepath, created_at, status)
                VALUES (%s, %s, %s, %s, %s, NOW(), 'done')
                ON CONFLICT (sim, param_name) 
                DO UPDATE SET 
                    param_value = EXCLUDED.param_value,
                    timeout = EXCLUDED.timeout,
                    filepath = EXCLUDED.filepath,
                    updated_at = NOW(),
                    status = 'done'
            """, (sim, param_name, str(param_value), timeout, filepath))

            self.logger.info(f"📊 Конфигурация сохранена в историю: {filepath}")

        except Exception as e:
            self.logger.warning(f"⚠️ Не удалось сохранить в историю: {e}")