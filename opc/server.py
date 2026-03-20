# opc/server.py
# -*- coding: utf-8 -*-
"""
OPC UA сервер — управление сервером и узлами
Структура: Objects -> ObjectName -> [Parameters, Commands]
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
from pathlib import Path
from opcua import ua, Server
from opcua.ua import (
    NodeClass, ObjectIds, Argument,
    LocalizedText,
    DataValue,
    Variant,
    VariantType,
    StatusCode,
    StatusCodes,
    AttributeIds,
    SecurityPolicyType,
    MessageSecurityMode,
)

from db.connection import Database
from db.data_loader import DataLoader, TelemetryData
from opc.nodes import NodeCreator
from opc.types import OPCTypeMapper
from opc.commands.registry import OpcCommandRegistry
from opc.status_codes import status_determiner
from opcua.common.manage_nodes import create_method as create_method_node

logger = logging.getLogger(__name__)


class OPCServer:
    """Управление OPC UA сервером"""
    def __init__(self, config: dict, db: Database):
        self.config = config
        self.db = db
        self.logger = logging.getLogger('opc.server')
        # ✅ ДОБАВЛЯЕМ default_period_min
        self.default_period_min = config.get('default_period_min', 1440)  # 24 часа по умолчанию
        self.server: Optional[Server] = None
        self.idx: Optional[int] = None
        self.node_creator: Optional[NodeCreator] = None
        self.data_loader: Optional[DataLoader] = None

        # ✅ Создаём реестр команд (внутри него - receiver)
        self.opc_command_registry = OpcCommandRegistry(db)
        # self.opc_command_registry: Optional[OpcCommandRegistry] = None

        self._telemetry_nodes: Dict[str, Any] = {}
        self._device_nodes: Dict[str, Any] = {}
        self._command_nodes: Dict[str, Any] = {}
        self._command_by_browsename: Dict[str, str] = {}  # BrowseName -> code  ← ← ← НОВОЕ!

    def start(self) -> None:
        """Запускает OPC UA сервер"""
        srv_cfg = self.config.get('server', {})
        app_cfg = self.config.get('app', {})

        # 1. Создаём сервер
        self.server = Server()

        # 2. Устанавливаем эндпоинт
        endpoint_url = srv_cfg.get('endpoint', 'opc.tcp://0.0.0.0:4840/')
        self.server.set_endpoint(endpoint_url)

        # 3. Имя сервера
        self.server.set_server_name(app_cfg.get('name', 'OPC UA Server'))

        # 4. ✅ НАСТРОЙКА БЕЗОПАСНОСТИ (ТОЛЬКО set_security_policy!)
        self._setup_security_policy()

        # 5. Namespace
        self.idx = self.server.register_namespace(
            app_cfg.get('namespace_uri', 'http://server')
        )

        # 6. ✅ ЗАПУСК СЕРВЕРА
        self.server.start()

        self.node_creator = NodeCreator(self.server, self.idx)

        self.logger.info(f"OPC UA сервер запущен: {endpoint_url}")

        # Инициализация загрузчиков
        default_period = self.config.get('polling.default_period_min', 1440)
        self.data_loader = DataLoader(self.db, default_period)
        self.opc_command_registry = OpcCommandRegistry(self.db)

        # Создание структуры
        self.create_address_space()

    def _setup_security_policy(self) -> None:
        """
        Настраивает политики безопасности

        ✅ ПРАВИЛЬНО: только set_security_policy(), без set_security_modes()
        """
        sec_cfg = self.config.get('server.security', {})

        if sec_cfg.get('enable_encryption', False):
            # Продакшен: шифрование
            cert_path = sec_cfg.get('certificate')
            key_path = sec_cfg.get('private_key')

            if cert_path and key_path and Path(cert_path).exists():
                try:
                    self.server.load_certificate(cert_path)
                    self.server.load_private_key(key_path)

                    # ✅ Только set_security_policy!
                    self.server.set_security_policy([
                        SecurityPolicyType.Basic256Sha256_SignAndEncrypt
                    ])
                    self.logger.info("🔐 Security: Basic256Sha256_SignAndEncrypt")

                except Exception as e:
                    self.logger.error(f"Ошибка загрузки сертификатов: {e}")
                    self._setup_no_security()
            else:
                self.logger.warning("⚠️ Сертификаты не найдены")
                self._setup_no_security()
        else:
            # Тесты: без безопасности
            self._setup_no_security()

    def _setup_no_security(self) -> None:
        """Настраивает режим без безопасности"""
        # ✅ ТОЛЬКО set_security_policy, без set_security_modes!
        self.server.set_security_policy([
            SecurityPolicyType.NoSecurity
        ])
        self.logger.info("🔓 Security: NoSecurity")

    def stop(self) -> None:
        """Останавливает сервер"""
        if self.server:
            self.server.stop()
            self.logger.info("OPC UA сервер остановлен")

    def get_endpoints_info(self) -> list:
        """Возвращает информацию о доступных эндпоинтах"""
        try:
            endpoints = self.server.get_endpoints()
            for ep in endpoints:
                self.logger.info(
                    f"Endpoint: {ep.EndpointUrl}, "
                    f"Security: {ep.SecurityPolicyUri}, "
                    f"Mode: {ep.SecurityMode}"
                )
            return endpoints
        except Exception as e:
            self.logger.error(f"Ошибка получения эндпоинтов: {e}")
            return []

    def get_session_info(self) -> list:
        """Получает информацию об активных сессиях"""
        try:
            sessions = self.server.get_active_sessions()
            for session in sessions:
                logger.info(
                    f"Active session: {session.name}, "
                    f"Client: {session.client_description}, "
                    f"Timeout: {session.timeout}"
                )
            return sessions
        except Exception as e:
            logger.error(f"Ошибка получения сессий: {e}")
            return []

    def create_address_space(self) -> None:
        """Создаёт адресное пространство сервера"""
        try:
            objects_node = self.server.get_objects_node()
            devices = self.data_loader.get_devices()

            # ✅ ОТЛАДКА: ПРОВЕРИТЬ ЧТО В registry.commands
            self.logger.info(f"🔍 opc_command_registry.commands keys: {list(self.opc_command_registry.commands.keys())}")

            for code, meta in self.opc_command_registry.commands.items():
                self.logger.info(f"🔍 {code} в registry:")
                self.logger.info(f"   has_params: {meta.get('has_params')}")
                self.logger.info(f"   param_schema: {meta.get('param_schema')}")
                self.logger.info(f"   param_schema len: {len(meta.get('param_schema', []))}")

            # ✅ Получаем команды
            commands = self.opc_command_registry.commands

            for obj_data in devices:
                obj_name = obj_data.get('name', 'Unknown')
                obj_sim = obj_data.get('sim')

                if not obj_sim:
                    continue

                # ✅ ОТЛАДКА: ПРОВЕРИТЬ ПЕРЕД СОЗДАНИЕМ
                self.logger.info(f"🔍 Перед созданием {obj_name}:")
                for code, meta in commands.items():
                    if code == 'SET_CONFIG':
                        self.logger.info(f"   SET_CONFIG param_schema: {meta.get('param_schema')}")

                self._create_device_object(
                    objects_node,
                    obj_name,
                    obj_data,
                    commands  # ← ← ← Передаём commands
                )

            self.logger.info("✅ Адресное пространство создано")

        except Exception as e:
            self.logger.error(f"Ошибка создания адресного пространства: {e}", exc_info=True)

    def _create_device_object(
            self,
            parent_node,
            obj_name: str,
            obj_data: dict,
            commands: dict
    ) -> None:
        """
        Создаёт объект устройства с параметрами и командами
        """
        try:
            from opcua.ua import NodeClass, AttributeIds, LocalizedText, DataValue, Variant, VariantType

            # ✅ ОТЛАДКА: ПРОВЕРИТЬ commands
            self.logger.info(f"🔍 {obj_name}: commands keys: {list(commands.keys())}")

            for code, meta in commands.items():
                if code == 'SET_CONFIG':
                    self.logger.info(f"🔍 SET_CONFIG в _create_device_object:")
                    self.logger.info(f"   meta type: {type(meta)}")
                    self.logger.info(f"   meta keys: {meta.keys()}")
                    self.logger.info(f"   has_params: {meta.get('has_params')}")
                    self.logger.info(f"   param_schema: {meta.get('param_schema')}")
                    self.logger.info(f"   param_schema type: {type(meta.get('param_schema'))}")

            # ✅ ИЗВЛЕКАЕМ SIM
            obj_sim = obj_data.get('sim')

            if not obj_sim:
                self.logger.warning(f"⚠️ Устройство {obj_name} без SIM, пропускаем")
                return

            self.logger.info(f"📦 Создание устройства: {obj_name} (sim={obj_sim})")

            # Создаём объект устройства
            device_node = parent_node.add_object(
                self.idx,
                self._to_browse_name(obj_name)
            )
            device_node.set_attribute(
                AttributeIds.DisplayName,
                DataValue(LocalizedText(obj_name))
            )

            # ✅ Папка Parameters
            params_folder = device_node.add_object(self.idx, "Parameters")
            params_folder.set_attribute(
                AttributeIds.DisplayName,
                DataValue(LocalizedText("Параметры"))
            )

            # ✅ ✅ ИСПРАВЛЕНО: get_object_params, а не get_device_params!
            params = self.data_loader.get_object_params(obj_sim)

            self.logger.info(f"   Найдено параметров: {len(params)}")

            # Создаём параметры устройства
            for p in params:
                # Создаём временный объект для совместимости с _create_parameter_node
                from db.data_loader import TelemetryData

                # Формируем кортеж как ожидает TelemetryData.__init__
                # (obj_name, sim, lpu, period, alias, name, unit, comment,
                #  param_type, description, value, timestamp, nico, pgroup, disp)
                temp_row = (
                    obj_name,  # obj_name
                    obj_sim,  # sim
                    obj_data.get('sname', ''),  # lpu
                    self.default_period_min,  # period
                    p['alias'],  # alias
                    p['name'],  # name
                    p['unit'],  # unit
                    p['comment'],  # comment
                    p['type'],  # param_type
                    p['description'],  # description
                    None,  # value (загрузится из pvalues)
                    None,  # timestamp
                    None,  # nico
                    p['pgroup'],  # pgroup
                    p['disp']  # disp
                )

                param_data = TelemetryData(temp_row)
                self._create_parameter_node(params_folder, param_data)

            # ✅ Папка Commands
            commands_folder = device_node.add_object(self.idx, "Commands")
            commands_folder.set_attribute(
                AttributeIds.DisplayName,
                DataValue(LocalizedText("Команды"))
            )

            # ✅ Создаём методы команд
            for code, meta in commands.items():
                self.logger.info(f"🔍 Вызов _create_command_node для {code}:")
                self.logger.info(f"   meta: {meta}")

                self._create_command_node(
                    commands_folder,
                    code,
                    meta,
                    sim=obj_sim  # ← ← ← Привязка к устройству!
                )

            # Кэш устройства
            self._device_nodes[obj_sim] = {
                'node': device_node,
                'name': obj_name,
                'sim': obj_sim
            }

            self.logger.info(f"✅ Устройство создано: {obj_name} (sim={obj_sim})")

        except Exception as e:
            self.logger.error(f"Ошибка создания устройства {obj_name}: {e}", exc_info=True)

    # opc/server.py

    def _create_command_node(self, parent_node, code: str, meta: dict, sim: str) -> None:
        """Создаёт метод команды с поддержкой _meta структуры"""
        try:
            from opcua.ua import NodeClass, AttributeIds, LocalizedText, DataValue, Variant

            self.logger.info(f"🔍 Создание команды: {code}")
            self.logger.info(f"   meta keys: {meta.keys()}")
            self.logger.info(f"   param_schema: {meta.get('param_schema')}")

            # ✅ ФОРМИРУЕМ ВХОДНЫЕ АРГУМЕНТЫ
            input_args = []

            # ✅ Получаем схему параметров (теперь это может быть dict с 'params')
            param_schema_raw = meta.get('param_schema', [])

            # ✅ Определяем где схема параметров
            if isinstance(param_schema_raw, dict):
                # Новая структура: {"_meta": {...}, "params": [...]}
                param_schema = param_schema_raw.get('params', [])
                self.logger.info(f"📋 Новая структура param_schema (с _meta)")
            elif isinstance(param_schema_raw, list):
                # Старая структура: [...]
                param_schema = param_schema_raw
                self.logger.info(f"📋 Старая структура param_schema (список)")
            else:
                param_schema = []
                self.logger.warning(f"⚠️ param_schema не dict и не list: {type(param_schema_raw)}")

            self.logger.info(f"📋 Схема параметров: {param_schema}")

            has_params = meta.get('has_params', False)

            if has_params and param_schema:
                self.logger.info(f"📋 {code}: Создаём input_args...")

                for i, p in enumerate(param_schema):
                    self.logger.info(f"   Параметр {i}: {p} (type={type(p)})")

                    # ✅ Проверяем что p — это dict
                    if not isinstance(p, dict):
                        self.logger.warning(f"⚠️ Параметр {i} не dict, пропускаем: {p}")
                        continue

                    param_type = p.get('type', 'string')
                    param_name = p.get('name', f'param_{i}')
                    param_desc = p.get('desc', '')

                    dtype = self._get_builtin_node_id(param_type)

                    self.logger.info(f"   + InputArgument: {param_name} (type={param_type}, dtype={dtype})")

                    arg = self._create_argument(
                        name=param_name,
                        data_type=dtype,
                        description=param_desc
                    )

                    input_args.append(arg)
                    self.logger.info(f"   ✅ Добавлен аргумент {i}: {arg.Name}")
            else:
                self.logger.info(f"📋 {code}: Без параметров (has_params={has_params}, schema_len={len(param_schema)})")

            self.logger.info(f"📋 {code}: Всего input_args: {len(input_args)}")

            # ✅ ВЫХОДНЫЕ АРГУМЕНТЫ
            output_args = [
                self._create_argument(
                    name='result_code',
                    data_type=ua.NodeId(ua.ObjectIds.Int32),
                    description='Код результата: 0=OK, <0=Error'
                ),
                self._create_argument(
                    name='result_message',
                    data_type=ua.NodeId(ua.ObjectIds.String),
                    description='Сообщение результата'
                )
            ]

            self.logger.info(f"📋 {code}: Всего output_args: {len(output_args)}")

            # ✅ Создаём метод
            def command_callback(method_nodeid, *args):
                return self._on_command_call_with_code(code, sim, method_nodeid, *args)

            self.logger.info(f"📋 {code}: Вызов add_method()...")
            self.logger.info(f"   input_args: {len(input_args)}")
            self.logger.info(f"   output_args: {len(output_args)}")

            node = parent_node.add_method(
                ua.NodeId(0, self.idx),
                ua.QualifiedName(code, self.idx),
                command_callback,
                input_args,
                output_args
            )

            method_node_id = node.nodeid

            # ✅ Устанавливаем атрибуты
            node.set_attribute(
                AttributeIds.DisplayName,
                DataValue(LocalizedText(meta.get('name', code)))
            )
            node.set_attribute(
                AttributeIds.Description,
                DataValue(LocalizedText(meta.get('description', '')))
            )
            node.set_attribute(
                AttributeIds.Executable,
                DataValue(Variant(True, VariantType.Boolean))
            )
            node.set_attribute(
                AttributeIds.UserExecutable,
                DataValue(Variant(True, VariantType.Boolean))
            )

            # ✅ Сохраняем в кэш
            cache_key = f"{code}:{sim}"
            self._command_nodes[cache_key] = {
                'node': node,
                'node_id': method_node_id,
                'sim': sim,
                'code': code,
                'meta': meta
            }

            self.logger.info(f"   ✅ Команда {cache_key} создана (NodeId: {method_node_id})")

        except Exception as e:
            self.logger.error(f"Ошибка создания команды {code}: {e}", exc_info=True)
            raise
    # def _create_command_node(self, parent_node, code: str, meta: dict, sim: str) -> None:
    #     """Создаёт метод команды с уникальным callback"""
    #     try:
    #         from opcua.ua import NodeClass, AttributeIds, LocalizedText, DataValue, Variant
    #
    #         self.logger.info(f"🔍 Создание команды: {code}")
    #         self.logger.info(f"   meta keys: {meta.keys()}")
    #         self.logger.info(f"   has_params: {meta.get('has_params')}")
    #         self.logger.info(f"   param_schema: {meta.get('param_schema')}")
    #         self.logger.info(f"   param_schema type: {type(meta.get('param_schema'))}")
    #
    #         # ✅ ФОРМИРУЕМ ВХОДНЫЕ АРГУМЕНТЫ
    #         input_args = []
    #
    #         # 🔍 ПРОВЕРЯЕМ УСЛОВИЕ
    #         has_params = meta.get('has_params')
    #         param_schema = meta.get('param_schema')
    #
    #         self.logger.info(f"   🔍 has_params truthy: {bool(has_params)}")
    #         self.logger.info(f"   🔍 param_schema truthy: {bool(param_schema)}")
    #         self.logger.info(f"   🔍 param_schema len: {len(param_schema) if param_schema else 0}")
    #
    #         if has_params and param_schema:
    #             self.logger.info(f"📋 {code}: Создаём input_args...")
    #
    #             for i, p in enumerate(param_schema):
    #                 self.logger.info(f"   Параметр {i}: {p}")
    #
    #                 param_type = p.get('type', 'string')
    #                 param_name = p.get('name', f'param_{i}')
    #                 param_desc = p.get('desc', '')
    #
    #                 dtype = self._get_builtin_node_id(param_type)
    #
    #                 self.logger.info(f"   + InputArgument: {param_name} (type={param_type}, dtype={dtype})")
    #
    #                 arg = self._create_argument(
    #                     name=param_name,
    #                     data_type=dtype,
    #                     description=param_desc
    #                 )
    #
    #                 input_args.append(arg)
    #                 self.logger.info(f"   ✅ Добавлен аргумент {i}: {arg.Name}")
    #         else:
    #             self.logger.warning(f"⚠️ {code}: НЕ создаём input_args!")
    #             self.logger.warning(f"   has_params: {has_params}")
    #             self.logger.warning(f"   param_schema: {param_schema}")
    #
    #         self.logger.info(f"📋 {code}: Всего input_args: {len(input_args)}")
    #
    #         # ✅ ВЫХОДНЫЕ АРГУМЕНТЫ
    #         output_args = [
    #             self._create_argument(
    #                 name='result_code',
    #                 data_type=ua.NodeId(ua.ObjectIds.Int32),
    #                 description='Код результата: 0=OK, <0=Error'
    #             ),
    #             self._create_argument(
    #                 name='result_message',
    #                 data_type=ua.NodeId(ua.ObjectIds.String),
    #                 description='Сообщение результата'
    #             )
    #         ]
    #
    #         self.logger.info(f"📋 {code}: Всего output_args: {len(output_args)}")
    #
    #         # ✅ Создаём метод
    #         def command_callback(method_nodeid, *args):
    #             return self._on_command_call_with_code(code, sim, method_nodeid, *args)
    #
    #         self.logger.info(f"📋 {code}: Вызов add_method()...")
    #         self.logger.info(f"   input_args: {len(input_args)}")
    #         self.logger.info(f"   output_args: {len(output_args)}")
    #
    #         node = parent_node.add_method(
    #             ua.NodeId(0, self.idx),
    #             ua.QualifiedName(code, self.idx),
    #             command_callback,
    #             input_args,  # ← ← ← Входные аргументы!
    #             output_args  # ← ← ← Выходные аргументы!
    #         )
    #
    #         self.logger.info(f"✅ Метод создан: {code}")
    #         self.logger.info(f"   NodeId: {node.nodeid}")
    #
    #         method_node_id = node.nodeid
    #
    #         # ✅ Устанавливаем атрибуты
    #         node.set_attribute(
    #             AttributeIds.DisplayName,
    #             DataValue(LocalizedText(meta['name']))
    #         )
    #         node.set_attribute(
    #             AttributeIds.Description,
    #             DataValue(LocalizedText(meta.get('description', '')))
    #         )
    #         node.set_attribute(
    #             AttributeIds.Executable,
    #             DataValue(Variant(True, VariantType.Boolean))
    #         )
    #         node.set_attribute(
    #             AttributeIds.UserExecutable,
    #             DataValue(Variant(True, VariantType.Boolean))
    #         )
    #
    #         # ✅ Сохраняем в кэш
    #         cache_key = f"{code}:{sim}"
    #         self._command_nodes[cache_key] = {
    #             'node': node,
    #             'node_id': method_node_id,
    #             'sim': sim,
    #             'code': code,
    #             'meta': meta
    #         }
    #
    #         self.logger.info(f"   ✅ Команда {cache_key} создана (NodeId: {method_node_id})")
    #
    #     except Exception as e:
    #         self.logger.error(f"Ошибка создания команды {code}: {e}", exc_info=True)

    def _on_command_call_with_code(self, code: str, sim: str, method_nodeid, *args):
        """
        Обработчик вызова команды с известным кодом (из замыкания)
        """
        from opcua.ua import NodeClass

        self.logger.info(f"📞 ════════════════════════════════════════")
        self.logger.info(f"📞 ВЫЗОВ КОМАНДЫ")
        self.logger.info(f"📞 code: {code}")
        self.logger.info(f"📞 sim: {sim}")
        self.logger.info(f"📞 method_nodeid: {method_nodeid}")
        self.logger.info(f"📞 args: {args}")

        # ✅ Проверяем узел (для отладки)
        try:
            node = self.server.get_node(method_nodeid)
            node_class = node.get_node_class()
            bn = node.get_browse_name()

            self.logger.info(f"📞 Узел: {node}")
            self.logger.info(f"📞 BrowseName: {bn}")
            self.logger.info(f"📞 NodeClass: {node_class}")

        except Exception as e:
            self.logger.error(f"📞 Ошибка получения узла: {e}")

        # ✅ Выполняем команду (код уже известен из замыкания!)
        self.logger.info(f"✅ Выполнение: {code} для sim={sim}")

        # ✅ ПЕРЕДАЁМ КОД НАПРЯМУЮ
        result = self.opc_command_registry.execute(
            method_nodeid,
            args,
            sim=sim,
            code=code  # ← ← ← Проверить что это не None!
        )

        self.logger.info(f"✅ Результат: {result}")
        self.logger.info(f"📞 ════════════════════════════════════════")

        return result

    def _on_command_call(self, method_nodeid, *args):
        """Обработчик вызова команды (поиск по BrowseName)"""
        try:
            from opcua.ua import NodeClass

            self.logger.info(f"📞 Вызов команды: nodeid={method_nodeid}")

            # ✅ Получаем узел и его BrowseName
            node = self.server.get_node(method_nodeid)
            bn = node.get_browse_name()
            node_class = node.get_node_class()

            self.logger.info(f"📞 BrowseName: {bn}")
            self.logger.info(f"📞 NodeClass: {node_class}")

            # ✅ Проверяем что это метод
            if node_class != NodeClass.Method:
                self.logger.error(f"❌ Вызван не метод, а {node_class}!")
                return [Variant(-1, VariantType.Int32), Variant("Не метод", VariantType.String)]

            # ✅ Ищем команду по BrowseName.Name
            code = bn.Name if bn else None

            if not code:
                self.logger.error(f"❌ Не удалось получить BrowseName")
                return [Variant(-1, VariantType.Int32), Variant("Нет имени", VariantType.String)]

            self.logger.info(f"📞 Код команды из BrowseName: {code}")

            # 🔍 Ищем в кэше по коду (игнорируя SIM для поиска)
            for cache_key, info in self._command_nodes.items():
                cached_code = info.get('code')

                if cached_code == code:
                    # ✅ Найдено!
                    sim = info.get('sim')
                    self.logger.info(f"✅ Найдено: {cache_key} -> sim={sim}")

                    # Выполняем через реестр
                    return self.opc_command_registry.execute(method_nodeid, args, sim=sim)

            # ❌ Не найдено
            self.logger.warning(f"❌ Команда '{code}' не найдена в кэше")
            self.logger.info(f"📋 Доступные коды: {set(info.get('code') for info in self._command_nodes.values())}")

            return [Variant(-1, VariantType.Int32), Variant(f"Команда не найдена: {code}", VariantType.String)]

        except Exception as e:
            self.logger.error(f"❌ Ошибка выполнения команды: {e}", exc_info=True)
            return [Variant(-999, VariantType.Int32), Variant(str(e), VariantType.String)]

    def _node_ids_match(self, node_id1, node_id2) -> bool:
        """Надёжное сравнение двух NodeId"""
        if node_id1 == node_id2:
            return True

        id1 = node_id1.Identifier if hasattr(node_id1, 'Identifier') else node_id1
        ns1 = node_id1.NamespaceIndex if hasattr(node_id1, 'NamespaceIndex') else 0

        id2 = node_id2.Identifier if hasattr(node_id2, 'Identifier') else node_id2
        ns2 = node_id2.NamespaceIndex if hasattr(node_id2, 'NamespaceIndex') else 0

        return id1 == id2 and ns1 == ns2

    def _create_parameter_node(self, parent_node, param: TelemetryData) -> None:
        """
        Создаёт узел параметра со StatusCode и Property со статусом

        Args:
            parent_node: Родительский узел (папка Parameters)
            param: Данные параметра из БД
        """
        try:
            # 1. Определение типа данных и конвертация значения
            variant_type = OPCTypeMapper.get_variant_type(param.param_type)
            value = OPCTypeMapper.convert_value(param.value, variant_type)

            # 2. Создание основного узла
            node = parent_node.add_variable(
                self.idx,
                param.alias,
                value,
                varianttype=variant_type
            )

            # 3. DisplayName
            node.set_attribute(
                AttributeIds.DisplayName,
                DataValue(LocalizedText(param.name or param.alias))
            )

            # 4. Description (статичное описание)
            display_unit = param.unit or param.disp or ''
            description = f"{param.comment}".strip()
            if display_unit:
                description += f" [{display_unit}]" if description else f"[{display_unit}]"

            node.set_attribute(
                AttributeIds.Description,
                DataValue(LocalizedText(description))
            )

            # 5. EngineeringUnits (если есть единица измерения)
            if display_unit:
                try:
                    eu_info = self.node_creator._create_engineering_unit(display_unit)
                    node.set_attribute(
                        AttributeIds.EngineeringUnits,
                        DataValue(eu_info)
                    )
                except Exception as e:
                    self.logger.debug(f"Не удалось установить EngineeringUnits для {param.alias}: {e}")

            # 6. Определение статуса через nico
            status_code, status_message = status_determiner.get_status(
                alias=param.alias,
                value=param.value,
                timestamp=param.timestamp,
                period_min=param.period,
                nico=param.nico,
                param_type=param.param_type
            )

            # 7. ✅ ВРЕМЕННЫЕ МЕТКИ (одинаковые для Value и Property!)
            now = datetime.now(timezone.utc)
            source_ts = param.timestamp or now  # ← Из БД (время получения)
            server_ts = now  # ← Время обработки сервером

            # 8. Установка значения основного узла
            node.set_value(DataValue(
                variant=Variant(value, variant_type),  # ← Ваша версия библиотеки
                status=StatusCode(status_code.value if hasattr(status_code, 'value') else status_code),
                sourceTimestamp=source_ts,  # ← Из БД
                serverTimestamp=server_ts  # ← Текущее
            ))

            # 9. ✅ СОЗДАНИЕ PROPERTY (StatusMessage)
            status_prop = node.add_property(
                self.idx,
                "StatusMessage",
                status_message
            )
            status_prop.set_attribute(
                AttributeIds.DisplayName,
                DataValue(LocalizedText("Сообщение статуса"))
            )
            status_prop.set_attribute(
                AttributeIds.Description,
                DataValue(LocalizedText("Текстовое описание текущего статуса параметра"))
            )
            status_prop.set_writable(False)  # Только чтение

            # 10. ✅ Установка значения Property (с ТАКИМИ ЖЕ timestamps!)
            status_prop.set_value(DataValue(
                variant=Variant(status_message, VariantType.String),  # ← Ваша версия
                status=StatusCode(0x00000000),  # Good
                sourceTimestamp=source_ts,  # ← ТО ЖЕ ЧТО У VALUE!
                serverTimestamp=server_ts  # ← ТО ЖЕ ЧТО У VALUE!
            ))

            # 11. Сохранение в кэш для обновления
            self._telemetry_nodes[param.alias] = {
                'node': node,
                'status_prop_node': status_prop,  # ← Ссылка на Property
                'sim': param.sim,
                'nico': param.nico,
                'period': param.period,
                'last_status': status_code,
                'last_status_message': status_message
            }

            # 12. Подписка на NOTIFY из БД
            self.db.listen(param.alias)

            # 13. Логирование
            self.logger.debug(
                f"Создан параметр: {param.alias}, "
                f"sim={param.sim}, "
                f"nico={param.nico}, "
                f"Status: {status_code}, "
                f"Message: {status_message}, "
                f"SourceTS: {source_ts}"
            )

        except Exception as e:
            self.logger.error(f"Ошибка создания узла {param.alias}: {e}", exc_info=True)

    def update_parameter(self, alias: str) -> bool:
        """
        Обновляет значение параметра и Property StatusMessage
        Args:
            alias: Алиас параметра
        Returns:
            True если успешно
        """
        if alias not in self._telemetry_nodes:
            return False

        try:
            info = self._telemetry_nodes[alias]
            node = info['node']
            status_prop = info.get('status_prop_node')

            # Получаем данные из БД
            value_data = self.data_loader.get_parameter_value(alias)

            # ❌ НЕТ ДАННЫХ
            if not value_data:
                status_code = StatusCode(0x80000005)  # Bad_NoData
                status_message = "Нет данных"

                # Временные метки (текущее время т.к. данных нет)
                now = datetime.now(timezone.utc)
                source_ts = now
                server_ts = now


                # Обновляем основной узел
                node.set_value(DataValue(
                    variant=Variant(0, VariantType.Double),
                    status=StatusCode(status_code.value if hasattr(status_code, 'value') else status_code),
                    sourceTimestamp=source_ts,
                    serverTimestamp=server_ts
                ))

                # ✅ Обновляем Property с ТАКИМИ ЖЕ timestamps
                if status_prop:
                    status_prop.set_value(DataValue(
                        variant=Variant(status_message, VariantType.String),
                        status=StatusCode(0x00000000),
                        sourceTimestamp=source_ts,  # ← ТО ЖЕ!
                        serverTimestamp=server_ts  # ← ТО ЖЕ!
                    ))

                return False

            # ✅ ЕСТЬ ДАННЫЕ
            value, timestamp = value_data  # ← timestamp из БД
            nico = self.data_loader.get_parameter_nico(alias)

            # Определение статуса
            status_code, status_message = status_determiner.get_status(
                alias=alias,
                value=value,
                timestamp=timestamp,
                period_min=info['period'],
                nico=nico
            )

            # ✅ ВРЕМЕННЫЕ МЕТКИ (одинаковые для Value и Property!)
            source_ts = timestamp  # ← Из БД (время получения)
            server_ts = datetime.now(timezone.utc)  # ← Время обработки сервером

            # Обновляем основной узел
            # В блоке "ЕСТЬ ДАННЫЕ", перед node.set_value():

            variant_type = node.get_data_type()

            # ✅ Обработка None перед созданием Variant
            if value is None:
                if variant_type == ua.NodeId(ua.ObjectIds.DateTime):
                    safe_value = []  # Пустой массив для DateTime
                    is_array = True
                elif variant_type in (ua.NodeId(ua.ObjectIds.Int32), ua.NodeId(ua.ObjectIds.Double)):
                    safe_value = 0  # Ноль для чисел
                    is_array = False
                elif variant_type == ua.NodeId(ua.ObjectIds.String):
                    safe_value = ""  # Пустая строка
                    is_array = False
                else:
                    safe_value = []
                    is_array = True

                variant = Variant(safe_value, variant_type, is_array=is_array)
            else:
                # Конвертация строки в datetime для DateTime типа
                if variant_type == ua.NodeId(ua.ObjectIds.DateTime) and isinstance(value, str):
                    try:
                        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    except:
                        value = datetime.now(timezone.utc)

                variant = Variant(value, variant_type)

            # Теперь используем safe variant
            node.set_value(DataValue(
                variant=variant,
                status=StatusCode(...),
                sourceTimestamp=source_ts,
                serverTimestamp=server_ts
            ))

            # ✅ Обновляем Property с ТАКИМИ ЖЕ timestamps!
            if status_prop:
                status_prop.set_value(DataValue(
                    variant=Variant(status_message, VariantType.String),
                    status=StatusCode(0x00000000),
                    sourceTimestamp=source_ts,  # ← ТО ЖЕ ИЗ БД!
                    serverTimestamp=server_ts  # ← ТО ЖЕ ТЕКУЩЕЕ!
                ))

            # Логирование изменений статуса
            if status_code != info.get('last_status'):
                self.logger.info(
                    f"Параметр {alias}: nico={nico}, "
                    f"Status: {status_code}, "
                    f"Message: {status_message}, "
                    f"SourceTS: {source_ts}"
                )
                info['last_status'] = status_code
                info['last_status_message'] = status_message

            return True

        except Exception as e:
            self.logger.error(f"Ошибка обновления параметра {alias}: {e}")
            return False

    def _get_builtin_node_id(self, type_name: str) -> ua.NodeId:
        """Возвращает NodeId для встроенного типа данных"""
        type_mapping = {
            'bool': ua.ObjectIds.Boolean,
            'boolean': ua.ObjectIds.Boolean,
            'int': ua.ObjectIds.Int32,
            'int32': ua.ObjectIds.Int32,
            'int64': ua.ObjectIds.Int64,
            'uint': ua.ObjectIds.UInt32,
            'uint32': ua.ObjectIds.UInt32,
            'uint64': ua.ObjectIds.UInt64,
            'float': ua.ObjectIds.Float,
            'double': ua.ObjectIds.Double,
            'string': ua.ObjectIds.String,
            'str': ua.ObjectIds.String,
            'datetime': ua.ObjectIds.DateTime,
            'guid': ua.ObjectIds.Guid,
            'byte': ua.ObjectIds.Byte,
            'bytes': ua.ObjectIds.ByteString,
        }

        type_lower = type_name.lower()
        object_id = type_mapping.get(type_lower, ua.ObjectIds.String)

        return ua.NodeId(object_id)

        # opc/server.py

    def _get_command_code_from_node_id(self, node_id) -> Optional[str]:
        """
        Получает код команды по NodeId через BrowseName (надёжный способ!)
        """
        try:
            self.logger.info(f"🔍 Поиск команды для NodeId: {node_id}")

            # ✅ Получаем узел по NodeId
            node = self.server.get_node(node_id)

            # ✅ Получаем BrowseName узла
            browse_name = node.get_browse_name()
            code = browse_name.Name if browse_name else None

            self.logger.info(f"   Узел найден: {node}")
            self.logger.info(f"   BrowseName: {browse_name}")
            self.logger.info(f"   BrowseName.Name: {code}")
            self.logger.info(f"   BrowseName.NamespaceIndex: {browse_name.NamespaceIndex if browse_name else 'None'}")

            # ✅ Проверяем что это известная команда
            if code and code in self._command_nodes:
                self.logger.info(f"   ✅ Найдено по BrowseName: {code}")
                return code

            # 🔍 Показываем все доступные команды
            self.logger.warning(f"⚠️ Команда '{code}' не найдена в кэше")
            self.logger.info(f"   📋 Доступные команды: {list(self._command_nodes.keys())}")

            self.logger.info(f"   BrowseName.Name: '{code}'")
            self.logger.info(f"   code in cache: {code in self._command_nodes if code else False}")

            # Попробовать найти по частичному совпадению
            if code:
                for cached_code in self._command_nodes.keys():
                    self.logger.info(f"   Сравнение: '{code}' == '{cached_code}' ? {code == cached_code}")
                    if code.upper() == cached_code.upper():  # Игнорировать регистр
                        self.logger.info(f"   ✅ Найдено (case-insensitive): {cached_code}")
                        return cached_code

            # 🔍 Показываем что в кэше для отладки
            for cached_code, info in self._command_nodes.items():
                cached_node_id = info.get('node_id')
                self.logger.info(f"   Кэш: {cached_code} -> {cached_node_id}")

            return None

        except Exception as e:
            self.logger.error(f"❌ Ошибка поиска команды: {e}", exc_info=True)
            return None

    def _get_command_code_by_nodeid(self, node_id) -> Optional[str]:
        """Резервный метод поиска по NodeId"""
        target_ns = node_id.NamespaceIndex if hasattr(node_id, 'NamespaceIndex') else 0
        target_id = node_id.Identifier if hasattr(node_id, 'Identifier') else node_id

        self.logger.debug(f"🔍 Поиск по NodeId: ns={target_ns}, id={target_id}")

        for code, info in self._command_nodes.items():
            stored_node_id = info.get('node_id')
            if stored_node_id is None:
                continue

            stored_ns = stored_node_id.NamespaceIndex if hasattr(stored_node_id, 'NamespaceIndex') else 0
            stored_id = stored_node_id.Identifier if hasattr(stored_node_id, 'Identifier') else stored_node_id

            if target_ns == stored_ns and target_id == stored_id:
                self.logger.debug(f"   ✅ Найдено совпадение: {code}")
                return code

        return None

    def _get_sim_from_node_id(self, node_id) -> Optional[str]:
        """
        Определяет SIM устройства по NodeId команды
        Команда находится в: Device → Commands → Command
        """
        try:
            for sim, device_node in self._device_nodes.items():
                if self._is_child_of_device(node_id, device_node.nodeid):
                    return sim
            return None
        except Exception as e:
            self.logger.error(f"Ошибка определения sim: {e}")
            return None

    def _create_argument(self, name: str, data_type: ua.NodeId, description: str = '') -> ua.Argument:
        """
        Создаёт Argument через установку атрибутов (работает во всех версиях!)
        """
        arg = ua.Argument()
        arg.Name = name
        arg.DataType = data_type
        arg.ValueRank = -1
        arg.ArrayDimensions = []
        arg.Description = LocalizedText(description)
        return arg

        # opc/server.py

    def _is_child_of_device(self, node_id, device_node_id) -> bool:
        """Проверяет является ли узел потомком устройства"""
        try:
            node = self.server.get_node(node_id)
            parent = node.get_parent()

            # Команда находится в: Device → Commands → Command
            if parent:
                grandparent = parent.get_parent()
                if grandparent and grandparent.nodeid == device_node_id:
                    return True
            return False
        except Exception:
            return False

    def _to_browse_name(self, name: str) -> str:
        """Конвертирует имя в допустимый BrowseName"""
        # Заменяем недопустимые символы
        browse_name = name.strip()
        browse_name = ''.join(c if c.isalnum() or c == '_' else '_' for c in browse_name)

        # Если начинается с цифры - добавляем префикс
        if browse_name and browse_name[0].isdigit():
            browse_name = 'Obj_' + browse_name

        return browse_name or 'Unknown'

    def update_telemetry(self) -> None:
        """Обновляет значения всех узлов телеметрии"""
        for alias, info in self._telemetry_nodes.items():
            self.update_parameter(alias)

    def _determine_status(self, nico: Optional[int], timestamp: datetime,
                          period_min: int) -> StatusCode:
        """
        Определяет StatusCode на основе NICО и времени

        Returns:
            Good — данные актуальны
            Bad — данные устарели или ошибка
        """
        bad_nico = {41, 44, 45, 46}  # Коды ошибок из вашей системы

        now = datetime.now(timezone.utc)

        # 1. Проверка актуальности по времени
        if timestamp and (now - timestamp).total_seconds() > period_min * 60:
            return StatusCode(StatusCodes.Bad_Timeout)  # ⚠️ Данные устарели

        # 2. Проверка NICО (координаты/статус)
        if nico in bad_nico:
            return StatusCode(StatusCodes.Bad_Unreliable)  # ⚠️ Ошибка устройства

        # 3. Всё хорошо
        return StatusCode(StatusCodes.Good)  # ✅ Данные валидны


