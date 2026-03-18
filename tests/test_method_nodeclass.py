# tests/test_method_nodeclass.py

from opcua import ua, Server
from opcua.ua import NodeClass, Variant, VariantType

def test_handler(method_nodeid, *args):
    return [Variant(0, VariantType.Int32), Variant("OK", VariantType.String)]

server = Server()
server.set_endpoint("opc.tcp://0.0.0.0:4840/")
idx = server.register_namespace("http://test")

objects = server.get_objects_node()
folder = objects.add_object(idx, "Commands")

print(f"Folder NodeClass: {folder.get_node_class()} ({NodeClass(folder.get_node_class()).name})")

# Создаём метод
method = folder.add_method(
    ua.NodeId(0, idx),
    "TEST_METHOD",
    test_handler,
    [],
    []
)

print(f"\nMethod NodeClass: {method.get_node_class()} ({NodeClass(method.get_node_class()).name})")
print(f"Method NodeId: {method.nodeid}")
print(f"Method BrowseName: {method.get_browse_name()}")

if method.get_node_class() == NodeClass.Method:
    print("\n✅ Метод создан корректно!")
else:
    print(f"\n❌ ОШИБКА: Создан {NodeClass(method.get_node_class()).name} вместо Method!")
    print("   Попробуйте: pip install --upgrade opcua")

server.start()