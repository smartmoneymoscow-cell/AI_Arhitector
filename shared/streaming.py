"""
shared/streaming.py — SSE (Server-Sent Events) progress streaming.

Позволяет клиенту получать real-time обновления прогресса генерации
без polling.

Использование:
    # Бэкенд (FastAPI):
    from shared.streaming import ProgressStreamer

    streamer = ProgressStreamer(job_id)
    streamer.emit("parse", "running", progress=10)
    streamer.emit("geometry", "running", progress=50)
    streamer.emit("render", "done", progress=100)

    # Endpoint:
    @app.get("/api/v1/stream/{job_id}")
    async def stream(job_id: str):
        return EventSourceResponse(stream_generator(job_id))
"""

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field


@dataclass
class ProgressEvent:
    """Одно событие прогресса."""

    job_id: str
    step: str
    status: str  # "running" | "done" | "failed"
    progress: int  # 0-100
    message: str = ""
    data: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_sse(self) -> str:
        """Формат SSE: data: {...}\n\n"""
        payload = {
            "job_id": self.job_id,
            "step": self.step,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "timestamp": self.timestamp,
        }
        if self.data:
            payload["data"] = self.data
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "step": self.step,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "data": self.data,
            "timestamp": self.timestamp,
        }


class ProgressStreamer:
    """
    Накапливает события прогресса для конкретной задачи.
    Клиенты подключаются через SSE и получают события в реальном времени.
    """

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.events: list[ProgressEvent] = []
        self._subscribers: list[asyncio.Queue] = []
        self._finished = False

    def emit(self, step: str, status: str, progress: int = 0, message: str = "", data: dict | None = None):
        """Добавить событие и уведомить подписчиков."""
        event = ProgressEvent(
            job_id=self.job_id,
            step=step,
            status=status,
            progress=progress,
            message=message,
            data=data or {},
        )
        self.events.append(event)

        # Уведомить всех подписчиков
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass  # Пропускаем если очередь полна

        if status in ("done", "failed"):
            self._finished = True

    async def subscribe(self) -> AsyncGenerator[ProgressEvent, None]:
        """Подписаться на события (для SSE endpoint)."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(queue)

        try:
            # Сначала отправить все накопленные события
            for event in self.events:
                yield event

            # Если задача уже завершена — выйти
            if self._finished:
                return

            # Ждать новые события
            while not self._finished:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield event
                    if event.status in ("done", "failed"):
                        return
                except TimeoutError:
                    # Heartbeat каждые30с (предотвращает disconnect)
                    yield ProgressEvent(
                        job_id=self.job_id,
                        step="heartbeat",
                        status="running",
                        progress=self._get_current_progress(),
                        message="still processing...",
                    )
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    def _get_current_progress(self) -> int:
        """Текущий прогресс из последнего события."""
        if self.events:
            return self.events[-1].progress
        return 0

    @property
    def is_finished(self) -> bool:
        return self._finished


# ═══════════════════════════════════════════════════════════════
# GLOBAL STREAMER REGISTRY
# ═══════════════════════════════════════════════════════════════

_streamers: dict[str, ProgressStreamer] = {}


def get_streamer(job_id: str) -> ProgressStreamer | None:
    """Получить streamer по job_id."""
    return _streamers.get(job_id)


def create_streamer(job_id: str) -> ProgressStreamer:
    """Создать новый streamer."""
    streamer = ProgressStreamer(job_id)
    _streamers[job_id] = streamer
    return streamer


def cleanup_streamers(max_age_seconds: int = 3600):
    """Удалить старые streamers (вызывать периодически)."""
    now = time.time()
    expired = [
        jid
        for jid, s in _streamers.items()
        if s.is_finished and (now - (s.events[-1].timestamp if s.events else 0)) > max_age_seconds
    ]
    for jid in expired:
        del _streamers[jid]
