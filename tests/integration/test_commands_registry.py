# tests/unit/test_commands_registry.py

import pytest
from unittest.mock import MagicMock, patch
from opcua import ua
from opcua.ua import Variant, VariantType

from opc.commands.registry import CommandRegistry


class TestCommandRegistry:
    """Тесты реестра команд"""

    @pytest.mark.unit
    def test_load_commands_success(self, mock_db):
        """Успешная загрузка команд из БД"""
        mock_db.query.return_value = [
            (1, 'CMD_1', 'Command 1', 'Desc 1', False, '[]', True),
            (2, 'CMD_2', 'Command 2', 'Desc 2', True, '[{"name": "val"}]', True)
        ]

        registry = CommandRegistry(mock_db)

        assert len(registry.commands) == 2
        assert 'CMD_1' in registry.commands
        assert 'CMD_2' in registry.commands
        assert registry.commands['CMD_2']['has_params'] is True

    @pytest.mark.unit
    def test_load_commands_empty(self, mock_db):
        """Загрузка при отсутствии команд"""
        mock_db.query.return_value = []

        registry = CommandRegistry(mock_db)

        assert len(registry.commands) == 0

    @pytest.mark.unit
    def test_execute_command_success(self, mock_db):
        """Успешное выполнение команды"""
        mock_db.query.side_effect = [
            # Загрузка команд
            [(1, 'TEST_CMD', 'Test', 'Desc', False, '[]', True)],
            # Queue command (RETURNING id)
            [(100,)]
        ]

        registry = CommandRegistry(mock_db)

        # Мок для _get_code_from_node_id
        registry._get_code_from_node_id = MagicMock(return_value='TEST_CMD')

        status, outputs = registry.execute(MagicMock(), [])

        assert status == ua.StatusCode(ua.StatusCodes.Good)
        assert outputs[0].Value == 0  # status_code
        assert '100' in outputs[1].Value  # message с ID очереди

    @pytest.mark.unit
    def test_execute_command_not_found(self, mock_db):
        """Выполнение несуществующей команды"""
        mock_db.query.return_value = []

        registry = CommandRegistry(mock_db)
        registry._get_code_from_node_id = MagicMock(return_value='NONEXISTENT')

        status, outputs = registry.execute(MagicMock(), [])

        assert status == ua.StatusCode(ua.StatusCodes.Bad_NodeIdUnknown)
        assert outputs[0].Value == -1

    @pytest.mark.unit
    def test_validate_params_with_schema(self, mock_db):
        """Валидация параметров со схемой"""
        mock_db.query.return_value = [
            (1, 'CMD_PARAMS', 'Test', 'Desc', True,
             '[{"name": "value", "type": "float"}]', True)
        ]

        registry = CommandRegistry(mock_db)

        variant_args = [Variant(42.5, VariantType.Double)]
        params = registry._validate_params(registry.commands['CMD_PARAMS'], variant_args)

        assert params['value'] == 42.5

    @pytest.mark.unit
    def test_validate_params_missing(self, mock_db):
        """Валидация при отсутствующих параметрах"""
        mock_db.query.return_value = [
            (1, 'CMD_PARAMS', 'Test', 'Desc', True,
             '[{"name": "value", "type": "float"}, {"name": "priority", "type": "int"}]',
             True)
        ]

        registry = CommandRegistry(mock_db)

        # Передаём только 1 параметр вместо 2
        variant_args = [Variant(42.5, VariantType.Double)]
        params = registry._validate_params(registry.commands['CMD_PARAMS'], variant_args)

        assert 'value' in params
        assert 'priority' not in params  # Отсутствующий параметр не добавляется