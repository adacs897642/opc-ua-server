# tests/test_call_command_direct.py (ОБНОВЛЕНО)
# -*- coding: utf-8 -*-
"""
Тест вызова команды через низкий уровень UA (с извлечением результата)
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
        device_name = device.get_browse_name().Name
        if "08П" in device_name or "Переход" in device_name:
            print(f"📦 Найдено устройство: {device_name}")

            # Находим Commands
            for child in device.get_children():
                if child.get_browse_name().Name == "Commands":
                    commands_node = child
                    commands_nodeid = child.nodeid
                    print(f"📁 Найдена папка Commands: {commands_nodeid}")

                    # Находим метод CLEAR_ALARM
                    for cmd in child.get_children():
                        cmd_name = cmd.get_browse_name().Name
                        cmd_class = cmd.get_node_class()

                        if cmd_name == "CLEAR_ALARM" and cmd_class == NodeClass.Method:
                            method_nodeid = cmd.nodeid
                            print(f"\n🔘 Найдена команда: {cmd_name}")
                            print(f"   ObjectId (папка): {commands_nodeid}")
                            print(f"   MethodId (метод): {method_nodeid}")

                            # ✅ ВЫЗОВ ЧЕРЕЗ CallMethodRequest
                            print(f"\n🚀 Вызов через CallMethodRequest...")

                            try:
                                # Создаём запрос
                                request = CallMethodRequest()
                                request.ObjectId = commands_nodeid
                                request.MethodId = method_nodeid
                                request.InputArguments = []

                                print(f"   ObjectId: {request.ObjectId}")
                                print(f"   MethodId: {request.MethodId}")

                                # Вызываем
                                result = client.uaclient.call([request])

                                # ✅ ИЗВЛЕКАЕМ РЕЗУЛЬТАТ
                                print(f"\n📊 Результат вызова:")
                                if result and len(result) > 0:
                                    call_result = result[0]

                                    # StatusCode
                                    status_code = call_result.StatusCode
                                    print(f"   StatusCode: {status_code}")

                                    # OutputArguments
                                    output_args = call_result.OutputArguments
                                    print(f"   OutputArguments: {output_args}")

                                    if output_args and len(output_args) >= 2:
                                        result_code = output_args[0].Value if hasattr(output_args[0], 'Value') else \
                                        output_args[0]
                                        result_message = output_args[1].Value if hasattr(output_args[1], 'Value') else \
                                        output_args[1]

                                        print(f"\n   ✅ result_code: {result_code}")
                                        print(f"   ✅ result_message: {result_message}")

                                        if result_code == 0:
                                            print(f"\n   🎉 КОМАНДА УСПЕШНО ВЫПОЛНЕНА!")
                                        else:
                                            print(f"\n   ⚠️ Команда вернула код ошибки: {result_code}")
                                    else:
                                        print(f"   ⚠️ Нет выходных аргументов")
                                else:
                                    print(f"   ⚠️ Пустой результат")


                            except Exception as e:
                                print(f"❌ Ошибка: {e}")
                                import traceback
                                traceback.print_exc()

                            client.disconnect()
                            return

    print("❌ Команда CLEAR_ALARM не найдена!")
    client.disconnect()


if __name__ == '__main__':
    main()