# tests/mocks/mock_db.py

from unittest.mock import MagicMock
from typing import List, Tuple, Any


class MockDatabase:
    """Продвинутый мок базы данных с поддержкой query caching"""

    def __init__(self):
        self.conn = MagicMock()
        self.conn.autocommit = True
        self.conn.notifies = []
        self.conn.poll = MagicMock()
        self.conn.close = MagicMock()

        self._query_results: dict[str, List[Tuple]] = {}
        self._execute_results: dict[str, int] = {}
        self._call_history: List[dict] = []

    def set_query_result(self, sql_pattern: str, result: List[Tuple]):
        """Устанавливает ожидаемый результат для запроса"""
        self._query_results[sql_pattern] = result

    def set_execute_result(self, sql_pattern: str, rowcount: int):
        """Устанавливает ожидаемый результат для INSERT/UPDATE"""
        self._execute_results[sql_pattern] = rowcount

    def query(self, sql: str, params: tuple = ()) -> List[Tuple]:
        """Эмулирует выполнение SELECT"""
        self._call_history.append({'type': 'query', 'sql': sql, 'params': params})

        for pattern, result in self._query_results.items():
            if pattern in sql:
                return result

        return []

    def execute(self, sql: str, params: tuple = ()) -> int:
        """Эмулирует выполнение INSERT/UPDATE/DELETE"""
        self._call_history.append({'type': 'execute', 'sql': sql, 'params': params})

        for pattern, count in self._execute_results.items():
            if pattern in sql:
                return count

        return 1

    def listen(self, channel: str) -> bool:
        """Эмулирует LISTEN"""
        self._call_history.append({'type': 'listen', 'channel': channel})
        return True

    def get_call_history(self) -> List[dict]:
        """Возвращает историю вызовов"""
        return self._call_history

    def clear_history(self):
        """Очищает историю вызовов"""
        self._call_history = []