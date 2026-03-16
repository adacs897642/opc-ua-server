# tests/unit/test_nodes_parent.py

import pytest
from opc.nodes import NodeCreator


class TestNodeParentValidation:

    @pytest.mark.unit
    def test_create_object_with_none_parent(self, mock_opc_server):
        """Создание объекта с None родителем"""
        creator = NodeCreator(mock_opc_server, namespace_idx=2)

        # Мокаем get_objects_node для возврата валидного узла
        mock_opc_server.get_objects_node = MagicMock()
        mock_opc_server.get_objects_node.return_value = MagicMock()

        # Должно использовать Objects folder по умолчанию
        obj = creator.create_object(
            parent=None,  # ← None родитель
            browse_name='Test',
            display_name='Test'
        )

        assert obj is not None
        mock_opc_server.get_objects_node.assert_called()

    @pytest.mark.unit
    def test_create_object_with_valid_parent(self, mock_opc_server, mock_opc_node):
        """Создание объекта с валидным родителем"""
        creator = NodeCreator(mock_opc_server, namespace_idx=2)

        obj = creator.create_object(
            parent=mock_opc_node,  # ← Валидный родитель
            browse_name='Test',
            display_name='Test'
        )

        assert obj is not None
        mock_opc_node.add_object.assert_called()