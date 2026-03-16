# tests/unit/test_nodes.py

import pytest
from unittest.mock import MagicMock
from opc.nodes import NodeCreator, VariableMetadata


class TestNodeCreator:

    @pytest.fixture
    def creator(self, mock_opc_server):
        return NodeCreator(mock_opc_server, namespace_idx=2)

    @pytest.mark.unit
    def test_create_object(self, creator, mock_opc_node):
        mock_opc_server.get_objects_node.return_value = mock_opc_node

        obj = creator.create_object(
            parent=mock_opc_node,
            browse_name='TestObj',
            display_name='Test Object'
        )

        assert obj is not None
        mock_opc_node.add_object.assert_called_once()

    @pytest.mark.unit
    def test_create_variable_readonly(self, creator, mock_opc_node):
        var = creator.create_variable(
            parent=mock_opc_node,
            browse_name='TestVar',
            display_name='Test Variable',
            value=42,
            is_writable=False
        )

        assert var is not None
        var.set_writable.assert_not_called()

    @pytest.mark.unit
    def test_create_variable_writable(self, creator, mock_opc_node):
        var = creator.create_variable(
            parent=mock_opc_node,
            browse_name='TestCmd',
            display_name='Test Command',
            value=0,
            is_writable=True
        )

        var.set_writable.assert_called_once()

    @pytest.mark.unit
    def test_update_variable_value(self, creator, mock_opc_node):
        creator.update_variable_value(mock_opc_node, 100.5)

        mock_opc_node.set_value.assert_called_once()

    @pytest.mark.unit
    def test_cache_node_by_alias(self, creator, mock_opc_node):
        creator.create_telemetry_variable(
            parent=mock_opc_node,
            alias='test_sensor',
            name='Test',
            value=25.0
        )

        assert 'telemetry:test_sensor' in creator._node_cache

    @pytest.mark.unit
    def test_update_by_alias(self, creator, mock_opc_node):
        creator.create_telemetry_variable(
            parent=mock_opc_node,
            alias='test_sensor',
            name='Test',
            value=25.0
        )

        result = creator.update_variable_by_alias('test_sensor', 30.0)

        assert result is True