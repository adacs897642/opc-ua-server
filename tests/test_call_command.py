# tests/test_call_command.py
# -*- coding: utf-8 -*-
"""
Тест вызова команды через Python-клиент (ИСПРАВЛЕНО)
"""

from opcua import Client
from opcua.ua import Variant, VariantType, NodeClass


def main():
    # Подключаемся к серверу
    client = Client("opc.tcp://localhost:4840/")
    client.connect()

    print("✅ Подключено к серверу\n")

    # Находим устройство
    objects = client.get_objects_node()

    for device in objects.get_children():
        device_name = device.get_browse_name().Name
        if "Переход" in device_name or "08П" in device_name:
            print(f"📦 Найдено устройство: {device_name}")

            # Находим Commands
            for child in device.get_children():
                if child.get_browse_name().Name == "Commands":
                    print(f"📁 Найдена папка Commands")

                    # Находим метод CLEAR_ALARM
                    for cmd in child.get_children():
                        cmd_name = cmd.get_browse_name().Name
                        cmd_class = cmd.get_node_class()

                        if cmd_name == "CLEAR_ALARM":
                            print(f"\n🔘 Найдена команда: {cmd_name}")
                            print(f"   NodeId: {cmd.nodeid}")
                            print(f"   NodeClass: {cmd_class} ({NodeClass(cmd_class).name})")

                            # ✅ ПРАВИЛЬНЫЙ ВЫЗОВ МЕТОДА (без аргументов!)
                            print(f"\n🚀 Вызов метода CLEAR_ALARM...")

                            try:
                                # Вариант 1: Вызвать без аргументов (для методов без input)
                                result = cmd.call_method()

                                print(f"✅ Результат (вариант 1): {result}")

                            except Exception as e1:
                                print(f"⚠️ Вариант 1 не сработал: {e1}")

                                try:
                                    # Вариант 2: Передать NodeId метода явно
                                    result = cmd.call_method(cmd.nodeid)
                                    print(f"✅ Результат (вариант 2): {result}")

                                except Exception as e2:
                                    print(f"⚠️ Вариант 2 не сработал: {e2}")

                                    # Вариант 3: Использовать server.call_method()
                                    try:
                                        result = client.call_method(cmd.nodeid)
                                        print(f"✅ Результат (вариант 3): {result}")
                                    except Exception as e3:
                                        print(f"❌ Все варианты не сработали: {e3}")




                            return

    print("❌ Команда CLEAR_ALARM не найдена!")
    client.disconnect()


if __name__ == '__main__':
    main()