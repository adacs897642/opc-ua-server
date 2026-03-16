#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OPC UA Server — точка входа
"""

import sys
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