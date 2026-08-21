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
    groq_configured = bool(os.environ.get("GROQ_API_KEY", ""))
    gemini_configured = bool(os.environ.get("GOOGLE_API_KEY", ""))
    deepseek_configured = bool(os.environ.get("DEEPSEEK_API_KEY", ""))
    openrouter_configured = bool(os.environ.get("OPENROUTER_API_KEY", ""))
    return HealthResponse(
        status="ok",
        service="llm-service",
        version="13.2.0",
        model=settings.LLM_MODEL,
        services={
            "groq": "configured" if groq_configured else "not_configured",
            "gemini": "configured" if gemini_configured else "not_configured",
            "deepseek": "configured" if deepseek_configured else "not_configured",
            "openrouter": "configured" if openrouter_configured else "not_configured",
        },
    )


@app.post("/api/v1/chat/completions", response_model=ChatResponse)
async def chat_completions(req: ChatRequest):
    """Chat proxy — полный LLM каскад: Groq → Gemini → DeepSeek → OpenRouter.
    Автоматически пропускает недоступные провайдеры."""
    import shared.parser as _parser

    messages = [m.model_dump() for m in req.messages]
    max_tokens = req.max_tokens or 2048
    temperature = req.temperature or 0.3
    last_error: tuple[int, str] | None = None

    # ═══ 0. Groq — ПЕРВЫЙ! free tier, fast inference ═══
    groq_keys = _parser._get_groq_keys()
    if groq_keys:
        for key in groq_keys:
            try:
                async with httpx.AsyncClient() as client:
                    r = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": "qwen/qwen3.6-27b",
                            "messages": messages,
                            "max_tokens": max_tokens,
                            "temperature": temperature,
                        },
                        timeout=45.0,
                    )
                if r.status_code == 200:
                    logger.info("chat: Groq responded successfully")
                    return r.json()
                if r.status_code == 429:
                    logger.warning("chat: Groq rate limited, trying next")
                    _parser._mark_key_dead(key, _parser._COOLDOWN_RATE_LIMIT, "groq_chat_rpm")
                    continue
                logger.warning("chat: Groq HTTP %d: %s", r.status_code, r.text[:200])
            except httpx.TimeoutException:
                logger.warning("chat: Groq timeout")
            except Exception as e:
                logger.warning("chat: Groq error: %s", e)

    # ═══ 1. Google Gemini — БЕСПЛАТНО ═══
    gemini_keys = _parser._get_google_keys()
    if gemini_keys:
        for key in _parser._filter_alive(gemini_keys):
            try:
                gemini_messages = []
                for m in messages:
                    role = "user" if m["role"] == "user" else "model"
                    gemini_messages.append({"role": role, "parts": [{"text": m["content"]}]})
                async with httpx.AsyncClient() as client:
                    r = await client.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent",
                        headers={"Content-Type": "application/json"},
                        params={"key": key},
                        json={"contents": gemini_messages, "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature}},
                        timeout=30.0,
                    )
                if r.status_code == 200:
                    data = r.json()
                    text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    logger.info("chat: Gemini responded successfully")
                    return {
                        "id": "gemini-chat",
                        "object": "chat.completion",
                        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                    }
                if r.status_code == 429:
                    logger.warning("chat: Gemini rate limited, trying next")
                    _parser._mark_key_dead(key, _parser._COOLDOWN_RATE_LIMIT, "gemini_chat_rpm")
                    continue
                logger.warning("chat: Gemini HTTP %d: %s", r.status_code, r.text[:200])
            except httpx.TimeoutException:
                logger.warning("chat: Gemini timeout")
            except Exception as e:
                logger.warning("chat: Gemini error: %s", e)

    # ═══ 2. DeepSeek — direct API ═══
    deepseek_keys = _parser._get_deepseek_keys()
    if deepseek_keys:
        for key in deepseek_keys:
            try:
                async with httpx.AsyncClient() as client:
                    r = await client.post(
                        "https://api.deepseek.com/chat/completions",
                        headers={
                            "Authorization": f"Bearer {key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": "deepseek-chat",
                            "messages": messages,
                            "max_tokens": max_tokens,
                            "temperature": temperature,
                        },
                        timeout=30.0,
                    )
                if r.status_code == 200:
                    logger.info("chat: DeepSeek responded successfully")
                    return r.json()
                if r.status_code == 429:
                    logger.warning("chat: DeepSeek rate limited")
                    continue
                logger.warning("chat: DeepSeek HTTP %d: %s", r.status_code, r.text[:200])
            except httpx.TimeoutException:
                logger.warning("chat: DeepSeek timeout")
            except Exception as e:
                logger.warning("chat: DeepSeek error: %s", e)

    # ═══ 3. OpenRouter — все ключи с round-robin ═══
    all_keys = _get_api_keys()
    if all_keys:
        keys = _filter_alive(all_keys)
        payload = {
            "model": req.model or settings.LLM_MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        for attempt in range(len(keys)):
            key = keys[_parser._OR_KEY_IDX % len(keys)]
            _parser._OR_KEY_IDX = (_parser._OR_KEY_IDX + 1) % len(keys)
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
                logger.info("chat: OpenRouter responded successfully")
                return r.json()

            if r.status_code in (429, 402):
                if _looks_like_quota_exhausted(r.status_code, r.text):
                    _mark_key_dead(key, _COOLDOWN_QUOTA_EXHAUSTED, f"chat_http_{r.status_code}_quota")
                else:
                    _mark_key_dead(key, _COOLDOWN_RATE_LIMIT, f"chat_http_{r.status_code}_rate_limit")
                logger.warning("chat: OpenRouter key %s exhausted", _mask_key(key))
                last_error = (r.status_code, r.text)
                continue
            raise HTTPException(status_code=r.status_code, detail=r.text)

    # ═══ 4. Ollama — local last resort ═══
    ollama_result = await _parser._call_ollama(" ")  # just check if available
    if ollama_result:
        try:
            import os as _os
            ollama_url = _os.environ.get("OLLAMA_URL", "")
            ollama_model = _os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{ollama_url}/api/chat",
                    json={"model": ollama_model, "messages": messages, "stream": False},
                    timeout=60.0,
                )
            if r.status_code == 200:
                data = r.json()
                text = data.get("message", {}).get("content", "")
                logger.info("chat: Ollama responded successfully")
                return {
                    "id": "ollama-chat",
                    "object": "chat.completion",
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                }
        except Exception as e:
            logger.warning("chat: Ollama error: %s", e)

    status, detail = last_error or (503, "All LLM providers failed (Groq, Gemini, DeepSeek, OpenRouter, Ollama)")
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
    from shared.parser import _get_google_keys, _get_groq_keys, _get_deepseek_keys, _is_key_cooling

    or_keys = _get_api_keys()
    gm_keys = _get_google_keys()
    gr_keys = _get_groq_keys()
    ds_keys = _get_deepseek_keys()

    def _status(keys):
        return [
            {"key": _mask_key(k), "alive": not _is_key_cooling(k)}
            for k in keys
        ]

    or_status = _status(or_keys)
    gm_status = _status(gm_keys)
    gr_status = _status(gr_keys)
    ds_status = _status(ds_keys)
    return {
        "groq": {"total": len(gr_keys), "alive": sum(s["alive"] for s in gr_status), "keys": gr_status},
        "gemini": {"total": len(gm_keys), "alive": sum(s["alive"] for s in gm_status), "keys": gm_status},
        "deepseek": {"total": len(ds_keys), "alive": sum(s["alive"] for s in ds_status), "keys": ds_status},
        "openrouter": {"total": len(or_keys), "alive": sum(s["alive"] for s in or_status), "keys": or_status},
        "total_accounts": len(gr_keys) + len(gm_keys) + len(ds_keys) + len(or_keys),
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
