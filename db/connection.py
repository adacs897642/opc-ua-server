# db/connection.py
# -*- coding: utf-8 -*-
"""
Подключение к PostgreSQL с авто-переподключением
"""

import psycopg2
from psycopg2.extensions import connection as PgConnection
from psycopg2 import OperationalError, InterfaceError
from psycopg2 import sql, extras
from typing import Optional, List, Tuple
import logging
import time


logger = logging.getLogger('db')


class Database:
    """Обёртка над psycopg2 с авто-переподключением"""

    MAX_RETRIES = 3
    RETRY_DELAY_SEC = 1

    def __init__(self, config: dict, validate_schema: bool = True):
        """
        Инициализация подключения к БД

        Args:
            config: Конфигурация подключения
            validate_schema: Автоматически проверять/создавать схему
        """
        self.config = config
        self.conn: Optional[PgConnection] = None
        self.logger = logging.getLogger('db')
        self._schema_validated = False
        self._schema_report = None

        self._connect()
        # ✅ Импортируем здесь (после инициализации)
        # from db.schema import SchemaValidator
        # ✅ Валидация схемы внутри Database
        if validate_schema:
            self._schema_report = self.validate_schema()
            self._schema_validated = self._schema_report.get('is_valid', False)
        else:
            self.logger.warning("⚠️ Валидация схемы отключена")
        # ✅ ✅ ✅ Подписаться на канал opc_user_change
        self._listen_to_opc_users()

    def _connect(self) -> None:
        """Устанавливает соединение с БД"""
        try:
            if self.conn:
                try:
                    self.conn.close()
                except Exception:
                    pass
        except Exception:
            pass

        try:
            self.conn = psycopg2.connect(
                dbname=self.config.get('dbname'),
                host=self.config.get('host', 'localhost'),
                user=self.config.get('user'),
                password=self.config.get('password'),
                port=self.config.get('port', 5432),
                connect_timeout=self.config.get('connect_timeout', 10)
            )
            self.conn.autocommit = True
            logger.info(f"✅ Подключено к БД: {self.config.get('dbname')}@{self.config.get('host')}")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к БД: {e}")
            raise

    def validate_schema(self, auto_fix: bool = True) -> dict:
        """
        Проверяет и при необходимости создаёт схему БД

        Args:
            auto_fix: Автоматически создавать отсутствующие таблицы

        Returns:
            dict: Отчёт о проверке
        """
        self.logger.info("🔍 Валидация схемы базы данных...")

        try:
            # ✅ Импортируем здесь (после инициализации conn)
            from db.schema import SchemaValidator

            validator = SchemaValidator(self.conn)
            report = validator.validate_and_fix()

            if report['created_tables']:
                self.logger.info(f"📊 Создано таблиц: {len(report['created_tables'])}")
                for table in report['created_tables']:
                    self.logger.info(f"   - {table}")

            if report['created_indexes']:
                self.logger.info(f"📊 Создано индексов: {len(report['created_indexes'])}")

            return report

        except Exception as e:
            self.logger.error(f"❌ Ошибка валидации схемы: {e}", exc_info=True)
            return {'is_valid': False, 'error': str(e)}

    def _ensure_connection(self) -> None:
        """Проверяет и восстанавливает соединение"""
        try:
            if self.conn is None:
                logger.warning("Соединение = None, переподключение...")
                self._connect()
                return

            if self.conn.closed:
                logger.warning("Соединение закрыто, переподключение...")
                self._connect()
                return

            # Проверяем что соединение активно
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1")

        except (OperationalError, InterfaceError) as e:
            logger.warning(f"Соединение неактивно: {e}, переподключение...")
            self._connect()
        except Exception as e:
            logger.error(f"Ошибка проверки соединения: {e}")
            self._connect()

    def query(self, sql: str, params: tuple = ()) -> List[Tuple]:
        """Выполняет SELECT-запрос с авто-переподключением"""
        for attempt in range(self.MAX_RETRIES):
            try:
                self._ensure_connection()

                with self.conn.cursor() as cur:
                    cur.execute(sql, params)
                    result = cur.fetchall() if cur.description else []
                    return result

            except (OperationalError, InterfaceError) as e:
                logger.warning(f"Попытка {attempt + 1}/{self.MAX_RETRIES}: {type(e).__name__}: {e}")
                self._connect()
                time.sleep(self.RETRY_DELAY_SEC)

                if attempt == self.MAX_RETRIES - 1:
                    logger.error(f"Не удалось выполнить запрос после {self.MAX_RETRIES} попыток")
                    raise

            except Exception as e:
                logger.error(f"Ошибка запроса: {type(e).__name__}: {e}\nSQL: {sql[:200]}")
                return []

        return []

    def execute(self, sql: str, params: tuple = ()) -> int:
        """Выполняет INSERT/UPDATE/DELETE с авто-переподключением"""
        for attempt in range(self.MAX_RETRIES):
            try:
                self._ensure_connection()

                with self.conn.cursor() as cur:
                    cur.execute(sql, params)
                    return cur.rowcount

            except (OperationalError, InterfaceError) as e:
                logger.warning(f"Попытка {attempt + 1}/{self.MAX_RETRIES}: {type(e).__name__}: {e}")
                self._connect()
                time.sleep(self.RETRY_DELAY_SEC)

                if attempt == self.MAX_RETRIES - 1:
                    raise
            except Exception as e:
                logger.error(f"Ошибка выполнения: {type(e).__name__}: {e}\nSQL: {sql[:200]}")
                return 0

        return 0

    def poll_notifications(self) -> None:
        """Обрабатывает NOTIFY с проверкой соединения"""
        try:
            self._ensure_connection()
            self.conn.poll()
        except (OperationalError, InterfaceError) as e:
            logger.warning(f"Ошибка poll: {e}, переподключение...")
            self._connect()
        except Exception as e:
            logger.error(f"Ошибка poll: {e}")

    def listen(self, channel: str) -> bool:
        """Подписка на канал с проверкой соединения"""
        try:
            self._ensure_connection()
            with self.conn.cursor() as cur:
                cur.execute(f'LISTEN "{channel}";')
            logger.debug(f"Подписка на канал: {channel}")
            return True
        except Exception as e:
            logger.error(f"Ошибка LISTEN {channel}: {e}")
            return False

    def _listen_to_opc_users(self):
        """Подписаться на уведомления об изменениях пользователей"""
        try:
            # ✅ Важно: autocommit=True для LISTEN/NOTIFY
            self.conn.set_session(autocommit=True)

            with self.conn.cursor() as cursor:
                cursor.execute("LISTEN opc_user_change;")
                self.conn.commit()

            self.logger.info("✅ Подписка на канал: opc_user_change")

        except Exception as e:
            self.logger.error(f"❌ Ошибка подписки на opc_user_change: {e}")
            # ✅ Не блокировать запуск приложения

    def close(self) -> None:
        """Закрывает соединение"""
        if self.conn:
            try:
                self.conn.close()
                logger.info("Соединение с БД закрыто")
            except Exception as e:
                logger.error(f"Ошибка закрытия соединения: {e}")