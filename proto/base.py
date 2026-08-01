"""
proto/base.py — SHARED base types for agents (protocol only).

ONLY data types and enums. NO business logic.
NO imports from services, httpx, redis, blender.
"""

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Task:
    """Task for an agent."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    agent: str = ""
    params: dict = field(default_factory=dict)
    parent_id: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    result: "TaskResult | None" = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None

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
    """Result of agent task execution."""
    status: TaskStatus = TaskStatus.DONE
    data: Any = None
    error: str | None = None
    duration_ms: float = 0
    metadata: dict = field(default_factory=dict)


class BaseAgent(ABC):
    """Base class for all agents. ONLY interface, NO implementation."""

    name: str = "base"

    @abstractmethod
    def process(self, task: Task) -> TaskResult:
        """Process a task and return result."""
        ...

    def can_handle(self, task: Task) -> bool:
        return task.agent == self.name

    def decompose(self, task: Task) -> list[Task]:
        return [task]
