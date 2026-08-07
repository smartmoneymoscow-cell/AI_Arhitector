"""
LLM Microservice — LLM-only парсинг промтов через ModelManager.

v10.0 — Центральный менеджер моделей:
  - Auto-discovery бесплатных моделей каждые 4 часа
  - Ротация 8 OpenRouter ключей + 8 Gemini ключей
  - Каскад: OpenRouter free → Gemini free
  - Только бесплатные модели

Endpoints:
  POST /api/v1/parse          — парсинг промта
  POST /api/v1/chat/completions — chat proxy
  GET  /api/v1/models         — текущий каскад моделей
  POST /api/v1/models/refresh — принудительное обновление
  GET  /api/v1/models/health  — здоровье ключей
  GET  /api/v1/cache/stats    — статистика кеша
  GET  /health                — health check
"""

import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from shared.config import settings
from shared.logging_config import setup_logging
from shared.model_manager import AllModelsFailedError, get_model_manager
from shared.model_discovery import (
    get_discovery_status,
    start_discovery_scheduler,
    stop_discovery_scheduler,
)
from shared.models import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ParsedParams,
    ParseRequest,
)
from shared.parser import (
    get_cache_stats,
    parse_prompt_async,
)

setup_logging("llm-service")
logger = logging.getLogger("archai.llm")

app = FastAPI(
    title="Architect LLM Service",
    description="ModelManager: auto-discovery free models, 8 OpenRouter keys + 8 Gemini keys",
    version="10.0.0",
)

_cors_origins = os.environ.get("CORS_ORIGINS", "*")
_origins_list = [o.strip() for o in _cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════
# LIFESPAN — start/stop discovery scheduler
# ═══════════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    """Initialize ModelManager and start discovery scheduler."""
    manager = get_model_manager()
    logger.info(
        "LLM Service starting — %d OpenRouter keys, %d Gemini keys",
        len(manager._openrouter_keys), len(manager._gemini_keys),
    )
    # Start background discovery (every 4 hours)
    start_discovery_scheduler()
    # Run initial discovery
    try:
        models = await manager.discover_free_models(force=True)
        logger.info("Initial discovery: %d free models found", len(models))
    except Exception as e:
        logger.warning("Initial discovery failed: %s", e)


@app.on_event("shutdown")
async def shutdown():
    stop_discovery_scheduler()


# ═══════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    manager = get_model_manager()
    stats = manager.get_stats()
    return HealthResponse(
        status="ok",
        service="llm-service",
        version="10.0.0",
        model="ModelManager (auto-discovery)",
        services={
            "openrouter_keys": str(stats["openrouter_keys_available"]),
            "gemini_keys": str(stats["gemini_keys_available"]),
            "free_models": str(stats["free_models_count"]),
            "discovery_ago": str(stats["last_discovery_ago"]),
        },
    )


# ═══════════════════════════════════════════════════════════════
# PARSE — main endpoint
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/parse", response_model=ParsedParams)
async def parse_prompt_endpoint(req: ParseRequest):
    """
    Парсинг промта → структурированные параметры.

    Каскад: OpenRouter free models → Gemini (8 ключей).
    Только бесплатные модели. БЕЗ regex fallback.
    """
    try:
        params = await parse_prompt_async(req.text)
        return ParsedParams(**params)
    except AllModelsFailedError as e:
        manager = get_model_manager()
        stats = manager.get_stats()
        raise HTTPException(
            status_code=503,
            detail={
                "error": "all_models_failed",
                "message": str(e),
                "openrouter_keys": stats["openrouter_keys"],
                "gemini_keys": stats["gemini_keys"],
                "free_models": stats["free_models_count"],
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


# ═══════════════════════════════════════════════════════════════
# CHAT COMPLETIONS — proxy to ModelManager
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/chat/completions", response_model=ChatResponse)
async def chat_completions(req: ChatRequest):
    """Chat proxy через ModelManager (OpenRouter → Gemini cascade)."""
    manager = get_model_manager()

    messages = [{"role": "system", "content": "You are a helpful architectural assistant."}]
    for m in req.messages:
        messages.append({"role": m.role, "content": m.content})

    try:
        result = await manager.send_request(
            messages=messages,
            max_tokens=req.max_tokens or 500,
            temperature=req.temperature or 0.7,
        )
        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": result["content"],
                },
                "finish_reason": "stop",
            }],
            "model": result["model"],
            "provider": result["provider"],
        }
    except AllModelsFailedError as e:
        raise HTTPException(503, detail=str(e))
    except Exception as e:
        raise HTTPException(502, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# MODEL MANAGEMENT ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.get("/api/v1/models")
async def models_list():
    """Получить текущий каскад бесплатных моделей."""
    manager = get_model_manager()
    stats = manager.get_stats()
    return {
        "cascade": [m.to_dict() for m in manager.get_active_models()],
        "count": stats["free_models_count"],
        "last_discovery_ago": stats["last_discovery_ago"],
        "discovery_interval": stats["discovery_interval"],
        "providers": {
            "openrouter": {
                "keys_total": stats["openrouter_keys"],
                "keys_available": stats["openrouter_keys_available"],
            },
            "gemini": {
                "keys_total": stats["gemini_keys"],
                "keys_available": stats["gemini_keys_available"],
            },
        },
    }


@app.post("/api/v1/models/refresh")
async def models_refresh():
    """Принудительное обновление каскада бесплатных моделей."""
    manager = get_model_manager()
    models = await manager.discover_free_models(force=True)
    return {
        "refreshed": True,
        "discovered": len(models),
        "models": [m.to_dict() for m in models],
    }


@app.get("/api/v1/models/health")
async def models_health():
    """Здоровье всех API ключей."""
    manager = get_model_manager()
    keys = manager.get_keys_health()
    stats = manager.get_stats()
    return {
        "keys": keys,
        "summary": {
            "openrouter_total": stats["openrouter_keys"],
            "openrouter_available": stats["openrouter_keys_available"],
            "gemini_total": stats["gemini_keys"],
            "gemini_available": stats["gemini_keys_available"],
        },
        "stats": {
            "total_requests": stats["total_requests"],
            "openrouter_successes": stats["openrouter_successes"],
            "openrouter_failures": stats["openrouter_failures"],
            "gemini_successes": stats["gemini_successes"],
            "gemini_failures": stats["gemini_failures"],
        },
    }


@app.post("/api/v1/models/reset-breakers")
async def reset_circuit_breakers():
    """Сбросить все circuit breaker'ы."""
    manager = get_model_manager()
    manager.reset_all_circuit_breakers()
    return {"status": "ok", "message": "All circuit breakers reset"}


@app.get("/api/v1/models/discovery")
async def discovery_status():
    """Статус фонового discovery планировщика."""
    return get_discovery_status()


# ═══════════════════════════════════════════════════════════════
# CACHE STATS
# ═══════════════════════════════════════════════════════════════

@app.get("/api/v1/cache/stats")
async def cache_stats():
    """Статистика кеша парсинга."""
    return get_cache_stats()


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8081))
    logger.info("LLM Service starting on port %d", port)
    uvicorn.run(app, host="0.0.0.0", port=port)
