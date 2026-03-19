# opc/commands/registry.py
# -*- coding: utf-8 -*-
"""
Реестр OPC UA методов команд с валидацией из БД
"""

import logging
import json
from typing import Dict, Any, Optional, Tuple
from opcua import ua
from opcua.ua import Variant, VariantType, NodeId, ObjectIds
from db.connection import Database
from opc.commands.executor import OpcCommandReceiver

logger = logging.getLogger(__name__)


class OpcCommandRegistry:
    """Реестр OPC UA методов команд"""

    def __init__(self, db: Database):
        self.db = db
        self.logger = logging.getLogger('opc.commands.registry')
        self.commands: Dict[str, dict] = {}
        self._command_nodes: Dict[str, Any] = {}
        self.receiver = OpcCommandReceiver(db)
        self.load()

    def load(self) -> None:
        """Загружает каталог команд из БД"""
        try:
            rows = self.db.query("""
                SELECT id, code, name, description, has_params, param_schema, is_active
                FROM commands_catalog
                WHERE is_active = TRUE
                ORDER BY code
            """)

            self.commands = {}
            for row in rows:
                cmd_id, code, name, desc, has_params, param_schema, is_active = row

                if param_schema is None:
                    schema = []
                elif isinstance(param_schema, (list, dict)):
                    schema = param_schema
                elif isinstance(param_schema, str):
                    try:
                        schema = json.loads(param_schema)
                    except:
                        schema = []
                else:
                    schema = []

                self.commands[code] = {
                    'id': cmd_id,
                    'code': code,
                    'name': name,
                    'description': desc,
                    'has_params': bool(has_params),
                    'param_schema': schema,
                    'is_active': bool(is_active)
                }

            self.logger.info(f"📋 Загружено команд: {len(self.commands)}")

        except Exception as e:
            self.logger.error(f"Ошибка загрузки команд: {e}", exc_info=True)

    def execute(
            self,
            nodeid: ua.NodeId,
            args: tuple,
            sim: str,
            code: str = None
    ) -> list:
        """Выполняет команду с валидацией из БД"""
        if code:
            self.logger.info(f"🔍 Код команды из замыкания: {code}")
        else:
            code = self._get_code_from_node_id(nodeid)
            self.logger.info(f"🔍 Код команды из NodeId: {code}")

        if not code or code not in self.commands:
            return [
                Variant(-3, VariantType.Int32),
                Variant(f"Команда не найдена: {code}", VariantType.String)
            ]

        meta = self.commands[code]

        try:
            params = self._parse_args(meta, args)
            self.logger.info(f"📋 Параметры: {params}")

            # ✅ ВАЛИДАЦИЯ С ДАННЫМИ ИЗ БД (desc_params)
            is_valid, error_msg = self._validate_command_params(code, params, sim)

            if not is_valid:
                self.logger.warning(f"❌ Валидация не пройдена: {error_msg}")
                return [
                    Variant(-2, VariantType.Int32),
                    Variant(error_msg, VariantType.String)
                ]

            queue_id = self.receiver.queue_command(
                command_code=code,
                sim=sim,
                params=params,
                requested_by='opc_user'
            )

            if queue_id > 0:
                self.logger.info(f"✅ Команда {code} добавлена в очередь: ID={queue_id}")
                return [
                    Variant(0, VariantType.Int32),
                    Variant(f"Команда принята, ID: {queue_id}", VariantType.String)
                ]
            else:
                return [
                    Variant(-1, VariantType.Int32),
                    Variant("Ошибка записи в очередь", VariantType.String)
                ]

        except Exception as e:
            self.logger.exception(f"Ошибка выполнения команды {code}")
            return [
                Variant(-999, VariantType.Int32),
                Variant(str(e), VariantType.String)
            ]

    def _validate_command_params(self, code: str, params: dict, sim: str) -> Tuple[bool, str]:
        """
        Валидирует параметры команды с данными из desc_params

        Args:
            code: Код команды
            params: Параметры команды
            sim: SIM устройства (для поиска в desc_params)

        Returns:
            tuple: (is_valid: bool, error_message: str)
        """
        if code == 'SET_CONFIG':
            param_name = params.get('param_name', '')
            param_value = params.get('param_value')
            timeout = params.get('timeout', 0)

            # ✅ 1. Базовая валидация обязательных полей
            if not param_name or not isinstance(param_name, str) or not str(param_name).strip():
                return False, "param_name обязателен и не может быть пустым"

            if len(param_name) > 50:
                return False, "param_name должен быть не более 50 символов"

            if param_value is None or param_value == '':
                return False, "param_value обязателен и не может быть пустым"

            if isinstance(param_value, str) and not str(param_value).strip():
                return False, "param_value обязателен и не может быть пустым"

            # ✅ 2. Валидация timeout (1-3600)
            try:
                timeout_int = int(timeout) if timeout is not None else 0
                if timeout_int < 1 or timeout_int > 3600:
                    return False, "timeout должен быть от 1 до 3600 секунд"
            except (ValueError, TypeError):
                return False, "timeout должен быть целым числом от 1 до 3600"

            # ✅ 3. ВАЛИДАЦИЯ ПО desc_params (диапазон min/max для параметра)
            validation_result = self._validate_param_from_desc_params(sim, param_name, param_value)

            if not validation_result['is_valid']:
                return False, validation_result['error_message']

            return True, ""

        # Для других команд (CLEAR_ALARM, REBOOT) - всегда OK
        return True, ""

    # opc/commands/registry.py

    def _validate_param_from_desc_params(self, sim: str, param_name: str, param_value: Any) -> dict:
        """Проверяет параметр по таблице desc_params"""

        try:
            rows = self.db.query("""
                SELECT id_dev, alias, name, min, max, type, units
                FROM desc_params
                WHERE id_dev = 1
                  AND (alias = %s OR name = %s)
                LIMIT 1
            """, (param_name, param_name))

            if not rows:
                return {
                    'is_valid': False,
                    'error_message': f"Параметр '{param_name}' не найден в справочнике"
                }

            row = rows[0]
            id_dev, alias, name, min_val, max_val, param_type, units = row

            # ✅ 1. ПРОВЕРКА: type НЕ ДОЛЖЕН БЫТЬ NULL
            if param_type is None:
                self.logger.error(f"❌ У параметра '{param_name}' не указан тип (type=NULL)")
                return {
                    'is_valid': False,
                    'error_message': f"Ошибка конфигурации: у параметра '{param_name}' не указан тип"
                }

            # ✅ 2. Нормализуем тип (lowercase)
            param_type_lower = param_type.lower().strip()

            # ✅ 3. Строковые типы — не проверяем диапазон min/max
            STRING_TYPES = ('string', 'str', 'text', 'varchar', 'char', 'phone', 'tel', 'telephone')

            if param_type_lower in STRING_TYPES:
                self.logger.info(
                    f"📋 Параметр {param_name} — строковый тип ({param_type}), проверка диапазона пропускается")

                # ✅ 4. Специальная валидация для phone
                if param_type_lower in ('phone', 'tel', 'telephone'):
                    is_valid, error_msg = self._validate_phone_format(param_value)
                    if not is_valid:
                        return {
                            'is_valid': False,
                            'error_message': error_msg,
                            'min': min_val,
                            'max': max_val
                        }

                return {
                    'is_valid': True,
                    'error_message': '',
                    'min': min_val,
                    'max': max_val
                }

            # ✅ 5. Числовые типы — конвертируем и проверяем диапазон
            try:
                numeric_value = float(param_value)
            except (ValueError, TypeError):
                return {
                    'is_valid': False,
                    'error_message': f"param_value должно быть числом (тип параметра: {param_type})"
                }

            # ✅ 6. Проверка min/max
            if min_val is not None and numeric_value < min_val:
                return {
                    'is_valid': False,
                    'error_message': f"Значение {numeric_value} меньше минимального {min_val} {units or ''}"
                }

            if max_val is not None and numeric_value > max_val:
                return {
                    'is_valid': False,
                    'error_message': f"Значение {numeric_value} больше максимального {max_val} {units or ''}"
                }

            return {
                'is_valid': True,
                'error_message': '',
                'min': min_val,
                'max': max_val
            }

        except Exception as e:
            self.logger.error(f"❌ Ошибка проверки desc_params: {e}", exc_info=True)
            return {
                'is_valid': False,
                'error_message': f"Ошибка проверки справочника: {str(e)}"
            }

    def _validate_phone_format(self, phone_value: Any) -> tuple:
        """
        Проверяет формат телефонного номера
        Args:
            phone_value: Значение телефона
        Returns:
            tuple: (is_valid: bool, error_message: str)
        """
        import re

        if phone_value is None or phone_value == '':
            return False, "Номер телефона не может быть пустым"

        phone_str = str(phone_value).strip()

        # ✅ Базовая проверка: только цифры, +, -, (), пробелы
        if not re.match(r'^[\d\s\-\+\(\)]+$', phone_str):
            return False, f"Недопустимые символы в номере телефона: {phone_str}"

        # ✅ Извлекаем только цифры
        digits_only = re.sub(r'[^\d]', '', phone_str)

        # ✅ Проверка длины (для России: 10 или 11 цифр)
        if len(digits_only) < 10:
            return False, f"Слишком короткий номер телефона (минимум 10 цифр, получено: {len(digits_only)})"

        if len(digits_only) > 15:
            return False, f"Слишком длинный номер телефона (максимум 15 цифр, получено: {len(digits_only)})"

        # ✅ Для России: должен начинаться с 7 или 8
        if len(digits_only) >= 10:
            if digits_only[0] not in ('7', '8'):
                self.logger.warning(f"⚠️ Номер телефона не начинается с 7 или 8: {phone_str}")
                # Не блокируем, но предупреждаем (международные номера)

        self.logger.info(f"✅ Номер телефона прошёл валидацию: {phone_str} ({len(digits_only)} цифр)")

        return True, ""



    def _parse_args(self, meta: dict, args: tuple) -> dict:
        """Парсит аргументы метода в словарь параметров"""
        params = {}

        if not meta.get('has_params') or not meta.get('param_schema'):
            return params

        schema = meta['param_schema']

        for i, arg in enumerate(args):
            if i < len(schema):
                param_name = schema[i].get('name', f'param_{i}')

                param_value = None
                if hasattr(arg, 'Value'):
                    param_value = arg.Value
                elif hasattr(arg, 'value'):
                    param_value = arg.value
                else:
                    param_value = arg

                params[param_name] = param_value

        return params

    def _get_code_from_node_id(self, node_id: ua.NodeId) -> Optional[str]:
        """Получает код команды по NodeId"""
        for code, info in self._command_nodes.items():
            if info.get('node_id') == node_id:
                return code
        return None

    def register_command_node(self, code: str, node: Any, node_id: ua.NodeId = None) -> None:
        """Регистрирует узел команды"""
        if node_id is None:
            node_id = node.nodeid if hasattr(node, 'nodeid') else None

        self._command_nodes[code] = {
            'node': node,
            'node_id': node_id
        }

    def get_command_meta(self, code: str) -> Optional[dict]:
        """Получает метаданные команды"""
        return self.commands.get(code)

# # opc/commands/registry.py
# # -*- coding: utf-8 -*-
# """
# Реестр команд OPC UA
# """
#
# import logging
# import json
# from typing import Dict, Any, Optional, Callable, Tuple, List
# from datetime import datetime, timezone
#
# from opcua import ua
# from opcua.ua import Variant, VariantType, StatusCode, StatusCodes, LocalizedText
#
# from db.connection import Database
#
# logger = logging.getLogger(__name__)
#
#
# class OpcCommandRegistry:
#     """Реестр команд с кэшированием"""
#
#     def __init__(self, db: Database):
#         self.db = db
#         self.logger = logging.getLogger('commands.registry')
#         self.commands: Dict[str, dict] = {}
#         self._command_nodes: Dict[str, Any] = {}
#         self.load()
#
#     def load(self) -> None:
#         """Загружает каталог команд из БД"""
#         try:
#             rows = self.db.query("""
#                 SELECT id, code, name, description, has_params, param_schema, is_active
#                 FROM commands_catalog
#                 WHERE is_active = TRUE
#                 ORDER BY code
#             """)
#
#             self.commands = {}
#             for row in rows:
#                 cmd_id, code, name, desc, has_params, param_schema, is_active = row
#
#                 self.logger.info(f"📋 Загрузка команды: {code}")
#                 self.logger.info(f"   has_params: {has_params}")
#                 self.logger.info(f"   param_schema тип: {type(param_schema)}")
#
#                 # ✅ ПРОВЕРЯЕМ ТИП ПЕРЕД ПАРСИНГОМ
#                 if param_schema is None:
#                     schema = []
#                 elif isinstance(param_schema, (list, dict)):
#                     schema = param_schema
#                 elif isinstance(param_schema, str):
#                     try:
#                         schema = json.loads(param_schema)
#                     except (json.JSONDecodeError, TypeError) as e:
#                         self.logger.error(f"   ❌ Ошибка парсинга: {e}")
#                         schema = []
#                 else:
#                     schema = []
#
#                 self.logger.info(f"   param_schema: {schema}")
#
#                 self.commands[code] = {
#                     'id': cmd_id,
#                     'code': code,
#                     'name': name,
#                     'description': desc,
#                     'has_params': bool(has_params),
#                     'param_schema': schema,
#                     'is_active': bool(is_active)
#                 }
#
#                 self.logger.info(f"   ✅ Команда загружена: {code}")
#
#             self.logger.info(f"📋 Всего загружено команд: {len(self.commands)}")
#
#         except Exception as e:
#             self.logger.error(f"Ошибка загрузки команд: {e}", exc_info=True)
#
#     def execute(
#             self,
#             nodeid: ua.NodeId,
#             args: tuple,
#             sim: str,
#             code: str = None
#     ) -> list:
#         """
#         Выполняет команду через очередь
#
#         Args:
#             nodeid: NodeId вызванного метода
#             args: Кортеж входных аргументов (Variant)
#             sim: SIM устройства
#             code: Код команды (если известен из замыкания)
#
#         Returns:
#             list: [result_code Variant, result_message Variant]
#         """
#         # ✅ Если код передан напрямую - используем его!
#         if code:
#             self.logger.info(f"🔍 Код команды из замыкания: {code}")
#         else:
#             code = self._get_code_from_node_id(nodeid)
#             self.logger.info(f"🔍 Код команды из NodeId: {code}")
#
#         if not code or code not in self.commands:
#             self.logger.warning(f"❌ Команда не найдена: {code}")
#             self.logger.info(f"📋 Доступные команды: {list(self.commands.keys())}")
#             return [
#                 Variant(-1, VariantType.Int32),
#                 Variant(f"Команда не найдена: {code}", VariantType.String)
#             ]
#
#         meta = self.commands[code]
#
#         try:
#             # Парсим аргументы
#             params = self._parse_args(meta, args)
#
#             # Добавляем команду в очередь
#             queue_id = self._queue_command(meta['id'], sim, params)
#
#             self.logger.info(f"✅ Команда {code} добавлена в очередь: ID={queue_id}")
#
#             # Возвращаем результат
#             return [
#                 Variant(0, VariantType.Int32),
#                 Variant(f"Команда принята, ID: {queue_id}", VariantType.String)
#             ]
#
#         except Exception as e:
#             self.logger.exception(f"Ошибка выполнения команды {code}")
#             return [
#                 Variant(-999, VariantType.Int32),
#                 Variant(str(e), VariantType.String)
#             ]
#
#     def _parse_args(self, meta: dict, args: tuple) -> dict:
#         """
#         Парсит аргументы метода в словарь параметров
#
#         Args:
#             meta: Метаданные команды (включая param_schema)
#             args: Кортеж Variant аргументов
#
#         Returns:
#             dict: {param_name: value, ...}
#         """
#         params = {}
#
#         if not meta.get('has_params') or not meta.get('param_schema'):
#             self.logger.info(f"📋 Команда без параметров")
#             return params
#
#         schema = meta['param_schema']
#         self.logger.info(f"📋 Схема параметров: {schema}")
#         self.logger.info(f"📋 Получено аргументов: {len(args)}")
#
#         for i, arg in enumerate(args):
#             self.logger.info(f"📋 Аргумент {i}: {arg}")
#             self.logger.info(f"📋 Тип аргумента: {type(arg)}")
#
#             if i < len(schema):
#                 param_name = schema[i].get('name', f'param_{i}')
#
#                 # ✅ ИЗВЛЕКАЕМ ЗНАЧЕНИЕ ИЗ VARIANT
#                 param_value = None
#
#                 if hasattr(arg, 'Value'):
#                     param_value = arg.Value
#                     self.logger.info(f"📋 Извлечено через .Value")
#                 elif hasattr(arg, 'value'):
#                     param_value = arg.value
#                     self.logger.info(f"📋 Извлечено через .value")
#                 else:
#                     param_value = arg
#                     self.logger.info(f"📋 Используется как есть")
#
#                 params[param_name] = param_value
#                 self.logger.info(f"📋 {param_name} = {param_value} (type={type(param_value)})")
#
#         self.logger.info(f"📋 Итоговые параметры: {params}")
#         return params
#
#     def _get_code_from_node_id(self, node_id: ua.NodeId) -> Optional[str]:
#         """Получает код команды по NodeId"""
#         for code, info in self._command_nodes.items():
#             if info.get('node_id') == node_id:
#                 return code
#         return None
#
#     def _queue_command(self, command_id: int, sim: str, params: dict) -> int:
#         """Добавляет команду в очередь"""
#         self.logger.info(f"📋 Добавление в очередь: command_id={command_id}, sim={sim}, params={params}")
#
#         rows = self.db.query("""
#             INSERT INTO commands_queue (command_id, sim, params, status, requested_by)
#             VALUES (%s, %s, %s, 'pending', 'opc_user')
#             RETURNING id
#         """, (command_id, sim, json.dumps(params)))
#
#         queue_id = rows[0][0]
#         self.logger.info(f"Команда добавлена в очередь: ID={queue_id}, sim={sim}")
#
#         return queue_id
#
#     def register_command_node(self, code: str, node: Any, node_id: ua.NodeId = None) -> None:
#         """Регистрирует узел команды для обратного поиска"""
#         if node_id is None:
#             node_id = node.nodeid if hasattr(node, 'nodeid') else None
#
#         self.logger.debug(f"📝 Регистрация команды: {code}")
#         self.logger.debug(f"   NodeId: {node_id}")
#
#         self._command_nodes[code] = {
#             'node': node,
#             'node_id': node_id
#         }
#
#         self.logger.debug(f"   Зарегистрировано: {code in self._command_nodes}")
#
#     def get_command_meta(self, code: str) -> Optional[dict]:
#         """Получает метаданные команды"""
#         return self.commands.get(code)