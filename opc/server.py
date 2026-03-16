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
from opc.commands.registry import CommandRegistry

logger = logging.getLogger(__name__)


class OPCServer:
    """Управление OPC UA сервером"""

    def __init__(self, config: dict, db: Database):
        self.config = config
        self.db = db
        self.logger = logging.getLogger('opc.server')

        self.server: Optional[Server] = None
        self.idx: Optional[int] = None
        self.node_creator: Optional[NodeCreator] = None
        self.data_loader: Optional[DataLoader] = None
        self.command_registry: Optional[CommandRegistry] = None

        self._telemetry_nodes: Dict[str, Any] = {}
        self._device_nodes: Dict[str, Any] = {}
        self._command_nodes: Dict[str, Any] = {}

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
        self.command_registry = CommandRegistry(self.db)

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
        """
        Создаёт полную структуру адресного пространства:
        Objects -> ObjectName -> [Parameters, Commands]
        """
        self.logger.info("Создание адресного пространства...")

        # Загружаем данные
        devices = self.data_loader.load_telemetry()
        commands = self.command_registry.commands

        if not devices:
            self.logger.warning("Нет устройств для создания узлов")
            return

        objects_node = self.server.get_objects_node()

        # Группируем устройства по имени (objects_new.name)
        devices_by_name: Dict[str, Dict[str, Any]] = {}

        for sim, params in devices.items():
            if not params:
                continue

            obj_name = params[0].obj_name or f"Device_{sim}"

            if obj_name not in devices_by_name:
                devices_by_name[obj_name] = {
                    'sim_list': [],
                    'params': [],
                    'lpu': params[0].lpu
                }

            devices_by_name[obj_name]['sim_list'].append(sim)
            devices_by_name[obj_name]['params'].extend(params)

        # Создаём узлы для каждого объекта
        for obj_name, data in devices_by_name.items():
            self._create_device_object(objects_node, obj_name, data, commands)

        self.logger.info(
            f"Создано адресное пространство: объектов={len(devices_by_name)}, "
            f"параметров={len(self._telemetry_nodes)}, "
            f"команд={len(self._command_nodes)}"
        )

    def _create_device_object(
            self,
            parent_node,
            obj_name: str,
            data: dict,
            commands: dict
    ) -> None:
        """
        Создаёт объект устройства с параметрами и командами

        Структура:
        <obj_name>
        ├── Parameters
        │   ├── <param_alias>
        │   └── ...
        └── Commands
            ├── <command_code>
            └── ...
        """
        try:
            # Создаём основной объект устройства
            device_node = parent_node.add_object(
                self.idx,
                self._to_browse_name(obj_name)
            )
            device_node.set_attribute(
                AttributeIds.DisplayName,
                DataValue(LocalizedText(obj_name))
            )
            device_node.set_attribute(
                AttributeIds.Description,
                DataValue(LocalizedText(f"LPU: {data['lpu']}, Устройств: {len(data['sim_list'])}"))
            )

            # Сохраняем ссылку на устройство
            for sim in data['sim_list']:
                self._device_nodes[sim] = device_node

            # Создаём папку Parameters
            params_folder = device_node.add_object(
                self.idx,
                "Parameters"
            )
            params_folder.set_attribute(
                AttributeIds.DisplayName,
                DataValue(LocalizedText("Параметры"))
            )
            params_folder.set_attribute(
                AttributeIds.Description,
                DataValue(LocalizedText("Параметры телеметрии устройства"))
            )

            # Создаём параметры телеметрии
            for param in data['params']:
                self._create_parameter_node(params_folder, param)

            # Создаём папку Commands
            commands_folder = device_node.add_object(
                self.idx,
                "Commands"
            )
            commands_folder.set_attribute(
                AttributeIds.DisplayName,
                DataValue(LocalizedText("Команды"))
            )
            commands_folder.set_attribute(
                AttributeIds.Description,
                DataValue(LocalizedText("Доступные команды управления"))
            )

            # Создаём методы команд
            for code, meta in commands.items():
                self._create_command_node(commands_folder, code, meta)

        except Exception as e:
            self.logger.error(f"Ошибка создания объекта {obj_name}: {e}", exc_info=True)

    def _create_parameter_node(self, parent_node, param: TelemetryData) -> None:
        """Создаёт узел параметра телеметрии"""
        try:
            variant_type = OPCTypeMapper.get_variant_type(param.param_type)
            value = OPCTypeMapper.convert_value(param.value, variant_type)

            node = parent_node.add_variable(
                self.idx,
                param.alias,
                value,
                varianttype=variant_type
            )

            # DisplayName
            node.set_attribute(
                AttributeIds.DisplayName,
                DataValue(LocalizedText(param.name or param.alias))
            )

            # Description
            display_unit = param.unit or param.disp or ''
            description = f"{param.comment}".strip()
            if display_unit:
                description += f" [{display_unit}]" if description else f"[{display_unit}]"

            node.set_attribute(
                AttributeIds.Description,
                DataValue(LocalizedText(description))
            )

            # EngineeringUnits
            if display_unit:
                try:
                    eu_info = self.node_creator._create_engineering_unit(display_unit)
                    node.set_attribute(
                        AttributeIds.EngineeringUnits,
                        DataValue(eu_info)
                    )
                except Exception as e:
                    self.logger.debug(f"Не удалось установить EngineeringUnits для {param.alias}: {e}")

            # Значение
            now = datetime.now(timezone.utc)
            node.set_value(
                DataValue(
                    variant=Variant(value, variant_type),
                    status=StatusCode(StatusCodes.Good),
                    sourceTimestamp=param.timestamp or now,
                    serverTimestamp=now
                )
            )

            # Кэш
            self._telemetry_nodes[param.alias] = {
                'node': node,
                'sim': param.sim,
                'nico': param.nico,
                'period': param.period
            }

            # Подписка на NOTIFY
            self.db.listen(param.alias)

        except Exception as e:
            self.logger.error(f"Ошибка создания узла параметра {param.alias}: {e}", exc_info=True)

    def _create_command_node(self, parent_node, code: str, meta: dict) -> None:
        """Создаёт метод команды"""
        try:
            # Формируем аргументы метода
            input_args = []
            if meta.get('has_params') and meta.get('param_schema'):
                for p in meta['param_schema']:
                    dtype = OPCTypeMapper.get_variant_type(p.get('type', 'string'))
                    input_args.append(
                        ua.Argument(
                            Name=p['name'],
                            DataType=ua.NodeId(dtype),
                            ValueRank=-1,
                            ArrayDimensions=[],
                            Description=LocalizedText(p.get('desc', ''))
                        )
                    )

            # Стандартные выходные аргументы
            output_args = [
                ua.Argument(
                    Name='status',
                    DataType=ua.NodeId(VariantType.Int32),
                    ValueRank=-1,
                    Description=LocalizedText('Код результата: 0=OK, <0=Error')
                ),
                ua.Argument(
                    Name='message',
                    DataType=ua.NodeId(VariantType.String),
                    ValueRank=-1,
                    Description=LocalizedText('Сообщение результата')
                )
            ]

            # Создаём метод
            node = parent_node.add_method(
                self.idx,
                code,
                self._on_command_call,
                input_args,
                output_args
            )

            node.set_attribute(
                AttributeIds.DisplayName,
                DataValue(LocalizedText(meta['name']))
            )
            node.set_attribute(
                AttributeIds.Description,
                DataValue(LocalizedText(meta.get('description', '')))
            )

            # Кэш
            self._command_nodes[code] = {
                'node': node,
                'meta': meta
            }

        except Exception as e:
            self.logger.error(f"Ошибка создания команды {code}: {e}", exc_info=True)

    def _on_command_call(self, method_id, variant_args):
        """Обработчик вызова команды"""
        try:
            # Определяем код команды по NodeId
            code = self._get_command_code_from_node_id(method_id)

            if not code or code not in self.command_registry.commands:
                return StatusCode(StatusCodes.Bad_NodeIdUnknown), [
                    Variant(-1, VariantType.Int32),
                    Variant("Команда не найдена", VariantType.String)
                ]

            # Выполняем команду через реестр
            return self.command_registry.execute(method_id, variant_args)

        except Exception as e:
            self.logger.error(f"Ошибка выполнения команды: {e}", exc_info=True)
            return StatusCode(StatusCodes.Bad_InternalError), [
                Variant(-999, VariantType.Int32),
                Variant(str(e), VariantType.String)
            ]

    def _get_command_code_from_node_id(self, node_id) -> Optional[str]:
        """Получает код команды по NodeId"""
        for code, info in self._command_nodes.items():
            if info['node'].nodeid == node_id:
                return code
        return None

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

    def update_parameter(self, alias: str) -> bool:
        """Обновляет значение конкретного параметра"""
        if alias not in self._telemetry_nodes:
            return False

        try:
            info = self._telemetry_nodes[alias]
            node = info['node']

            value_data = self.data_loader.get_parameter_value(alias)

            if not value_data:
                self.logger.debug(f"Нет данных для параметра {alias}")
                return False

            value, timestamp = value_data
            nico = self.data_loader.get_parameter_nico(alias)

            status = self._determine_status(nico, timestamp, info['period'])

            variant_type = node.get_data_type()
            node.set_value(
                DataValue(
                    variant=Variant(value, variant_type),
                    status=status,
                    sourceTimestamp=timestamp,
                    serverTimestamp=datetime.now(timezone.utc)
                )
            )

            return True

        except Exception as e:
            self.logger.error(f"Ошибка обновления параметра {alias}: {e}")
            return False

    def _determine_status(
            self,
            nico: Optional[int],
            timestamp: datetime,
            period_min: int
    ) -> StatusCode:
        """Определяет статус качества данных"""
        bad_nico = {41, 44, 45, 46}

        now = datetime.now(timezone.utc)
        if timestamp and (now - timestamp).total_seconds() > period_min * 60:
            return StatusCode(StatusCodes.Bad)

        if nico in bad_nico:
            return StatusCode(StatusCodes.Bad)

        return StatusCode(StatusCodes.Good)
