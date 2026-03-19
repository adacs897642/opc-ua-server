# tests/test_command_with_params.py
# -*- coding: utf-8 -*-
"""
Тест вызова команды с параметрами
"""

from opcua import Client
from opcua.ua import CallMethodRequest, Variant, VariantType, NodeClass


def main():
    client = Client("opc.tcp://localhost:4840/")
    client.connect()

    print("✅ Подключено к серверу\n")

    # Находим устройство
    objects = client.get_objects_node()

    for device in objects.get_children():
        if "08П" in device.get_browse_name().Name:
            print(f"📦 Найдено устройство: {device.get_browse_name().Name}")

            # Находим Commands
            for child in device.get_children():
                if child.get_browse_name().Name == "Commands":
                    commands_node = child
                    commands_nodeid = child.nodeid

                    # Находим SET_CONFIG
                    for cmd in child.get_children():
                        if cmd.get_browse_name().Name == "SET_CONFIG":
                            method_nodeid = cmd.nodeid

                            print(f"\n🔘 Найдена команда: SET_CONFIG")
                            print(f"   ObjectId: {commands_nodeid}")
                            print(f"   MethodId: {method_nodeid}")

                            # ✅ ВЫЗОВ С ПАРАМЕТРАМИ
                            print(f"\n🚀 Вызов с параметрами...")

                            request = CallMethodRequest()
                            request.ObjectId = commands_nodeid
                            request.MethodId = method_nodeid

                            # ✅ Входные аргументы (должны соответствовать param_schema!)
                            request.InputArguments = [
                                Variant("gas_threshold", VariantType.String),  # param_name
                                Variant("25.5", VariantType.String),  # param_value
                                Variant(30, VariantType.Int32)  # timeout
                            ]

                            print(f"   Параметры:")
                            print(f"      param_name: gas_threshold")
                            print(f"      param_value: 25.5")
                            print(f"      timeout: 30")

                            # Вызываем
                            result = client.uaclient.call([request])

                            # Извлекаем результат
                            if result and len(result) > 0:
                                call_result = result[0]
                                output_args = call_result.OutputArguments

                                if output_args and len(output_args) >= 2:
                                    result_code = output_args[0].Value
                                    result_message = output_args[1].Value

                                    print(f"\n✅ result_code: {result_code}")
                                    print(f"✅ result_message: {result_message}")

                                    if result_code == 0:
                                        print(f"\n🎉 КОМАНДА УСПЕШНО ВЫПОЛНЕНА!")
                                    else:
                                        print(f"\n⚠️ Код ошибки: {result_code}")

                            return

    print("❌ Команда не найдена!")
    client.disconnect()


if __name__ == '__main__':
    main()