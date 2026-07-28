"""
API Gateway — routes requests to microservices (FastAPI)

Endpoints:
  GET  /health, /api/v1/health  — Health check
  POST /api/v1/generate         — Unified: text → GLB/PNG
  POST /api/v1/parse            — Text → structured params
  POST /api/v1/proxy/claude     — Chat proxy (legacy)
  POST /api/v1/generate/building — Legacy
  POST /api/v1/render/interior   — Legacy
  GET  /docs                     — OpenAPI documentation
"""
import os
import re
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from pydantic import BaseModel

app = FastAPI(
    title="Architect Gateway",
    description="API Gateway — маршрутизация к микросервисам",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BLENDER_SVC = os.environ.get("BLENDER_SERVICE_URL", "http://localhost:8082")
LLM_SVC = os.environ.get("LLM_SERVICE_URL", "http://localhost:8081")
FRONTEND_DIR = os.environ.get("FRONTEND_DIR", os.path.join(os.path.dirname(__file__), "..", "frontend"))
if not os.path.isdir(FRONTEND_DIR):
    FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")
if not os.path.isdir(FRONTEND_DIR):
    FRONTEND_DIR = os.path.join("/", "app", "frontend")


# ═══════════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════════

class GenerateRequest(BaseModel):
    prompt: str
    object_type: Optional[str] = None
    building_type: str = "house"
    room_type: Optional[str] = None
    floors: int = 2
    width_m: int = 10
    length_m: int = 12
    height_m: int = 3
    style: str = "modern"
    material: str = "plaster"
    roof_type: str = "gabled"
    features: list = []
    furniture: list = []


class ParseRequest(BaseModel):
    text: str


class ChatRequest(BaseModel):
    messages: list
    max_tokens: int = 400
    temperature: float = 0.7
    model: Optional[str] = None


# ═══════════════════════════════════════════════════════════════
# RETRY HELPER
# ═══════════════════════════════════════════════════════════════

async def request_with_retry(
    method: str,
    url: str,
    max_retries: int = 2,
    timeout: float = 120.0,
    **kwargs,
) -> httpx.Response:
    """Retry с exponential backoff для Render cold start."""
    last_error = None
    async with httpx.AsyncClient() as client:
        for attempt in range(max_retries + 1):
            try:
                r = await getattr(client, method)(url, timeout=timeout, **kwargs)
                return r
            except httpx.TimeoutException:
                last_error = "timeout"
                if attempt < max_retries:
                    import asyncio
                    await asyncio.sleep(5 * (attempt + 1))
            except httpx.ConnectError:
                last_error = "connection_error"
                if attempt < max_retries:
                    import asyncio
                    await asyncio.sleep(5 * (attempt + 1))
    raise HTTPException(502, f"Service unavailable after {max_retries + 1} attempts: {last_error}")


# ═══════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════

@app.get("/health")
@app.get("/api/v1/health")
async def health():
    services = {}
    async with httpx.AsyncClient() as client:
        for name, url in [("llm", LLM_SVC), ("blender", BLENDER_SVC)]:
            try:
                r = await client.get(f"{url}/health", timeout=5.0)
                services[name] = "ok" if r.status_code == 200 else "error"
            except Exception:
                services[name] = "unreachable"
    return {"status": "ok", "service": "gateway", "services": services}


# ═══════════════════════════════════════════════════════════════
# ROUTING HELPERS + UNIFIED GENERATE
# ═══════════════════════════════════════════════════════════════

INTERIOR_KEYWORDS = [
    "спальн", "детск", "кухн", "гостин", "ванн", "кабинет",
    "салон", "столов", "интерьер", "дизайн интерьера", "комнат",
]


def _detect_gen_type(prompt: str, object_type: Optional[str] = None) -> str:
    """Определить тип генерации: 'interior' или 'building'."""
    if object_type in ("interior", "room"):
        return "interior"
    t = prompt.lower()
    for kw in INTERIOR_KEYWORDS:
        if kw in t:
            return "interior"
    return "building"


@app.post("/api/v1/generate")
async def generate(req: GenerateRequest):
    """Единый endpoint: определяет тип → роутит на правильный legacy endpoint blender-service."""
    gen_type = _detect_gen_type(req.prompt, req.object_type)

    if gen_type == "interior":
        target_url = f"{BLENDER_SVC}/api/v1/render/interior"
    else:
        target_url = f"{BLENDER_SVC}/api/v1/generate/building"

    r = await request_with_retry(
        "post",
        target_url,
        json=req.model_dump(),
        timeout=180.0,
        max_retries=2,
    )
    if r.status_code == 200:
        content_type = r.headers.get("content-type", "application/octet-stream")
        return Response(content=r.content, media_type=content_type)
    raise HTTPException(r.status_code, detail=r.text)


# ═══════════════════════════════════════════════════════════════
# PARSE
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/parse")
async def parse(req: ParseRequest):
    """Парсинг промта → структурированные параметры."""
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(f"{LLM_SVC}/api/v1/parse", json=req.model_dump(), timeout=30.0)
            if r.status_code == 200:
                return r.json()
            raise HTTPException(r.status_code, detail=r.text)
        except httpx.TimeoutException:
            raise HTTPException(504, "LLM parse timeout")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(502, str(e))


# ═══════════════════════════════════════════════════════════════
# LEGACY ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/proxy/claude")
async def proxy_claude(request: Request):
    data = await request.json()
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(f"{LLM_SVC}/api/v1/chat/completions", json=data, timeout=60.0)
            if r.status_code == 200:
                result = r.json()
                text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                return {"content": [{"type": "text", "text": text or ""}]}
            raise HTTPException(r.status_code, detail=r.text)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(502, str(e))


@app.post("/api/v1/generate/building")
async def generate_building_legacy(req: GenerateRequest):
    """Legacy endpoint → blender /api/v1/generate/building."""
    r = await request_with_retry(
        "post",
        f"{BLENDER_SVC}/api/v1/generate/building",
        json=req.model_dump(),
        timeout=180.0,
        max_retries=2,
    )
    if r.status_code == 200:
        content_type = r.headers.get("content-type", "application/octet-stream")
        return Response(content=r.content, media_type=content_type)
    raise HTTPException(r.status_code, detail=r.text)


@app.post("/api/v1/render/interior")
async def render_interior_legacy(req: GenerateRequest):
    """Legacy endpoint → blender /api/v1/render/interior."""
    r = await request_with_retry(
        "post",
        f"{BLENDER_SVC}/api/v1/render/interior",
        json=req.model_dump(),
        timeout=180.0,
        max_retries=2,
    )
    if r.status_code == 200:
        content_type = r.headers.get("content-type", "application/octet-stream")
        return Response(content=r.content, media_type=content_type)
    raise HTTPException(r.status_code, detail=r.text)


# ═══════════════════════════════════════════════════════════════
# STATIC FILES
# ═══════════════════════════════════════════════════════════════

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/{filename:path}")
async def serve_static(filename: str):
    path = os.path.join(FRONTEND_DIR, filename)
    if os.path.isfile(path):
        return FileResponse(path)
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    print(f"Gateway starting on port {port}")
    print(f"LLM: {LLM_SVC}")
    print(f"Blender: {BLENDER_SVC}")
    uvicorn.run(app, host="0.0.0.0", port=port)
