"""
gateway/app.py — API Gateway: ALL routing goes through here.
Nginx → Gateway → LLM Service / Blender Service

NO direct Nginx → service bypass.
"""

import asyncio
import json
import logging
import os
import uuid

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from shared.auth import get_api_key_required, rate_limit_middleware
from shared.config import settings
from shared.logging_config import setup_logging

setup_logging("gateway")
logger = logging.getLogger("archai.gateway")

app = FastAPI(
    title="Architect Gateway",
    description="API Gateway — ALL routing through here. Nginx → Gateway → Services",
    version="8.0.0",
)

# CORS — NEVER wildcard in production
_cors_origins = os.environ.get("CORS_ORIGINS", "")
if not _cors_origins:
    logger.error("CORS_ORIGINS not set — defaulting to empty (no CORS)")
_origins_list = [o.strip() for o in _cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins_list,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)


# ═══════════════════════════════════════════════════════════════
# RETRY with circuit breaker
# ═══════════════════════════════════════════════════════════════

_circuit_state: dict[str, dict] = {}


def _check_circuit(service: str) -> bool:
    """Returns True if circuit is OPEN (service unavailable)."""
    state = _circuit_state.get(service, {"failures": 0, "last_failure": 0})
    if state["failures"] >= 5:
        import time

        if time.time() - state["last_failure"] < 60:  # 60s cooldown
            return True
        # Half-open: allow one retry
        state["failures"] = 3
    return False


def _record_failure(service: str):
    import time

    state = _circuit_state.setdefault(service, {"failures": 0, "last_failure": 0})
    state["failures"] += 1
    state["last_failure"] = time.time()


def _record_success(service: str):
    _circuit_state[service] = {"failures": 0, "last_failure": 0}


async def request_with_retry(
    method: str,
    url: str,
    max_retries: int = 2,
    timeout: float = 120,
    **kwargs,
) -> httpx.Response:
    service = "llm" if ":8081" in url else "blender" if ":8082" in url else "unknown"

    if _check_circuit(service):
        raise HTTPException(503, f"Service {service} circuit breaker OPEN — try again later")

    last_error = None
    async with httpx.AsyncClient() as client:
        for attempt in range(max_retries + 1):
            try:
                r = await getattr(client, method)(url, timeout=timeout, **kwargs)
                _record_success(service)
                return r
            except httpx.TimeoutException:
                last_error = "timeout"
            except httpx.ConnectError:
                last_error = "connection_error"
            if attempt < max_retries:
                await asyncio.sleep(3 * (attempt + 1))

    _record_failure(service)
    logger.error("Service unavailable after %d retries: %s %s — %s", max_retries, method, url, last_error)
    raise HTTPException(502, f"Service {service} unavailable: {last_error}")


# ═══════════════════════════════════════════════════════════════
# REDIS JOBS STORE
# ═══════════════════════════════════════════════════════════════

_redis = None


def _get_redis():
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
        logger.warning("Redis unavailable for jobs: %s", e)
        return None


def _store_job(job_id: str, data: dict) -> None:
    r = _get_redis()
    if r:
        try:
            r.setex(f"job:{job_id}", 86400, json.dumps(data, ensure_ascii=False, default=str))
            return
        except Exception as e:
            logger.error("Redis store failed: %s", e)
    # Fallback: in-memory (survives within same process)
    _jobs_memory[job_id] = data


def _get_job(job_id: str) -> dict | None:
    r = _get_redis()
    if r:
        try:
            raw = r.get(f"job:{job_id}")
            return json.loads(raw) if raw else None
        except Exception as e:
            logger.error("Redis get failed: %s", e)
    return None


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
        "version": "8.0.0",
        "services": services,
        "redis": redis_status,
    }


# ═══════════════════════════════════════════════════════════════
# PARSE → routes to LLM Service
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/parse")
async def parse_proxy(
    req: dict,
    api_key: str = Depends(get_api_key_required),
    _rl: None = Depends(rate_limit_middleware),
):
    """Proxy parse request to LLM Service."""
    text = req.get("text", req.get("prompt", ""))
    if not text:
        raise HTTPException(400, "No text provided")

    r = await request_with_retry(
        "post",
        f"{settings.LLM_SERVICE_URL}/api/v1/parse",
        json={"text": text},
        timeout=60,
    )
    return r.json()


# ═══════════════════════════════════════════════════════════════
# GENERATE → routes to Blender Service
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/generate")
async def generate_proxy(
    req: dict,
    api_key: str = Depends(get_api_key_required),
    _rl: None = Depends(rate_limit_middleware),
):
    """Proxy generate request to Blender Service."""
    r = await request_with_retry(
        "post",
        f"{settings.BLENDER_SERVICE_URL}/api/v1/generate",
        json=req,
        timeout=300,
    )
    return r.json()


# ═══════════════════════════════════════════════════════════════
# PREVIEW → routes to Blender Service
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/preview")
async def preview_proxy(
    req: dict,
    api_key: str = Depends(get_api_key_required),
    _rl: None = Depends(rate_limit_middleware),
):
    """Proxy preview request to Blender Service."""
    r = await request_with_retry(
        "post",
        f"{settings.BLENDER_SERVICE_URL}/api/v1/preview",
        json=req,
        timeout=120,
    )
    return StreamingResponse(r.aiter_bytes(), media_type="image/png")


# ═══════════════════════════════════════════════════════════════
# CHAT → routes to LLM Service
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/chat")
async def chat_proxy(
    req: dict,
    api_key: str = Depends(get_api_key_required),
    _rl: None = Depends(rate_limit_middleware),
):
    """Proxy chat to LLM Service."""
    r = await request_with_retry(
        "post",
        f"{settings.LLM_SERVICE_URL}/api/v1/chat/completions",
        json=req,
        timeout=60,
    )
    return r.json()


# ═══════════════════════════════════════════════════════════════
# ORCHESTRATOR — full pipeline (Gateway owns this)
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/orchestrator/execute")
async def orchestrator_execute(
    req: dict,
    api_key: str = Depends(get_api_key_required),
    _rl: None = Depends(rate_limit_middleware),
):
    from shared.agents import Orchestrator

    prompt = req.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "No prompt provided")

    quality = req.get("quality", "standard")
    export_formats = req.get("export_formats", ["glb"])
    skip_clarification = req.get("skip_clarification", False)
    pipeline_profile = req.get("pipeline_profile", "standard")

    job_id = uuid.uuid4().hex[:8]

    orch = Orchestrator(
        blender_service_url=settings.BLENDER_SERVICE_URL,
        llm_service_url=settings.LLM_SERVICE_URL,
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
        logger.error("Orchestrator error: %s: %s", type(e).__name__, str(e)[:500], exc_info=True)
        if "AllModelsFailed" in type(e).__name__:
            raise HTTPException(503, detail={"error": "all_models_failed", "message": str(e)})
        raise HTTPException(500, detail={"error": "orchestrator_failed", "message": str(e)[:500]})

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
        "confidence": r.get("confidence"),
        "duration_ms": result.get("duration_ms", 0),
        "steps": [
            {"name": s["name"], "status": s["status"], "duration_ms": s.get("duration_ms", 0)}
            for s in result.get("steps", [])
        ],
        "agent_results": r.get("agent_results", {}),
    }


@app.get("/api/v1/orchestrator/jobs/{job_id}")
async def orchestrator_job_status(
    job_id: str,
    api_key: str = Depends(get_api_key_required),
):
    job = _get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.get("/api/v1/orchestrator/jobs/{job_id}/stream")
async def orchestrator_stream(
    job_id: str,
    api_key: str = Depends(get_api_key_required),
):
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


@app.get("/api/v1/orchestrator/agents")
async def orchestrator_agents(
    api_key: str = Depends(get_api_key_required),
):
    from shared.agents import AGENT_REGISTRY

    return {"agents": list(AGENT_REGISTRY.keys())}
