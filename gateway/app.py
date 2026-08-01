"""
API Gateway — маршрутизация к микросервисам [FastAPI]

v6.0 — Парсинг ТОЛЬКО через LLM-service.
Regex fallback УДАЛЁН.
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse, StreamingResponse

from shared.config import settings
from shared.models import GenerateRequest, ParseRequest, HealthResponse
from shared.parser import get_cache_stats

app = FastAPI(
    title="Architect Gateway",
    description="API Gateway — маршрутизация к микросервисам (LLM-only)",
    version="6.0.0",
)

_cors_origins = os.environ.get("CORS_ORIGINS", "*")
_origins_list = [o.strip() for o in _cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins_list,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization"],
)


# ═══════════════════════════════════════════════════════════════
# RETRY HELPER
# ═══════════════════════════════════════════════════════════════

async def request_with_retry(
    method: str, url: str, max_retries: int = 2, timeout: float = 120, **kwargs,
) -> httpx.Response:
    last_error = None
    async with httpx.AsyncClient() as client:
        for attempt in range(max_retries + 1):
            try:
                r = await getattr(client, method)(url, timeout=timeout, **kwargs)
                return r
            except httpx.TimeoutException:
                last_error = "timeout"
            except httpx.ConnectError:
                last_error = "connection_error"
            if attempt < max_retries:
                await asyncio.sleep(3 * (attempt + 1))
    raise HTTPException(502, f"Service unavailable: {last_error}")


# ═══════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════

@app.get("/health")
@app.get("/api/v1/health")
async def health():
    services = {}
    for name, url in {"llm": settings.LLM_SERVICE_URL, "blender": settings.BLENDER_SERVICE_URL}.items():
        if not url:
            services[name] = "not_configured"
            continue
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{url}/health", timeout=5.0)
                services[name] = "ok" if r.status_code == 200 else "error"
        except Exception:
            services[name] = "unreachable"

    cache = get_cache_stats()
    return {
        "status": "ok",
        "service": "gateway",
        "version": "6.0.0",
        "services": services,
        "cache": {
            "l1_entries": cache["l1_entries"],
            "redis_connected": cache["redis_connected"],
        },
    }


# ═══════════════════════════════════════════════════════════════
# ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════

_orchestrator_jobs: dict = {}


@app.post("/api/v1/orchestrator/execute")
async def orchestrator_execute(req: dict):
    """Полный pipeline: LLM parse → geometry → texture → render → quality → export."""
    from shared.agents import Orchestrator
    from shared.parser import AllModelsFailedError

    prompt = req.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "No prompt provided")

    quality = req.get("quality", "standard")
    export_formats = req.get("export_formats", ["glb"])
    skip_clarification = req.get("skip_clarification", False)

    orch = Orchestrator(
        blender_service_url=settings.BLENDER_SERVICE_URL,
        output_dir=settings.OUTPUT_DIR,
    )

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: orch.execute(
                prompt,
                quality=quality,
                export_formats=export_formats,
                skip_clarification=skip_clarification,
            ),
        )
    except Exception as e:
        if "AllModelsFailed" in type(e).__name__ or "all_models_failed" in str(e):
            raise HTTPException(503, detail={
                "error": "all_models_failed",
                "message": "Все LLM-модели недоступны. Проверьте OPENROUTER_API_KEY.",
            })
        raise

    job_id = result["job_id"]
    _orchestrator_jobs[job_id] = result

    r = result.get("result") or {}
    return {
        "job_id": job_id,
        "status": result["status"],
        "gen_type": r.get("gen_type"),
        "quality": quality,
        "params": r.get("params"),
        "render": r.get("render"),
        "exports": r.get("exports", {}),
        "steps": [
            {"name": s["name"], "status": s["status"], "duration_ms": s.get("duration_ms", 0)}
            for s in result.get("steps", [])
        ],
        "duration_ms": result.get("duration_ms", 0),
    }


@app.get("/api/v1/orchestrator/jobs/{job_id}")
async def orchestrator_job_status(job_id: str):
    job = _orchestrator_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.get("/api/v1/orchestrator/jobs/{job_id}/stream")
async def orchestrator_stream(job_id: str):
    from shared.streaming import get_streamer
    streamer = get_streamer(job_id)
    if not streamer:
        raise HTTPException(404, "Job not found or stream expired")

    async def event_generator():
        async for event in streamer.subscribe():
            yield event.to_sse()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ═══════════════════════════════════════════════════════════════
# PREVIEW
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/preview")
async def preview(req: dict):
    """Быстрое превью через blender-service (LLM-only парсинг)."""
    prompt = req.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "No prompt provided")
    if not settings.BLENDER_SERVICE_URL:
        raise HTTPException(503, "Blender service not configured")

    r = await request_with_retry(
        "post", f"{settings.BLENDER_SERVICE_URL}/api/v1/preview",
        json=req, timeout=90.0,
    )
    if r.status_code == 200:
        return Response(content=r.content, media_type="image/png")
    raise HTTPException(r.status_code, detail=r.text)


# ═══════════════════════════════════════════════════════════════
# LEGACY GENERATE
# ═══════════════════════════════════════════════════════════════

INTERIOR_KEYWORDS = [
    "спальн", "детск", "кухн", "гостин", "ванн", "кабинет",
    "салон", "столов", "интерьер", "дизайн интерьера", "комнат",
]


def _detect_gen_type(prompt: str, object_type: str | None = None) -> str:
    if object_type in ("interior", "room"):
        return "interior"
    t = prompt.lower()
    for kw in INTERIOR_KEYWORDS:
        if kw in t:
            return "interior"
    return "building"


@app.post("/api/v1/generate")
async def generate(req: GenerateRequest):
    """Legacy: генерация через blender-service (LLM-only парсинг)."""
    gen_type = _detect_gen_type(req.prompt, req.object_type)
    target_url = (
        f"{settings.BLENDER_SERVICE_URL}/api/v1/render/interior"
        if gen_type == "interior"
        else f"{settings.BLENDER_SERVICE_URL}/api/v1/generate/building"
    )
    r = await request_with_retry("post", target_url, json=req.model_dump(), timeout=180.0)
    if r.status_code == 200:
        return Response(content=r.content, media_type=r.headers.get("content-type", "application/octet-stream"))
    raise HTTPException(r.status_code, detail=r.text)


# ═══════════════════════════════════════════════════════════════
# PARSE (прокси к LLM-service, БЕЗ regex)
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/parse")
async def parse(req: ParseRequest):
    """Парсинг промта. ТОЛЬКО через LLM-service. Regex УДАЛЁН."""
    if not settings.LLM_SERVICE_URL:
        raise HTTPException(503, "LLM service not configured")

    r = await request_with_retry(
        "post", f"{settings.LLM_SERVICE_URL}/api/v1/parse",
        json=req.model_dump(), timeout=60.0,
    )
    if r.status_code == 200:
        return r.json()
    raise HTTPException(r.status_code, detail=r.text)


# ═══════════════════════════════════════════════════════════════
# STATIC FILES
# ═══════════════════════════════════════════════════════════════

FRONTEND_DIR = settings.FRONTEND_DIR
if not FRONTEND_DIR:
    FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if not os.path.isdir(FRONTEND_DIR):
    FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")
if not os.path.isdir(FRONTEND_DIR):
    FRONTEND_DIR = os.path.join("/", "app", "frontend")


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
    port = settings.PORT
    print(f"Gateway starting on port {port}")
    print(f"LLM: {settings.LLM_SERVICE_URL}")
    print(f"Blender: {settings.BLENDER_SERVICE_URL}")
    uvicorn.run(app, host="0.0.0.0", port=port)
