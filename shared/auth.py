"""
shared/auth.py — API аутентификация и rate limiting.

v7.0:
- API key теперь ОБЯЗАТЕЛЕН (если ARCH_API_KEYS настроен)
- Rate limiter: Redis-based (с fallback на in-memory)
- Structured logging

Использование:
    from shared.auth import get_api_key, rate_limit_middleware

    @app.get("/protected")
    async def protected(api_key: str = Depends(get_api_key)):
        ...
"""

import logging
import os
import time
from collections import defaultdict

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

logger = logging.getLogger("archai.auth")

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


def get_api_key_optional(api_key: str | None = Security(API_KEY_HEADER)) -> str | None:
    """Получить API key (необязательный). Если ключи не настроены — пропускает всех."""
    valid_keys = _load_api_keys()
    if not valid_keys:
        logger.warning("No API keys configured — auth disabled. Set ARCH_API_KEYS env var.")
        return None
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Pass X-API-Key header.",
        )
    if api_key not in valid_keys:
        logger.warning("Invalid API key attempt: %s...", api_key[:8] if len(api_key) > 8 else "***")
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key


def get_api_key_required(api_key: str = Security(API_KEY_HEADER)) -> str:
    """Получить API key (ОБЯЗАТЕЛЬНЫЙ). Без ключа — 401."""
    valid_keys = _load_api_keys()
    if not valid_keys:
        logger.error("CRITICAL: ARCH_API_KEYS not set — API is unsecured!")
        raise HTTPException(
            status_code=500,
            detail="Server misconfiguration: API keys not configured. Contact admin.",
        )
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Pass X-API-Key header.",
        )
    if api_key not in valid_keys:
        logger.warning("Invalid API key attempt")
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key


# ═══════════════════════════════════════════════════════════════
# RATE LIMITING — Redis-based (with in-memory fallback)
# ═══════════════════════════════════════════════════════════════

_redis_client = None


def _get_redis():
    """Get Redis client for rate limiting (lazy init)."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    redis_url = os.environ.get("REDIS_URL", "")
    if not redis_url:
        return None
    try:
        import redis

        _redis_client = redis.from_url(redis_url, decode_responses=True, socket_timeout=2)
        _redis_client.ping()
        logger.info("Rate limiter: Redis connected at %s", redis_url.split("@")[-1])
        return _redis_client
    except Exception as e:
        logger.warning("Rate limiter: Redis unavailable (%s), using in-memory fallback", e)
        _redis_client = None
        return None


class RateLimiter:
    """
    Rate limiter with Redis backend and in-memory fallback.

    In-memory mode: works for single-instance deployments.
    Redis mode: works across multiple instances.
    """

    def __init__(self, requests_per_minute: int = 30, requests_per_hour: int = 200):
        self.rpm = requests_per_minute
        self.rph = requests_per_hour
        # In-memory fallback
        self._minute_hits: dict[str, list[float]] = defaultdict(list)
        self._hour_hits: dict[str, list[float]] = defaultdict(list)

    def _get_client_id(self, request: Request) -> str:
        """Определяет клиента по IP или API key."""
        api_key = request.headers.get("X-API-Key", "")
        if api_key:
            return f"key:{api_key[:8]}"
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"
        return f"ip:{request.client.host if request.client else 'unknown'}"

    def _check_redis(self, client_id: str) -> None:
        """Check rate limit using Redis (sliding window)."""
        r = _get_redis()
        if r is None:
            return self._check_memory(client_id)

        now = time.time()
        pipe = r.pipeline()

        # Per-minute check
        minute_key = f"rl:minute:{client_id}"
        pipe.zremrangebyscore(minute_key, 0, now - 60)
        pipe.zadd(minute_key, {str(now): now})
        pipe.zcard(minute_key)
        pipe.expire(minute_key, 70)

        # Per-hour check
        hour_key = f"rl:hour:{client_id}"
        pipe.zremrangebyscore(hour_key, 0, now - 3600)
        pipe.zadd(hour_key, {str(now): now})
        pipe.zcard(hour_key)
        pipe.expire(hour_key, 3660)

        results = pipe.execute()
        minute_count = results[2]
        hour_count = results[6]

        if minute_count > self.rpm:
            logger.warning("Rate limit exceeded (per-minute): %s hits for %s", minute_count, client_id)
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {self.rpm} requests/minute",
                headers={"Retry-After": "60"},
            )
        if hour_count > self.rph:
            logger.warning("Rate limit exceeded (per-hour): %s hits for %s", hour_count, client_id)
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {self.rph} requests/hour",
                headers={"Retry-After": "3600"},
            )

    def _check_memory(self, client_id: str) -> None:
        """Check rate limit using in-memory counters (fallback)."""
        now = time.time()

        self._minute_hits[client_id] = [h for h in self._minute_hits[client_id] if now - h < 60.0]
        if len(self._minute_hits[client_id]) >= self.rpm:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {self.rpm} requests/minute",
                headers={"Retry-After": "60"},
            )

        self._hour_hits[client_id] = [h for h in self._hour_hits[client_id] if now - h < 3600.0]
        if len(self._hour_hits[client_id]) >= self.rph:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {self.rph} requests/hour",
                headers={"Retry-After": "3600"},
            )

        self._minute_hits[client_id].append(now)
        self._hour_hits[client_id].append(now)

    def check(self, request: Request) -> None:
        """Проверяет rate limit. Выбрасывает HTTPException при превышении."""
        client_id = self._get_client_id(request)
        self._check_redis(client_id)


# Глобальный rate limiter
_default_limiter = RateLimiter(requests_per_minute=30, requests_per_hour=200)


async def rate_limit_middleware(request: Request) -> None:
    """Dependency для rate limiting в FastAPI."""
    _default_limiter.check(request)
