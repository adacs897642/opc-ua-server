# tests/fixtures/opc.py
# -*- coding: utf-8 -*-
"""
Специализированные фикстуры для OPC UA
"""

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def opc_server_with_nodes(mock_opc_server, mock_opc_node):
    """Сервер с предсозданными узлами"""
    mock_opc_server.get_objects_node.return_value = mock_opc_node
    mock_opc_node.get_children.return_value = [mock_opc_node, mock_opc_node]
    return mock_opc_server


@pytest.fixture
def opc_server_stopped(mock_opc_server):
    """Остановленный сервер"""
    mock_opc_server.is_running = False
    mock_opc_server.start = MagicMock(side_effect=Exception("Server stopped"))
    return mock_opc_server


@pytest.fixture
def opc_node_writable(mock_opc_node):
    """Записываемый узел"""
    mock_opc_node.set_writable = MagicMock()
    return mock_opc_node


@pytest.fixture
def opc_node_readonly(mock_opc_node):
    """Узел только для чтения"""
    mock_opc_node.set_writable = MagicMock(side_effect=Exception("Read-only"))
    return mock_opc_node