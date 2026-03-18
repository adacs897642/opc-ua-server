# opc/commands/executor.py
# -*- coding: utf-8 -*-
"""
Исполнитель команд OPC UA
Обрабатывает очередь команд в фоновом потоке
"""

import logging
import json
import time
import threading
from typing import Optional, Dict, Any, Callable
from datetime import datetime, timezone
from queue import Queue, Empty

from db.connection import Database

logger = logging.getLogger(__name__)


class ExecutorConfig:
    """Конфигурация исполнителя команд"""

    DEFAULT_QUEUE_SIZE = 100
    DEFAULT_POLL_INTERVAL_SEC = 2
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_DELAY_SEC = 5
    DEFAULT_WORKER_THREADS = 1

    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_DONE = 'done'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'

    # ✅ ИСПРАВЛЕНО: Запрос с обработкой отсутствия priority
    QUERY_FETCH_PENDING = """
            SELECT 
                q.id, 
                q.command_id, 
                q.sim,
                c.code, 
                q.params,
                COALESCE(q.priority, 2) as priority,
                COALESCE(q.requested_by, 'system') as requested_by,
                q.created_at
            FROM commands_queue q
            JOIN commands_catalog c ON c.id = q.command_id
            WHERE q.status = %s
            ORDER BY COALESCE(q.priority, 2) ASC, q.created_at ASC
            LIMIT 10
        """


class CommandTask:
    """Задача выполнения команды"""

    def __init__(
            self,
            task_id: int,
            command_id: int,
            command_code: str,
            sim: str,
            params: Dict[str, Any],
            priority: int = 2,
            requested_by: str = 'system',
            created_at: datetime = None
    ):
        self.task_id = task_id
        self.command_id = command_id
        self.command_code = command_code
        self.sim = sim
        self.params = params or {}
        self.priority = priority
        self.requested_by = requested_by
        self.created_at = created_at or datetime.now(timezone.utc)
        self.retry_count = 0
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.error_message: Optional[str] = None

    def __repr__(self) -> str:
        return f"CommandTask(id={self.task_id}, code='{self.command_code}', sim={self.sim})"

    def to_dict(self) -> dict:
        """Конвертирует задачу в словарь"""
        return {
            'task_id': self.task_id,
            'command_id': self.command_id,
            'command_code': self.command_code,
            'sim': self.sim,
            'params': self.params,
            'priority': self.priority,
            'requested_by': self.requested_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'retry_count': self.retry_count
        }


class CommandExecutor:
    """Фоновый исполнитель команд из очереди"""

    def __init__(
            self,
            db: Database,
            command_handlers: Dict[str, Callable] = None,
            queue_size: int = ExecutorConfig.DEFAULT_QUEUE_SIZE,
            poll_interval_sec: int = ExecutorConfig.DEFAULT_POLL_INTERVAL_SEC,
            worker_threads: int = ExecutorConfig.DEFAULT_WORKER_THREADS
    ):
        self.db = db
        self.command_handlers = command_handlers or {}
        self.queue_size = queue_size
        self.poll_interval = poll_interval_sec
        self.worker_threads = worker_threads

        self.logger = logging.getLogger('commands.executor')

        self._queue: Queue = Queue(maxsize=queue_size)
        self._running = False
        self._workers: list[threading.Thread] = []

        self._processed_count = 0
        self._failed_count = 0
        self._cancelled_count = 0
        self._start_time: Optional[datetime] = None

    def start(self) -> None:
        """Запускает исполнителя в фоновых потоках"""
        if self._running:
            self.logger.warning("Исполнитель уже запущен")
            return

        self._running = True
        self._start_time = datetime.now(timezone.utc)

        for i in range(self.worker_threads):
            worker = threading.Thread(
                target=self._worker_loop,
                daemon=True,
                name=f"CommandWorker-{i + 1}"
            )
            worker.start()
            self._workers.append(worker)

        poller = threading.Thread(
            target=self._poll_database_loop,
            daemon=True,
            name="CommandPoller"
        )
        poller.start()
        self._workers.append(poller)

        self.logger.info(
            f"Исполнитель запущен (потоков: {self.worker_threads}, "
            f"очередь: {self.queue_size})"
        )

    def stop(self, timeout: int = 10) -> None:
        """Останавливает исполнителя"""
        if not self._running:
            return

        self.logger.info("Остановка исполнителя команд...")
        self._running = False

        for worker in self._workers:
            worker.join(timeout=timeout)

        self._workers.clear()

        self.logger.info(
            f"Исполнитель остановлен (обработано: {self._processed_count}, "
            f"ошибок: {self._failed_count})"
        )

    def is_running(self) -> bool:
        """Проверяет, запущен ли исполнитель"""
        return self._running

    def register_handler(self, command_code: str, handler: Callable) -> None:
        """Регистрирует обработчик для команды"""
        self.command_handlers[command_code] = handler
        self.logger.debug(f"Зарегистрирован обработчик для команды: {command_code}")

    def unregister_handler(self, command_code: str) -> None:
        """Отменяет регистрацию обработчика"""
        self.command_handlers.pop(command_code, None)
        self.logger.debug(f"Удалён обработчик для команды: {command_code}")

    def get_registered_handlers(self) -> list[str]:
        """Возвращает список зарегистрированных обработчиков"""
        return list(self.command_handlers.keys())

    def _poll_database_loop(self) -> None:
        """Опрашивает БД на наличие новых команд"""
        while self._running:
            try:
                time.sleep(self.poll_interval)

                if not self._running:
                    break

                tasks = self._fetch_pending_tasks()

                for task in tasks:
                    try:
                        self._queue.put_nowait(task)
                        self.logger.debug(f"Задача добавлена в очередь: {task}")

                        self._update_task_status(
                            task.task_id,
                            ExecutorConfig.STATUS_PROCESSING
                        )

                    except Exception as e:
                        self.logger.warning(
                            f"Очередь переполнена, задача {task.task_id} отложена: {e}"
                        )

            except Exception as e:
                self.logger.error(f"Ошибка в цикле опроса БД: {e}", exc_info=True)
                time.sleep(ExecutorConfig.DEFAULT_RETRY_DELAY_SEC)

    # def _fetch_pending_tasks(self) -> list[CommandTask]:
    #     """Получает ожидающие команды из БД"""
    #     try:
    #         rows = self.db.query(
    #             ExecutorConfig.QUERY_FETCH_PENDING,
    #             (ExecutorConfig.STATUS_PENDING,)
    #         )
    #
    #         tasks = []
    #         for row in rows:
    #             task_id, command_id, code, params_json, priority, requested_by, created_at = row
    #
    #             try:
    #                 params = json.loads(params_json) if params_json else {}
    #             except (json.JSONDecodeError, TypeError):
    #                 params = {}
    #
    #             task = CommandTask(
    #                 task_id=task_id,
    #                 command_id=command_id,
    #                 command_code=code,
    #                 params=params,
    #                 priority=priority or 2,
    #                 requested_by=requested_by or 'system',
    #                 created_at=created_at
    #             )
    #             tasks.append(task)
    #
    #         if tasks:
    #             self.logger.debug(f"Получено задач из БД: {len(tasks)}")
    #
    #         return tasks
    #
    #     except Exception as e:
    #         self.logger.error(f"Ошибка получения задач из БД: {e}")
    #         return []
    def _fetch_pending_tasks(self) -> list[CommandTask]:
        """Получает ожидающие команды из БД"""
        try:
            rows = self.db.query(
                ExecutorConfig.QUERY_FETCH_PENDING,
                (ExecutorConfig.STATUS_PENDING,)
            )

            tasks = []
            for row in rows:
                task_id, command_id, sim, code, params_json, priority, requested_by, created_at = row

                try:
                    params = json.loads(params_json) if params_json else {}
                except (json.JSONDecodeError, TypeError):
                    params = {}

                # ✅ НОВОЕ: передаём sim в задачу
                task = CommandTask(
                    task_id=task_id,
                    command_id=command_id,
                    command_code=code,
                    sim=sim or '',  # ← НОВОЕ!
                    params=params,
                    priority=priority or 2,
                    requested_by=requested_by or 'system',
                    created_at=created_at
                )
                tasks.append(task)

            if tasks:
                self.logger.debug(f"Получено задач из БД: {len(tasks)}")

            return tasks

        except Exception as e:
            self.logger.error(f"Ошибка получения задач из БД: {e}")
            return []

    def _worker_loop(self) -> None:
        """Основной цикл рабочего потока"""
        thread_name = threading.current_thread().name
        self.logger.debug(f"Рабочий поток {thread_name} запущен")

        while self._running:
            try:
                try:
                    task = self._queue.get(timeout=self.poll_interval)
                except Empty:
                    continue

                if not self._running:
                    break

                self._process_task(task)
                self._queue.task_done()

            except Exception as e:
                self.logger.error(f"Ошибка в рабочем потоке {thread_name}: {e}", exc_info=True)

        self.logger.debug(f"Рабочий поток {thread_name} остановлен")

    # def _process_task(self, task: CommandTask) -> None:
    #     """Обрабатывает одну задачу"""
    #     self.logger.info(f"Обработка задачи: {task}")
    #     task.started_at = datetime.now(timezone.utc)
    #
    #     try:
    #         handler = self.command_handlers.get(task.command_code)
    #
    #         if handler is None:
    #             raise ValueError(f"Обработчик для команды '{task.command_code}' не найден")
    #
    #         result = handler(task.params)
    #
    #         task.completed_at = datetime.now(timezone.utc)
    #         self._processed_count += 1
    #
    #         self._update_task_status(
    #             task.task_id,
    #             ExecutorConfig.STATUS_DONE,
    #             result_message=json.dumps(result) if result else 'OK'
    #         )
    #
    #         self.logger.info(f"✅ Задача {task.task_id} выполнена успешно")
    #
    #     except Exception as e:
    #         self.logger.error(f"❌ Ошибка выполнения задачи {task.task_id}: {e}", exc_info=True)
    #         task.error_message = str(e)
    #         task.retry_count += 1

    def _process_task(self, task: CommandTask) -> None:
        """Обрабатывает одну задачу"""
        self.logger.info(f"Обработка задачи: {task} для устройства {task.sim}")
        task.started_at = datetime.now(timezone.utc)

        try:
            handler = self.command_handlers.get(task.command_code)

            if handler is None:
                raise ValueError(f"Обработчик для команды '{task.command_code}' не найден")

            # Вызов обработчика с параметрами и sim
            result = handler(task.params, task.sim)

            task.completed_at = datetime.now(timezone.utc)
            self._processed_count += 1

            # Обновляем статус в БД
            self._update_task_status(
                task.task_id,
                ExecutorConfig.STATUS_DONE,
                result_message=json.dumps(result) if result else 'OK'
            )

            self.logger.info(f"✅ Задача {task.task_id} выполнена для {task.sim}")

        except Exception as e:
            self.logger.error(f"❌ Ошибка выполнения задачи {task.task_id}: {e}", exc_info=True)
            task.error_message = str(e)
            task.retry_count += 1

            if task.retry_count < ExecutorConfig.DEFAULT_MAX_RETRIES:
                self._update_task_status(
                    task.task_id,
                    ExecutorConfig.STATUS_PENDING,
                    result_message=f"Ошибка: {e}. Попытка {task.retry_count}"
                )
                time.sleep(ExecutorConfig.DEFAULT_RETRY_DELAY_SEC)
                try:
                    self._queue.put_nowait(task)
                except Exception:
                    self._failed_count += 1
                    self._update_task_status(
                        task.task_id,
                        ExecutorConfig.STATUS_FAILED,
                        result_message=f"Ошибка после {task.retry_count} попыток: {e}"
                    )
            else:
                self._failed_count += 1
                self._update_task_status(
                    task.task_id,
                    ExecutorConfig.STATUS_FAILED,
                    result_message=f"Ошибка после {task.retry_count} попыток: {e}"
                )

    def _update_task_status(
            self,
            task_id: int,
            status: str,
            result_message: str = None
    ) -> None:
        """Обновляет статус задачи в БД"""
        try:
            now = datetime.now(timezone.utc)

            if status == ExecutorConfig.STATUS_DONE:
                self.db.execute("""
                    UPDATE commands_queue 
                    SET status = %s, 
                        result_message = %s,
                        executed_at = %s
                    WHERE id = %s
                """, (status, result_message, now, task_id))

            elif status == ExecutorConfig.STATUS_FAILED:
                self.db.execute("""
                    UPDATE commands_queue 
                    SET status = %s, 
                        result_message = %s,
                        executed_at = %s
                    WHERE id = %s
                """, (status, result_message, now, task_id))

            elif status == ExecutorConfig.STATUS_PROCESSING:
                self.db.execute("""
                    UPDATE commands_queue 
                    SET status = %s,
                        started_at = %s
                    WHERE id = %s
                """, (status, now, task_id))

            else:  # PENDING
                self.db.execute("""
                    UPDATE commands_queue 
                    SET status = %s, 
                        result_message = %s
                    WHERE id = %s
                """, (status, result_message, task_id))

        except Exception as e:
            self.logger.error(f"Ошибка обновления статуса задачи {task_id}: {e}")

    # def submit_command(
    #         self,
    #         command_code: str,
    #         params: Dict[str, Any] = None,
    #         priority: int = 2,
    #         requested_by: str = 'system'
    # ) -> Optional[int]:
    #     """Отправляет команду напрямую в очередь (без БД)"""
    #     if not self._running:
    #         self.logger.warning("Исполнитель не запущен")
    #         return None
    #
    #     task = CommandTask(
    #         task_id=0,
    #         command_id=0,
    #         command_code=command_code,
    #         params=params or {},
    #         priority=priority,
    #         requested_by=requested_by
    #     )
    #
    #     try:
    #         self._queue.put_nowait(task)
    #         self.logger.debug(f"Команда отправлена напрямую: {command_code}")
    #         return id(task)
    #     except Exception as e:
    #         self.logger.warning(f"Очередь переполнена: {e}")
    #         return None
    def submit_command(
            self,
            command_code: str,
            sim: str,  # ← НОВОЕ!
            params: Dict[str, Any] = None,
            priority: int = 2,
            requested_by: str = 'system'
    ) -> Optional[int]:
        """
        Отправляет команду напрямую в очередь

        Args:
            command_code: Код команды
            sim: SIM устройства ← НОВОЕ!
            params: Параметры команды
            priority: Приоритет
            requested_by: Имя запросившего
        """
        if not self._running:
            self.logger.warning("Исполнитель не запущен")
            return None

        # Получаем command_id из реестра
        command_meta = None
        for code, meta in self.command_handlers.items():
            if code == command_code:
                command_meta = meta
                break

        if not command_meta:
            self.logger.error(f"Команда {command_code} не найдена")
            return None

        task = CommandTask(
            task_id=0,
            command_id=0,  # Нужно получить из БД
            command_code=command_code,
            sim=sim,  # ← НОВОЕ!
            params=params or {},
            priority=priority,
            requested_by=requested_by
        )

        try:
            self._queue.put_nowait(task)
            self.logger.debug(f"Команда отправлена напрямую: {command_code} для {sim}")
            return id(task)
        except Exception as e:
            self.logger.warning(f"Очередь переполнена: {e}")
            return None

    def get_stats(self) -> dict:
        """Возвращает статистику исполнителя"""
        return {
            'running': self._running,
            'queue_size': self._queue.qsize(),
            'queue_max': self.queue_size,
            'processed_count': self._processed_count,
            'failed_count': self._failed_count,
            'cancelled_count': self._cancelled_count,
            'worker_threads': len(self._workers),
            'registered_handlers': len(self.command_handlers),
            'uptime_seconds': (
                (datetime.now(timezone.utc) - self._start_time).total_seconds()
                if self._start_time else 0
            )
        }

    def get_queue_info(self) -> dict:
        """Возвращает информацию об очереди"""
        return {
            'size': self._queue.qsize(),
            'max_size': self.queue_size,
            'empty': self._queue.empty(),
            'full': self._queue.full()
        }

    def clear_queue(self) -> int:
        """Очищает очередь задач"""
        count = 0
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
                count += 1
                self._cancelled_count += 1
            except Empty:
                break

        self.logger.info(f"Очередь очищена ({count} задач)")
        return count

    def __repr__(self) -> str:
        return (
            f"CommandExecutor(running={self._running}, "
            f"queue={self._queue.qsize()}/{self.queue_size}, "
            f"processed={self._processed_count})"
        )
