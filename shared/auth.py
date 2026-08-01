"""
shared/auth.py — API auth + rate limiting with fixes.

Fixes:
  S1 — API key MANDATORY (if ARCH_API_KEYS configured)
  S3 — Keys masked in logs
  S5 — Trusted proxy for rate limiting (Nginx only)
"""

import logging
import os
import time
from collections import defaultdict

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

logger = logging.getLogger("archai.auth")

# ═══════════════════════════════════════════════════════════════
# S3: KEY MASKING — never log full keys
# ═══════════════════════════════════════════════════════════════

def _mask_key(key: str) -> str:
    """Mask API key for safe logging. S3 fix."""
    if not key or len(key) < 8:
        return "***"
    return f"{key[:4]}***{key[-3:]}"


# ═══════════════════════════════════════════════════════════════
# API KEY AUTH
# ═══════════════════════════════════════════════════════════════

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

_api_keys: set[str] = set()


def _load_api_keys() -> set[str]:
    global _api_keys
    if _api_keys:
        return _api_keys
    raw = os.environ.get("ARCH_API_KEYS", "")
    if raw:
        _api_keys = {k.strip() for k in raw.split(",") if k.strip()}
    return _api_keys


def get_api_key_required(api_key: str = Security(API_KEY_HEADER)) -> str:
    """S1: API key MANDATORY. Without key → 401. Without config → 500."""
    valid_keys = _load_api_keys()
    if not valid_keys:
        logger.error("CRITICAL: ARCH_API_KEYS not set — API is unsecured!")
        raise HTTPException(
            status_code=500,
            detail="Server misconfiguration: API keys not configured.",
        )
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key. Pass X-API-Key header.")
    if api_key not in valid_keys:
        logger.warning("Invalid API key attempt: %s", _mask_key(api_key))  # S3: masked
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key


def get_api_key_optional(api_key: str | None = Security(API_KEY_HEADER)) -> str | None:
    """Optional auth. Only used for endpoints that can be public."""
    valid_keys = _load_api_keys()
    if not valid_keys:
        return None
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key.")
    if api_key not in valid_keys:
        logger.warning("Invalid API key: %s", _mask_key(api_key))  # S3: masked
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key


# ═══════════════════════════════════════════════════════════════
# S5: TRUSTED PROXIES — only trust Nginx
# ═══════════════════════════════════════════════════════════════

# Docker internal network — Nginx is the only proxy
TRUSTED_PROXIES = {
    "172.16.0.0/12",  # Docker default network
    "10.0.0.0/8",     # Docker custom network
    "127.0.0.1",      # localhost
}

def _get_real_ip(request: Request) -> str:
    """S5: Get real client IP, trusting ONLY Nginx (not client headers)."""
    # Only trust X-Forwarded-For from known proxies
    client_ip = request.client.host if request.client else "unknown"
    
    # Check if request comes from trusted proxy (Nginx)
    from ipaddress import ip_address, ip_network
    is_trusted = False
    for proxy in TRUSTED_PROXIES:
        try:
            if ip_address(client_ip) in ip_network(proxy):
                is_trusted = True
                break
        except ValueError:
            continue
    
    if is_trusted:
        # Trust X-Forwarded-For from Nginx
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            # Take the FIRST IP (original client), not the last (Nginx)
            return forwarded.split(",")[0].strip()
    
    # Not from trusted proxy → use direct IP
    return client_ip


# ═══════════════════════════════════════════════════════════════
# RATE LIMITING — Redis-based with trusted IP
# ═══════════════════════════════════════════════════════════════

_redis_client = None

def _get_redis():
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
        return _redis_client
    except Exception:
        _redis_client = None
        return None


class RateLimiter:
    def __init__(self, requests_per_minute: int = 30, requests_per_hour: int = 200):
        self.rpm = requests_per_minute
        self.rph = requests_per_hour
        self._minute_hits: dict[str, list[float]] = defaultdict(list)
        self._hour_hits: dict[str, list[float]] = defaultdict(list)

    def _get_client_id(self, request: Request) -> str:
        """S5: Use real IP from trusted proxy."""
        api_key = request.headers.get("X-API-Key", "")
        if api_key:
            return f"key:{_mask_key(api_key)}"  # S3: masked
        
        real_ip = _get_real_ip(request)  # S5: trusted proxy
        return f"ip:{real_ip}"

    def _check_redis(self, client_id: str) -> None:
        r = _get_redis()
        if r is None:
            return self._check_memory(client_id)

        now = time.time()
        pipe = r.pipeline()

        minute_key = f"rl:minute:{client_id}"
        pipe.zremrangebyscore(minute_key, 0, now - 60)
        pipe.zadd(minute_key, {str(now): now})
        pipe.zcard(minute_key)
        pipe.expire(minute_key, 70)

        hour_key = f"rl:hour:{client_id}"
        pipe.zremrangebyscore(hour_key, 0, now - 3600)
        pipe.zadd(hour_key, {str(now): now})
        pipe.zcard(hour_key)
        pipe.expire(hour_key, 3660)

        results = pipe.execute()
        minute_count = results[2]
        hour_count = results[6]

        if minute_count > self.rpm:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {self.rpm} requests/minute",
                headers={"Retry-After": "60"},
            )
        if hour_count > self.rph:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {self.rph} requests/hour",
                headers={"Retry-After": "3600"},
            )

    def _check_memory(self, client_id: str) -> None:
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
        client_id = self._get_client_id(request)
        self._check_redis(client_id)


_rate_limiter = RateLimiter()

async def rate_limit_middleware(request: Request) -> None:
    """FastAPI dependency for rate limiting."""
    _rate_limiter.check(request)
