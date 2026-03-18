# test_status_codes_available.py

from opcua.ua import StatusCodes

# Проверка что доступно
print("Доступные StatusCodes:")
for attr in dir(StatusCodes):
    if not attr.startswith('_'):
        print(f"  {attr} = {getattr(StatusCodes, attr)}")

# Проверка конкретных кодов
print("\nПроверка кодов:")
print(f"Good: {StatusCodes.Good}")
print(f"Bad: {StatusCodes.Bad}")
print(f"Uncertain: {StatusCodes.Uncertain}")

# Проверка есть ли Uncertain_LastUsableValue
if hasattr(StatusCodes, 'Uncertain_LastUsableValue'):
    print(f"Uncertain_LastUsableValue: {StatusCodes.Uncertain_LastUsableValue}")
else:
    print("❌ Uncertain_LastUsableValue НЕ доступен")
    print("✅ Используйте числовое значение: 0x40000004")