"""
LLM Microservice — LLM-only парсинг промтов через OpenRouter.

v6.0 — БЕЗ REGEX FALLBACK.
Каскад 7 моделей: сильная → средняя → слабая → бесплатные.
Кеш: Redis (L2) + in-memory (L1).
Если все модели недоступны → HTTP 503.
"""

import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from shared.config import settings
from shared.models import (
    ChatMessage, ChatRequest, ChatResponse,
    ParseRequest, ParsedParams, HealthResponse,
)
from shared.parser import (
    parse_prompt_async, AllModelsFailedError,
    get_cache_stats, LLM_CASCADE,
)
from shared.logging_config import setup_logging

setup_logging("llm-service")
logger = logging.getLogger("archai.llm")

app = FastAPI(
    title="Architect LLM Service",
    description="LLM-only парсинг архитектурных промтов (каскад 7 моделей, Redis кеш)",
    version="7.0.0",
)

_cors_origins = os.environ.get("CORS_ORIGINS", "*")
_origins_list = [o.strip() for o in _cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    cache = get_cache_stats()
    return HealthResponse(
        status="ok",
        service="llm-service",
        version="6.0.0",
        model=settings.LLM_MODEL,
        services={
            "redis": "connected" if cache["redis_connected"] else "disconnected",
            "l1_cache": f"{cache['l1_entries']}/{cache['l1_max']}",
            "l2_cache": str(cache["l2_redis_entries"]),
            "cascade_models": str(len(cache["llm_cascade"])),
        },
    )


@app.post("/api/v1/chat/completions", response_model=ChatResponse)
async def chat_completions(req: ChatRequest):
    """Chat proxy to OpenRouter."""
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "HTTP-Referer": "https://archai.app",
        "X-Title": "Architect LLM",
    }
    if settings.OPENROUTER_API_KEY:
        headers["Authorization"] = f"Bearer {settings.OPENROUTER_API_KEY}"

    payload = {
        "model": req.model or settings.LLM_MODEL,
        "messages": [m.model_dump() for m in req.messages],
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
    }

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{settings.OPENROUTER_BASE}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60.0,
            )
        if r.status_code == 200:
            return r.json()
        raise HTTPException(status_code=r.status_code, detail=r.text)
    except httpx.TimeoutException:
        raise HTTPException(504, "OpenRouter timeout")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, str(e))


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


@app.get("/api/v1/cache/stats")
async def cache_stats():
    """Статистика кеша парсинга."""
    return get_cache_stats()


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8081))
    print(f"LLM Service starting on port {port}")
    print(f"Cascade: {[m['model'] for m in LLM_CASCADE]}")
    uvicorn.run(app, host="0.0.0.0", port=port)
