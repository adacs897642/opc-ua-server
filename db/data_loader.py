# db/data_loader.py
# -*- coding: utf-8 -*-
"""
Загрузчик данных телеметрии из базы данных
Версия для схемы: objects_new + opc_params + pvalues (без изменений)
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

from db.connection import Database
from db import queries

logger = logging.getLogger(__name__)


# db/data_loader.py

class TelemetryData:
    """Модель данных телеметрии (обновлённая)"""

    def __init__(self, row: tuple):
        (
            self.obj_name,
            self.sim,
            self.lpu,
            self.period,
            self.alias,
            self.name,
            self.unit,
            self.comment,
            self.param_type,
            self.description,
            self.value,
            self.timestamp,
            self.nico,
            self.pgroup,  # ← Добавлено
            self.disp  # ← Добавлено
        ) = row

        self.device_key = f"{self.sim}"

    def get_display_unit(self) -> str:
        """Возвращает единицу для отображения"""
        return self.unit or self.disp or ''

    def __repr__(self) -> str:
        return f"TelemetryData(alias='{self.alias}', group='{self.pgroup}', value={self.value})"


    # def __repr__(self) -> str:
    #     return f"TelemetryData(alias='{self.alias}', value={self.value})"


class DataLoader:
    """Загружает телеметрию из базы данных"""

    def __init__(self, db: Database, default_period_min: int = 1440):
        self.db = db
        self.default_period = default_period_min
        self.logger = logging.getLogger('db.loader')

    def load_telemetry(self) -> Dict[str, List[TelemetryData]]:
        """
        Загружает все данные телеметрии

        Returns:
            Словарь {sim: [TelemetryData, ...]}
        """
        try:
            rows = self.db.query(
                queries.LOAD_TELEMETRY,
                (self.default_period,)
            )

            if not rows:
                self.logger.warning("Нет данных телеметрии для загрузки")
                return {}

            # Группируем по устройству (sim)
            devices: Dict[str, List[TelemetryData]] = {}

            for row in rows:
                data = TelemetryData(row)

                if data.sim not in devices:
                    devices[data.sim] = []

                devices[data.sim].append(data)

            self.logger.info(
                f"Загружено телеметрии: устройств={len(devices)}, "
                f"параметров={sum(len(params) for params in devices.values())}"
            )

            return devices

        except Exception as e:
            self.logger.error(f"Ошибка загрузки телеметрии: {e}", exc_info=True)
            return {}

    def get_parameter_value(self, alias: str) -> Optional[Tuple[Any, datetime]]:
        """
        Получает последнее значение параметра

        Args:
            alias: Идентификатор параметра

        Returns:
            (value, timestamp) или None
        """
        rows = self.db.query(
            queries.GET_PARAMETER_VALUE,
            (alias,)
        )
        return rows[0] if rows else None

    def get_parameter_nico(self, alias: str) -> Optional[int]:
        """
        Получает код NICО для параметра

        Args:
            alias: Идентификатор параметра

        Returns:
            NICО код или None
        """
        rows = self.db.query(
            queries.GET_PARAMETER_NICO,
            (alias,)
        )
        return rows[0][0] if rows else None

    def update_parameter_value(
            self,
            alias: str,
            value: Any,
            timestamp: datetime = None,
            units: str = '',
            valid: bool = True,
            msg: str = ''
    ) -> bool:
        """
        Обновляет значение параметра в pvalues

        Args:
            alias: Идентификатор параметра
            value: Новое значение
            timestamp: Время значения
            units: Единицы измерения
            valid: Флаг валидности
            msg: Сообщение

        Returns:
            True если успешно
        """
        try:
            if timestamp is None:
                timestamp = datetime.now(timezone.utc)

            self.db.execute(
                queries.UPSERT_PVALUE,
                (alias, alias, str(value), timestamp, units, valid, msg)
            )
            return True
        except Exception as e:
            self.logger.error(f"Ошибка обновления значения {alias}: {e}")
            return False

    def get_parameter_history(
            self,
            alias: str,
            limit: int = 100
    ) -> List[Tuple[Any, datetime]]:
        """
        Получает историю значений параметра

        Args:
            alias: Идентификатор параметра
            limit: Количество записей

        Returns:
            Список (value, timestamp)
        """
        return self.db.query(
            queries.GET_PARAMETER_HISTORY,
            (alias, limit)
        )

    def clear_old_history(self, days: int = 30) -> int:
        """
        Очищает старую историю

        Args:
            days: Хранить историю за N дней

        Returns:
            Количество удалённых записей
        """
        return self.db.execute(
            queries.CLEAR_OLD_HISTORY,
            (days,)
        )

    def get_object_params(self, sim: str) -> List[dict]:
        """Получает параметры объекта"""
        rows = self.db.query(
            queries.GET_OBJECT_PARAMS,
            (sim,)
        )
        params = []
        for row in rows:
            params.append({
                'alias': row[0],
                'name': row[1],
                'unit': row[2],
                'type': row[3],
                'comment': row[4],
                'description': row[5],
                'pgroup': row[6],
                'disp': row[7]
            })
        return params


    def get_devices(self) -> List[dict]:
        """
        Получает список устройств из objects_new

        Returns:
            List[dict]: Список словарей с данными устройств
        """
        try:
            rows = self.db.query("""
                SELECT 
                    id,
                    name,
                    sim,
                    sname,
                    tb,
                    num
                FROM objects_new
                WHERE sim IS NOT NULL AND sim <> ''
                ORDER BY name
            """)

            devices = []
            for row in rows:
                devices.append({
                    'id': row[0],
                    'name': row[1],
                    'sim': row[2],  # ← ← ← SIM устройства!
                    'sname': row[3],
                    'tb': row[4],
                    'num': row[5]
                })

            self.logger.info(f"📊 Загружено устройств: {len(devices)}")
            return devices

        except Exception as e:
            self.logger.error(f"Ошибка загрузки устройств: {e}", exc_info=True)
            return []

    def get_device_commands(self, sim: str) -> dict:
        """
        Получает доступные команды для устройства

        Args:
            sim: SIM устройства

        Returns:
            dict: {code: meta} доступных команд
        """
        # Пока возвращаем все активные команды из каталога
        # В будущем можно добавить привязку команд к устройствам
        rows = self.db.query("""
            SELECT code, name, description, has_params, param_schema
            FROM commands_catalog
            WHERE is_active = TRUE
            ORDER BY code
        """)

        commands = {}
        for row in rows:
            code, name, desc, has_params, param_schema = row
            import json
            try:
                schema = json.loads(param_schema) if param_schema else []
            except:
                schema = []

            commands[code] = {
                'code': code,
                'name': name,
                'description': desc,
                'has_params': bool(has_params),
                'param_schema': schema
            }

        return commands