# tests/unit/test_data_loader.py
# -*- coding: utf-8 -*-

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from db.data_loader import DataLoader, TelemetryData
from db import queries


class TestDataLoader:

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.query = MagicMock(return_value=[])
        db.listen = MagicMock(return_value=True)
        return db

    @pytest.fixture
    def loader(self, mock_db):
        return DataLoader(mock_db, default_period_min=60)

    @pytest.mark.unit
    def test_load_telemetry_uses_query(self, loader, mock_db):
        """Проверка что используется LOAD_TELEMETRY"""
        mock_db.query.return_value = [
            ('Device1', '12345', 'LPU1', 120, 'temp_1', 'Temperature', '°C',
             'Temp sensor', 'float', 'Temperature sensor', 25.5,
             datetime.now(timezone.utc), 0)
        ]

        result = loader.load_telemetry()

        assert len(result) == 1
        assert '12345' in result
        mock_db.query.assert_called_with(queries.LOAD_TELEMETRY, (60,))

    @pytest.mark.unit
    def test_get_parameter_value_uses_query(self, loader, mock_db):
        """Проверка что используется GET_PARAMETER_VALUE"""
        mock_db.query.return_value = [(25.5, datetime.now(timezone.utc))]

        result = loader.get_parameter_value('temp_1')

        assert result is not None
        mock_db.query.assert_called_with(
            queries.GET_PARAMETER_VALUE,
            ('temp_1',)
        )

    @pytest.mark.unit
    def test_get_parameter_nico_uses_query(self, loader, mock_db):
        """Проверка что используется GET_PARAMETER_NICO"""
        mock_db.query.return_value = [(0,)]

        result = loader.get_parameter_nico('temp_1')

        assert result == 0
        mock_db.query.assert_called_with(
            queries.GET_PARAMETER_NICO,
            ('temp_1',)
        )