# tests/unit/test_executor.py
# -*- coding: utf-8 -*-

import pytest
import time
from unittest.mock import MagicMock

from opc.commands.executor import OpcCommandReceiver, CommandTask, ExecutorConfig


class TestCommandTask:

    @pytest.mark.unit
    def test_create_task(self):
        """Создание задачи"""
        task = CommandTask(
            task_id=1,
            command_id=10,
            command_code='TEST_CMD',
            params={'value': 42}
        )

        assert task.task_id == 1
        assert task.command_code == 'TEST_CMD'
        assert task.params == {'value': 42}
        assert task.retry_count == 0

    @pytest.mark.unit
    def test_task_to_dict(self):
        """Конвертация задачи в словарь"""
        task = CommandTask(
            task_id=1,
            command_id=10,
            command_code='TEST_CMD',
            params={'value': 42}
        )

        d = task.to_dict()

        assert d['task_id'] == 1
        assert d['command_code'] == 'TEST_CMD'
        assert 'created_at' in d


class TestCommandExecutor:

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.query = MagicMock(return_value=[])
        db.execute = MagicMock()
        return db

    @pytest.fixture
    def executor(self, mock_db):
        exec = OpcCommandReceiver(
            db=mock_db,
            queue_size=10,
            poll_interval_sec=1,
            worker_threads=1
        )
        return exec

    @pytest.mark.unit
    def test_start_stop(self, executor):
        """Запуск и остановка исполнителя"""
        assert not executor.is_running()

        executor.start()
        assert executor.is_running()

        time.sleep(0.5)

        executor.stop()
        assert not executor.is_running()

    @pytest.mark.unit
    def test_register_handler(self, executor):
        """Регистрация обработчика"""
        handler = lambda params: {'ok': True}

        executor.register_handler('TEST_CMD', handler)

        assert 'TEST_CMD' in executor.get_registered_handlers()

    @pytest.mark.unit
    def test_unregister_handler(self, executor):
        """Отмена регистрации обработчика"""
        handler = lambda params: {'ok': True}
        executor.register_handler('TEST_CMD', handler)
        executor.unregister_handler('TEST_CMD')

        assert 'TEST_CMD' not in executor.get_registered_handlers()

    @pytest.mark.unit
    def test_get_stats(self, executor):
        """Получение статистики"""
        stats = executor.get_stats()

        assert 'running' in stats
        assert 'queue_size' in stats
        assert 'processed_count' in stats
        assert stats['processed_count'] == 0

    @pytest.mark.unit
    def test_get_queue_info(self, executor):
        """Информация об очереди"""
        info = executor.get_queue_info()

        assert 'size' in info
        assert 'max_size' in info
        assert info['max_size'] == 10

    @pytest.mark.unit
    def test_clear_queue(self, executor):
        """Очистка очереди"""
        # Добавляем задачи
        for i in range(5):
            task = CommandTask(i, 0, 'CMD', {})
            executor._queue.put(task)

        count = executor.clear_queue()

        assert count == 5
        assert executor._queue.empty()

    @pytest.mark.unit
    def test_submit_command(self, executor):
        """Отправка команды напрямую"""
        executor.start()
        time.sleep(0.5)

        task_id = executor.submit_command(
            command_code='TEST_CMD',
            params={'value': 42},
            priority=1
        )

        assert task_id is not None

        executor.stop()