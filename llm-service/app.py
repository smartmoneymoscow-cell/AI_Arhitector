"""
LLM Microservice — LLM-only парсинг промтов через OpenRouter.

v6.0 — БЕЗ REGEX FALLBACK.
Каскад 7 моделей: сильная → средняя → слабая → бесплатные.
Кеш: Redis (L2) + in-memory (L1).
Если все модели недоступны → HTTP 503.
"""

import asyncio
import logging
import os


import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from shared.config import settings
from shared.logging_config import setup_logging
from shared.models import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ParsedParams,
    ParseRequest,
)
from shared.parser import (
    LLM_CASCADE,
    AllModelsFailedError,
    get_cache_stats,
    parse_prompt_async,
    discover_free_models,
    get_active_cascade,
    get_discovery_stats,
    invalidate_discovery,
    proactive_health_loop,
    _get_api_keys,
    _filter_alive,
    _mark_key_dead,
    _looks_like_quota_exhausted,
    _mask_key,
    _cascade_is_stale,
    _COOLDOWN_RATE_LIMIT,
    _COOLDOWN_QUOTA_EXHAUSTED,
    _DISCOVER_TTL,
)

setup_logging("llm-service")
logger = logging.getLogger("archai.llm")

app = FastAPI(
    title="Architect LLM Service",
    description="LLM-only парсинг архитектурных промтов (каскад 7 моделей, Redis кеш)",
    version="7.0.0",
)

_cors_origins = os.environ.get("CORS_ORIGINS", "")
if not _cors_origins:
    logger.warning("CORS_ORIGINS not set — defaulting to empty (no CORS). Set env var for production.")
_origins_list = [o.strip() for o in _cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════
# Фоновое проактивное обновление списка бесплатных моделей.
#
# Раньше обновление списка бесплатных моделей OpenRouter случалось
# только "по требованию" внутри пользовательского запроса — и то
# из-за бага срабатывало лишь ОДИН раз за всё время жизни процесса.
# Теперь отдельная фоновая корутина каждые _DISCOVER_TTL секунд сама
# ходит в OpenRouter /models и обновляет кэш (в памяти + Redis), так
# что пользовательские запросы почти всегда получают уже тёплый,
# актуальный список и не платят задержкой за обновление.
# ═══════════════════════════════════════════════════════════════

_discovery_task: asyncio.Task | None = None
_health_check_task: asyncio.Task | None = None


async def _discovery_background_loop():
    # Небольшая случайная задержка перед первым запуском, чтобы не
    # штурмовать OpenRouter в момент старта, если поднимается сразу
    # несколько инстансов сервиса.
    await asyncio.sleep(5)
    while True:
        try:
            api_key = os.environ.get("OPENROUTER_API_KEY", "") or (
                _filter_alive(_get_api_keys())[0] if _get_api_keys() else ""
            )
            if api_key:
                models = await discover_free_models(api_key)
                logger.info("Background discovery: %d free models cached", len(models))
            else:
                logger.warning("Background discovery: no OPENROUTER_API_KEY, skipping")
        except Exception as e:
            logger.warning("Background discovery loop error: %s", e)
        await asyncio.sleep(_DISCOVER_TTL)


@app.on_event("startup")
async def _on_startup():
    global _discovery_task, _health_check_task
    # Eager discovery: обновляем список бесплатных моделей СРАЗУ при старте,
    # а не ждём первого пользовательского запроса или первого тика фонового цикла.
    try:
        api_key = os.environ.get("OPENROUTER_API_KEY", "") or (
            _filter_alive(_get_api_keys())[0] if _get_api_keys() else ""
        )
        if api_key:
            models = await discover_free_models(api_key)
            logger.info("Eager discovery at startup: %d free models", len(models))
    except Exception as e:
        logger.warning("Eager discovery at startup failed: %s", e)
    _discovery_task = asyncio.create_task(_discovery_background_loop())
    _health_check_task = asyncio.create_task(proactive_health_loop())
    logger.info("Proactive key health check started")


@app.on_event("shutdown")
async def _on_shutdown():
    if _discovery_task:
        _discovery_task.cancel()
    if _health_check_task:
        _health_check_task.cancel()


@app.get("/health")
async def health():
    # Fast health check — don't wait for Redis
    gemini_configured = bool(os.environ.get("GOOGLE_API_KEY", ""))
    return HealthResponse(
        status="ok",
        service="llm-service",
        version="8.0.0",
        model=settings.LLM_MODEL,
        services={"gemini": "configured" if gemini_configured else "not_configured"},
    )


@app.post("/api/v1/chat/completions", response_model=ChatResponse)
async def chat_completions(req: ChatRequest):
    """Chat proxy to OpenRouter — перебирает ВСЕ аккаунты (primary + fallback),
    автоматически пропуская те, что сейчас 'остывают' после 429/402,
    и переключаясь на следующий при исчерпании текущего."""
    all_keys = _get_api_keys()
    if not all_keys:
        raise HTTPException(503, "No OPENROUTER_API_KEY configured")

    keys = _filter_alive(all_keys)

    payload = {
        "model": req.model or settings.LLM_MODEL,
        "messages": [m.model_dump() for m in req.messages],
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
    }

    last_error: tuple[int, str] | None = None

    for key in keys:
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {key}",
            "HTTP-Referer": "https://archai.app",
            "X-Title": "Architect LLM",
        }
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{settings.OPENROUTER_BASE}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60.0,
                )
        except httpx.TimeoutException:
            last_error = (504, "OpenRouter timeout")
            continue
        except Exception as e:
            last_error = (502, str(e))
            continue

        if r.status_code == 200:
            return r.json()

        if r.status_code in (429, 402):
            if _looks_like_quota_exhausted(r.status_code, r.text):
                _mark_key_dead(key, _COOLDOWN_QUOTA_EXHAUSTED, f"chat_http_{r.status_code}_quota")
            else:
                _mark_key_dead(key, _COOLDOWN_RATE_LIMIT, f"chat_http_{r.status_code}_rate_limit")
            logger.warning("chat_completions: key %s exhausted, switching account", _mask_key(key))
            last_error = (r.status_code, r.text)
            continue

        # Другая ошибка (400/500 и т.п.) — не проблема ключа, дальше пробовать бессмысленно
        raise HTTPException(status_code=r.status_code, detail=r.text)

    status, detail = last_error or (503, "No live OpenRouter keys")
    raise HTTPException(status_code=status if status in (429, 402) else 503, detail=detail)


@app.post("/api/v1/parse", response_model=ParsedParams)
async def parse_prompt_endpoint(req: ParseRequest):
    """
    Парсинг промта → структурированные параметры.
    LLM-only (каскад 7 моделей). БЕЗ regex fallback.
    Кеш: Redis + in-memory.
    """
    try:
        params = await parse_prompt_async(req.text)
        return ParsedParams(**params)
    except AllModelsFailedError as e:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "all_models_failed",
                "message": str(e),
                "cascade": [m["model"] for m in LLM_CASCADE],
            },
        )
    except Exception as e:
        logger.error("Parse unexpected error: %s: %s", type(e).__name__, str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "parse_error",
                "message": f"{type(e).__name__}: {str(e)[:500]}",
            },
        )


@app.get("/api/v1/keys/status")
async def keys_status():
    """Сколько аккаунтов настроено / живо прямо сейчас (для мониторинга)."""
    from shared.parser import _get_google_keys, _is_key_cooling

    or_keys = _get_api_keys()
    gm_keys = _get_google_keys()

    def _status(keys):
        return [
            {"key": _mask_key(k), "alive": not _is_key_cooling(k)}
            for k in keys
        ]

    or_status = _status(or_keys)
    gm_status = _status(gm_keys)
    return {
        "openrouter": {"total": len(or_keys), "alive": sum(s["alive"] for s in or_status), "keys": or_status},
        "gemini": {"total": len(gm_keys), "alive": sum(s["alive"] for s in gm_status), "keys": gm_status},
        "total_accounts": len(or_keys) + len(gm_keys),
    }


@app.get("/api/v1/cache/stats")
async def cache_stats():
    """Статистика кеша парсинга."""
    return get_cache_stats()


@app.get("/api/v1/models/discover")
async def models_discover():
    """Trigger free model discovery and return results."""
    from shared.config import settings
    api_key = settings.OPENROUTER_API_KEY or os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise HTTPException(503, "No OPENROUTER_API_KEY configured")
    models = await discover_free_models(api_key)
    return {
        "discovered": len(models),
        "models": models,
        "stats": get_discovery_stats(),
    }


@app.post("/api/v1/models/refresh")
async def models_refresh():
    """Force refresh of free model cache."""
    from shared.config import settings
    invalidate_discovery()
    api_key = settings.OPENROUTER_API_KEY or os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise HTTPException(503, "No OPENROUTER_API_KEY configured")
    models = await discover_free_models(api_key)
    return {
        "refreshed": True,
        "discovered": len(models),
        "models": [m["model"] for m in models[:20]],
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8081))
    logger.info("LLM Service starting on port %d", port)
    logger.info("Cascade: %s", [m["model"] for m in LLM_CASCADE])
    uvicorn.run(app, host="0.0.0.0", port=port)
