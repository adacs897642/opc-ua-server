#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OPC UA Server — точка входа
"""

import sys
import argparse
import logging
from core.app import OPCApp
from utils.logging_config import setup_logging


# Уменьшить уровень логирования для OPC UA (если слишком много сообщений)
#logging.getLogger('opcua.server.uaprocessor').setLevel(logging.WARNING)

# Или увеличить для отладки
logging.getLogger('opcua.server.uaprocessor').setLevel(logging.DEBUG)

# Настройка для всех OPC UA компонентов
logging.getLogger('opcua').setLevel(logging.INFO)


def main():
    # ✅ Настройка парсера аргументов
    parser = argparse.ArgumentParser(description='OPC UA Server')

    parser.add_argument(
        'config',
        nargs='?',  # ← ← ← Опциональный позиционный аргумент
        default='config.json',
        help='Путь к файлу конфигурации (по умолчанию: config.json)'
    )

    parser.add_argument(
        '--migrate-opc-params',
        action='store_true',
        help='Выполнить миграцию параметров из opc_params'
    )

    parser.add_argument(
        '--migrate-schema',
        action='store_true',
        help='Выполнить миграцию схемы БД'
    )

    parser.add_argument(
        '--check-schema',
        action='store_true',
        help='Проверить схему БД и выйти'
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Включить debug логирование'
    )

    args = parser.parse_args()

    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )

    logger = logging.getLogger('main')

    # ✅ Выполнить миграции если указано
    if args.migrate_opc_params:
        logger.info("📈 Запуск миграции opc_params...")
        from db.migrations.generate_opc_params import OpcParamsGenerator
        from config.loader import ConfigLoader
        from db.connection import Database
        config = ConfigLoader(args.config)
        db = Database(config.db_config)

        OpcParamsGenerator(db)

        logger.info("✅ Миграция завершена успешно")
        return 0  # ← ← ← Выйти после миграции!

    if args.migrate_schema:
        logger.info("📈 Запуск миграции схемы...")
        from db.migrations.generate_opc_params import OpcParamsGenerator
        from config.loader import ConfigLoader
        from db.connection import Database

        config = ConfigLoader(args.config)
        db = Database(config.db_config)

        OpcParamsGenerator(db)

        logger.info("✅ Миграция схемы завершена")
        return 0

    if args.check_schema:
        logger.info("🔍 Проверка схемы БД...")
        from db.connection import Database
        from config.loader import ConfigLoader

        config = ConfigLoader(args.config)
        db = Database(config.db_config)

        report = db.validate_schema(auto_fix=False)

        if report.get('is_valid'):
            logger.info("✅ Схема валидна")
            return 0
        else:
            logger.error("❌ Схема не валидна")
            return 1

    config_path = sys.argv[1] if len(sys.argv) > 1 else 'config.json'

    try:
        # Настройка логирования (до загрузки приложения)
        setup_logging(config_path)
        logger = logging.getLogger('opc_server')

        logger.info(f"Запуск OPC UA Server")
        logger.info(f"Конфигурация: {config_path}")

        # ✅ Включить отладочное логирование библиотеки opcua
        # logging.getLogger('opcua').setLevel(logging.DEBUG)
        # logging.getLogger('opcua.server').setLevel(logging.DEBUG)
        # logging.getLogger('opcua.server.binary_server_asyncio').setLevel(logging.DEBUG)

        # Инициализация и запуск приложения
        app = OPCApp(config_path)
        # ✅ Запустить асинхронный метод через asyncio.run()
        app.run()

        return 0

    except FileNotFoundError as e:
        logging.critical(f"Файл не найден: {e}")
        return 1
    except KeyboardInterrupt:
        logging.info("Прервано пользователем")
        return 0
    except Exception as e:
        logging.exception(f"Критическая ошибка: {e}")
        return 2


if __name__ == '__main__':
    sys.exit(main())