# tests/test_minimal_method.py
# -*- coding: utf-8 -*-
"""
Минимальный тест создания метода для opcua==0.98.13
"""

from opcua import ua, Server
from opcua.ua import NodeClass, Variant, VariantType, LocalizedText


def minimal_handler(method_nodeid, *args):
    """Минимальный обработчик метода"""
    print(f"✅ Метод вызван! NodeId: {method_nodeid}, args: {args}")
    return [
        Variant(0, VariantType.Int32),
        Variant("OK", VariantType.String)
    ]


def main():
    # Создаём сервер
    server = Server()
    server.set_endpoint("opc.tcp://0.0.0.0:4840/")
    idx = server.register_namespace("http://test")

    # Создаём объект и папку
    objects = server.get_objects_node()
    device = objects.add_object(idx, "TestDevice")
    commands = device.add_object(idx, "Commands")

    print(f"📁 Commands NodeClass: {commands.get_node_class()} ({NodeClass(commands.get_node_class()).name})")

    # ✅ Создаём метод через add_method() (правильная сигнатура для 0.98.13)
    method = commands.add_method(
        ua.NodeId(0, idx),  # NodeId (0 = авто)
        ua.QualifiedName("TEST_CMD", idx),  # BrowseName с правильным namespace
        minimal_handler,  # Callback
        [],  # Input arguments
        []  # Output arguments
    )

    # 🔍 Проверяем что создалось
    print(f"\n📝 Метод создан:")
    print(f"   NodeId: {method.nodeid}")
    print(f"   BrowseName: {method.get_browse_name()}")
    print(f"   NodeClass: {method.get_node_class()} ({NodeClass(method.get_node_class()).name})")

    # 🔍 Проверяем через get_children()
    children = commands.get_children()
    print(f"\n📋 Дети Commands ({len(children)}):")
    for child in children:
        print(f"   ├── {child.get_browse_name().Name}")
        print(f"   │   ├── NodeId: {child.nodeid}")
        print(f"   │   └── NodeClass: {child.get_node_class()} ({NodeClass(child.get_node_class()).name})")

    # ✅ Если всё хорошо — запускаем сервер
    if method.get_node_class() == NodeClass.Method:
        print(f"\n✅ Тест ПРОЙДЕН! Метод создан корректно.")
        print(f"🚀 Запускаю сервер на opc.tcp://0.0.0.0:4840/")
        server.start()
    else:
        print(f"\n❌ Тест НЕ ПРОЙДЕН! Создан {NodeClass(method.get_node_class()).name} вместо Method.")
        print(f"💡 Попробуйте: pip install --force-reinstall opcua==0.98.13")


if __name__ == '__main__':
    main()