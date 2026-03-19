# commands/executor.py
# -*- coding: utf-8 -*-
"""
Исполнитель команд из очереди
"""

import logging
import json
import time
import threading
from typing import Optional
from datetime import datetime, timezone
from db.connection import Database
from commands.registry import HandlerRegistry

logger = logging.getLogger(__name__)


class CommandTask:
    """Задача выполнения команды"""

    def __init__(self, task_id: int, command_code: str, sim: str, params: dict):
        self.task_id = task_id
        self.command_code = command_code
        self.sim = sim
        self.params = params
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None

    def __repr__(self) -> str:
        return f"CommandTask(id={self.task_id}, code='{self.command_code}', sim={self.sim})"


class CommandExecutor:
    """Исполнитель команд из очереди"""

    def __init__(self, db: Database, config: dict = None):
        self.db = db
        self.config = config or {}
        self.logger = logging.getLogger('commands.executor')

        # ✅ Реестр обработчиков
        self.handler_registry = HandlerRegistry(db, config)

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._check_interval = config.get('command_check_interval', 5)
        self._processed_count = 0

    def start(self) -> None:
        """Запускает исполнитель в отдельном потоке"""
        if self._running:
            self.logger.warning("⚠️ Исполнитель уже запущен")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self.logger.info("✅ CommandExecutor запущен")

    def stop(self) -> None:
        """Останавливает исполнитель"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        self.logger.info("⏹️ CommandExecutor остановлен")

    def _run_loop(self) -> None:
        """Основной цикл обработки команд"""
        self.logger.info("🔄 Запуск цикла обработки команд")

        while self._running:
            try:
                task = self._fetch_next_task()

                if task:
                    self._process_task(task)
                else:
                    time.sleep(self._check_interval)

            except Exception as e:
                self.logger.error(f"❌ Ошибка в цикле обработки: {e}", exc_info=True)
                time.sleep(self._check_interval)

    def _fetch_next_task(self) -> Optional[CommandTask]:
        """Получает следующую задачу из очереди"""
        rows = self.db.query("""
            SELECT id, command_id, sim, params
            FROM commands_queue
            WHERE status = 'pending'
            ORDER BY priority DESC, created_at ASC
            LIMIT 1
        """)

        if not rows:
            return None

        row = rows[0]
        task_id, command_id, sim, params = row

        # Получаем код команды из catalog
        cmd_rows = self.db.query("""
            SELECT code FROM commands_catalog WHERE id = %s
        """, (command_id,))

        if not cmd_rows:
            self.logger.error(f"❌ Команда с id={command_id} не найдена")
            self._update_task_status(task_id, 'error', 'Команда не найдена в каталоге')
            return None

        command_code = cmd_rows[0][0]

        return CommandTask(task_id, command_code, sim, params or {})

    def _process_task(self, task: CommandTask) -> None:
        """Обрабатывает одну задачу"""
        self.logger.info(f"Обработка задачи: {task} для устройства {task.sim}")
        task.started_at = datetime.now(timezone.utc)

        try:
            # ✅ Получаем обработчик из реестра
            handler = self.handler_registry.get_handler(task.command_code)

            # ✅ Вызов обработчика
            result = handler.execute(task.params, task.sim)

            task.completed_at = datetime.now(timezone.utc)
            self._processed_count += 1

            # Обновляем статус в БД
            self._update_task_status(
                task.task_id,
                'done',
                result_message=json.dumps(result, ensure_ascii=False) if result else 'OK'
            )

            self.logger.info(f"✅ Задача {task.task_id} выполнена для {task.sim}")
            self.logger.info(f"   Результат: {result}")

        except ValueError as e:
            self.logger.error(f"❌ Обработчик не найден: {e}")
            self._update_task_status(task.task_id, 'error', str(e))

        except Exception as e:
            self.logger.error(f"❌ Ошибка выполнения задачи {task.task_id}: {e}", exc_info=True)
            self._update_task_status(task.task_id, 'error', str(e))

    def _update_task_status(self, task_id: int, status: str, result_message: str = None) -> None:
        """Обновляет статус задачи в БД"""
        now = datetime.now(timezone.utc)

        self.db.execute("""
            UPDATE commands_queue 
            SET status = %s,
                started_at = %s,
                completed_at = %s,
                result_message = %s
            WHERE id = %s
        """, (
            status,
            now if status != 'pending' else None,
            now if status in ('done', 'error') else None,
            result_message,
            task_id
        ))

    def get_stats(self) -> dict:
        """Возвращает статистику выполнения"""
        return {
            'processed_count': self._processed_count,
            'running': self._running,
            'handlers': self.handler_registry.get_handler_codes()
        }