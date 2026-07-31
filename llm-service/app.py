"""
LLM Microservice — proxy to OpenRouter + prompt parsing (FastAPI)

Использует shared-пакет для парсинга и валидации.
Нет дублирования кода.

Endpoints:
  GET  /health                        — Health check
  POST /api/v1/chat/completions       — Chat proxy to OpenRouter
  POST /api/v1/parse                  — Prompt → structured params (LLM + regex fallback)
  GET  /docs                          — OpenAPI documentation
"""

import sys
import os

# Добавить корень проекта в path для импорта shared
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from shared.config import settings
from shared.models import (
    ChatMessage, ChatRequest, ChatResponse,
    ParseRequest, ParsedParams, HealthResponse,
)
from shared.parser import parse_prompt_async, fallback_regex_parse

app = FastAPI(
    title="Architect LLM Service",
    description="Прокси к OpenRouter + парсинг архитектурных промтов",
    version="4.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return HealthResponse(
        status="ok",
        service="llm-service",
        version="4.0.0",
        model=settings.LLM_MODEL,
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
async def parse_prompt(req: ParseRequest):
    """
    Парсинг промта → структурированные параметры.
    Использует shared.parser (LLM + regex fallback).
    """
    params = await parse_prompt_async(req.text)
    return ParsedParams(**params)


# ═══════════════════════════════════════════════════════════════
# STARTUP
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8081))
    print(f"LLM Service starting on port {port}")
    print(f"Model: {settings.LLM_MODEL}")
    uvicorn.run(app, host="0.0.0.0", port=port)
