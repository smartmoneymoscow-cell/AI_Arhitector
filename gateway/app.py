"""
API Gateway — маршрутизация к микросервисам [FastAPI]

Обновлённая архитектура:
- Единый orchestrator endpoint с quality параметрами
- Preview endpoint для быстрого превью
- SSE stream для real-time прогресса
- Все сервисы через shared-пакет

Endpoints:
  POST /api/v1/generate            — Генерация (legacy, быстрая)
  POST /api/v1/orchestrator/execute — Полный pipeline через оркестратор
  POST /api/v1/preview             — Быстрое превью
  POST /api/v1/parse               — Парсинг промта
  GET  /api/v1/health              — Health check всех сервисов
  GET  /api/v1/orchestrator/jobs/{id} — Статус задачи
  GET  /api/v1/orchestrator/jobs/{id}/stream — SSE stream прогресса
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

app = FastAPI(
    title="Architect Gateway",
    description="API Gateway — маршрутизация к микросервисам",
    version="5.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════
# FRONTEND DIR
# ═══════════════════════════════════════════════════════════════

FRONTEND_DIR = settings.FRONTEND_DIR
if not FRONTEND_DIR:
    FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if not os.path.isdir(FRONTEND_DIR):
    FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")
if not os.path.isdir(FRONTEND_DIR):
    FRONTEND_DIR = os.path.join("/", "app", "frontend")


# ═══════════════════════════════════════════════════════════════
# RETRY HELPER
# ═══════════════════════════════════════════════════════════════

async def request_with_retry(
    method: str, url: str, max_retries: int = 0, timeout: float = 0, **kwargs,
) -> httpx.Response:
    if max_retries <= 0:
        max_retries = settings.MAX_RETRIES
    if timeout <= 0:
        timeout = settings.REQUEST_TIMEOUT

    last_error = None
    async with httpx.AsyncClient() as client:
        for attempt in range(max_retries + 1):
            try:
                r = await getattr(client, method)(url, timeout=timeout, **kwargs)
                return r
            except httpx.TimeoutException:
                last_error = "timeout"
                if attempt < max_retries:
                    await asyncio.sleep(settings.RETRY_DELAY_BASE * (attempt + 1))
            except httpx.ConnectError:
                last_error = "connection_error"
                if attempt < max_retries:
                    await asyncio.sleep(settings.RETRY_DELAY_BASE * (attempt + 1))
    raise HTTPException(502, f"Service unavailable: {last_error}")


async def proxy_request(request: Request, target_base: str, path: str):
    if not target_base:
        raise HTTPException(503, f"Service not configured for path: {path}")
    data = await request.json()
    r = await request_with_retry("post", f"{target_base}{path}", json=data, timeout=60.0)
    if r.status_code == 200:
        return Response(content=r.content, media_type=r.headers.get("content-type", "application/json"))
    raise HTTPException(r.status_code, detail=r.text)


# ═══════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════

@app.get("/health")
@app.get("/api/v1/health")
async def health():
    services = {}
    service_urls = {
        "llm": settings.LLM_SERVICE_URL,
        "blender": settings.BLENDER_SERVICE_URL,
    }
    async with httpx.AsyncClient() as client:
        for name, url in service_urls.items():
            if not url:
                services[name] = "not_configured"
                continue
            try:
                r = await client.get(f"{url}/health", timeout=5.0)
                services[name] = "ok" if r.status_code == 200 else "error"
            except Exception:
                services[name] = "unreachable"
    return {
        "status": "ok",
        "service": "gateway",
        "version": "5.0.0",
        "services": services,
    }


# ═══════════════════════════════════════════════════════════════
# ORCHESTRATOR (main pipeline)
# ═══════════════════════════════════════════════════════════════

_orchestrator_jobs: dict = {}


@app.post("/api/v1/orchestrator/execute")
async def orchestrator_execute(req: dict):
    """
    Полный pipeline генерации через multi-agent оркестратор.

    Body:
    {
        "prompt": "двухэтажный кирпичный дом 10×12",
        "quality": "standard",  // preview|standard|high|ultra|16k
        "export_formats": ["glb"],  // glb|obj|fbx|ifc|svg
        "skip_clarification": false
    }
    """
    from shared.agents import Orchestrator

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
    result = await loop.run_in_executor(
        None,
        lambda: orch.execute(
            prompt,
            quality=quality,
            export_formats=export_formats,
            skip_clarification=skip_clarification,
        ),
    )

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
        "clarification": result.get("clarification"),
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


@app.get("/api/v1/orchestrator/jobs/{job_id}/progress")
async def orchestrator_job_progress(job_id: str):
    from shared.agents import Orchestrator
    orch = Orchestrator()
    orch.jobs = _orchestrator_jobs
    progress = orch.get_progress(job_id)
    if "error" in progress:
        raise HTTPException(404, progress["error"])
    return progress


@app.get("/api/v1/orchestrator/jobs/{job_id}/stream")
async def orchestrator_stream(job_id: str):
    """SSE stream прогресса генерации (real-time)."""
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
# PREVIEW (fast, low quality)
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/preview")
async def preview(req: dict):
    """Быстрое превью через blender-service."""
    prompt = req.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "No prompt provided")

    if not settings.BLENDER_SERVICE_URL:
        raise HTTPException(503, "Blender service not configured")

    r = await request_with_retry(
        "post",
        f"{settings.BLENDER_SERVICE_URL}/api/v1/preview",
        json=req,
        timeout=90.0,
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
    """Legacy: быстрая генерация через blender-service."""
    gen_type = _detect_gen_type(req.prompt, req.object_type)
    target_url = (
        f"{settings.BLENDER_SERVICE_URL}/api/v1/render/interior"
        if gen_type == "interior"
        else f"{settings.BLENDER_SERVICE_URL}/api/v1/generate/building"
    )
    r = await request_with_retry("post", target_url, json=req.model_dump(), timeout=180.0, max_retries=2)
    if r.status_code == 200:
        return Response(content=r.content, media_type=r.headers.get("content-type", "application/octet-stream"))
    raise HTTPException(r.status_code, detail=r.text)


# ═══════════════════════════════════════════════════════════════
# PARSE
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/parse")
async def parse(req: ParseRequest):
    """Парсинг промта через LLM-service."""
    if not settings.LLM_SERVICE_URL:
        from shared.parser import fallback_regex_parse
        from shared.router import route_generation
        params = fallback_regex_parse(req.text)
        plan = route_generation(req.text, params)
        return {"params": params, "gen_type": plan.gen_type, "building_params": plan.params.get("building", {})}

    r = await request_with_retry(
        "post",
        f"{settings.LLM_SERVICE_URL}/api/v1/parse",
        json=req.model_dump(),
        timeout=30.0,
    )
    if r.status_code == 200:
        return r.json()
    raise HTTPException(r.status_code, detail=r.text)


@app.post("/api/v1/parse-local")
async def parse_local(req: GenerateRequest):
    """Локальный парсинг (regex, без LLM)."""
    from shared.parser import fallback_regex_parse
    from shared.router import route_generation
    params = fallback_regex_parse(req.prompt)
    plan = route_generation(req.prompt, params)
    return {
        "params": params,
        "gen_type": plan.gen_type,
        "building_params": plan.params.get("building", {}),
    }


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


# ═══════════════════════════════════════════════════════════════
# STARTUP
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    port = settings.PORT
    print(f"Gateway starting on port {port}")
    print(f"LLM: {settings.LLM_SERVICE_URL}")
    print(f"Blender: {settings.BLENDER_SERVICE_URL}")
    uvicorn.run(app, host="0.0.0.0", port=port)
