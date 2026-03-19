# opc/commands/hot_reload.py
# -*- coding: utf-8 -*-
"""
Hot-Reload модуль для динамического обновления команд OPC UA
Мониторит изменения в базе данных и обновляет узлы без перезапуска сервера
"""

import logging
import time
import threading
import hashlib
from typing import Optional, Dict, Set, Any, List
from datetime import datetime

from opcua import ua
from opcua.ua import LocalizedText

from db.connection import Database
from opc.nodes import NodeCreator
from opc.commands.registry import OpcCommandRegistry

logger = logging.getLogger(__name__)


# ============================================================================
# Константы
# ============================================================================

class HotReloadConfig:
    """Конфигурация hot-reload"""

    DEFAULT_CHECK_INTERVAL_SEC = 30
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_DELAY_SEC = 5

    # SQL-запросы
    QUERY_GET_CONFIG_HASH = """
        SELECT config_hash FROM commands_config_version WHERE id = 1
    """

    QUERY_GET_ACTIVE_COMMANDS = """
        SELECT id, code, name, description, has_params, param_schema, is_active
        FROM commands_catalog
        WHERE is_active = TRUE
        ORDER BY code
    """

    QUERY_GET_ALL_COMMANDS = """
        SELECT id, code, name, description, has_params, param_schema, is_active
        FROM commands_catalog
        ORDER BY code
    """


# ============================================================================
# Data-классы
# ============================================================================

class CommandNodeInfo:
    """Информация о узле команды"""

    def __init__(self, code: str, node_id: ua.NodeId, meta: dict):
        self.code = code
        self.node_id = node_id
        self.meta = meta
        self.created_at = datetime.now()
        self.hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Вычисляет хэш метаданных команды"""
        meta_str = f"{self.code}:{self.meta.get('name', '')}:{self.meta.get('has_params', False)}:{self.meta.get('param_schema', [])}"
        return hashlib.md5(meta_str.encode('utf-8')).hexdigest()

    def __repr__(self) -> str:
        return f"CommandNodeInfo(code='{self.code}', hash='{self.hash[:8]}')"


# ============================================================================
# Основной класс Hot-Reload
# ============================================================================

class CommandHotReload:
    """
    Мониторит изменения конфигурации команд и обновляет OPC UA узлы

    Пример использования:
        reload = CommandHotReload(db, opc_server, registry, check_interval_sec=30)
        reload.start()
        # ... работа сервера ...
        reload.stop()
    """

    def __init__(
            self,
            db: Database,
            opc_server: Any,
            registry: OpcCommandRegistry,
            check_interval_sec: int = HotReloadConfig.DEFAULT_CHECK_INTERVAL_SEC,
            commands_folder: Any = None
    ):
        """
        Инициализирует hot-reload монитор

        Args:
            db: Подключение к базе данных
            opc_server: Экземпляр OPCServer
            registry: Реестр команд
            check_interval_sec: Интервал проверки изменений (сек)
            commands_folder: OPC UA папка для команд
        """
        self.db = db
        self.opc_server = opc_server
        self.registry = registry
        self.check_interval = check_interval_sec
        self.commands_folder = commands_folder

        self.logger = logging.getLogger('commands.hot_reload')

        # Состояние
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._current_hash: Optional[str] = None

        # Кэш узлов команд: code -> CommandNodeInfo
        self._node_cache: Dict[str, CommandNodeInfo] = {}

        # Статистика
        self._reload_count = 0
        self._last_reload_time: Optional[datetime] = None
        self._error_count = 0
        self._last_hash = None
        self._attempt_count = 0
        self._max_attempts = 10



    # ========================================================================
    # Управление жизненным циклом
    # ========================================================================

    def start(self) -> None:
        """Запускает монитор hot-reload в фоновом потоке"""
        if self._running:
            self.logger.warning("Hot-reload уже запущен")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="CommandHotReload"
        )
        self._thread.start()

        # Первоначальная загрузка хэша
        self._current_hash = self._get_config_hash()

        self.logger.info(
            f"Hot-reload запущен (интервал: {self.check_interval}с, "
            f"текущий хэш: {self._current_hash[:8] if self._current_hash else 'None'})"
        )

    def stop(self) -> None:
        """Останавливает монитор hot-reload"""
        if not self._running:
            return

        self.logger.info("Остановка hot-reload монитора...")
        self._running = False

        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None

        self.logger.info(
            f"Hot-reload остановлен (всего перезагрузок: {self._reload_count})"
        )

    def is_running(self) -> bool:
        """Проверяет, запущен ли монитор"""
        return self._running

    # ========================================================================
    # Основной цикл мониторинга
    # ========================================================================

    def _monitor_loop(self) -> None:
        """Основной цикл проверки изменений конфигурации"""
        retry_count = 0

        while self._running:
            try:
                time.sleep(self.check_interval)

                if not self._running:
                    break

                # Получаем текущий хэш из БД
                new_hash = self._get_config_hash()

                if new_hash is None:
                    self.logger.warning("Не удалось получить хэш конфигурации")
                    retry_count += 1
                    if retry_count > HotReloadConfig.DEFAULT_MAX_RETRIES:
                        self.logger.error("Превышено количество попыток получения хэша")
                        retry_count = 0
                    continue

                retry_count = 0

                # Сравниваем хэши
                if new_hash != self._current_hash:
                    self.logger.info(
                        f"Обнаружено изменение конфигурации команд "
                        f"({self._current_hash[:8] if self._current_hash else 'None'} → {new_hash[:8]})"
                    )

                    self._reload_commands()

                    self._current_hash = new_hash
                    self._reload_count += 1
                    self._last_reload_time = datetime.now()
                    self._error_count = 0

                else:
                    self.logger.debug(f"Конфигурация не изменилась (хэш: {new_hash[:8]})")

            except Exception as e:
                self._error_count += 1
                self.logger.error(
                    f"Ошибка в цикле hot-reload (ошибок подряд: {self._error_count}): {e}",
                    exc_info=True
                )

                # Пауза перед повторной попыткой
                time.sleep(HotReloadConfig.DEFAULT_RETRY_DELAY_SEC)

    # ========================================================================
    # Перезагрузка команд
    # ========================================================================

    def _reload_commands(self) -> None:
        """Перезагружает команды из БД и обновляет OPC UA узлы"""
        try:
            # Загружаем актуальный список команд из БД
            rows = self.db.query(HotReloadConfig.QUERY_GET_ALL_COMMANDS)

            if not rows:
                self.logger.warning("Список команд пуст")
                rows = []

            # Создаём множество активных кодов
            active_codes: Set[str] = set()
            active_commands: Dict[str, dict] = {}

            for row in rows:
                cmd_id, code, name, desc, has_params, schema, is_active = row

                if is_active:
                    active_codes.add(code)
                    active_commands[code] = {
                        'id': cmd_id,
                        'code': code,
                        'name': name,
                        'description': desc,
                        'has_params': has_params,
                        'param_schema': schema or []
                    }

            # Определяем изменения
            cached_codes = set(self._node_cache.keys())
            codes_to_add = active_codes - cached_codes
            codes_to_remove = cached_codes - active_codes
            codes_to_check = active_codes & cached_codes

            self.logger.info(
                f"План обновления: добавить={len(codes_to_add)}, "
                f"удалить={len(codes_to_remove)}, проверить={len(codes_to_check)}"
            )

            # 1. Добавляем новые команды
            for code in codes_to_add:
                self._add_command(code, active_commands[code])

            # 2. Удаляем отключенные команды
            for code in codes_to_remove:
                self._remove_command(code)

            # 3. Проверяем изменения в существующих командах
            for code in codes_to_check:
                self._check_command_changed(code, active_commands[code])

            # 4. Обновляем реестр команд
            self.registry.commands = active_commands

            self.logger.info(
                f"Hot-reload завершён (активных команд: {len(active_codes)})"
            )

        except Exception as e:
            self.logger.error(f"Ошибка при перезагрузке команд: {e}", exc_info=True)
            raise

    # ========================================================================
    # Операции с отдельными командами
    # ========================================================================

    def _add_command(self, code: str, meta: dict) -> None:
        """Добавляет новую команду"""
        try:
            if self.commands_folder is None:
                self.logger.error(f"Невозможно добавить команду {code}: папка не инициализирована")
                return

            # Создаём метод команды через NodeCreator
            node = self.opc_server.node_creator.create_command_method(
                parent=self.commands_folder,
                command_code=code,
                command_name=meta['name'],
                callback=self.registry.execute,
                description=meta.get('description', ''),
                param_schema=meta.get('param_schema', [])
            )

            # Сохраняем в кэш
            self._node_cache[code] = CommandNodeInfo(code, node.nodeid, meta)

            self.logger.info(f"✅ Добавлена команда: {code}")

        except Exception as e:
            self.logger.error(f"Ошибка добавления команды {code}: {e}")
            raise

    def _remove_command(self, code: str) -> None:
        """Удаляет команду"""
        try:
            node_info = self._node_cache.pop(code, None)

            if node_info is None:
                self.logger.warning(f"Команда {code} не найдена в кэше")
                return

            # Получаем узел и удаляем
            node = self.opc_server.server.get_node(node_info.node_id)
            node.delete()

            self.logger.info(f"❌ Удалена команда: {code}")

        except Exception as e:
            self.logger.error(f"Ошибка удаления команды {code}: {e}")
            # Удаляем из кэша даже при ошибке
            self._node_cache.pop(code, None)

    def _check_command_changed(self, code: str, meta: dict) -> None:
        """Проверяет, изменились ли метаданные команды"""
        try:
            node_info = self._node_cache.get(code)

            if node_info is None:
                return

            # Вычисляем новый хэш
            new_hash = self._compute_command_hash(meta)

            if new_hash != node_info.hash:
                self.logger.info(f"🔄 Обнаружены изменения в команде: {code}")

                # Обновляем DisplayName и Description
                node = self.opc_server.server.get_node(node_info.node_id)

                if node.get_display_name().Text != meta['name']:
                    node.set_display_name(LocalizedText(meta['name']))
                    self.logger.debug(f"  Обновлено имя: {meta['name']}")

                if node.get_description().Text != meta.get('description', ''):
                    node.set_description(LocalizedText(meta.get('description', '')))
                    self.logger.debug(f"  Обновлено описание: {meta.get('description', '')}")

                # ⚠️ Если изменилась сигнатура (параметры) - нужно пересоздать узел
                if meta.get('has_params') != node_info.meta.get('has_params'):
                    self.logger.info(f"  Изменена сигнатура параметров - пересоздаём узел")
                    self._remove_command(code)
                    self._add_command(code, meta)
                else:
                    # Обновляем кэш
                    node_info.meta = meta
                    node_info.hash = new_hash

            else:
                self.logger.debug(f"  Команда {code} не изменилась")

        except Exception as e:
            self.logger.error(f"Ошибка проверки команды {code}: {e}")

    # ========================================================================
    # Вспомогательные методы
    # ========================================================================

    def _get_config_hash(self) -> Optional[str]:
        """Получает хэш текущей конфигурации команд"""
        try:
            # ✅ ПРОВЕРИТЬ ЧТО db подключён
            if not self.db:
                self.logger.error("❌ Database connection is None!")
                return None

            rows = self.db.query("""
                SELECT MD5(
                    STRING_AGG(
                        code || ':' || 
                        COALESCE(param_schema::text, '') || ':' || 
                        COALESCE(updated_at::text, ''),
                        ','
                    )
                )
                FROM commands_catalog
                WHERE is_active = TRUE
            """)

            if rows and rows[0] and rows[0][0]:
                hash_value = rows[0][0]
                self.logger.debug(f"🔍 Хэш конфигурации: {hash_value}")
                return hash_value

            self.logger.warning("⚠️ Пустой результат хэша")
            return None

        except Exception as e:
            self._attempt_count += 1
            self.logger.error(f"❌ Ошибка получения хэша (попытка {self._attempt_count}/{self._max_attempts}): {e}")

            if self._attempt_count >= self._max_attempts:
                self.logger.error(f"🚫 Превышено количество попыток получения хэша")
                self.logger.error(f"💡 Отключаю hot_reload или проверьте подключение к БД")

            return None

    def _compute_command_hash(self, meta: dict) -> str:
        """Вычисляет хэш метаданных команды"""
        meta_str = (
            f"{meta.get('code', '')}:"
            f"{meta.get('name', '')}:"
            f"{meta.get('has_params', False)}:"
            f"{meta.get('param_schema', [])}"
        )
        return hashlib.md5(meta_str.encode('utf-8')).hexdigest()

    def set_commands_folder(self, folder_node: Any) -> None:
        """
        Устанавливает папку для команд

        Args:
            folder_node: OPC UA узел папки Commands
        """
        self.commands_folder = folder_node
        self.logger.debug(f"Установлена папка команд: {folder_node.nodeid if folder_node else None}")

    # ========================================================================
    # Статистика и отладка
    # ========================================================================

    def get_stats(self) -> dict:
        """Возвращает статистику hot-reload"""
        return {
            'running': self._running,
            'reload_count': self._reload_count,
            'last_reload_time': self._last_reload_time.isoformat() if self._last_reload_time else None,
            'error_count': self._error_count,
            'cached_commands': len(self._node_cache),
            'current_hash': self._current_hash[:8] if self._current_hash else None,
            'check_interval_sec': self.check_interval
        }

    def get_cached_commands(self) -> List[str]:
        """Возвращает список закэшированных команд"""
        return list(self._node_cache.keys())

    def clear_cache(self) -> None:
        """Очищает кэш узлов (без удаления из OPC UA)"""
        self._node_cache.clear()
        self._current_hash = None
        self.logger.debug("Кэш hot-reload очищен")

    def force_reload(self) -> bool:
        """
        Принудительно запускает перезагрузку команд

        Returns:
            True если успешно
        """
        try:
            self.logger.info("Принудительная перезагрузка команд...")
            self._reload_commands()
            self._current_hash = self._get_config_hash()
            return True
        except Exception as e:
            self.logger.error(f"Ошибка принудительной перезагрузки: {e}")
            return False

    def __repr__(self) -> str:
        return (
            f"CommandHotReload(running={self._running}, "
            f"commands={len(self._node_cache)}, reloads={self._reload_count})"
        )