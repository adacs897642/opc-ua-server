# tests/unit/test_db_connection.py

import pytest
from unittest.mock import MagicMock, patch

from db.connection import Database


class TestDatabase:
    """Тесты подключения к базе данных"""

    @pytest.mark.unit
    def test_connect_success(self, mock_db_connection):
        """Успешное подключение к БД"""
        with patch('db.connection.psycopg2.connect', return_value=mock_db_connection):
            db = Database({
                'dbname': 'test_db',
                'host': 'localhost',
                'user': 'test',
                'password': 'test'
            })

            assert db.conn is not None
            assert db.conn.autocommit is True

    @pytest.mark.unit
    def test_query_success(self, mock_db, mock_db_cursor):
        """Успешное выполнение SELECT запроса"""
        mock_db_cursor.fetchall.return_value = [('row1',), ('row2',)]
        mock_db_cursor.description = [('col1',)]

        result = mock_db.query("SELECT * FROM test")

        assert len(result) == 2
        assert result[0] == ('row1',)
        mock_db_cursor.execute.assert_called_once()

    @pytest.mark.unit
    def test_query_empty_result(self, mock_db, mock_db_cursor):
        """Запрос без результатов"""
        mock_db_cursor.fetchall.return_value = []
        mock_db_cursor.description = [('col1',)]

        result = mock_db.query("SELECT * FROM test WHERE 1=0")

        assert len(result) == 0

    @pytest.mark.unit
    def test_query_error(self, mock_db, mock_db_cursor):
        """Ошибка при выполнении запроса"""
        import psycopg2
        mock_db_cursor.execute.side_effect = psycopg2.Error("SQL Error")

        result = mock_db.query("SELECT * FROM test")

        assert result == []  # Должен вернуть пустой список, не выбрасывать

    @pytest.mark.unit
    def test_execute_success(self, mock_db, mock_db_cursor):
        """Успешное выполнение INSERT/UPDATE"""
        mock_db_cursor.rowcount = 5

        result = mock_db.execute("INSERT INTO test VALUES (%s)", ('value',))

        assert result == 5

    @pytest.mark.unit
    def test_listen_success(self, mock_db, mock_db_cursor):
        """Успешная подписка на NOTIFY канал"""
        result = mock_db.listen('test_channel')

        assert result is True
        mock_db_cursor.execute.assert_called_with('LISTEN "test_channel";')

    @pytest.mark.unit
    def test_close_connection(self, mock_db, mock_db_connection):
        """Закрытие соединения"""
        mock_db.close()

        mock_db_connection.close.assert_called_once()