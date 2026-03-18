# tests/test_command_nodeids.py
# -*- coding: utf-8 -*-
"""
Проверка NodeId методов команд
"""

from opcua import Client
from opcua.ua import NodeClass


def main():
    client = Client("opc.tcp://localhost:4840/")
    client.connect()
    print("✅ Подключено\n")

    objects = client.get_objects_node()

    for device in objects.get_children():
        device_name = device.get_browse_name().Name
        if "ПР" in device_name or "Переход" in device_name:
            print(f"📦 Устройство: {device_name}")

            for child in device.get_children():
                if child.get_browse_name().Name == "Commands":
                    print(f"📁 Commands NodeId: {child.nodeid}")

                    for cmd in child.get_children():
                        cmd_name = cmd.get_browse_name().Name
                        cmd_class = cmd.get_node_class()
                        cmd_nodeid = cmd.nodeid

                        if cmd_class == NodeClass.Method:
                            print(f"   ✅ {cmd_name}: NodeId={cmd_nodeid}")
                        else:
                            print(f"   ❌ {cmd_name}: NodeClass={cmd_class} (не метод!)")

                    print()

    client.disconnect()


if __name__ == '__main__':
    main()