# tests/test_phone_validation.py
# -*- coding: utf-8 -*-
"""
Тест валидации телефонных номеров
"""

from opcua import Client
from opcua.ua import CallMethodRequest, Variant, VariantType, NodeClass


def test_phone_validation():
    client = Client("opc.tcp://localhost:4840/")
    client.connect()

    objects = client.get_objects_node()

    for device in objects.get_children():
        if "08П" in device.get_browse_name().Name:
            for child in device.get_children():
                if child.get_browse_name().Name == "Commands":
                    commands_node = child
                    commands_nodeid = child.nodeid

                    for cmd in child.get_children():
                        if cmd.get_browse_name().Name == "SET_CONFIG":
                            method_nodeid = cmd.nodeid

                            # Тест 1: Валидный номер (79101234567)
                            print("🧪 Тест 1: contact_phone=79101234567...")
                            request = CallMethodRequest()
                            request.ObjectId = commands_nodeid
                            request.MethodId = method_nodeid
                            request.InputArguments = [
                                Variant("P1", VariantType.String),
                                Variant("79101234567", VariantType.String),
                                Variant(30, VariantType.Int32)
                            ]

                            result = client.uaclient.call([request])
                            output = result[0].OutputArguments
                            print(f"   result_code: {output[0].Value}")
                            print(f"   result_message: {output[1].Value}")
                            print()

                            # Тест 2: Невалидный номер (слишком короткий)
                            print("🧪 Тест 2: contact_phone=12345 (короткий)...")
                            request.InputArguments = [
                                Variant("contact_phone", VariantType.String),
                                Variant("12345", VariantType.String),
                                Variant(30, VariantType.Int32)
                            ]

                            result = client.uaclient.call([request])
                            output = result[0].OutputArguments
                            print(f"   result_code: {output[0].Value}")
                            print(f"   result_message: {output[1].Value}")

                            if output[0].Value == -2:
                                print("   ✅ ВАЛИДАЦИЯ ТЕЛЕФОНА РАБОТАЕТ!")
                            print()

                            # Тест 3: Номер с форматированием
                            print("🧪 Тест 3: contact_phone=+7 (910) 123-45-67...")
                            request.InputArguments = [
                                Variant("P1", VariantType.String),
                                Variant("+7 (910) 123-45-67", VariantType.String),
                                Variant(30, VariantType.Int32)
                            ]

                            result = client.uaclient.call([request])
                            output = result[0].OutputArguments
                            print(f"   result_code: {output[0].Value}")
                            print(f"   result_message: {output[1].Value}")
                            print()

                            client.disconnect()
                            return

    client.disconnect()


if __name__ == '__main__':
    test_phone_validation()