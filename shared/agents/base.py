"""
shared/agents/base.py — Базовые классы для multi-agent системы.
"""

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Task:
    """Задача для агента."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    agent: str = ""
    params: dict = field(default_factory=dict)
    parent_id: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    result: Optional["TaskResult"] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    def start(self):
        self.status = TaskStatus.RUNNING
        self.started_at = time.time()

    def complete(self, result: "TaskResult"):
        self.status = TaskStatus.DONE
        self.result = result
        self.finished_at = time.time()

    def fail(self, error: str):
        self.status = TaskStatus.FAILED
        self.result = TaskResult(status=TaskStatus.FAILED, error=error)
        self.finished_at = time.time()

    @property
    def duration_ms(self) -> float:
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at) * 1000
        return 0


@dataclass
class TaskResult:
    """Результат выполнения задачи."""
    status: TaskStatus = TaskStatus.DONE
    data: Any = None
    error: Optional[str] = None
    duration_ms: float = 0
    metadata: dict = field(default_factory=dict)


class BaseAgent(ABC):
    """Базовый класс для всех агентов."""

    name: str = "base"

    @abstractmethod
    def process(self, task: Task) -> TaskResult:
        """
        Обработать задачу и вернуть результат.

        Args:
            task: задача с параметрами

        Returns:
            TaskResult с данными или ошибкой
        """
        ...

    def can_handle(self, task: Task) -> bool:
        """Может ли агент обработать эту задачу."""
        return task.agent == self.name

    def decompose(self, task: Task) -> list[Task]:
        """
        Разбить задачу на подзадачи.
        По умолчанию — нет декомпозиции (одна задача = один шаг).
        Переопределяется в агентах для параллельного выполнения.
        """
        return [task]
