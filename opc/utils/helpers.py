# opc/utils/helpers.py

from opcua.ua import Variant, VariantType, NodeId, ObjectIds


def safe_variant(value, type_hint):
    """
    Создаёт Variant с автоматической конвертацией NodeId → VariantType
    """
    # Если NodeId — конвертируем
    if isinstance(type_hint, NodeId):
        mapping = {
            ObjectIds.String: VariantType.String,
            ObjectIds.Int32: VariantType.Int32,
            ObjectIds.Int64: VariantType.Int64,
            ObjectIds.Double: VariantType.Double,
            ObjectIds.Float: VariantType.Float,
            ObjectIds.Boolean: VariantType.Boolean,
            ObjectIds.DateTime: VariantType.DateTime,
            ObjectIds.Byte: VariantType.Byte,
        }
        type_hint = mapping.get(type_hint.Identifier, VariantType.String)

    return Variant(value, type_hint)