# opc/commands/registry.py
# -*- coding: utf-8 -*-
"""
Реестр команд OPC UA
"""

import logging
import json
from typing import Dict, Any, Optional, Callable, Tuple
from datetime import datetime, timezone

from opcua import ua
from opcua.ua import Variant, VariantType, StatusCode, StatusCodes, LocalizedText

from db.connection import Database

logger = logging.getLogger(__name__)


class CommandRegistry:
    """Реестр команд с кэшированием"""

    def __init__(self, db: Database):
        self.db = db
        self.logger = logging.getLogger('commands.registry')
        self.commands: Dict[str, dict] = {}
        self._command_nodes: Dict[str, Any] = {}  # code -> node
        self.load()

    def load(self) -> None:
        """Загружает каталог команд из БД"""
        try:
            rows = self.db.query("""
                SELECT id, code, name, description, has_params, param_schema, is_active
                FROM commands_catalog
                WHERE is_active = TRUE
                ORDER BY code
            """)

            self.commands = {}
            for row in rows:
                cmd_id, code, name, desc, has_params, param_schema, is_active = row

                try:
                    schema = json.loads(param_schema) if param_schema else []
                except (json.JSONDecodeError, TypeError):
                    schema = []

                self.commands[code] = {
                    'id': cmd_id,
                    'code': code,
                    'name': name,
                    'description': desc,
                    'has_params': bool(has_params),
                    'param_schema': schema,
                    'is_active': bool(is_active)
                }

            self.logger.info(f"Загружено команд: {len(self.commands)}")

        except Exception as e:
            self.logger.error(f"Ошибка загрузки команд: {e}", exc_info=True)

    # opc/commands/registry.py

    # opc/commands/registry.py

    def execute(
            self,
            nodeid: ua.NodeId,
            args: tuple,
            sim: str,
            code: str = None  # ← ← ← ЭТОТ ПАРАМЕТР ДОЛЖЕН БЫТЬ!
    ) -> list:
        """
        Выполняет команду через очередь

        Args:
            nodeid: NodeId вызванного метода
            args: Кортеж входных аргументов
            sim: SIM устройства
            code: Код команды (если известен из замыкания) ← ← ←
        """
        # ✅ Если код передан напрямую - используем его!
        # В начале execute()
        self.logger.info(f"🔍 execute() вызван:")
        self.logger.info(f"   code параметр: {code}")
        self.logger.info(f"   self.commands ключи: {list(self.commands.keys())}")
        self.logger.info(f"   code in self.commands: {code in self.commands if code else False}")
        if code:
            self.logger.info(f"🔍 Код команды из замыкания: {code}")
        else:
            # Ищем по NodeId (старый способ)
            code = self._get_code_from_node_id(nodeid)
            self.logger.info(f"🔍 Код команды из NodeId: {code}")

        if not code or code not in self.commands:
            self.logger.warning(f"❌ Команда не найдена: {code}")
            return [
                Variant(-1, VariantType.Int32),
                Variant(f"Команда не найдена: {code}", VariantType.String)
            ]

        meta = self.commands[code]

        try:
            params = self._parse_args(meta, args)
            queue_id = self._queue_command(meta['id'], sim, params)

            self.logger.info(f"✅ Команда {code} добавлена в очередь: ID={queue_id}")

            return [
                Variant(0, VariantType.Int32),
                Variant(f"Команда принята, ID: {queue_id}", VariantType.String)
            ]

        except Exception as e:
            self.logger.exception(f"Ошибка выполнения команды {code}")
            return [
                Variant(-999, VariantType.Int32),
                Variant(str(e), VariantType.String)
            ]

    def _parse_args(self, meta: dict, args: tuple) -> dict:
        """Парсит аргументы метода в словарь"""
        params = {}

        if not meta.get('has_params') or not meta.get('param_schema'):
            return params

        schema = meta['param_schema']

        for i, arg in enumerate(args):
            if i < len(schema):
                param_name = schema[i].get('name', f'param_{i}')
                # ✅ Получаем значение из Variant
                params[param_name] = arg.Value if hasattr(arg, 'Value') else arg

        return params

    def _get_code_from_node_id(self, node_id: ua.NodeId) -> Optional[str]:
        """Получает код команды по NodeId"""
        for code, info in self._command_nodes.items():
            if info.get('node_id') == node_id:
                return code
        return None

    def _parse_args(self, meta: dict, variant_args: list) -> dict:
        """Парсит аргументы метода в словарь"""
        params = {}

        if not meta.get('has_params') or not meta.get('param_schema'):
            return params

        schema = meta['param_schema']

        for i, arg in enumerate(variant_args):
            if i < len(schema):
                param_name = schema[i].get('name', f'param_{i}')
                params[param_name] = arg.Value if hasattr(arg, 'Value') else arg

        return params

    def _queue_command(self, command_id: int, sim: str, params: dict) -> int:
        """Добавляет команду в очередь"""
        rows = self.db.query("""
            INSERT INTO commands_queue (command_id, sim, params, status, requested_by)
            VALUES (%s, %s, %s, 'pending', 'opc_user')
            RETURNING id
        """, (command_id, sim, json.dumps(params)))

        queue_id = rows[0][0]
        self.logger.info(f"Команда добавлена в очередь: ID={queue_id}, sim={sim}")

        return queue_id

    # opc/commands/registry.py

    def register_command_node(self, code: str, node: Any, node_id: ua.NodeId = None) -> None:
        """
        Регистрирует узел команды для обратного поиска

        Args:
            code: Код команды
            node: Узел OPC UA
            node_id: NodeId узла (явно переданный)
        """
        # Если node_id не передан, пробуем получить из узла
        if node_id is None:
            node_id = node.nodeid if hasattr(node, 'nodeid') else None

        self.logger.debug(f"📝 Регистрация команды: {code}")
        self.logger.debug(f"   NodeId: {node_id}")

        self._command_nodes[code] = {
            'node': node,
            'node_id': node_id
        }

        self.logger.debug(f"   Зарегистрировано: {code in self._command_nodes}")

    def get_command_meta(self, code: str) -> Optional[dict]:
        """Получает метаданные команды"""
        return self.commands.get(code)