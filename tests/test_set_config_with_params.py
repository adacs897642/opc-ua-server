# tests/test_set_config_with_params.py

from asyncua import Client
from asyncua.ua import CallMethodRequest, Variant, VariantType, NodeClass


def main():
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

                            print("🚀 Вызов SET_CONFIG с параметрами...")

                            request = CallMethodRequest()
                            request.ObjectId = commands_nodeid
                            request.MethodId = method_nodeid

                            # ✅ Вводим параметры!
                            request.InputArguments = [
                                Variant("gas_threshold", VariantType.String),  # param_name
                                Variant("25.5", VariantType.String),  # param_value
                                Variant(30, VariantType.Int32)  # timeout
                            ]

                            result = client.uaclient.call([request])

                            if result and len(result) > 0:
                                output = result[0].OutputArguments
                                print(f"✅ result_code: {output[0].Value}")
                                print(f"✅ result_message: {output[1].Value}")

                            # Проверка в БД


    client.disconnect()


if __name__ == '__main__':
    main()