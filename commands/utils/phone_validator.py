# commands/utils/phone_validator.py
# -*- coding: utf-8 -*-
"""
Валидация и нормализация телефонных номеров
"""

import re
import logging

logger = logging.getLogger(__name__)


class PhoneValidator:
    """
    Валидатор и нормализатор телефонных номеров

    Поддерживает:
    - Российские номера (+7, 8)
    - Международные номера
    - Очистка от форматирования (пробелы, тире, скобки)
    """

    # ✅ Коды стран для авто-добавления (если нет префикса)
    DEFAULT_COUNTRY_CODES = {
        'RU': '+7',
        'KZ': '+7',
        'BY': '+375',
        'UA': '+380',
    }

    @classmethod
    def normalize(cls, phone: str, country: str = 'RU') -> str:
        """
        Нормализует телефонный номер к формату +71234567890

        Args:
            phone: Исходный номер (например, "+7 (910) 123-45-67")
            country: Код страны для авто-добавления префикса

        Returns:
            str: Нормализованный номер (например, "+79101234567")

        Raises:
            ValueError: Если номер невалидный
        """
        if not phone:
            raise ValueError("Номер телефона не может быть пустым")

        # ✅ Конвертируем в строку
        phone_str = str(phone).strip()

        # ✅ Очищаем от лишних символов (оставляем только цифры и +)
        cleaned = re.sub(r'[^\d+]', '', phone_str)

        # ✅ Если начинается с 8 — заменяем на +7 (для России/Казахстана)
        if cleaned.startswith('8') and len(cleaned) == 11:
            cleaned = '+7' + cleaned[1:]

        # ✅ Если начинается с 7 и длина 11 — добавляем +
        if cleaned.startswith('7') and len(cleaned) == 11:
            cleaned = '+7' + cleaned[1:]

        # ✅ Если нет + в начале — добавляем префикс страны
        if not cleaned.startswith('+'):
            country_code = cls.DEFAULT_COUNTRY_CODES.get(country, '+7')
            cleaned = country_code + cleaned.lstrip('+')

        # ✅ Проверка длины (минимум 10 цифр после +)
        digits_only = re.sub(r'[^\d]', '', cleaned)
        if len(digits_only) < 10:
            raise ValueError(f"Слишком короткий номер: {phone_str} (минимум 10 цифр)")

        if len(digits_only) > 15:
            raise ValueError(f"Слишком длинный номер: {phone_str} (максимум 15 цифр)")

        # ✅ Проверка что после + только цифры
        if not re.match(r'^\+\d+$', cleaned):
            raise ValueError(f"Недопустимый формат: {phone_str}")

        logger.info(f"✅ Номер нормализован: {phone_str} → {cleaned}")

        return cleaned

    @classmethod
    def validate(cls, phone: str, country: str = 'RU') -> tuple:
        """
        Проверяет и нормализует номер

        Returns:
            tuple: (is_valid: bool, normalized_phone: str or None, error_message: str or None)
        """
        try:
            normalized = cls.normalize(phone, country)
            return True, normalized, None
        except ValueError as e:
            return False, None, str(e)

    @classmethod
    def format_display(cls, phone: str) -> str:
        """
        Форматирует номер для отображения (например, +7 (910) 123-45-67)

        Args:
            phone: Нормализованный номер (+79101234567)

        Returns:
            str: Форматированный номер
        """
        # Очищаем от +
        digits = re.sub(r'[^\d]', '', phone)

        if len(digits) == 11 and digits.startswith('7'):
            # Российский формат: +7 (XXX) XXX-XX-XX
            return f"+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"

        # Default: просто возвращаем как есть
        return phone