# commands/utils/command_builder.py
# -*- coding: utf-8 -*-
"""
Утилита для подготовки файлов команд для отправки на устройства
"""

import os
import json
import random
import string
import logging
from typing import Any, Optional, Dict, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class CommandFileBuilder:
    """
    Строитель файлов команд для отправки на устройства

    Поддерживает:
    - Разные форматы команд (text, hex, json, binary)
    - Случайное расширение файла (безопасность)
    - Метаданные для отправителя
    - Логирование операций
    """

    # ✅ Типы форматов команд
    COMMAND_FORMATS = {
        'text': '.cmd',
        'hex': '.hex',
        'json': '.json',
        'binary': '.bin',
        'xml': '.xml'
    }

    # ✅ Символы для генерации случайного расширения
    SAFE_CHARS = string.ascii_lowercase + string.digits
    SAFE_CHARS = SAFE_CHARS.replace('l', '').replace('1', '').replace('i', '').replace('o', '').replace('0', '')

    def __init__(self, command_dir: str = 'device_commands'):
        """
        Инициализация строителя команд

        Args:
            command_dir: Директория для хранения файлов команд
        """
        self.command_dir = command_dir
        self.logger = logging.getLogger('commands.utils.command_builder')

        # ✅ Создаём директорию если не существует
        os.makedirs(self.command_dir, exist_ok=True)
        self.logger.info(f"📁 Директория команд: {self.command_dir}")

    def generate_random_extension(self, length: int = 4) -> str:
        """
        Генерирует случайное расширение файла

        Args:
            length: Длина расширения (без учёта '.')

        Returns:
            str: Случайное расширение (например, '.x7k9')
        """
        random_part = ''.join(random.choice(self.SAFE_CHARS) for _ in range(length))
        return f".{random_part}"

    def generate_filename(
            self,
            sim: str,
            command_code: str,
            extension: Optional[str] = None,
            include_random: bool = True
    ) -> str:
        """
        Генерирует имя файла команды

        Args:
            sim: SIM устройства
            command_code: Код команды (например, cmd06)
            extension: Расширение (если None — по формату или случайное)
            include_random: Добавить случайную часть к расширению

        Returns:
            str: Имя файла (например, '79215851634.cmd06.x7k9')
        """
        # ✅ Безопасный код команды
        safe_code = command_code.replace('/', '_').replace('\\', '_').replace(':', '_')
        safe_code = ''.join(c for c in safe_code if c.isalnum() or c in '._-')

        # ✅ Расширение
        if extension is None:
            if include_random:
                extension = self.generate_random_extension(length=4)
            else:
                extension = '.cmd'  # По умолчанию
        elif not extension.startswith('.'):
            extension = f".{extension}"
        elif include_random and extension in self.COMMAND_FORMATS.values():
            # Добавляем случайную часть к стандартному расширению
            random_part = self.generate_random_extension(length=4)
            extension = f"{extension}{random_part}"

        # ✅ Имя файла: sim.command_code.ext
        filename = f"{sim}{extension}"

        return filename

    def build_command(
            self,
            sim: str,
            command_code: str,
            command_type: str = 'text',
            params: Optional[Dict[str, Any]] = None,
            extension: Optional[str] = None,
            include_metadata: bool = True,
            priority: int = 2,
            command_data: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Строит команду для отправки на устройство

        Args:
            sim: SIM устройства
            command_code: Внутренний код команды (например, cmd06)
            command_type: Тип команды (text, hex, json, binary)
            params: Параметры команды
            extension: Расширение файла
            include_metadata: Включать метаданные в файл
            priority: Приоритет команды

        Returns:
            dict: {
                'filepath': str,      # Путь к файлу
                'sim': str,           # SIM устройства
                'command_code': str,  # Код команды
                'command_type': str,  # Тип команды
                'command_data': str,  # Данные команды
                'priority': int,      # Приоритет
                'created_at': str     # Время создания
            }
        """
        try:
            # ✅ Генерируем имя файла
            filename = self.generate_filename(sim, command_code, extension)
            filepath = os.path.join(self.command_dir, filename)

            self.logger.info(f"📝 Построение команды: {command_code} для {sim}")

            # ✅ Форматируем данные команды
            if command_data:
                # ← ← ← Используем готовые данные (для SET_CONFIG)
                final_command_data = command_data
            else:
                # ← ← ← Форматируем автоматически
                final_command_data = self._format_command_data(
                    command_code=command_code,
                    command_type=command_type,
                    params=params or {}
                )

                # ✅ Формируем содержимое файла
            file_content = self._build_file_content(
                sim=sim,
                command_code=command_code,
                command_type=command_type,
                command_data=final_command_data,
                params=params,
                include_metadata=include_metadata,
                priority=priority
            )

            # ✅ Запись в файл
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(file_content)

            self.logger.info(f"✅ Файл команды создан: {filepath}")

            # ✅ Возвращаем информацию о команде
            return {
                'filepath': filepath,
                'sim': sim,
                'command_code': command_code,
                'command_type': command_type,
                'command_data': final_command_data,
                'params': params,
                'priority': priority,
                'created_at': self._get_timestamp()
            }

        except Exception as e:
            self.logger.error(f"❌ Ошибка построения команды: {e}", exc_info=True)
            raise IOError(f"Не удалось создать файл команды: {str(e)}")

    def _format_command_data(
            self,
            command_code: str,
            command_type: str,
            params: Dict[str, Any]
    ) -> str:
        """
        Форматирует данные команды в зависимости от типа

        Args:
            command_code: Код команды
            command_type: Тип команды
            params: Параметры

        Returns:
            str: Отформатированные данные команды
        """
        if command_type == 'text':
            # ✅ Текстовый формат: command_code|param1|param2
            param_values = [str(v) for v in params.values()] if params else []
            return '|'.join([command_code] + param_values)

        elif command_type == 'keyvalue':  # ← ← ← НОВЫЙ ТИП!
            # ✅ Формат key=value (для SET_CONFIG)
            # {"param_name": "T1", "param_value": 30.0} → T1=30
            param_name = params.get('param_name', '')
            param_value = params.get('param_value', '')
            return f"{param_name}={param_value}"

        elif command_type == 'hex':
            # ✅ HEX формат: байты команды
            # Пример: cmd06 -> 0x43 0x6D 0x64 0x30 0x36
            hex_bytes = command_code.encode('utf-8').hex()
            if params:
                param_hex = ' '.join(str(v) for v in params.values())
                hex_bytes = f"{hex_bytes} {param_hex}"
            return hex_bytes.upper()

        elif command_type == 'json':
            # ✅ JSON формат
            return json.dumps({
                'command': command_code,
                'params': params
            }, ensure_ascii=False)

        elif command_type == 'binary':
            # ✅ Binary формат (base64 для хранения в тексте)
            import base64
            binary_data = command_code.encode('utf-8')
            if params:
                binary_data += json.dumps(params).encode('utf-8')
            return base64.b64encode(binary_data).decode('utf-8')

        elif command_type == 'xml':
            # ✅ XML формат
            params_xml = ''.join(f'<{k}>{v}</{k}>' for k, v in params.items())
            return f'<command><code>{command_code}</code>{params_xml}</command>'

        else:
            # ✅ По умолчанию — текст
            return command_code

    def _build_file_content(
            self,
            sim: str,
            command_code: str,
            command_type: str,
            command_data: str,
            params: Optional[Dict[str, Any]],
            include_metadata: bool,
            priority: int
    ) -> str:
        """
        Строит содержимое файла команды

        Args:
            sim: SIM устройства
            command_code: Код команды
            command_type: Тип команды
            command_data: Данные команды
            params: Параметры
            include_metadata: Включать метаданные
            priority: Приоритет

        Returns:
            str: Содержимое файла
        """
        lines = []

        if include_metadata:
            # ✅ Метаданные (для отправителя, не для устройства)
            lines.extend([
                f"To: {sim}",
                f"",
            ])

        lines.append(f"RQWQR:{command_data.upper()}")
        # ✅ Параметры отдельно (если нужны)
        # if params:
        #     for key, value in params.items():
        #         lines.append(f"{key.upper()}={value}")
        # else:
        # ✅ Данные команды (это отправляется на устройство)
        # lines.append(f"RQWQR:{command_data.upper()}")

        # ✅ Служебная информация
        # lines.append(f"#")
        # lines.append(f"SIM={sim}")
        # lines.append(f"PRIORITY={priority}")
        # lines.append(f"STATUS=pending")

        return '\n'.join(lines) + '\n'

    def read_command(self, filepath: str) -> Dict[str, Any]:
        """
        Читает команду из файла

        Args:
            filepath: Путь к файлу команды

        Returns:
            dict: Данные команды
        """
        command = {}

        if not os.path.exists(filepath):
            self.logger.error(f"❌ Файл не найден: {filepath}")
            return command

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()

                    # Пропускаем пустые строки и комментарии
                    if not line or line.startswith('#'):
                        continue

                    # Парсим key=value
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()

                        if key == 'CMD':
                            command['command_data'] = value
                        elif key == 'SIM':
                            command['sim'] = value
                        elif key == 'PRIORITY':
                            command['priority'] = int(value)
                        elif key == 'STATUS':
                            command['status'] = value
                        elif key.startswith('PARAM_'):
                            param_name = key[6:].lower()
                            command.setdefault('params', {})[param_name] = self._parse_value(value)

            self.logger.info(f"📖 Прочитана команда: {command.get('command_data')}")
            return command

        except Exception as e:
            self.logger.error(f"❌ Ошибка чтения файла: {e}")
            return {}

    def _parse_value(self, value: str) -> Any:
        """Конвертирует строковое значение в подходящий тип"""
        if value.lower() in ('true', 'yes', '1'):
            return True
        if value.lower() in ('false', 'no', '0'):
            return False

        try:
            return int(value)
        except ValueError:
            pass

        try:
            return float(value)
        except ValueError:
            pass

        return value

    def _get_timestamp(self) -> str:
        """Возвращает текущую метку времени UTC"""
        return datetime.now(timezone.utc).isoformat()

    def delete_command(self, filepath: str) -> bool:
        """
        Удаляет файл команды

        Args:
            filepath: Путь к файлу

        Returns:
            bool: True если удалено
        """
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                self.logger.info(f"🗑️ Удалён файл команды: {filepath}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"❌ Ошибка удаления: {e}")
            return False

    def get_pending_commands(self, sim: str) -> List[Dict[str, Any]]:
        """
        Получает все ожидающие команды для устройства

        Args:
            sim: SIM устройства

        Returns:
            list: Список команд
        """
        commands = []

        if not os.path.exists(self.command_dir):
            return commands

        pattern = f"{sim}."

        for filename in os.listdir(self.command_dir):
            if filename.startswith(pattern):
                filepath = os.path.join(self.command_dir, filename)
                command = self.read_command(filepath)

                if command.get('status') == 'pending':
                    command['filepath'] = filepath
                    command['filename'] = filename
                    commands.append(command)

        self.logger.info(f"📊 Найдено команд для {sim}: {len(commands)}")
        return commands

    def mark_command_sent(self, filepath: str) -> bool:
        """
        Отмечает команду как отправленную

        Args:
            filepath: Путь к файлу команды

        Returns:
            bool: True если обновлено
        """
        try:
            command = self.read_command(filepath)

            if not command:
                return False

            # Обновляем статус в файле
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            content = content.replace('STATUS=pending', 'STATUS=sent')
            content = content.replace(
                f"Created: {command.get('created_at', '')}",
                f"Created: {command.get('created_at', '')}\n# Sent: {self._get_timestamp()}"
            )

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)

            self.logger.info(f"✅ Команда отмечена как отправленная: {filepath}")
            return True

        except Exception as e:
            self.logger.error(f"❌ Ошибка обновления статуса: {e}")
            return False
