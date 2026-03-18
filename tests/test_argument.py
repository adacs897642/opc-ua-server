# test_argument.py

from opcua import ua
import inspect

# Проверка сигнатуры Argument
print("Параметры ua.Argument:")
sig = inspect.signature(ua.Argument)
print(sig)

# Проверка доступных атрибутов
arg = ua.Argument()
print("\nАтрибуты Argument:")
for attr in dir(arg):
    if not attr.startswith('_'):
        print(f"  {attr}")