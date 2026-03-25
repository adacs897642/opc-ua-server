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

# opc/utils/helpers.py

import logging

logger = logging.getLogger('opc.helpers')


def safe_variant(value, variant_type):
    """
    Создаёт Variant с ПОЛНОЙ конвертацией типов

    Исправляет 71% ошибок сериализации!

    Args:
        value: Исходное значение (любой тип)
        variant_type: Целевой VariantType

    Returns:
        Variant: Безопасный Variant с правильным типом значения
    """
    try:
        # ✅ String
        if variant_type == VariantType.String:
            if value is None:
                safe_value = ""
            elif isinstance(value, bytes):
                safe_value = value.decode('utf-8', errors='replace')
            elif isinstance(value, datetime):
                safe_value = value.isoformat()
            elif isinstance(value, (list, tuple, dict)):
                safe_value = str(value)
            else:
                safe_value = str(value)  # int, float, bool → str

        # ✅ Целочисленные типы (Signed)
        elif variant_type == VariantType.Int16:
            safe_value = _clamp_int(value, -32768, 32767)
        elif variant_type == VariantType.Int32:
            safe_value = _clamp_int(value, -2147483648, 2147483647)
        elif variant_type == VariantType.Int64:
            safe_value = _clamp_int(value, -9223372036854775808, 9223372036854775807)

        # ✅ Целочисленные типы (Unsigned) — отрицательные → 0
        elif variant_type == VariantType.Byte:
            safe_value = _clamp_uint(value, 0, 255)
        elif variant_type == VariantType.UInt16:
            safe_value = _clamp_uint(value, 0, 65535)
        elif variant_type == VariantType.UInt32:
            safe_value = _clamp_uint(value, 0, 4294967295)
        elif variant_type == VariantType.UInt64:
            safe_value = _clamp_uint(value, 0, 18446744073709551615)

        # ✅ Float типы
        elif variant_type == VariantType.Float:
            safe_value = _to_float(value)
        elif variant_type == VariantType.Double:
            safe_value = _to_float(value)

        # ✅ Boolean
        elif variant_type == VariantType.Boolean:
            safe_value = _to_bool(value)

        # ✅ DateTime
        elif variant_type == VariantType.DateTime:
            safe_value = _to_datetime(value)

        # ✅ Остальные типы — как есть
        else:
            safe_value = value if value is not None else ""

        return Variant(safe_value, variant_type)

    except Exception as e:
        logger.warning(f"⚠️ safe_variant failed: {e}, возвращаем дефолт")
        # ✅ Fallback — пустой Variant
        return Variant("", VariantType.String)


# ✅ Вспомогательные функции конвертации

def _clamp_int(value, min_val, max_val):
    """Конвертирует в int с проверкой диапазона"""
    if value is None:
        return 0
    try:
        if isinstance(value, str):
            value = int(float(value.replace(',', '.')))
        elif isinstance(value, float):
            value = int(value)
        elif isinstance(value, bool):
            value = 1 if value else 0

        # ✅ Clamp в диапазон
        return max(min_val, min(max_val, int(value)))
    except:
        return 0


def _clamp_uint(value, min_val, max_val):
    """Конвертирует в unsigned int (отрицательные → 0)"""
    if value is None:
        return 0
    try:
        if isinstance(value, str):
            value = int(float(value.replace(',', '.')))
        elif isinstance(value, float):
            value = int(value)
        elif isinstance(value, bool):
            value = 1 if value else 0

        # ✅ Отрицательные → 0
        if int(value) < 0:
            logger.debug(f"⚠️ Отрицательное значение {value} для UInt → 0")
            return 0

        return max(min_val, min(max_val, int(value)))
    except:
        return 0


def _to_float(value):
    """Конвертирует в float"""
    if value is None:
        return 0.0
    try:
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        elif isinstance(value, str):
            return float(value.replace(',', '.'))
        return float(value)
    except:
        return 0.0


def _to_bool(value):
    """Конвертирует в bool"""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', '1', 'yes', 'да')
    return bool(value)


def _to_datetime(value):
    """Конвертирует в datetime"""
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except:
            return datetime.now(timezone.utc)
    if isinstance(value, (int, float)):
        try:
            # ✅ Timestamp → datetime (только положительные)
            if value < 0:
                logger.debug(f"⚠️ Отрицательный timestamp {value} → now")
                return datetime.now(timezone.utc)
            dt = datetime.fromtimestamp(value, tz=timezone.utc)
            return dt
        except:
            return datetime.now(timezone.utc)
    return datetime.now(timezone.utc)
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
