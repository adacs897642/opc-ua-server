# tests/test_method_arguments.py
# -*- coding: utf-8 -*-
"""
Проверка Input/Output Arguments метода (исправлено для python-opcua 0.98.13)
"""

from opcua import Client
from opcua.ua import NodeClass, NodeId, ObjectIds


def main():
    client = Client("opc.tcp://localhost:4840/")
    client.connect()

    print("✅ Подключено к серверу\n")

    objects = client.get_objects_node()

    for device in objects.get_children():
        if "08П" in device.get_browse_name().Name:
            print(f"📦 Устройство: {device.get_browse_name().Name}")

            for child in device.get_children():
                if child.get_browse_name().Name == "Commands":
                    print(f"📁 Commands NodeId: {child.nodeid}\n")

                    for cmd in child.get_children():
                        cmd_name = cmd.get_browse_name().Name
                        cmd_class = cmd.get_node_class()
                        cmd_nodeid = cmd.nodeid

                        if cmd_class == NodeClass.Method:
                            print(f"🔘 Метод: {cmd_name}")
                            print(f"   NodeId: {cmd_nodeid}")

                            # ✅ ЧИТАЕМ ЧЕРЕЗ Дочерние узлы (не атрибуты!)
                            children = cmd.get_children()

                            input_args = []
                            output_args = []

                            for c in children:
                                c_name = c.get_browse_name().Name
                                c_nodeid = c.nodeid

                                # InputArguments и OutputArguments — это переменные-метаданные
                                if c_name == "InputArguments":
                                    try:
                                        val = c.get_value()
                                        input_args = val if val else []
                                        print(f"   ✅ InputArguments: {len(input_args)}")
                                        for i, arg in enumerate(input_args):
                                            print(f"      [{i}] {arg.Name}: DataType={arg.DataType}")
                                    except Exception as e:
                                        print(f"   ⚠️ InputArguments: Ошибка чтения: {e}")

                                elif c_name == "OutputArguments":
                                    try:
                                        val = c.get_value()
                                        output_args = val if val else []
                                        print(f"   ✅ OutputArguments: {len(output_args)}")
                                        for i, arg in enumerate(output_args):
                                            print(f"      [{i}] {arg.Name}: DataType={arg.DataType}")
                                    except Exception as e:
                                        print(f"   ⚠️ OutputArguments: Ошибка чтения: {e}")

                            # Если аргументы не найдены
                            if not input_args and not output_args:
                                print(f"   ⚠️ Аргументы не найдены в дочерних узлах")
                                print(f"   📋 Дочерние узлы ({len(children)}):")
                                for c in children:
                                    print(f"      - {c.get_browse_name().Name} ({c.nodeid})")

                            print()

    client.disconnect()


if __name__ == '__main__':
    main()