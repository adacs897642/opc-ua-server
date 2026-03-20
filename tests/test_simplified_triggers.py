# tests/test_simplified_triggers.py
# -*- coding: utf-8 -*-
"""
Тест упрощённых триггерных функций
"""

from db.connection import Database
from config.loader import ConfigLoader
import time


def test_simplified_triggers():
    config = ConfigLoader('config.json')
    db = Database(config.db_config)

    print("\n🧪 Тест упрощённых триггеров:\n")

    # ✅ 1. Вставка нового значения
    print("📝 Вставка тестового значения...")
    db.execute("""
        INSERT INTO pvalues (alias, name, time, value, units, valid, msg)
        VALUES ('test_param', 'Тест', now(), '100', 'ед.', true, 'test')
        ON CONFLICT (alias) DO UPDATE
            SET value = EXCLUDED.value,
                time = EXCLUDED.time
    """)
    print("   ✅ Значение вставлено")

    time.sleep(0.1)  # Ждём срабатывания триггеров

    # ✅ 2. Проверка pvaluesM1
    print("\n📊 Проверка pvaluesM1...")
    rows = db.query("""
        SELECT alias, time, value, valid 
        FROM pvaluesM1 
        WHERE alias = 'test_param'
    """)
    if rows:
        print(f"   ✅ pvaluesM1: {rows[0]}")
    else:
        print("   ❌ pvaluesM1 пусто!")

    # ✅ 3. Проверка pvalues_log
    print("\n📊 Проверка pvalues_log...")
    rows = db.query("""
        SELECT alias, time, value, grad, valid 
        FROM pvalues_log 
        WHERE alias = 'test_param'
        ORDER BY time DESC
        LIMIT 1
    """)
    if rows:
        print(f"   ✅ pvalues_log: {rows[0]}")
    else:
        print("   ❌ pvalues_log пусто!")

    # ✅ 4. Обновление значения (проверка градиента)
    print("\n📝 Обновление значения...")
    db.execute("""
        INSERT INTO pvalues (alias, name, time, value, units, valid, msg)
        VALUES ('test_param', 'Тест', now(), '150', 'ед.', true, 'test')
        ON CONFLICT (alias) DO UPDATE
            SET value = EXCLUDED.value,
                time = EXCLUDED.time
    """)

    time.sleep(0.1)

    # ✅ 5. Проверка градиента
    print("\n📊 Проверка градиента...")
    rows = db.query("""
        SELECT alias, value, grad 
        FROM pvalues_log 
        WHERE alias = 'test_param'
        ORDER BY time DESC
        LIMIT 2
    """)
    if rows and len(rows) >= 2:
        print(f"   ✅ Предыдущее: {rows[1]}")
        print(f"   ✅ Текущее: {rows[0]}")
        print(f"   ✅ Градиент: {rows[0][2]} (ожидалось ~50)")

    # ✅ Очистка
    print("\n🧹 Очистка тестовых данных...")
    db.execute("DELETE FROM pvalues WHERE alias = 'test_param'")
    db.execute("DELETE FROM pvaluesM1 WHERE alias = 'test_param'")
    db.execute("DELETE FROM pvalues_log WHERE alias = 'test_param'")
    print("   ✅ Очистка завершена")

    print("\n✅ Тест завершён!")

    db.close()


if __name__ == '__main__':
    test_simplified_triggers()