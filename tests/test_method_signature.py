# tests/test_method_signature.py

from opcua import ua, Server
from opcua.ua import Variant, VariantType, LocalizedText


def create_argument(name, data_type, description=''):
    """Создаёт Argument через атрибуты (работает во всех версиях!)"""
    arg = ua.Argument()
    arg.Name = name
    arg.DataType = data_type
    arg.ValueRank = -1
    arg.ArrayDimensions = []
    arg.Description = LocalizedText(description)
    return arg


# ✅ Сигнатура для вашей версии библиотеки
def test_handler(method_nodeid, *args):
    """Тестовый обработчик метода"""
    print(f"method_nodeid: {method_nodeid}")
    print(f"args: {args}")
    print(f"args types: {[type(arg) for arg in args]}")
    return [
        Variant(0, VariantType.Int32),
        Variant("OK", VariantType.String)
    ]


# Создаём сервер
server = Server()
server.set_endpoint("opc.tcp://0.0.0.0:4840/")
idx = server.register_namespace("http://test")

# Создаём объект
objects = server.get_objects_node()
obj = objects.add_object(idx, "TestObject")

# ✅ Создаём аргументы через функцию
input_args = []  # Нет входных аргументов для REBOOT

output_args = [
    create_argument("result_code", ua.NodeId(ua.ObjectIds.Int32), "Код результата"),
    create_argument("result_message", ua.NodeId(ua.ObjectIds.String), "Сообщение")
]

# Добавляем метод
method = obj.add_method(
    idx,
    "TestMethod",
    test_handler,  # ← Обработчик
    input_args,
    output_args
)

print("✅ Метод создан успешно!")
print("Запустите сервер и проверьте вызов в UaExpert")

server.start()