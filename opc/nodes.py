# opc/nodes.py
# -*- coding: utf-8 -*-
"""
Модуль для создания и управления узлами OPC UA
Объекты, переменные, методы с поддержкой телеметрии и команд
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Any, Dict, List, Callable
from dataclasses import dataclass, field

from opcua import ua
from opcua.ua import (
    LocalizedText, DataValue, Variant, VariantType,
    StatusCode, StatusCodes, NodeId, QualifiedName, AttributeIds
)

from opc.types import OPCTypeMapper

logger = logging.getLogger(__name__)


# ============================================================================
# Константы и конфигурация
# ============================================================================

class NodeConfig:
    """Конфигурация узлов OPC UA"""

    # AccessLevel флаги
    READ_ONLY = ua.AccessLevel.CurrentRead
    READ_WRITE = ua.AccessLevel.CurrentRead | ua.AccessLevel.CurrentWrite

    # UserAccessLevel флаги
    USER_READ_ONLY = ua.AccessLevel.CurrentRead
    USER_READ_WRITE = ua.AccessLevel.CurrentRead | ua.AccessLevel.CurrentWrite

    # Статусы по умолчанию
    STATUS_GOOD = StatusCode(StatusCodes.Good)
    STATUS_BAD = StatusCode(StatusCodes.Bad)
    STATUS_UNCERTAIN = StatusCode(StatusCodes.Uncertain)


# ============================================================================
# Data-классы для метаданных узлов
# ============================================================================

@dataclass
class VariableMetadata:
    """Метаданные для переменной OPC UA"""
    browse_name: str
    display_name: str
    description: str = ''
    data_type: VariantType = VariantType.Variant
    value: Any = 0
    is_writable: bool = False
    unit: str = ''
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    sampling_interval: int = 1000  # мс
    historical: bool = False


@dataclass
class ObjectMetadata:
    """Метаданные для объекта OPC UA"""
    browse_name: str
    display_name: str
    description: str = ''
    type_definition: NodeId = field(default_factory=lambda: ua.ObjectTypes.BaseObjectType)


@dataclass
class MethodMetadata:
    """Метаданные для метода OPC UA"""
    browse_name: str
    display_name: str
    description: str = ''
    callback: Callable = None
    input_args: List[ua.Argument] = field(default_factory=list)
    output_args: List[ua.Argument] = field(default_factory=list)


# ============================================================================
# Основной класс создания узлов
# ============================================================================

class NodeCreator:
    """
    Создает и управляет узлами OPC UA

    Пример использования:
        creator = NodeCreator(server, namespace_idx)
        obj_node = creator.create_object(parent, 'Device1', 'Устройство 1')
        var_node = creator.create_variable(obj_node, 'Temp', 'Температура', 25.5)
        method_node = creator.create_method(obj_node, 'Reboot', 'Перезагрузка', callback)
    """

    def __init__(self, server, namespace_idx: int):
        """
        Инициализирует создатель узлов

        Args:
            server: Экземпляр opcua.Server
            namespace_idx: Индекс пространства имен
        """
        self.server = server
        self.idx = namespace_idx
        self.logger = logging.getLogger('opc.nodes')

        # Кэш созданных узлов для быстрого доступа
        self._node_cache: Dict[str, ua.NodeId] = {}

    # ========================================================================
    # Создание объектов
    # ========================================================================

    # def create_object(
    #         self,
    #         parent: Any,
    #         browse_name: str,
    #         display_name: str,
    #         description: str = '',
    #         type_definition: NodeId = None
    # ) -> Any:
    #     """
    #     Создает объект OPC UA
    #
    #     Args:
    #         parent: Родительский узел
    #         browse_name: Имя для поиска (BrowseName)
    #         display_name: Отображаемое имя (DisplayName)
    #         description: Описание узла
    #         type_definition: Тип объекта (по умолчанию BaseObjectType)
    #
    #     Returns:
    #         Созданный узел объекта
    #     """
    #     self.logger.debug(f"Создание объекта: {browse_name}")
    #     self.logger.debug(f"  Родитель: {parent}")
    #     self.logger.debug(f"  Parent NodeId: {parent.nodeid if parent else 'None'}")
    #     if parent is None:
    #         self.logger.warning("Родительский узел = None, используем Objects folder")
    #         parent = self.server.get_objects_node()
    #     try:
    #         if type_definition is None:
    #             type_definition = ua.ObjectTypes.BaseObjectType
    #
    #         node = parent.add_object(
    #             self.idx,
    #             browse_name,
    #             type_definition
    #         )
    #
    #         # Устанавливаем метаданные
    #         node.set_display_name(LocalizedText(display_name))
    #         if description:
    #             node.set_description(LocalizedText(description))
    #
    #         # Кэшируем узел
    #         cache_key = f"{parent.nodeid.Identifier}:{browse_name}"
    #         self._node_cache[cache_key] = node.nodeid
    #
    #         self.logger.debug(f"Создан объект: {browse_name}")
    #         return node
    #
    #     except Exception as e:
    #         self.logger.error(f"Ошибка создания объекта {browse_name}: {e}")
    #         raise
    def create_object(self, parent, browse_name, display_name, description=''):
        """Создаёт объект с правильными атрибутами"""
        node = parent.add_object(self.idx, browse_name)

        # ✅ ИСПРАВЛЕНО
        node.set_attribute(
            AttributeIds.DisplayName,
            DataValue(LocalizedText(display_name))
        )

        if description:
            node.set_attribute(
                AttributeIds.Description,
                DataValue(LocalizedText(description))
            )

        return node

    def create_variable(self, parent, browse_name, display_name, value,
                        description='', data_type=None, is_writable=False, unit=''):
        """Создаёт переменную с правильными атрибутами"""
        if data_type is None:
            data_type = OPCTypeMapper.guess_variant_type(value)

        converted_value = OPCTypeMapper.convert_value(value, data_type)

        node = parent.add_variable(
            self.idx,
            browse_name,
            converted_value,
            varianttype=data_type
        )

        # ✅ ИСПРАВЛЕНО
        node.set_attribute(
            AttributeIds.DisplayName,
            DataValue(LocalizedText(display_name))
        )

        if description:
            node.set_attribute(
                AttributeIds.Description,
                DataValue(LocalizedText(description))
            )

        if is_writable:
            node.set_writable()

        if unit:
            try:
                eu_info = self._create_engineering_unit(unit)
                node.set_attribute(
                    AttributeIds.EngineeringUnits,
                    DataValue(eu_info)
                )
            except Exception as e:
                self.logger.debug(f"Не удалось установить EngineeringUnits: {e}")

        return node

    def create_method(self, parent, browse_name, display_name, callback,
                      description='', input_args=None, output_args=None):
        """Создаёт метод с правильными атрибутами"""
        input_args = input_args or []
        output_args = output_args or []

        node = parent.add_method(
            self.idx,
            browse_name,
            callback,
            input_args,
            output_args
        )

        # ✅ ИСПРАВЛЕНО
        node.set_attribute(
            AttributeIds.DisplayName,
            DataValue(LocalizedText(display_name))
        )

        if description:
            node.set_attribute(
                AttributeIds.Description,
                DataValue(LocalizedText(description))
            )

        return node

    def create_folder(
            self,
            parent: Any,
            browse_name: str,
            display_name: str
    ) -> Any:
        """
        Создает папку для группировки узлов

        Args:
            parent: Родительский узел
            browse_name: Имя папки
            display_name: Отображаемое имя

        Returns:
            Созданный узел папки
        """
        return self.create_object(
            parent,
            browse_name,
            display_name,
            description='Папка для группировки узлов',
            type_definition=ua.ObjectTypes.FolderType
        )

    # ========================================================================
    # Создание переменных
    # ========================================================================

    # def create_variable(
    #         self,
    #         parent: Any,
    #         browse_name: str,
    #         display_name: str,
    #         value: Any,
    #         description: str = '',
    #         data_type: VariantType = None,
    #         is_writable: bool = False,
    #         unit: str = '',
    #         min_value: Optional[float] = None,
    #         max_value: Optional[float] = None
    # ) -> Any:
    #     """
    #     Создает переменную OPC UA
    #
    #     Args:
    #         parent: Родительский узел
    #         browse_name: Имя для поиска
    #         display_name: Отображаемое имя
    #         value: Начальное значение
    #         description: Описание
    #         data_type: Тип данных OPC UA
    #         is_writable: Можно ли записывать значение
    #         unit: Единица измерения
    #         min_value: Минимальное значение (для валидации)
    #         max_value: Максимальное значение (для валидации)
    #
    #     Returns:
    #         Созданный узел переменной
    #     """
    #     try:
    #         # Определяем тип данных автоматически если не указан
    #         if data_type is None:
    #             data_type = OPCTypeMapper.guess_variant_type(value)
    #
    #         # Конвертируем значение в нужный тип
    #         converted_value = OPCTypeMapper.convert_value(value, data_type)
    #
    #         # Создаем переменную
    #         node = parent.add_variable(
    #             self.idx,
    #             browse_name,
    #             converted_value,
    #             varianttype=data_type
    #         )
    #
    #         # Устанавливаем метаданные
    #         node.set_display_name(LocalizedText(display_name))
    #         if description:
    #             node.set_description(LocalizedText(description))
    #
    #         # Устанавливаем доступ
    #         if is_writable:
    #             node.set_writable()
    #             node.set_attr_bit(ua.AttributeIds.UserAccessLevel, NodeConfig.USER_READ_WRITE)
    #         else:
    #             node.set_attr_bit(ua.AttributeIds.AccessLevel, NodeConfig.READ_ONLY)
    #             node.set_attr_bit(ua.AttributeIds.UserAccessLevel, NodeConfig.USER_READ_ONLY)
    #
    #         # Устанавливаем единицу измерения (EngineeringUnits)
    #         if unit:
    #             eu_info = self._create_engineering_unit(unit)
    #             node.set_attribute(
    #                 ua.AttributeIds.EngineeringUnits,  # ✅ Правильный AttributeId
    #                 ua.DataValue(eu_info)  # ✅ Оборачиваем в DataValue
    #             )
    #
    #         # Устанавливаем диапазон значений (если указан)
    #         if min_value is not None or max_value is not None:
    #             range_val = self._create_value_range(min_value, max_value)
    #             node.set_attribute(
    #                 ua.AttributeIds.Value,
    #                 DataValue(range_val)
    #             )
    #
    #         # Кэшируем узел
    #         cache_key = f"{parent.nodeid.Identifier}:{browse_name}"
    #         self._node_cache[cache_key] = node.nodeid
    #
    #         self.logger.debug(f"Создана переменная: {browse_name} (writable={is_writable})")
    #         return node
    #
    #     except Exception as e:
    #         self.logger.error(f"Ошибка создания переменной {browse_name}: {e}")
    #         raise

    def create_telemetry_variable(
            self,
            parent: Any,
            alias: str,
            name: str,
            value: Any,
            description: str = '',
            unit: str = '',
            data_type: str = 'float'
    ) -> Any:
        """
        Создает переменную телеметрии (только чтение)

        Args:
            parent: Родительский узел
            alias: Технический идентификатор (для кэша)
            name: Отображаемое имя
            value: Текущее значение
            description: Описание
            unit: Единица измерения
            data_type: Тип данных ('int', 'float', 'string', 'bool')

        Returns:
            Созданный узел переменной
        """
        variant_type = OPCTypeMapper.get_variant_type(data_type)

        node = self.create_variable(
            parent=parent,
            browse_name=alias,
            display_name=name,
            value=value,
            description=description,
            data_type=variant_type,
            is_writable=False,
            unit=unit
        )

        # Сохраняем в кэш по alias для быстрого обновления
        self._node_cache[f'telemetry:{alias}'] = node.nodeid

        return node

    def create_command_variable(
            self,
            parent: Any,
            alias: str,
            name: str,
            value: Any,
            description: str = '',
            unit: str = '',
            data_type: str = 'int',
            callback: Callable = None,
            min_value: Optional[float] = None,
            max_value: Optional[float] = None
    ) -> Any:
        """
        Создает переменную команды (запись разрешена)

        Args:
            parent: Родительский узел
            alias: Технический идентификатор
            name: Отображаемое имя
            value: Начальное значение
            description: Описание
            unit: Единица измерения
            data_type: Тип данных
            callback: Callback при изменении значения
            min_value: Минимальное значение
            max_value: Максимальное значение

        Returns:
            Созданный узел переменной
        """
        variant_type = OPCTypeMapper.get_variant_type(data_type)

        node = self.create_variable(
            parent=parent,
            browse_name=alias,
            display_name=name,
            value=value,
            description=description,
            data_type=variant_type,
            is_writable=True,
            unit=unit,
            min_value=min_value,
            max_value=max_value
        )

        # Регистрируем callback на изменение значения
        if callback:
            node.set_value_callback(callback)

        # Сохраняем в кэш по alias
        self._node_cache[f'command:{alias}'] = node.nodeid

        return node

    # ========================================================================
    # Создание методов
    # ========================================================================

    # def create_method(
    #         self,
    #         parent: Any,
    #         browse_name: str,
    #         display_name: str,
    #         callback: Callable,
    #         description: str = '',
    #         input_args: List[ua.Argument] = None,
    #         output_args: List[ua.Argument] = None
    # ) -> Any:
    #     """
    #     Создает метод OPC UA
    #
    #     Args:
    #         parent: Родительский узел
    #         browse_name: Имя метода
    #         display_name: Отображаемое имя
    #         callback: Функция-обработчик вызова
    #         description: Описание метода
    #         input_args: Входные аргументы
    #         output_args: Выходные аргументы
    #
    #     Returns:
    #         Созданный узел метода
    #
    #     Пример callback:
    #         def my_callback(method_id, variant_args):
    #             # variant_args: list[Variant] с входными параметрами
    #             # Возврат: (StatusCode, list[Variant] с выходными параметрами)
    #             return ua.StatusCode(StatusCodes.Good), [Variant("OK", VariantType.String)]
    #     """
    #     try:
    #         input_args = input_args or []
    #         output_args = output_args or []
    #
    #         node = parent.add_method(
    #             self.idx,
    #             browse_name,
    #             callback,
    #             input_args,
    #             output_args
    #         )
    #
    #         # Устанавливаем метаданные
    #         node.set_display_name(LocalizedText(display_name))
    #         if description:
    #             node.set_description(LocalizedText(description))
    #
    #         # Кэшируем узел
    #         cache_key = f"{parent.nodeid.Identifier}:{browse_name}"
    #         self._node_cache[cache_key] = node.nodeid
    #
    #         self.logger.debug(f"Создан метод: {browse_name}")
    #         return node
    #
    #     except Exception as e:
    #         self.logger.error(f"Ошибка создания метода {browse_name}: {e}")
    #         raise

    def create_command_method(
            self,
            parent: Any,
            command_code: str,
            command_name: str,
            callback: Callable,
            description: str = '',
            param_schema: List[dict] = None
    ) -> Any:
        """
        Создает метод команды на основе схемы параметров

        Args:
            parent: Родительский узел
            command_code: Код команды (browse_name)
            command_name: Отображаемое имя
            callback: Обработчик вызова
            description: Описание
            param_schema: Схема параметров [{'name': 'val', 'type': 'float'}, ...]

        Returns:
            Созданный узел метода
        """
        # Формируем входные аргументы из схемы
        input_args = []
        if param_schema:
            for param in param_schema:
                dtype = OPCTypeMapper.get_variant_type(param.get('type', 'string'))
                input_args.append(
                    ua.Argument(
                        Name=param.get('name', 'value'),
                        DataType=NodeId(dtype),
                        ValueRank=-1,
                        ArrayDimensions=[],
                        Description=LocalizedText(param.get('desc', ''))
                    )
                )

        # Стандартные выходные аргументы
        output_args = [
            ua.Argument(
                Name='status',
                DataType=NodeId(VariantType.Int32),
                ValueRank=-1,
                Description=LocalizedText('Код результата: 0=OK, <0=Error')
            ),
            ua.Argument(
                Name='message',
                DataType=NodeId(VariantType.String),
                ValueRank=-1,
                Description=LocalizedText('Сообщение результата')
            )
        ]

        return self.create_method(
            parent=parent,
            browse_name=command_code,
            display_name=command_name,
            callback=callback,
            description=description,
            input_args=input_args,
            output_args=output_args
        )

    # ========================================================================
    # Обновление значений узлов
    # ========================================================================

    def update_variable_value(
            self,
            node: Any,
            value: Any,
            status: StatusCode = None,
            source_timestamp: datetime = None
    ) -> None:
        """
        Обновляет значение переменной

        Args:
            node: Узел переменной
            value: Новое значение
            status: Статус качества (по умолчанию Good)
            source_timestamp: Время получения данных (по умолчанию сейчас)
        """
        try:
            if status is None:
                status = NodeConfig.STATUS_GOOD

            if source_timestamp is None:
                source_timestamp = datetime.now(timezone.utc)

            server_timestamp = datetime.now(timezone.utc)

            # Получаем тип данных из узла
            data_type = node.get_data_type()
            variant_type = OPCTypeMapper.nodeid_to_variant_type(data_type)

            # Конвертируем значение
            converted_value = OPCTypeMapper.convert_value(value, variant_type)

            # Создаем DataValue с метаданными
            data_value = DataValue(
                Value=Variant(converted_value, variant_type),
                StatusCode=status,
                SourceTimestamp=source_timestamp,
                ServerTimestamp=server_timestamp
            )

            node.set_value(data_value)

        except Exception as e:
            self.logger.error(f"Ошибка обновления значения узла: {e}")
            raise

    def update_variable_by_alias(
            self,
            alias: str,
            value: Any,
            status: StatusCode = None,
            source_timestamp: datetime = None
    ) -> bool:
        """
        Обновляет значение переменной по alias (из кэша)

        Args:
            alias: Технический идентификатор переменной
            value: Новое значение
            status: Статус качества
            source_timestamp: Время данных

        Returns:
            True если успешно, False если узел не найден
        """
        cache_key = f'telemetry:{alias}'
        node_id = self._node_cache.get(cache_key)

        if node_id is None:
            self.logger.warning(f"Узел не найден в кэше: {alias}")
            return False

        try:
            node = self.server.get_node(node_id)
            self.update_variable_value(node, value, status, source_timestamp)
            return True
        except Exception as e:
            self.logger.error(f"Ошибка обновления узла {alias}: {e}")
            return False

    # ========================================================================
    # Удаление узлов
    # ========================================================================

    def delete_node(self, node: Any) -> bool:
        """
        Безопасно удаляет узел

        Args:
            node: Узел для удаления

        Returns:
            True если успешно
        """
        try:
            node.delete()
            self.logger.debug(f"Узел удален: {node.nodeid}")
            return True
        except Exception as e:
            self.logger.error(f"Ошибка удаления узла: {e}")
            return False

    def delete_node_by_alias(self, alias: str) -> bool:
        """
        Удаляет узел по alias

        Args:
            alias: Технический идентификатор

        Returns:
            True если успешно
        """
        # Проверяем разные префиксы кэша
        for prefix in ['telemetry:', 'command:', '']:
            cache_key = f'{prefix}{alias}'
            node_id = self._node_cache.pop(cache_key, None)

            if node_id:
                try:
                    node = self.server.get_node(node_id)
                    node.delete()
                    self.logger.debug(f"Узел удален по alias: {alias}")
                    return True
                except Exception as e:
                    self.logger.error(f"Ошибка удаления узла {alias}: {e}")
                    return False

        self.logger.warning(f"Узел не найден для удаления: {alias}")
        return False

    # ========================================================================
    # Вспомогательные методы
    # ========================================================================

    def _create_engineering_unit(self, unit: str) -> ua.EUInformation:  # ✅ Правильный класс
        """
        Создает объект EUInformation для единицы измерения

        Args:
            unit: Строка единицы измерения (например, '°C', 'V', 'A')

        Returns:
            ua.EUInformation объект
        """
        # Маппинг распространенных единиц (EU URI из OPC UA стандарта)
        unit_map = {
            '°C': ('http://www.opcfoundation.org/UA/units/un/cefact', 62613, 'degree Celsius', '°C'),
            '°F': ('http://www.opcfoundation.org/UA/units/un/cefact', 62615, 'degree Fahrenheit', '°F'),
            'V': ('http://www.opcfoundation.org/UA/units/un/cefact', 5066857, 'volt', 'V'),
            'A': ('http://www.opcfoundation.org/UA/units/un/cefact', 5066858, 'ampere', 'A'),
            'Pa': ('http://www.opcfoundation.org/UA/units/un/cefact', 5066861, 'pascal', 'Pa'),
            'bar': ('http://www.opcfoundation.org/UA/units/un/cefact', 5066862, 'bar', 'bar'),
            '%': ('http://www.opcfoundation.org/UA/units/un/cefact', 5066870, 'percent', '%'),
            'Hz': ('http://www.opcfoundation.org/UA/units/un/cefact', 5066867, 'hertz', 'Hz'),
            's': ('http://www.opcfoundation.org/UA/units/un/cefact', 5066829, 'second', 's'),
            'ms': ('http://www.opcfoundation.org/UA/units/un/cefact', 5066830, 'millisecond', 'ms'),
            'm': ('http://www.opcfoundation.org/UA/units/un/cefact', 5066819, 'metre', 'm'),
            'mm': ('http://www.opcfoundation.org/UA/units/un/cefact', 5066820, 'millimetre', 'mm'),
            'kg': ('http://www.opcfoundation.org/UA/units/un/cefact', 5066841, 'kilogram', 'kg'),
            'g': ('http://www.opcfoundation.org/UA/units/un/cefact', 5066842, 'gram', 'g'),
            'L': ('http://www.opcfoundation.org/UA/units/un/cefact', 5066891, 'litre', 'L'),
            'm³': ('http://www.opcfoundation.org/UA/units/un/cefact', 5066895, 'cubic metre', 'm³'),
            'W': ('http://www.opcfoundation.org/UA/units/un/cefact', 5066859, 'watt', 'W'),
            'kW': ('http://www.opcfoundation.org/UA/units/un/cefact', 5066860, 'kilowatt', 'kW'),
            'rpm': ('http://www.opcfoundation.org/UA/units/un/cefact', 5066905, 'revolutions per minute', 'rpm'),
        }

        if unit in unit_map:
            namespace, unit_id, display_name, symbol = unit_map[unit]
            return ua.EUInformation(  # ✅ Правильный класс
                NamespaceUri=namespace,
                UnitId=unit_id,
                DisplayName=ua.LocalizedText(display_name),
                Description=ua.LocalizedText(symbol)
            )

        # Для неизвестных единиц создаем кастомную
        return ua.EUInformation(
            NamespaceUri='http://custom.units',
            UnitId=0,
            DisplayName=ua.LocalizedText(unit),
            Description=ua.LocalizedText(unit)
        )

    def _create_value_range(
            self,
            min_value: Optional[float],
            max_value: Optional[float]
    ) -> ua.Range:
        """
        Создает объект Range для диапазона значений

        Args:
            min_value: Минимальное значение
            max_value: Максимальное значение

        Returns:
            ua.Range объект
        """
        low = min_value if min_value is not None else -float('inf')
        high = max_value if max_value is not None else float('inf')
        return ua.Range(low=low, high=high)

    def get_node_by_alias(self, alias: str) -> Optional[Any]:
        """
        Получает узел по alias из кэша

        Args:
            alias: Технический идентификатор

        Returns:
            Узел OPC UA или None
        """
        for prefix in ['telemetry:', 'command:', '']:
            cache_key = f'{prefix}{alias}'
            node_id = self._node_cache.get(cache_key)
            if node_id:
                return self.server.get_node(node_id)
        return None

    def get_all_cached_nodes(self) -> Dict[str, ua.NodeId]:
        """
        Возвращает все закэшированные узлы

        Returns:
            Словарь {alias: NodeId}
        """
        return self._node_cache.copy()

    def clear_cache(self) -> None:
        """Очищает кэш узлов"""
        self._node_cache.clear()
        self.logger.debug("Кэш узлов очищен")

    def _validate_parent(self, parent, default_to_objects=True):
        """Проверяет валидность родительского узла"""
        if parent is None:
            if default_to_objects:
                return self.server.get_objects_node()
            raise ValueError("Родительский узел не указан")

        # Проверяем что NodeId не null (TwoByteNodeId(i=0))
        if hasattr(parent, 'nodeid'):
            if parent.nodeid.Identifier == 0 and parent.nodeid.NamespaceIndex == 0:
                self.logger.warning(f"Родительский узел имеет Null NodeId: {parent.nodeid}")
                if default_to_objects:
                    return self.server.get_objects_node()

        return parent