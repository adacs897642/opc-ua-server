# opc/status_codes.py
# -*- coding: utf-8 -*-
"""
Модуль определения StatusCode для параметров OPC UA
ИСПРАВЛЕНО: Используем hex-значения напрямую вместо имён констант
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Any, Tuple
from enum import IntEnum

from opcua import ua
from opcua.ua import StatusCode

logger = logging.getLogger(__name__)


# ============================================================================
# Числовые коды статуса OPC UA (HEX значения)
# ============================================================================

class StatusCodeHex:
    """
    Шестнадцатеричные коды StatusCode OPC UA

    Источник: OPC UA Specification Part 4 - Services
    https://reference.opcfoundation.org/Core/Part4/v105/docs/7.32
    """

    # Good (0xxxxxxx) - Бит 31 = 0
    GOOD = 0x00000000

    # Uncertain (4xxxxxxx) - Бит 30 = 1
    UNCERTAIN = 0x40000000
    UNCERTAIN_LAST_USABLE_VALUE = 0x40000004  # ← ← ← HEX   значение!

    # Bad (8xxxxxxx) - Бит 31 = 1
    BAD = 0x80000000
    BAD_UNRELIABLE = 0x80000001
    BAD_TIMEOUT = 0x80000004
    BAD_NO_DATA = 0x80000005


# ============================================================================
# Коды иконок (nico) для различных типов параметров
# ============================================================================

class GasIconCode(IntEnum):
    """Коды иконок (nico) для датчиков газа"""
    NORMAL = 12
    WARNING = 13
    ALARM = 14


class BatteryIconCode(IntEnum):
    """Коды иконок (nico) для батареи (АКБ)"""
    NORMAL = 18
    LEVEL_1 = 48
    LEVEL_2 = 19


# ============================================================================
# Определитель статуса
# ============================================================================

class StatusDeterminer:
    """Определитель StatusCode для параметров"""

    # Коды NICО которые указывают на общую ошибку устройства
    BAD_NICO_CODES = {41, 44, 45, 46}

    # Множители периода для проверки актуальности
    TIMEOUT_WARNING_MULTIPLIER = 1.5
    TIMEOUT_BAD_MULTIPLIER = 2.0

    def __init__(self):
        self.logger = logging.getLogger('opc.status')

    def get_status(
            self,
            alias: str,
            value: Any,
            timestamp: Optional[datetime],
            period_min: int,
            nico: Optional[int] = None,
            param_type: str = 'float'
    ) -> Tuple[StatusCode, str]:
        """Определяет StatusCode для параметра"""
        now = datetime.now(timezone.utc)

        # 1. Проверка критических ошибок NICО (приоритет 1)
        if nico is not None and nico in self.BAD_NICO_CODES:
            return self._create_status(
                StatusCodeHex.BAD_UNRELIABLE,
                f"Ошибка устройства (nico={nico})"
            )

        # 2. Проверка таймаута (приоритет 2)
        timeout_status = self._check_timeout(timestamp, period_min)
        if timeout_status[0].value != StatusCodeHex.GOOD:
            return timeout_status

        # 3. Проверка специальных параметров по nico (приоритет 3)
        if self._is_gas_param(alias):
            return self._check_gas_status(nico)

        if self._is_battery_param(alias):
            return self._check_battery_status(nico)

        # 4. Проверка значения (приоритет 4)
        value_status = self._check_value(value, param_type)
        if value_status[0].value != StatusCodeHex.GOOD:
            return value_status

        # 5. Всё хорошо
        return self._create_status(StatusCodeHex.GOOD, "OK")

    def _check_timeout(
            self,
            timestamp: Optional[datetime],
            period_min: int
    ) -> Tuple[StatusCode, str]:
        """Проверяет актуальность данных"""
        if timestamp is None:
            return self._create_status(
                StatusCodeHex.BAD_NO_DATA,
                "Нет данных"
            )

        now = datetime.now(timezone.utc)
        age_seconds = (now - timestamp).total_seconds()
        period_seconds = period_min * 60

        # ⚠️ Предупреждение (1.5 * period)
        if age_seconds > period_seconds * self.TIMEOUT_WARNING_MULTIPLIER:
            minutes_ago = age_seconds / 60
            return self._create_status(
                StatusCodeHex.UNCERTAIN_LAST_USABLE_VALUE,  #← ← ← HEX!
                f"Данные устарели ({minutes_ago:.1f} мин назад)"
            )

            # ❌ Критическая просрочка (2.0 * period)
            if age_seconds > period_seconds * self.TIMEOUT_BAD_MULTIPLIER:
                minutes_ago = age_seconds / 60
                return self._create_status(
                    StatusCodeHex.BAD_TIMEOUT, # ← ← ← HEX!
                f"Таймаут данных ({minutes_ago:.1f} мин назад)"
                )

                # ✅ Всё хорошо
                return self._create_status(StatusCodeHex.GOOD, "OK")

    def _check_battery_status(self, nico: Optional[int]) -> Tuple[StatusCode, str]:
        """Проверяет статус батареи по коду иконки (nico)"""
        if nico is None:
            return self._create_status(
                StatusCodeHex.UNCERTAIN,
                "АКБ: статус неизвестен (нет nico)"
            )

        try:
            code = int(nico)
        except (ValueError, TypeError):
            return self._create_status(
                StatusCodeHex.UNCERTAIN,
                f"АКБ: неверный формат nico ({nico})"
            )

        if code == BatteryIconCode.NORMAL.value:
            return self._create_status(
                StatusCodeHex.GOOD,
                "АКБ: норма (nico=18)"
            )
        elif code == BatteryIconCode.LEVEL_1.value:
            return self._create_status(
                StatusCodeHex.UNCERTAIN,
                "АКБ: 1-й уровень энергосбережения (nico=48)"
            )
        elif code == BatteryIconCode.LEVEL_2.value:
            return self._create_status(
                StatusCodeHex.BAD,
                "АКБ: 2-й уровень энергосбережения (nico=19) - АВАРИЯ"
            )
        else:
            return self._create_status(
                StatusCodeHex.UNCERTAIN,
                f"АКБ: неизвестный код иконки (nico={code})"
            )

    def _check_gas_status(self, nico: Optional[int]) -> Tuple[StatusCode, str]:
        """Проверяет статус датчика газа по коду иконки (nico)"""
        if nico is None:
            return self._create_status(
                StatusCodeHex.UNCERTAIN,
                "Газ: статус неизвестен (нет nico)"
            )

        try:
            code = int(nico)
        except (ValueError, TypeError):
            return self._create_status(
                StatusCodeHex.UNCERTAIN,
                f"Газ: неверный формат nico ({nico})"
            )

        if code == GasIconCode.NORMAL.value:
            return self._create_status(
                StatusCodeHex.GOOD,
                "Газ: норма (nico=12)"
            )
        elif code == GasIconCode.WARNING.value:
            return self._create_status(
                StatusCodeHex.UNCERTAIN,
                "Газ: предупреждение (nico=13)"
            )
        elif code == GasIconCode.ALARM.value:
            return self._create_status(
                StatusCodeHex.BAD,
                "Газ: АВАРИЯ (nico=14)!"
            )
        else:
            return self._create_status(
                StatusCodeHex.UNCERTAIN,
                f"Газ: неизвестный код иконки (nico={code})"
            )

    def _check_value(self, value: Any, param_type: str) -> Tuple[StatusCode, str]:
        """Проверяет корректность значения"""
        if value is None:
            return self._create_status(
                StatusCodeHex.BAD_NO_DATA,
                "Значение отсутствует"
            )

        if param_type in ('float', 'double', 'real'):
            try:
                val = float(value)
                import math
                if math.isnan(val) or math.isinf(val):
                    return self._create_status(
                        StatusCodeHex.BAD,
                        "Некорректное числовое значение"
                    )
            except (ValueError, TypeError):
                return self._create_status(
                    StatusCodeHex.BAD,
                    "Неверный формат числа"
                )

        return self._create_status(StatusCodeHex.GOOD, "OK")

    def _is_battery_param(self, alias: str) -> bool:
        """Определяет является ли параметр батареей (АКБ)"""
        battery_keywords = [
            'battery', 'batt', 'bat', 'акб', 'battery_level',
            'уровень_батареи', 'заряд', 'power'
        ]
        alias_lower = alias.lower()
        return any(kw in alias_lower for kw in battery_keywords)

    def _is_gas_param(self, alias: str) -> bool:
        """Определяет является ли параметр газом"""
        gas_keywords = [
            'gas', 'gaz', 'газ', 'метан', 'угарный', 'co', 'ch4',
            'methane', 'carbon_monoxide'
        ]
        alias_lower = alias.lower()
        return any(kw in alias_lower for kw in gas_keywords)

    def _create_status(self, hex_code: int, message: str) -> Tuple[StatusCode, str]:
        """
        Создаёт StatusCode из HEX значения

        Args:
            hex_code: Шестнадцатеричное значение статуса
            message: Описание статуса

        Returns:
            (StatusCode, message)
        """
        return (StatusCode(hex_code), message)  # ← ← ← Прямое                создание!


# ============================================================================
# Глобальный экземпляр
# ============================================================================

status_determiner = StatusDeterminer()