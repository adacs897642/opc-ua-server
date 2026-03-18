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
from db.migrations.generate_opc_params import OpcParamsGenerator
from config.loader import ConfigLoader
from db.connection import Database

# Уменьшить уровень логирования для OPC UA (если слишком много сообщений)
#logging.getLogger('opcua.server.uaprocessor').setLevel(logging.WARNING)

# Или увеличить для отладки
logging.getLogger('opcua.server.uaprocessor').setLevel(logging.DEBUG)

# Настройка для всех OPC UA компонентов
logging.getLogger('opcua').setLevel(logging.INFO)


def main():
    parser = argparse.ArgumentParser(description='OPC UA Server')
    parser.add_argument('config', nargs='?', default='config.json',
                        help='Путь к конфигурации')
    parser.add_argument('--migrate-opc-params', action='store_true',
                        help='Запустить миграцию opc_params перед запуском')
    parser.add_argument('--dry-run', action='store_true',
                        help='Режим сухой проверки для миграции')

    args = parser.parse_args()

    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )

    # Миграция opc_params (если запрошено)
    if args.migrate_opc_params:
        logger = logging.getLogger('main')
        logger.info("🔄 Запуск миграции opc_params...")

        config = ConfigLoader(args.config)
        db = Database(config.db_config)

        generator = OpcParamsGenerator(db, dry_run=args.dry_run)
        stats = generator.generate()

        if stats['errors'] > 0:
            logger.error(f"❌ Миграция завершилась с ошибками: {stats['errors']}")
            return 1

        logger.info("✅ Миграция завершена успешно")

    config_path = sys.argv[1] if len(sys.argv) > 1 else 'config.json'

    try:
        # Настройка логирования (до загрузки приложения)
        setup_logging(config_path)
        logger = logging.getLogger('opc_server')

        logger.info(f"Запуск OPC UA Server")
        logger.info(f"Конфигурация: {config_path}")

        # Инициализация и запуск приложения
        app = OPCApp(config_path)
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