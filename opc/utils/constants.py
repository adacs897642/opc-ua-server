# opc/utils/constants.py
# -*- coding: utf-8 -*-
"""
Константы типов данных для asyncua
"""

from asyncua.ua import NodeId, UInt32

# ✅ Маппинг имён типов → NodeId
BUILTIN_NODE_IDS = {
    'string': NodeId(12),  # ObjectIds.String
    'str': NodeId(12),
    'int': NodeId(6),  # ObjectIds.Int32
    'integer': NodeId(6),
    'int32': NodeId(6),
    'int64': NodeId(8),  # ObjectIds.Int64
    'bigint': NodeId(8),
    'float': NodeId(11),  # ObjectIds.Double
    'double': NodeId(11),
    'real': NodeId(10),  # ObjectIds.Float
    'bool': NodeId(1),  # ObjectIds.Boolean
    'boolean': NodeId(1),
    'byte': NodeId(2),  # ObjectIds.Byte
    'datetime': NodeId(13),  # ObjectIds.DateTime
    'timestamp': NodeId(13),
    'phone': NodeId(12),  # String
    'text': NodeId(12),  # String
}


def get_builtin_node_id(type_name: str) -> NodeId:
    """
    Получает NodeId для встроенного типа

    Args:
        type_name: Имя типа ('string', 'int', 'float', etc.)

    Returns:
        NodeId: Идентификатор типа
    """
    return BUILTIN_NODE_IDS.get(type_name.lower(), BUILTIN_NODE_IDS['string'])