# opc/commands/registry.py

import logging
import json
from typing import Optional, Dict, Any
from opcua import ua
from opcua.ua import Variant, StatusCodes, VariantType


from db.connection import Database


class CommandRegistry:
    """Реестр команд с кэшированием"""

    def __init__(self, db: Database):
        self.db = db
        self.logger = logging.getLogger('commands.registry')
        self.commands: Dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        """Загружает команды из БД в память"""
        rows = self.db.query("""
            SELECT id, code, name, description, has_params, param_schema, is_active
            FROM commands_catalog
            WHERE is_active = TRUE
        """)

        self.commands = {}
        for r in rows:
            cmd_id, code, name, desc, has_params, schema, is_active = r
            self.commands[code] = {
                'id': cmd_id,
                'name': name,
                'description': desc,
                'has_params': has_params,
                'schema': schema or []
            }

        self.logger.info(f"Загружено команд: {len(self.commands)}")

    # def execute(self, method_id, variant_args) -> tuple:
    #     """Выполняет команду"""
    #     # Определяем код команды по NodeId (нужен маппинг)
    #     code = self._get_code_from_node_id(method_id)
    #     meta = self.commands.get(code)
    #
    #     if not meta:
    #         return ua.StatusCode(StatusCodes.Bad_NodeIdUnknown), [
    #             Variant(-1, ua.VariantType.Int32),
    #             Variant("Команда не найдена", ua.VariantType.String)
    #         ]
    #
    #     # Валидация и выполнение
    #     try:
    #         params = self._validate_params(meta, variant_args)
    #         queue_id = self._queue_command(meta['id'], params)
    #
    #         return ua.StatusCode(StatusCodes.Good), [
    #             Variant(0, ua.VariantType.Int32),
    #             Variant(f"Команда принята, ID: {queue_id}", ua.VariantType.String)
    #         ]
    #     except Exception as e:
    #         self.logger.exception(f"Ошибка выполнения команды {code}")
    #         return ua.StatusCode(StatusCodes.Bad_InternalError), [
    #             Variant(-999, ua.VariantType.Int32),
    #             Variant(str(e), ua.VariantType.String)
    #         ]
    def execute(self, method_id, variant_args, sim: str = None) -> tuple:
        """
        Выполняет команду

        Args:
            method_id: NodeId вызванного метода
            variant_args: Аргументы метода
            sim: SIM устройства ← НОВОЕ!
        """
        code = self._get_code_from_node_id(method_id)
        meta = self.commands.get(code)

        if not meta:
            return ua.StatusCode(StatusCodes.Bad_NodeIdUnknown), [
                Variant(-1, VariantType.Int32),
                Variant("Команда не найдена", VariantType.String)
            ]

        try:
            params = self._validate_params(meta, variant_args)

            # ✅ НОВОЕ: передаём sim в очередь
            queue_id = self._queue_command(meta['id'], sim, params)

            return ua.StatusCode(StatusCodes.Good), [
                Variant(0, VariantType.Int32),
                Variant(f"Команда принята, ID: {queue_id}, Устройство: {sim}", VariantType.String)
            ]
        except Exception as e:
            self.logger.exception(f"Ошибка выполнения команды {code}")
            return ua.StatusCode(StatusCodes.Bad_InternalError), [
                Variant(-999, VariantType.Int32),
                Variant(str(e), VariantType.String)
            ]

    def _queue_command(self, command_id: int, sim: str, params: dict) -> int:
        """Добавляет команду в очередь"""
        rows = self.db.query("""
            INSERT INTO commands_queue (command_id, sim, params, status, requested_by)
            VALUES (%s, %s, %s, 'pending', %s)
            RETURNING id
        """, (command_id, sim, json.dumps(params), 'opc_user'))
        return rows[0][0]

    def _get_code_from_node_id(self, node_id) -> str:
        """Получает код команды по NodeId"""
        # Реализация через сохранённый маппинг {NodeId: code}
        pass

    def _validate_params(self, meta: dict, variant_args: list) -> dict:
        """Валидирует параметры команды"""
        params = {}
        if meta['has_params']:
            for i, arg_def in enumerate(meta['schema']):
                if i < len(variant_args):
                    params[arg_def['name']] = variant_args[i].Value
        return params

    def _queue_command(self, command_id: int, params: dict) -> int:
        """Добавляет команду в очередь"""
        rows = self.db.query("""
            INSERT INTO commands_queue (command_id, params, status)
            VALUES (%s, %s, 'pending')
            RETURNING id
        """, (command_id, json.dumps(params)))
        return rows[0][0]