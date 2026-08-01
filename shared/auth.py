"""
shared/auth.py — API аутентификация и rate limiting.

Использование:
    from shared.auth import get_api_key, rate_limit_middleware

    @app.get("/protected")
    async def protected(api_key: str = Depends(get_api_key)):
        ...
"""

import os
import time
from collections import defaultdict
from typing import Optional

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from shared.config import settings

# ═══════════════════════════════════════════════════════════════
# API KEY AUTH
# ═══════════════════════════════════════════════════════════════

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

# Ключи из env: ARCH_API_KEYS="key1,key2,key3"
_api_keys: set[str] = set()


def _load_api_keys() -> set[str]:
    """Загружает API ключи из переменной окружения."""
    global _api_keys
    if _api_keys:
        return _api_keys
    raw = os.environ.get("ARCH_API_KEYS", "")
    if raw:
        _api_keys = {k.strip() for k in raw.split(",") if k.strip()}
    return _api_keys


def get_api_key_optional(api_key: Optional[str] = Security(API_KEY_HEADER)) -> Optional[str]:
    """Получить API key (необязательный). Если ключи не настроены — пропускает всех."""
    valid_keys = _load_api_keys()
    if not valid_keys:
        return None  # Auth не настроен — пропускаем
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Pass X-API-Key header.",
        )
    if api_key not in valid_keys:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key


def get_api_key_required(api_key: str = Security(API_KEY_HEADER)) -> str:
    """Получить API key (обязательный)."""
    valid_keys = _load_api_keys()
    if not valid_keys:
        return "open"  # Auth не настроен
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Pass X-API-Key header.",
        )
    if api_key not in valid_keys:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key


# ═══════════════════════════════════════════════════════════════
# RATE LIMITING (in-memory, per-IP)
# ═══════════════════════════════════════════════════════════════

class RateLimiter:
    """
    Простой in-memory rate limiter.
    В production заменить на Redis-based (aioredis).
    """

    def __init__(self, requests_per_minute: int = 30, requests_per_hour: int = 200):
        self.rpm = requests_per_minute
        self.rph = requests_per_hour
        self._minute_hits: dict[str, list[float]] = defaultdict(list)
        self._hour_hits: dict[str, list[float]] = defaultdict(list)

    def _get_client_id(self, request: Request) -> str:
        """Определяет клиента по IP или API key."""
        # Приоритет: API key > X-Forwarded-For > client IP
        api_key = request.headers.get("X-API-Key", "")
        if api_key:
            return f"key:{api_key[:8]}"
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"
        return f"ip:{request.client.host if request.client else 'unknown'}"

    def _cleanup(self, hits: list[float], window: float) -> list[float]:
        """Удаляет старые hits за пределами окна."""
        now = time.time()
        return [h for h in hits if now - h < window]

    def check(self, request: Request) -> None:
        """Проверяет rate limit. Выбрасывает HTTPException при превышении."""
        client_id = self._get_client_id(request)
        now = time.time()

        # Check per-minute
        self._minute_hits[client_id] = self._cleanup(
            self._minute_hits[client_id], 60.0
        )
        if len(self._minute_hits[client_id]) >= self.rpm:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {self.rpm} requests/minute",
                headers={"Retry-After": "60"},
            )

        # Check per-hour
        self._hour_hits[client_id] = self._cleanup(
            self._hour_hits[client_id], 3600.0
        )
        if len(self._hour_hits[client_id]) >= self.rph:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {self.rph} requests/hour",
                headers={"Retry-After": "3600"},
            )

        # Record hit
        self._minute_hits[client_id].append(now)
        self._hour_hits[client_id].append(now)

    def get_stats(self) -> dict:
        """Статистика rate limiter."""
        return {
            "tracked_clients": len(self._hour_hits),
            "rpm_limit": self.rpm,
            "rph_limit": self.rph,
        }


# Глобальный экземпляр
rate_limiter = RateLimiter()


def check_rate_limit(request: Request) -> None:
    """Dependency для FastAPI."""
    rate_limiter.check(request)
