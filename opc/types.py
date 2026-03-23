# opc/types.py
# -*- coding: utf-8 -*-
"""
Маппинг типов данных для OPC UA
"""

import logging
from typing import Any, Optional
from opcua import ua
from opcua.ua import VariantType, NodeId

logger = logging.getLogger(__name__)


class OPCTypeMapper:
    """Маппинг между типами Python, JSON и OPC UA"""

    TYPE_MAP = {
        'int': VariantType.Int64,
        'integer': VariantType.Int64,
        'bigint': VariantType.Int64,
        'smallint': VariantType.Int16,
        'float': VariantType.Double,
        'double': VariantType.Double,
        'real': VariantType.Float,
        'bool': VariantType.Boolean,
        'boolean': VariantType.Boolean,
        'string': VariantType.String,
        'text': VariantType.String,
        'varchar': VariantType.String,
        'datetime': VariantType.DateTime,
        'timestamp': VariantType.DateTime,
    }

    @classmethod
    def get_variant_type(cls, type_str: str) -> VariantType:
        """Получает OPC UA тип по строковому описанию"""
        return cls.TYPE_MAP.get(type_str.lower(), VariantType.String)

    @classmethod
    def guess_variant_type(cls, value: Any) -> VariantType:
        """Определяет тип по значению Python"""
        if isinstance(value, bool):
            return VariantType.Boolean
        elif isinstance(value, int):
            return VariantType.Int64
        elif isinstance(value, float):
            return VariantType.Double
        elif isinstance(value, str):
            return VariantType.String
        elif isinstance(value, (list, tuple)):
            return VariantType.Variant
        return VariantType.Variant

    @classmethod
    def convert_value(cls, value: Any, variant_type: VariantType) -> Any:
        """Конвертирует значение в нужный тип"""
        if value is None:
            return 0

        try:
            if variant_type in (VariantType.Int64, VariantType.Int32, VariantType.Int16):
                return int(value)
            elif variant_type in (VariantType.Double, VariantType.Float):
                return float(value)
            elif variant_type == VariantType.Boolean:
                return bool(value)
            elif variant_type == VariantType.DateTime:
                return value  # datetime объект
            return str(value)
        except (ValueError, TypeError) as e:
            logger.warning(f"Конвертация значения '{value}': {e}")
            return value

    @classmethod
    def nodeid_to_variant_type(cls, node_id: NodeId) -> VariantType:
        """Определяет VariantType по NodeId типа данных"""
        if not node_id:
            return VariantType.Variant

        # Стандартные OPC UA типы данных
        type_map = {
            1: VariantType.Boolean,
            2: VariantType.SByte,
            3: VariantType.Byte,
            4: VariantType.Int16,
            5: VariantType.UInt16,
            6: VariantType.Int32,
            7: VariantType.UInt32,
            8: VariantType.Int64,
            9: VariantType.UInt64,
            10: VariantType.Float,
            11: VariantType.Double,
            12: VariantType.String,
            13: VariantType.DateTime,
            14: VariantType.Guid,
        }

        identifier = node_id.Identifier if hasattr(node_id, 'Identifier') else None
        return type_map.get(identifier, VariantType.Variant)