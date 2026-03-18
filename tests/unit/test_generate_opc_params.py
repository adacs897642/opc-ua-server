# tests/unit/test_generate_opc_params.py

import pytest
from unittest.mock import MagicMock
from db.migrations.generate_opc_params import OpcParamsGenerator


class TestOpcParamsGenerator:

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.query = MagicMock(return_value=[])
        db.execute = MagicMock(return_value=1)
        return db

    @pytest.fixture
    def generator(self, mock_db):
        return OpcParamsGenerator(mock_db, dry_run=True)

    @pytest.mark.unit
    def test_detect_param_type_bool(self, generator):
        """Определение булевого типа"""
        assert generator._detect_param_type('status', 'Device Status', '') == 'bool'
        assert generator._detect_param_type('alarm', 'Alarm Flag', '') == 'bool'

    @pytest.mark.unit
    def test_detect_param_type_int(self, generator):
        """Определение целочисленного типа"""
        assert generator._detect_param_type('count', 'Counter', '') == 'int'
        assert generator._detect_param_type('qty', 'Quantity', '') == 'int'

    @pytest.mark.unit
    def test_detect_param_type_float(self, generator):
        """Определение float по умолчанию"""
        assert generator._detect_param_type('temp', 'Temperature', '°C') == 'float'
        assert generator._detect_param_type('pressure', 'Pressure', 'бар') == 'float'

    @pytest.mark.unit
    def test_extract_unit_from_name(self, generator):
        """Извлечение единицы из имени"""
        assert generator._extract_unit_from_name('Температура') == '°C'
        assert generator._extract_unit_from_name('Напряжение') == 'V'
        assert generator._extract_unit_from_name('Давление') == 'бар'

    @pytest.mark.unit
    def test_generate_dry_run(self, generator, mock_db):
        """Генерация в режиме dry run"""
        mock_db.query.side_effect = [
            [(1, 'Device1', '12345', 'LPU1', 1, 1)],  # Объекты
            [(1, 'temp_1', 'Temperature', 'temperature', '°C', 'Temp sensor')],  # Параметры
            []  # Проверка существования (пусто)
        ]

        stats = generator.generate()

        assert stats['objects_processed'] == 1
        assert stats['params_found'] == 1
        assert stats['params_created'] == 1
        assert stats['errors'] == 0

    @pytest.mark.unit
    def test_validate_success(self, generator, mock_db):
        """Валидация без проблем"""
        mock_db.query.return_value = []  # Нет проблем

        validation = generator.validate()

        assert validation['valid'] is True
        assert len(validation['issues']) == 0

    @pytest.mark.unit
    def test_validate_with_issues(self, generator, mock_db):
        """Валидация с проблемами"""
        mock_db.query.side_effect = [
            [(1, 'orphan_param', 1)],  # orphan_params
            [],  # invalid_sims
            [],  # duplicates
            [(0,)]  # no_type
        ]

        validation = generator.validate()

        assert validation['valid'] is False
        assert len(validation['issues']) >= 1