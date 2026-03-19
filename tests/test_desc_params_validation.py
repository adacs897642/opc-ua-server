# tests/test_desc_params_validation.py
# -*- coding: utf-8 -*-
"""
Тест валидации параметров из desc_params
"""

from opcua import Client
from opcua.ua import CallMethodRequest, Variant, VariantType, NodeClass


def test_validation_with_desc_params():
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

                            # Тест 1: Значение в диапазоне (должно пройти)
                            print("🧪 Тест 1: gas_threshold=50 (в диапазоне 0-100)...")
                            request = CallMethodRequest()
                            request.ObjectId = commands_nodeid
                            request.MethodId = method_nodeid
                            request.InputArguments = [
                                Variant("gas_threshold", VariantType.String),
                                Variant("50", VariantType.String),
                                Variant(30, VariantType.Int32)
                            ]

                            result = client.uaclient.call([request])
                            output = result[0].OutputArguments
                            print(f"   result_code: {output[0].Value}")
                            print(f"   result_message: {output[1].Value}")
                            print()

                            # Тест 2: Значение вне диапазона (должна быть ошибка)
                            print("🧪 Тест 2: gas_threshold=150 (вне диапазона 0-100)...")
                            request.InputArguments = [
                                Variant("gas_threshold", VariantType.String),
                                Variant("150", VariantType.String),
                                Variant(30, VariantType.Int32)
                            ]

                            result = client.uaclient.call([request])
                            output = result[0].OutputArguments
                            print(f"   result_code: {output[0].Value}")
                            print(f"   result_message: {output[1].Value}")

                            if output[0].Value == -2:
                                print("   ✅ ВАЛИДАЦИЯ ДИАПАЗОНА РАБОТАЕТ!")
                            else:
                                print("   ❌ Ожидается код -2")
                            print()

                            # Тест 3: Другой параметр
                            print("🧪 Тест 3: pressure_limit=500 (в диапазоне 0-1000)...")
                            request.InputArguments = [
                                Variant("pressure_limit", VariantType.String),
                                Variant("500", VariantType.String),
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
    test_validation_with_desc_params()