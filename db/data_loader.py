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
    """
        Данные параметра телеметрии

        Ожидает кортеж из 15 элементов в порядке:
        0:obj_name, 1:sim, 2:lpu, 3:period, 4:alias, 5:name, 6:unit,
        7:comment, 8:param_type, 9:description, 10:value, 11:timestamp,
        12:nico, 13:pgroup, 14:disp
        """

    def __init__(self, row: tuple):
        # ✅ Безопасное извлечение с проверкой длины
        def safe_str(idx, default=''):
            return str(row[idx]) if len(row) > idx and row[idx] is not None else default

        def safe_int(idx, default=0):
            try:
                return int(row[idx]) if len(row) > idx and row[idx] is not None else default
            except (ValueError, TypeError):
                return default

        self.obj_name = safe_str(0)
        self.sim = safe_str(1)
        self.lpu = safe_str(2)
        self.period = safe_int(3, 5)  # period из запроса (tp.t1*2 или дефолт)
        self.alias = safe_str(4)
        self.name = safe_str(5)
        self.unit = safe_str(6)
        self.comment = safe_str(7)
        self.param_type = safe_str(8, 'string')
        self.description = safe_str(9)
        self.value = row[10] if len(row) > 10 else None  # value из pvalues
        self.timestamp = row[11] if len(row) > 11 else None  # time из pvalues
        self.nico = safe_int(12)  # nico из pcoords
        self.pgroup = safe_str(13)  # группа для OPC UA структуры
        self.disp = safe_int(14)  # отображение (из varchar в int)

    def get_display_unit(self) -> str:
        """Возвращает единицу для отображения"""
        return self.unit or self.disp or ''

    def __repr__(self) -> str:
        return f"TelemetryData(alias='{self.alias}', group='{self.pgroup}', value={self.value})"

    # def __repr__(self) -> str:
    #     return f"TelemetryData(alias='{self.alias}', value={self.value})"


class DataLoader:
    """Загружает телеметрию из базы данных"""

    def __init__(self, db, config: dict = None, default_period_min: int = None):
        """
        Инициализация DataLoader

        Args:
            db: Экземпляр Database
            config: Словарь конфигурации (опционально)
            default_period_min: Дефолтный период в минутах (опционально, приоритет над config)
        """
        self.db = db
        self.logger = logging.getLogger('db.data_loader')

        # ✅ Обработать config: может быть dict или int (для обратной совместимости)
        if isinstance(config, dict):
            self.config = config
        elif isinstance(config, (int, float)):
            # ← ← ← Старый вызов: DataLoader(db, default_period)
            self.config = {}
            default_period_min = int(config)
        else:
            self.config = {}

        # ✅ Определить default_period_min
        if default_period_min is not None:
            # Явно переданный период имеет приоритет
            self.default_period_min = int(default_period_min)
        else:
            # Из конфига: polling.update_interval_sec в секундах → минуты
            polling_config = self.config.get('polling', {})
            update_interval_sec = polling_config.get('update_interval_sec', 300)
            self.default_period_min = update_interval_sec // 60

        self.logger.info(f"📊 DataLoader инициализирован: default_period_min={self.default_period_min}")

    def load_telemetry(self) -> Dict[str, List[TelemetryData]]:
        """
        Загружает все параметры телеметрии из БД

        Returns:
            Dict[str, List[TelemetryData]]: {sim: [TelemetryData, ...], ...}
        """
        try:
            # ✅ ВЫЗВАТЬ ЗАПРОС С ПАРАМЕТРОМ!
            rows = self.db.query(queries.LOAD_TELEMETRY, (self.default_period_min,))

            # ✅ Сгруппировать по SIM
            telemetry_by_sim: Dict[str, List[TelemetryData]] = {}

            for row in rows:
                sim = row[1] if len(row) > 1 else ''

                if sim not in telemetry_by_sim:
                    telemetry_by_sim[sim] = []

                # ✅ Создать TelemetryData из строки БД
                param_data = TelemetryData(row)
                telemetry_by_sim[sim].append(param_data)

            total = sum(len(v) for v in telemetry_by_sim.values())
            self.logger.info(f"📊 Загружено {total} параметров для {len(telemetry_by_sim)} устройств")

            return telemetry_by_sim

        except Exception as e:
            self.logger.error(f"❌ Ошибка загрузки телеметрии: {e}", exc_info=True)
            return {}

    def load_telemetry2(self) -> Dict[str, List[TelemetryData]]:
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

    # data/loader.py (или где у вас этот метод)

    def get_parameter_value(self, alias: str) -> Optional[tuple]:
        """
        Получает значение параметра из БД

        Returns:
            tuple: (value, timestamp) или None если нет данных
        """
        try:
            rows = self.db.query(
                queries.GET_PARAMETER_VALUE,  # Ваш SQL запрос
                (alias,)
            )

            # ✅ ПРОВЕРКА: rows не None и не пустой
            if not rows:
                return None

            # ✅ ПРОВЕРКА: первая строка не None
            row = rows[0]
            if row is None:
                return None

            # ✅ ПРОВЕРКА: строка имеет минимум 2 элемента
            if len(row) < 2:
                self.logger.warning(f"⚠️ Недостаточно данных для {alias}: {row}")
                return None

            # ✅ Вернуть ТОЛЬКО (value, timestamp)
            value = row[0]
            timestamp = row[1]

            return (value, timestamp)  # ← ← ← Кортеж из 2 элементов!

        except Exception as e:
            self.logger.error(f"❌ Ошибка получения значения {alias}: {e}")
            return None

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
