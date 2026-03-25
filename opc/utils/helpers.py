# opc/utils/helpers.py
# -*- coding: utf-8 -*-
"""
Хелперы для asyncua с правильными типами
"""

from opcua.ua import (
    DataValue, Variant, VariantType, StatusCode,
    LocalizedText
)
from datetime import datetime, timezone
from typing import Optional, Any, Union


def make_attr_value(value: Any, variant_type: Optional[VariantType] = None) -> DataValue:
    """
    Создаёт DataValue для атрибутов узла (без timestamps)

    Args:
        value: Значение (str, LocalizedText, etc.)
        variant_type: Тип (авто-определение если None)

    Returns:
        DataValue с правильными типами для asyncua
    """
    if variant_type is None:
        variant_type = _infer_variant_type(value)

    # ✅ StatusCode_ не указываем — будет Good по умолчанию
    return DataValue(
        variant=Variant(value, variant_type),
        # StatusCode_ опущен → default_factory=StatusCode() → Good
    )


def make_data_value(
        value: Any,
        variant_type: Optional[VariantType] = None,
        status: Union[int, StatusCode] = 0x00000000,
        source_ts: Optional[datetime] = None,
        server_ts: Optional[datetime] = None
) -> DataValue:
    """
    Создаёт DataValue с timestamp для телеметрии

    Args:
        value: Значение
        variant_type: Тип (авто-определение если None)
        status: StatusCode как int или StatusCode объект
        source_ts: Source timestamp
        server_ts: Server timestamp

    Returns:
        DataValue с правильными типами для asyncua
    """
    now = datetime.now(timezone.utc)

    if variant_type is None:
        variant_type = _infer_variant_type(value)

    # ✅ Создать StatusCode с правильным типом
    if isinstance(status, StatusCode):
        status_code = status
    elif isinstance(status, int):
        status_code = StatusCode(status)
    else:
        status_code = StatusCode(0x00000000)

    return DataValue(
        variant=Variant(value, variant_type),
        status=status_code,
        sourceTimestamp=source_ts or now,
        serverTimestamp=server_ts or now
    )


def _infer_variant_type(value: Any) -> VariantType:
    """Определяет VariantType по значению"""
    if value is None:
        return VariantType.String
    elif isinstance(value, LocalizedText):
        return VariantType.LocalizedText
    elif isinstance(value, str):
        return VariantType.String
    elif isinstance(value, bool):
        return VariantType.Boolean
    elif isinstance(value, int):
        return VariantType.Int32
    elif isinstance(value, float):
        return VariantType.Double
    elif isinstance(value, datetime):
        return VariantType.DateTime
    else:
        return VariantType.String
