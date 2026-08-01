"""
API Gateway — маршрутизация к микросервисам [FastAPI]

v7.0:
- Jobs хранятся в Redis (переживают рестарт)
- Structured JSON logging
- API key ОБЯЗАТЕЛЕН
- Удалён sys.path hack
"""

import asyncio
import json
import logging
import os
import uuid

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse

from shared.auth import (
    get_api_key_optional,
    rate_limit_middleware,
)
from shared.config import settings
from shared.logging_config import setup_logging
from shared.models import GenerateRequest, ParseRequest

# Setup structured logging
setup_logging("gateway")
logger = logging.getLogger("archai.gateway")

app = FastAPI(
    title="Architect Gateway",
    description="API Gateway — маршрутизация к микросервисам (LLM-only)",
    version="7.0.0",
)

# ═══════════════════════════════════════════════════════════════
# CORS
# ═══════════════════════════════════════════════════════════════

_cors_origins = os.environ.get("CORS_ORIGINS", "*")
_origins_list = [o.strip() for o in _cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins_list,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization"],
)


# ═══════════════════════════════════════════════════════════════
# REDIS JOBS STORE
# ═══════════════════════════════════════════════════════════════

_redis = None


def _get_redis():
    """Lazy Redis connection for jobs storage."""
    global _redis
    if _redis is not None:
        return _redis
    try:
        import redis

        _redis = redis.from_url(settings.REDIS_URL, decode_responses=True, socket_timeout=3)
        _redis.ping()
        logger.info("Redis connected for jobs storage")
        return _redis
    except Exception as e:
        logger.warning("Redis unavailable for jobs: %s — falling back to in-memory", e)
        return None


# In-memory fallback (used only if Redis is down)
_jobs_memory: dict[str, dict] = {}


def _store_job(job_id: str, data: dict) -> None:
    """Store job data in Redis (with 24h TTL) or in-memory fallback."""
    r = _get_redis()
    if r:
        try:
            r.setex(f"job:{job_id}", 86400, json.dumps(data, ensure_ascii=False, default=str))
            return
        except Exception as e:
            logger.error("Redis store failed: %s", e)
    _jobs_memory[job_id] = data


def _get_job(job_id: str) -> dict | None:
    """Retrieve job data from Redis or in-memory fallback."""
    r = _get_redis()
    if r:
        try:
            raw = r.get(f"job:{job_id}")
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.error("Redis get failed: %s", e)
    return _jobs_memory.get(job_id)


# ═══════════════════════════════════════════════════════════════
# RETRY HELPER
# ═══════════════════════════════════════════════════════════════


async def request_with_retry(
    method: str,
    url: str,
    max_retries: int = 2,
    timeout: float = 120,
    **kwargs,
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
    logger.error("Service unavailable after %d retries: %s %s — %s", max_retries, method, url, last_error)
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

    # Check Redis
    redis_status = "not_configured"
    r = _get_redis()
    if r:
        try:
            r.ping()
            redis_status = "ok"
        except Exception:
            redis_status = "unreachable"

    return {
        "status": "ok",
        "service": "gateway",
        "version": "7.0.0",
        "services": services,
        "redis": redis_status,
    }


# ═══════════════════════════════════════════════════════════════
# ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/orchestrator/execute")
async def orchestrator_execute(
    req: dict,
    api_key: str = Depends(get_api_key_optional),
    _rl: None = Depends(rate_limit_middleware),
):
    """
    Полный pipeline через 20 LLM-агентов.

    Body:
        prompt: str — описание здания/интерьера
        quality: str — preview/standard/high/ultra/16k
        pipeline_profile: str — quick/standard/full/premium/interior/presentation
        export_formats: list[str] — glb/ifc/obj/svg
        skip_clarification: bool — пропустить уточняющие вопросы
    """
    from shared.agents import Orchestrator

    prompt = req.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "No prompt provided")

    quality = req.get("quality", "standard")
    export_formats = req.get("export_formats", ["glb"])
    skip_clarification = req.get("skip_clarification", False)
    pipeline_profile = req.get("pipeline_profile", "standard")

    valid_profiles = ["quick", "standard", "full", "premium", "interior", "presentation"]
    if pipeline_profile not in valid_profiles:
        raise HTTPException(400, f"Invalid pipeline_profile. Valid: {valid_profiles}")

    job_id = uuid.uuid4().hex[:8]
    logger.info(
        "Orchestrator execute: job=%s quality=%s profile=%s prompt=%s...",
        job_id,
        quality,
        pipeline_profile,
        prompt[:50],
    )

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
                pipeline_profile=pipeline_profile,
            ),
        )
    except Exception as e:
        if "AllModelsFailed" in type(e).__name__ or "all_models_failed" in str(e):
            logger.error("All LLM models failed for job %s", job_id)
            raise HTTPException(
                503,
                detail={
                    "error": "all_models_failed",
                    "message": "Все LLM-модели недоступны. Проверьте OPENROUTER_API_KEY.",
                },
            )
        raise

    result_job_id = result["job_id"]
    _store_job(result_job_id, result)

    r = result.get("result") or {}
    logger.info(
        "Orchestrator done: job=%s status=%s profile=%s duration=%dms",
        result_job_id,
        result["status"],
        pipeline_profile,
        result.get("duration_ms", 0),
    )

    # Собираем ответ со ВСЕМИ результатами агентов
    response = {
        "job_id": result_job_id,
        "status": result["status"],
        "gen_type": r.get("gen_type"),
        "quality": quality,
        "pipeline_profile": pipeline_profile,
        "params": r.get("params"),
        "render": r.get("render"),
        "exports": r.get("exports", {}),
        "confidence": r.get("confidence"),
        "duration_ms": result.get("duration_ms", 0),
        "steps": [
            {"name": s["name"], "status": s["status"], "duration_ms": s.get("duration_ms", 0)}
            for s in result.get("steps", [])
        ],
    }

    # Результаты интеллектуальных агентов
    for agent_name in ("concept", "style", "masterplan", "brand", "research", "market"):
        if r.get(agent_name):
            response[agent_name] = r[agent_name]

    # Результаты специализированных агентов
    for agent_name in ("landscape", "furniture", "lighting", "mep", "structural"):
        if r.get(agent_name):
            response[agent_name] = r[agent_name]

    # Пост-анализ
    for agent_name in ("compliance", "financial"):
        if r.get(agent_name):
            response[agent_name] = r[agent_name]

    # Презентация
    if r.get("presentation"):
        response["presentation"] = r["presentation"]

    # Clarification (если нужны уточнения)
    if result.get("clarification"):
        response["clarification"] = result["clarification"]

    return response


@app.post("/api/v1/orchestrator/clarify")
async def orchestrator_clarify(
    req: dict,
    api_key: str = Depends(get_api_key_optional),
    _rl: None = Depends(rate_limit_middleware),
):
    """Применить ответы на уточняющие вопросы и продолжить генерацию."""
    from shared.agents import Orchestrator
    from shared.clarification import ClarificationEngine

    job_id = req.get("job_id", "")
    answers = req.get("answers", {})
    quality = req.get("quality", "standard")
    pipeline_profile = req.get("pipeline_profile", "standard")

    if not job_id:
        raise HTTPException(400, "No job_id provided")

    job = _get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("status") != "clarification_needed":
        raise HTTPException(400, "Job is not waiting for clarification")

    engine = ClarificationEngine()
    partial = job.get("clarification", {}).get("partial_params", {})
    updated_params = engine.apply_answers(partial, answers)

    prompt = job.get("prompt", "")
    orch = Orchestrator(
        blender_service_url=settings.BLENDER_SERVICE_URL,
        output_dir=settings.OUTPUT_DIR,
    )

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: orch.execute(
            prompt,
            llm_params=updated_params,
            skip_clarification=True,
            quality=quality,
            pipeline_profile=pipeline_profile,
        ),
    )

    result_job_id = result["job_id"]
    _store_job(result_job_id, result)

    r = result.get("result") or {}
    return {
        "job_id": result_job_id,
        "status": result["status"],
        "gen_type": r.get("gen_type"),
        "quality": quality,
        "pipeline_profile": pipeline_profile,
        "params": r.get("params"),
        "render": r.get("render"),
        "exports": r.get("exports", {}),
        "duration_ms": result.get("duration_ms", 0),
    }


@app.get("/api/v1/orchestrator/agents")
async def orchestrator_agents():
    """Список всех 20 агентов."""
    from shared.agents import AGENT_REGISTRY

    return {
        "total": len(AGENT_REGISTRY),
        "agents": [{"name": name, "class": cls.__name__} for name, cls in AGENT_REGISTRY.items()],
    }


@app.get("/api/v1/orchestrator/profiles")
async def orchestrator_profiles():
    """Доступные pipeline profiles."""
    from shared.agents.orchestrator import PIPELINE_PROFILES

    return {
        "profiles": {
            name: {
                "agents": agents,
                "count": len(agents),
            }
            for name, agents in PIPELINE_PROFILES.items()
        }
    }


@app.get("/api/v1/orchestrator/jobs/{job_id}")
async def orchestrator_job_status(job_id: str):
    job = _get_job(job_id)
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
async def preview(
    req: dict,
    api_key: str = Depends(get_api_key_optional),
    _rl: None = Depends(rate_limit_middleware),
):
    """Быстрое превью через blender-service (LLM-only парсинг)."""
    prompt = req.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "No prompt provided")
    if not settings.BLENDER_SERVICE_URL:
        raise HTTPException(503, "Blender service not configured")

    logger.info("Preview request: %s...", prompt[:50])
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
    "спальн",
    "детск",
    "кухн",
    "гостин",
    "ванн",
    "кабинет",
    "салон",
    "столов",
    "интерьер",
    "дизайн интерьера",
    "комнат",
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
async def generate(
    req: GenerateRequest,
    api_key: str = Depends(get_api_key_optional),
    _rl: None = Depends(rate_limit_middleware),
):
    """Legacy: генерация через blender-service."""
    gen_type = _detect_gen_type(req.prompt, req.object_type)
    logger.info("Generate: type=%s prompt=%s...", gen_type, req.prompt[:50])

    if not settings.BLENDER_SERVICE_URL:
        raise HTTPException(503, "Blender service not configured")

    r = await request_with_retry(
        "post",
        f"{settings.BLENDER_SERVICE_URL}/api/v1/generate",
        json=req.model_dump(),
        timeout=300.0,
    )
    if r.status_code == 200:
        return Response(content=r.content, media_type="model/gltf-binary")
    raise HTTPException(r.status_code, detail=r.text)


# ═══════════════════════════════════════════════════════════════
# PARSE (proxy to LLM service)
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/parse")
async def parse(
    req: ParseRequest,
    api_key: str = Depends(get_api_key_optional),
    _rl: None = Depends(rate_limit_middleware),
):
    """Proxy parse request to LLM service."""
    logger.info("Parse request: %s...", req.text[:50])
    r = await request_with_retry(
        "post",
        f"{settings.LLM_SERVICE_URL}/api/v1/parse",
        json=req.model_dump(),
        timeout=60.0,
    )
    if r.status_code == 200:
        return r.json()
    raise HTTPException(r.status_code, detail=r.text)


# ═══════════════════════════════════════════════════════════════
# STATIC FILES (Frontend)
# ═══════════════════════════════════════════════════════════════

_frontend_dir = settings.FRONTEND_DIR or os.path.join(os.path.dirname(__file__), "frontend")


@app.get("/")
async def serve_index():
    index_path = os.path.join(_frontend_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    # Fallback to root index.html
    root_index = os.path.join(os.path.dirname(__file__), "..", "index.html")
    if os.path.exists(root_index):
        return FileResponse(os.path.abspath(root_index))
    raise HTTPException(404, "Frontend not found")


@app.get("/{path:path}")
async def serve_static(path: str):
    file_path = os.path.join(_frontend_dir, path)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    raise HTTPException(404)
