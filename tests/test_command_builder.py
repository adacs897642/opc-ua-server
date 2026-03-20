# tests/test_command_builder.py
# -*- coding: utf-8 -*-
"""
Тест утилиты CommandFileBuilder
"""

import sys
import os

# ✅ ДОБАВИТЬ КОРЕНЬ ПРОЕКТА В PATH
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

print(f"📁 Project root: {PROJECT_ROOT}")
print(f"📁 sys.path: {sys.path[:3]}")

from commands.utils.command_builder import CommandFileBuilder


def test_command_builder():
    """Тестирует CommandFileBuilder"""

    builder = CommandFileBuilder(command_dir='test_commands')

    print("\n🧪 Тест CommandFileBuilder:\n")

    # ✅ Тест 1: Текстовая команда
    print("📝 Тест 1: Текстовая команда (RESET)...")
    cmd1 = builder.build_command(
        sim='79215851634',
        command_code='cmd06',
        command_type='text'
    )
    print(f"   ✅ Файл: {cmd1['filepath']}")
    print(f"   ✅ Данные: {cmd1['command_data']}")

    # ✅ Тест 2: JSON команда с параметрами
    print("\n📝 Тест 2: JSON команда (DIAGNOSTIC)...")
    cmd2 = builder.build_command(
        sim='79215851634',
        command_code='cmd10',
        command_type='json',
        params={'test_level': 3}
    )
    print(f"   ✅ Файл: {cmd2['filepath']}")
    print(f"   ✅ Данные: {cmd2['command_data']}")

    # ✅ Тест 3: Чтение команды
    print("\n📖 Тест 3: Чтение команды...")
    read_cmd = builder.read_command(cmd1['filepath'])
    print(f"   ✅ Прочитано: {read_cmd}")

    # ✅ Тест 4: Отметка как отправленная
    print("\n✅ Тест 4: Отметка как отправленная...")
    builder.mark_command_sent(cmd1['filepath'])

    # ✅ Проверка файлов
    print("\n📁 Тест 5: Проверка файлов...")
    import glob
    files = glob.glob('test_commands/*')
    print(f"   ✅ Создано файлов: {len(files)}")
    for f in files:
        print(f"      - {f}")

    # ✅ Очистка
    print("\n🧹 Очистка...")
    # import shutil
    # if os.path.exists('test_commands'):
    #     shutil.rmtree('test_commands')
    # print("   ✅ Очистка завершена")

    print("\n✅ Тест завершён!")


if __name__ == '__main__':
    test_command_builder()