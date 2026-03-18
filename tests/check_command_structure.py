# tests/check_command_structure.py

from opcua import Client
from opcua.ua import NodeClass  # ← ← ← Используем константы!

client = Client("opc.tcp://localhost:4840/")
client.connect()

print("🔍 Проверка структуры команд...\n")

objects = client.get_objects_node()

for device in objects.get_children():
    browse_name = device.get_browse_name().Name
    print(f"\n📦 Устройство: {browse_name} ({device.nodeid})")

    for child in device.get_children():
        child_name = child.get_browse_name().Name
        child_class = child.get_node_class()

        print(f"   └── {child_name} (Class: {child_class} - {NodeClass(child_class).name})")

        if child_name == "Commands":
            print(f"       └── Commands NodeId: {child.nodeid}")

            try:
                commands_children = child.get_children()
                print(f"       └── Найдено детей: {len(commands_children)}")

                for cmd in commands_children:
                    cmd_name = cmd.get_browse_name().Name
                    cmd_class = cmd.get_node_class()
                    cmd_nodeid = cmd.nodeid

                    print(f"           ├── {cmd_name}")
                    print(f"           │   ├── NodeId: {cmd_nodeid}")
                    print(f"           │   └── NodeClass: {cmd_class} ({NodeClass(cmd_class).name})")

                    # ✅ ПРАВИЛЬНАЯ ПРОВЕРКА:
                    if cmd_class == NodeClass.Method:  # ← ← ← Не 8, а NodeClass.Method!
                        print(f"           │   └── ✅ Это МЕТОД!")
                    else:
                        print(f"           │   └── ❌ Это НЕ метод!")

            except Exception as e:
                print(f"       └── Ошибка получения детей: {e}")

client.disconnect()