# tests/test_call_command_direct.py
# -*- coding: utf-8 -*-
"""
Тест прямого вызова команд через OPC UA
"""

import sys
import os

# ✅ Добавить корень проекта в path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from opcua import Client
from opcua.ua import CallMethodRequest, Variant, VariantType, NodeClass


def find_commands_node(client):
    """Находит узел Commands устройства"""
    objects = client.get_objects_node()

    for device in objects.get_children():
        device_name = device.get_browse_name().Name
        if "08П" in device_name or "79215851634" in device_name:
            print(f"📦 Найдено устройство: {device_name}")

            for child in device.get_children():
                if child.get_browse_name().Name == "Commands":
                    return child, device_name

    return None, None


def call_command(client, commands_node, command_name, input_args=None):
    """
    Вызывает команду через OPC UA

    Args:
        client: OPC UA клиент
        commands_node: Узел Commands
        command_name: Имя команды (RESET, REBOOT, etc.)
        input_args: Список аргументов (Variant)

    Returns:
        dict: Результат вызова
    """
    # ✅ Найти метод команды
    method_node = None
    for cmd in commands_node.get_children():
        if cmd.get_browse_name().Name == command_name:
            method_node = cmd
            break

    if not method_node:
        print(f"❌ Команда {command_name} не найдена")
        return None

    print(f"🔘 Найдена команда: {command_name}")
    print(f"   NodeId: {method_node.nodeid}")

    # ✅ Создать запрос
    request = CallMethodRequest()
    request.ObjectId = commands_node.nodeid
    request.MethodId = method_node.nodeid
    request.InputArguments = input_args or []

    # ✅ Вызвать метод
    print(f"\n🚀 Вызов команды {command_name}...")
    result = client.uaclient.call([request])

    if result and len(result) > 0:
        output = result[0].OutputArguments
        print(f"\n✅ Результат:")
        print(f"   result_code: {output[0].Value}")
        print(f"   result_message: {output[1].Value}")

        return {
            'result_code': output[0].Value,
            'result_message': output[1].Value,
            'output': output
        }

    return None


def test_reset_command():
    """Тест команды RESET"""
    print("\n" + "=" * 60)
    print("🧪 ТЕСТ КОМАНДЫ RESET")
    print("=" * 60 + "\n")

    client = Client("opc.tcp://localhost:4840/")

    try:
        client.connect()
        print("✅ Подключено к серверу OPC UA\n")

        # ✅ Найти Commands узел
        commands_node, device_name = find_commands_node(client)

        if not commands_node:
            print("❌ Узел Commands не найден")
            return

        print(f"📁 Commands NodeId: {commands_node.nodeid}\n")

        # ✅ Вызвать RESET (без параметров)
        result = call_command(
            client=client,
            commands_node=commands_node,
            command_name='RESET',
            input_args=[]  # ← ← ← Нет параметров
        )

        if result:
            if result['result_code'] == 0:
                print("\n🎉 КОМАНДА УСПЕШНО ВЫПОЛНЕНА!")
            else:
                print(f"\n⚠️ Команда выполнена с кодом: {result['result_code']}")

        # ✅ Проверить файл команды
        print("\n📁 Проверка файла команды...")
        import glob
        files = glob.glob('device_commands/79215851634.cmd06.*')
        if files:
            print(f"   ✅ Найдено файлов: {len(files)}")
            latest_file = max(files, key=os.path.getctime)
            print(f"   📄 Последний файл: {latest_file}")

            # Показать содержимое
            print(f"\n   📖 Содержимое:")
            with open(latest_file, 'r', encoding='utf-8') as f:
                content = f.read()
                for line in content.split('\n')[:10]:
                    print(f"      {line}")
        else:
            print("   ⚠️ Файлы не найдены в device_commands/")

        # ✅ Проверить очередь в БД
        print("\n📊 Проверка device_command_queue...")
        from db.connection import Database
        from config.loader import ConfigLoader

        config = ConfigLoader('config.json')
        db = Database(config.db_config)

        rows = db.query("""
            SELECT id, sim, command_code, command_type, filepath, status, created_at
            FROM device_command_queue
            WHERE sim = '79215851634'
            ORDER BY created_at DESC
            LIMIT 3
        """)

        if rows:
            print(f"   ✅ Найдено записей: {len(rows)}")
            for row in rows:
                print(f"      ID={row[0]}, cmd={row[2]}, status={row[5]}, time={row[6]}")
        else:
            print("   ⚠️ Записей не найдено")

        db.close()

    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

    finally:
        client.disconnect()
        print("\n🔒 Отключено от сервера")


def test_reboot_command():
    """Тест команды REBOOT"""
    print("\n" + "=" * 60)
    print("🧪 ТЕСТ КОМАНДЫ REBOOT")
    print("=" * 60 + "\n")

    client = Client("opc.tcp://localhost:4840/")

    try:
        client.connect()
        print("✅ Подключено к серверу OPC UA\n")

        commands_node, device_name = find_commands_node(client)

        if not commands_node:
            print("❌ Узел Commands не найден")
            return

        # ✅ Вызвать REBOOT (без параметров)
        result = call_command(
            client=client,
            commands_node=commands_node,
            command_name='REBOOT',
            input_args=[]
        )

        if result and result['result_code'] == 0:
            print("\n🎉 КОМАНДА REBOOT УСПЕШНО ВЫПОЛНЕНА!")

    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
    finally:
        client.disconnect()


def test_diagnostic_command():
    """Тест команды DIAGNOSTIC (с параметрами)"""
    print("\n" + "=" * 60)
    print("🧪 ТЕСТ КОМАНДЫ DIAGNOSTIC")
    print("=" * 60 + "\n")

    client = Client("opc.tcp://localhost:4840/")

    try:
        client.connect()
        print("✅ Подключено к серверу OPC UA\n")

        commands_node, device_name = find_commands_node(client)

        if not commands_node:
            print("❌ Узел Commands не найден")
            return

        # ✅ Вызвать DIAGNOSTIC (с параметром test_level)
        result = call_command(
            client=client,
            commands_node=commands_node,
            command_name='DIAGNOSTIC',
            input_args=[
                Variant(3, VariantType.Int32)  # test_level = 3
            ]
        )

        if result and result['result_code'] == 0:
            print("\n🎉 КОМАНДА DIAGNOSTIC УСПЕШНО ВЫПОЛНЕНА!")

    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
    finally:
        client.disconnect()


def main():
    """Запуск всех тестов"""
    print("\n" + "=" * 60)
    print("🧪 ТЕСТИРОВАНИЕ ВЫЗОВА КОМАНД OPC UA")
    print("=" * 60 + "\n")

    # ✅ Тест 1: RESET
    test_reset_command()

    # ✅ Тест 2: REBOOT
    input("\nНажмите Enter для теста REBOOT...")
    test_reboot_command()

    # ✅ Тест 3: DIAGNOSTIC
    input("\nНажмите Enter для теста DIAGNOSTIC...")
    test_diagnostic_command()

    print("\n" + "=" * 60)
    print("✅ ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ")
    print("=" * 60 + "\n")


if __name__ == '__main__':
    # ✅ Запустить только RESET по умолчанию
    test_reset_command()

    # ✅ Или все тесты:
    # main()