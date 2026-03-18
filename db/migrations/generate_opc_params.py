# db/migrations/generate_opc_params.py
# -*- coding: utf-8 -*-
"""
Модуль автоматической генерации данных в opc_params
на основе obj_params и objects_new
"""

import logging
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timezone

from db.connection import Database

logger = logging.getLogger('db.migrations')


class OpcParamsGenerator:
    """
    Генератор данных для таблицы opc_params

    Использование:
        generator = OpcParamsGenerator(db)
        stats = generator.generate()
        print(f"Создано параметров: {stats['created']}")
    """

    # SQL-запросы
    QUERY_GET_OBJECTS = """
        SELECT id, name, sim, sname, tb, num
        FROM objects_new
        WHERE sim IS NOT NULL AND sim <> ''
        ORDER BY id
    """

    QUERY_GET_OBJ_PARAMS = """
        SELECT id, alias, name, pgroup, disp, comment
        FROM obj_params
        WHERE id = %s
        ORDER BY alias
    """

    QUERY_CHECK_OPC_PARAM_EXISTS = """
        SELECT alias, sim
        FROM opc_params
        WHERE alias = %s AND sim = %s
    """

    QUERY_INSERT_OPC_PARAM = """
        INSERT INTO opc_params (
            alias, sim, name, unit, comment, type, 
            description, pgroup, disp
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (alias) DO UPDATE SET
            sim = EXCLUDED.sim,
            name = EXCLUDED.name,
            unit = EXCLUDED.unit,
            comment = EXCLUDED.comment,
            type = EXCLUDED.type,
            description = EXCLUDED.description,
            pgroup = EXCLUDED.pgroup,
            disp = EXCLUDED.disp            
    """

    QUERY_GET_STATS = """
        SELECT 
            COUNT(*) as total,
            COUNT(DISTINCT sim) as devices,
            COUNT(DISTINCT pgroup) as groups
        FROM opc_params
    """

    def __init__(self, db: Database, dry_run: bool = False):
        """
        Инициализирует генератор

        Args:
            db: Подключение к базе данных
            dry_run: Если True, только показывает что будет сделано (без записи)
        """
        self.db = db
        self.dry_run = dry_run
        self.logger = logging.getLogger('db.migrations.opc_params')

        # Статистика
        self.stats = {
            'objects_processed': 0,
            'params_found': 0,
            'params_created': 0,
            'params_updated': 0,
            'params_skipped': 0,
            'errors': 0
        }

    def generate(self) -> dict:
        """
        Запускает генерацию opc_params

        Returns:
            Статистика выполнения
        """
        self.logger.info("🚀 Запуск генерации opc_params...")
        self.logger.info(f"Режим: {'DRY RUN (без записи)' if self.dry_run else 'ЗАПИСЬ в БД'}")

        start_time = datetime.now()

        try:
            # Получаем все объекты
            objects = self.db.query(self.QUERY_GET_OBJECTS)

            if not objects:
                self.logger.warning("⚠️ Нет объектов в objects_new")
                return self.stats

            self.logger.info(f"📊 Найдено объектов: {len(objects)}")

            # Обрабатываем каждый объект
            for obj in objects:
                self._process_object(obj)

            # Финальная статистика
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            self._log_final_stats(duration)

            return self.stats

        except Exception as e:
            self.logger.error(f"❌ Ошибка генерации: {e}", exc_info=True)
            self.stats['errors'] += 1
            return self.stats

    def _process_object(self, obj: tuple) -> None:
        """
        Обрабатывает один объект

        Args:
            obj: Кортеж (id, name, sim, sname, tb, num)
        """
        obj_id, obj_name, sim, sname, tb, num = obj

        self.stats['objects_processed'] += 1

        self.logger.debug(f"Обработка объекта: {obj_name} (sim={sim})")

        # Получаем параметры объекта
        params = self.db.query(self.QUERY_GET_OBJ_PARAMS, (obj_id,))

        if not params:
            self.logger.debug(f"  Нет параметров для объекта {obj_name}")
            return

        self.stats['params_found'] += len(params)

        # Обрабатываем каждый параметр
        for param in params:
            self._process_parameter(param, sim)

    def _process_parameter(self, param: tuple, sim: str) -> None:
        """
        Обрабатывает один параметр

        Args:
            param: Кортеж (id, alias, name, pgroup, disp, comment)
            sim: SIM устройства
        """
        param_id, alias, name, pgroup, disp, comment = param

        # Проверяем существует ли уже в opc_params
        existing = self.db.query(
            self.QUERY_CHECK_OPC_PARAM_EXISTS,
            (alias, sim)
        )

        # Определяем тип данных (по умолчанию float)
        param_type = self._detect_param_type(alias, name, disp)

        # Формируем описание
        description = comment or name or alias

        # Единица измерения (приоритет: disp → unit из имени)
        unit = disp or self._extract_unit_from_name(name)

        if existing:
            # Обновляем существующий
            self.stats['params_skipped'] += 1
            self.logger.debug(f"  ✓ Пропущен (существует): {alias}")
        else:
            # Создаём новый
            if not self.dry_run:
                try:
                    self.db.execute(
                        self.QUERY_INSERT_OPC_PARAM,
                        (
                            alias,  # alias
                            sim,  # sim
                            name,  # name
                            unit,  # unit
                            comment,  # comment
                            param_type,  # type
                            description,  # description
                            pgroup,  # pgroup
                            disp  # disp
                        )
                    )
                    self.stats['params_created'] += 1
                    self.logger.info(f"  ✅ Создан: {alias} (sim={sim}, type={param_type})")
                except Exception as e:
                    self.logger.error(f"  ❌ Ошибка создания {alias}: {e}")
                    self.stats['errors'] += 1
            else:
                self.stats['params_created'] += 1
                self.logger.info(f"  📝 [DRY RUN] Будет создан: {alias}")

    def _detect_param_type(self, alias: str, name: str, disp: str) -> str:
        """
        Определяет тип данных параметра по имени/алиасу

        Args:
            alias: Алиас параметра
            name: Имя параметра
            disp: Отображение (единицы)

        Returns:
            Тип данных ('int', 'float', 'string', 'bool')
        """
        combined = f"{alias} {name} {disp}".lower()

        # Булевы значения
        if any(kw in combined for kw in ['status', 'alarm', 'error', 'fault', 'on', 'off', 'bool']):
            return 'bool'

        # Целочисленные значения
        if any(kw in combined for kw in ['count', 'qty', 'quantity', 'int', 'integer']):
            return 'int'

        # Строковые значения
        if any(kw in combined for kw in ['text', 'string', 'message', 'desc']):
            return 'string'

        # По умолчанию float (для измерений)
        return 'float'

    def _extract_unit_from_name(self, name: str) -> str:
        """
        Извлекает единицу измерения из имени параметра

        Args:
            name: Имя параметра

        Returns:
            Единица измерения или пустая строка
        """
        if not name:
            return ''

        # Распространённые единицы
        units = {
            '°C': ['температур', 'temp'],
            'V': ['напряж', 'volt', 'voltage'],
            'A': ['ток', 'ampere', 'current'],
            'бар': ['давлен', 'press', 'bar'],
            '%': ['влаж', 'humid', 'percent'],
            'Гц': ['частот', 'freq', 'hertz'],
            'м': ['уровен', 'level', 'meter'],
            'Вт': ['мощн', 'power', 'watt'],
        }

        name_lower = name.lower()

        for unit, keywords in units.items():
            if any(kw in name_lower for kw in keywords):
                return unit

        return ''

    def _log_final_stats(self, duration: float) -> None:
        """Выводит финальную статистику"""
        self.logger.info("=" * 60)
        self.logger.info("📊 ФИНАЛЬНАЯ СТАТИСТИКА")
        self.logger.info("=" * 60)
        self.logger.info(f"⏱️  Время выполнения: {duration:.2f} сек")
        self.logger.info(f"📦 Обработано объектов: {self.stats['objects_processed']}")
        self.logger.info(f"📝 Найдено параметров: {self.stats['params_found']}")
        self.logger.info(f"✅ Создано параметров: {self.stats['params_created']}")
        self.logger.info(f"🔄 Обновлено параметров: {self.stats['params_updated']}")
        self.logger.info(f"⏭️  Пропущено параметров: {self.stats['params_skipped']}")
        self.logger.info(f"❌ Ошибок: {self.stats['errors']}")
        self.logger.info("=" * 60)

        # Получаем общую статистику из БД
        if not self.dry_run:
            stats = self.db.query(self.QUERY_GET_STATS)
            if stats:
                self.logger.info(f"📈 Всего в opc_params: {stats[0][0]} параметров")
                self.logger.info(f"📈 Устройств: {stats[0][1]}")
                self.logger.info(f"📈 Групп: {stats[0][2]}")

    def validate(self) -> dict:
        """
        Проверяет целостность данных после миграции

        Returns:
            Отчёт о валидации
        """
        self.logger.info("🔍 Валидация данных...")

        validation = {
            'valid': True,
            'issues': []
        }

        # 1. Проверка что все alias из obj_params есть в opc_params
        orphan_params = self.db.query("""
            SELECT op.id, op.alias, op.id as obj_id
            FROM obj_params op
            LEFT JOIN opc_params ocp ON ocp.alias = op.alias
            WHERE ocp.alias IS NULL
        """)

        if orphan_params:
            validation['valid'] = False
            validation['issues'].append({
                'type': 'orphan_params',
                'count': len(orphan_params),
                'message': f'Найдено {len(orphan_params)} параметров без связи с opc_params'
            })
            self.logger.warning(f"⚠️ {validation['issues'][-1]['message']}")

        # 2. Проверка что все sim в opc_params существуют в objects_new
        invalid_sims = self.db.query("""
            SELECT DISTINCT ocp.sim
            FROM opc_params ocp
            LEFT JOIN objects_new onew ON onew.sim = ocp.sim
            WHERE onew.sim IS NULL
        """)

        if invalid_sims:
            validation['valid'] = False
            validation['issues'].append({
                'type': 'invalid_sims',
                'count': len(invalid_sims),
                'message': f'Найдено {len(invalid_sims)} параметров с несуществующим sim'
            })
            self.logger.warning(f"⚠️ {validation['issues'][-1]['message']}")

        # 3. Проверка на дубликаты (alias + sim)
        duplicates = self.db.query("""
            SELECT alias, sim, COUNT(*)
            FROM opc_params
            GROUP BY alias, sim
            HAVING COUNT(*) > 1
        """)

        if duplicates:
            validation['valid'] = False
            validation['issues'].append({
                'type': 'duplicates',
                'count': len(duplicates),
                'message': f'Найдено {len(duplicates)} дубликатов (alias + sim)'
            })
            self.logger.warning(f"⚠️ {validation['issues'][-1]['message']}")

        # 4. Проверка параметров без типа
        no_type = self.db.query("""
            SELECT COUNT(*)
            FROM opc_params
            WHERE type IS NULL OR type = ''
        """)

        if no_type and no_type[0][0] > 0:
            validation['issues'].append({
                'type': 'missing_type',
                'count': no_type[0][0],
                'message': f'Найдено {no_type[0][0]} параметров без типа'
            })
            self.logger.warning(f"⚠️ {validation['issues'][-1]['message']}")

        if validation['valid']:
            self.logger.info("✅ Валидация пройдена успешно!")
        else:
            self.logger.warning(f"⚠️ Валидация выявила проблем: {len(validation['issues'])}")

        return validation


# ============================================================================
# Точка входа для запуска миграции
# ============================================================================

def main():
    """Запуск миграции из командной строки"""
    import sys
    import argparse
    from config.loader import ConfigLoader
    from db.connection import Database

    # Парсинг аргументов
    parser = argparse.ArgumentParser(
        description='Генерация opc_params из obj_params и objects_new'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Режим сухой проверки (без записи в БД)'
    )
    parser.add_argument(
        '--validate',
        action='store_true',
        help='Только валидация без генерации'
    )
    parser.add_argument(
        '--config',
        default='config.json',
        help='Путь к файлу конфигурации'
    )

    args = parser.parse_args()

    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )

    try:
        # Загрузка конфигурации
        config = ConfigLoader(args.config)

        # Подключение к БД
        db = Database(config.db_config)

        # Создание генератора
        generator = OpcParamsGenerator(db, dry_run=args.dry_run)

        if args.validate:
            # Только валидация
            validation = generator.validate()
            sys.exit(0 if validation['valid'] else 1)
        else:
            # Генерация
            stats = generator.generate()

            # Валидация после генерации
            if not args.dry_run:
                validation = generator.validate()
                if not validation['valid']:
                    logger.warning("⚠️ Валидация выявила проблемы после миграции!")

            sys.exit(0 if stats['errors'] == 0 else 1)

    except Exception as e:
        logging.exception(f"Критическая ошибка: {e}")
        sys.exit(2)

# Запуск в режиме сухой проверки (без записи)
# python -m db.migrations.generate_opc_params --dry-run
# Запуск реальной миграции
# python -m db.migrations.generate_opc_params
# Только валидация
# python -m db.migrations.generate_opc_params --validate
# С кастомным конфигом
# python -m db.migrations.generate_opc_params --config config.prod.json


if __name__ == '__main__':
    main()