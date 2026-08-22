"""
gateway/app.py — API Gateway: ALL routing goes through here.
Nginx → Gateway → LLM Service / Blender Service

NO direct Nginx → service bypass.
"""

import asyncio
import json
import logging
import os
import time
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
    version="13.5.0",
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


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("Unhandled error: %s: %s", type(exc).__name__, str(exc)[:500], exc_info=True)
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=500,
        content={"error": "internal", "message": str(exc)[:500]},
    )


# ═══════════════════════════════════════════════════════════════
# CIRCUIT BREAKER — auto-recovery with half-open probing
# ═══════════════════════════════════════════════════════════════

_circuit_state: dict[str, dict] = {}  # {service: {failures, open_until, last_failure}}
_CIRCUIT_FAIL_THRESHOLD = 5
_CIRCUIT_OPEN_SECONDS = 60
_CIRCUIT_HALF_OPEN_AFTER = 30  # seconds before allowing a probe request


def _check_circuit(service: str) -> bool:
    """Check if circuit is OPEN (service disabled). Returns True if blocked."""
    state = _circuit_state.get(service)
    if not state:
        return False
    now = time.time()
    # If open_until has passed → half-open (allow probe)
    if state.get("open_until", 0) > 0 and now >= state["open_until"]:
        logger.info("Circuit breaker HALF-OPEN for %s — allowing probe", service)
        return False  # allow one probe request
    return state.get("open_until", 0) > now


def _record_failure(service: str) -> None:
    """Record a failure. Open circuit after threshold."""
    state = _circuit_state.setdefault(service, {"failures": 0, "open_until": 0, "last_failure": 0})
    state["failures"] += 1
    state["last_failure"] = time.time()
    if state["failures"] >= _CIRCUIT_FAIL_THRESHOLD:
        state["open_until"] = time.time() + _CIRCUIT_OPEN_SECONDS
        logger.warning(
            "Circuit breaker OPEN for %s (%d failures, retry in %ds)", service, state["failures"], _CIRCUIT_OPEN_SECONDS
        )


def _record_success(service: str) -> None:
    """Record a success. Reset circuit."""
    if service in _circuit_state:
        old_failures = _circuit_state[service].get("failures", 0)
        if old_failures > 0:
            logger.info("Circuit breaker CLOSED for %s (recovered after %d failures)", service, old_failures)
    _circuit_state[service] = {"failures": 0, "open_until": 0, "last_failure": 0}


def _get_circuit_stats() -> dict:
    """Return circuit breaker state for health/debug endpoints."""
    return {
        svc: {
            "failures": s.get("failures", 0),
            "is_open": _check_circuit(svc),
            "last_failure_ago": int(time.time() - s.get("last_failure", 0)) if s.get("last_failure") else None,
        }
        for svc, s in _circuit_state.items()
    }


# ═══════════════════════════════════════════════════════════════
# LLM SERVICE AUTO-DISCOVERY — find working LLM URL
# ═══════════════════════════════════════════════════════════════

_LLM_CANDIDATES = [
    "https://architect-llm-5mdk.onrender.com",
    "https://architect-llm-1s1j.onrender.com",
    "https://architect-llm-s5q7.onrender.com",
    "https://architect-llm-zczl.onrender.com",
    "https://architect-llm-2pmo.onrender.com",
    "https://architect-llm-sdrh.onrender.com",
    "https://architect-llm-qarj.onrender.com",
]
_cached_llm_url: str | None = None


def _discover_llm_url() -> str:
    """Find first working LLM service URL. Cache result."""
    global _cached_llm_url
    if _cached_llm_url:
        return _cached_llm_url
    # If settings has a non-default URL, try it first
    configured = settings.LLM_SERVICE_URL
    if configured and configured != "http://localhost:8081":
        try:
            import httpx as _httpx
            with _httpx.Client(timeout=5.0) as c:
                r = c.get(f"{configured}/health")
                if r.status_code == 200:
                    _cached_llm_url = configured
                    logger.info("LLM discovered (configured): %s", configured)
                    return configured
        except Exception:
            pass
    # Try candidates
    import httpx as _httpx
    for url in _LLM_CANDIDATES:
        try:
            with _httpx.Client(timeout=5.0) as c:
                r = c.get(f"{url}/health")
                if r.status_code == 200:
                    _cached_llm_url = url
                    logger.info("LLM discovered: %s", url)
                    return url
        except Exception:
            continue
    logger.warning("No working LLM service found")
    return configured or "http://localhost:8081"


def _get_llm_url() -> str:
    """Get LLM URL with auto-discovery."""
    global _cached_llm_url
    if _cached_llm_url:
        return _cached_llm_url
    return _discover_llm_url()


# ═══════════════════════════════════════════════════════════════
# BLENDER LOAD BALANCER — multiple instances
# ═══════════════════════════════════════════════════════════════


def _get_blender_urls() -> list[str]:
    """Get all Blender service URLs — KAGGLE FIRST, Render as fallback.
    v9.0: Blender rendering works ONLY via Kaggle GPU (T4/P100).
    Render blender-service is kept as emergency fallback only.
    v13.5.0: auto-discover Render blender URL if not configured.
    """
    urls = []
    # ═══ KAGGLE GPU RENDERER — PRIMARY (v9.0) ═══
    kaggle_url = os.environ.get("KAGGLE_RENDERER_URL", "")
    if kaggle_url:
        urls.append(kaggle_url)
        logger.info("Kaggle GPU renderer registered as PRIMARY: %s", kaggle_url)
    # ═══ Render blender-service — FALLBACK ONLY ═══
    primary = settings.BLENDER_SERVICE_URL
    if primary and primary not in urls and primary != "http://localhost:8082":
        urls.append(primary)
    # v13.5.0: auto-discover Render blender if primary is default
    if not urls or (len(urls) == 1 and urls[0] == "http://localhost:8082"):
        _BLENDER_CANDIDATES = [
            "https://ai-arch-blender3d.onrender.com",
        ]
        for candidate in _BLENDER_CANDIDATES:
            if candidate not in urls:
                urls.append(candidate)
    for i in range(2, 6):
        url = os.environ.get(f"BLENDER_SERVICE_URL_{i}", "")
        if url and url not in urls:
            urls.append(url)
    if not kaggle_url:
        logger.warning("KAGGLE_RENDERER_URL not set — Blender will use Render fallback (may fail)")
    return urls


_blender_rr_index = 0  # round-robin counter


def _next_blender_url() -> str:
    """Get next Blender URL using round-robin with circuit breaker."""
    global _blender_rr_index
    urls = _get_blender_urls()
    if not urls:
        return ""

    # Filter out circuits that are open
    available = [u for u in urls if not _check_circuit(u)]
    if not available:
        # All circuits open — try primary anyway
        return urls[0]

    url = available[_blender_rr_index % len(available)]
    _blender_rr_index += 1
    return url


async def request_with_retry(
    method: str,
    url: str,
    max_retries: int = 2,
    timeout: float = 120,
    **kwargs,
) -> httpx.Response:
    service = "llm" if ":8081" in url or "llm" in url else "blender" if "blender" in url else "unknown"

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


async def blender_request_with_fallback(
    method: str,
    path: str,
    max_retries: int = 2,
    timeout: float = 120,
    **kwargs,
) -> httpx.Response:
    """Try Blender request with failover — Kaggle first, then Render.
    v9.0: If KAGGLE_POLLING_ENABLED, uses Kaggle queue for /generate.
    """
    urls = _get_blender_urls()
    if not urls:
        raise HTTPException(503, "No Blender service configured — set KAGGLE_RENDERER_URL")

    last_error = None
    for url in urls:
        if _check_circuit(url):
            continue
        try:
            result = await request_with_retry(method, f"{url}{path}", max_retries=1, timeout=timeout, **kwargs)
            _record_success(url)
            return result
        except (HTTPException, Exception) as e:
            last_error = str(e)
            _record_failure(url)
            logger.warning("Blender %s failed: %s, trying next", url, last_error[:100])

    # All HTTP endpoints failed — try Kaggle polling queue as last resort
    if os.environ.get("KAGGLE_POLLING_ENABLED", "").lower() in ("true", "1", "yes"):
        logger.warning("All Blender HTTP failed — trying Kaggle polling queue")
        try:
            return await _kaggle_polling_render(kwargs.get("json", {}), timeout=timeout)
        except Exception as e:
            logger.error("Kaggle polling also failed: %s", e)

    raise HTTPException(502, f"All Blender instances failed: {last_error}")


async def _kaggle_polling_render(req_data: dict, timeout: float = 300) -> httpx.Response:
    """Enqueue render task to Kaggle polling queue and wait for result."""
    task_id = uuid.uuid4().hex[:8]
    task = {
        "id": task_id,
        "prompt": req_data.get("prompt", ""),
        "params": req_data.get("params", req_data),
        "status": "pending",
        "created_at": time.time(),
    }
    _kaggle_queue.append(task)
    logger.info("Kaggle polling: task %s enqueued, waiting up to %ds", task_id, timeout)

    # Poll for result
    deadline = time.time() + timeout
    while time.time() < deadline:
        await asyncio.sleep(3)
        result = _kaggle_results.get(task_id)
        if result and result.get("status") == "completed":
            _kaggle_results.pop(task_id, None)
            # Wrap result as httpx.Response-compatible
            import json as _json
            content = _json.dumps(result.get("result", {})).encode()
            return httpx.Response(200, content=content, headers={"content-type": "application/json"})

    raise HTTPException(504, f"Kaggle polling timeout ({timeout}s) for task {task_id}")


# ═══════════════════════════════════════════════════════════════
# REDIS JOBS STORE
# ═══════════════════════════════════════════════════════════════

_redis = None
_jobs_memory: dict[str, dict] = {}  # In-memory fallback when Redis unavailable


def _get_redis():
    global _redis
    if _redis is not None:
        return _redis
    try:
        import redis

        _redis = redis.from_url(
            settings.REDIS_URL, decode_responses=True, socket_timeout=5, socket_connect_timeout=5, retry_on_timeout=True
        )
        _redis.ping()
        logger.info("Redis connected for jobs storage")
        return _redis
    except Exception as e:
        logger.warning("Redis unavailable for jobs: %s", e)
        _redis = None  # ensure retry on next call
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
    # Fast health check — respond immediately, don't wait for downstream services
    # Downstream status is checked lazily via circuit breakers
    return {
        "status": "ok",
        "service": "gateway",
        "version": "13.5.0",
        "services": {
            "llm": "configured" if settings.LLM_SERVICE_URL else "not_configured",
            "blender": "configured" if settings.BLENDER_SERVICE_URL else "not_configured",
        },
        "redis": "not_configured",
        "blender_instances": len(_get_blender_urls()),
        "circuit_breakers": _get_circuit_stats(),
    }


# ═══════════════════════════════════════════════════════════════
# PARSE → routes to LLM Service
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/parse")
async def parse_proxy(
    req: dict,
    _rl: None = Depends(rate_limit_middleware),
):
    """Proxy parse request to LLM Service."""
    text = req.get("text", req.get("prompt", ""))
    if not text:
        raise HTTPException(400, "No text provided")

    r = await request_with_retry(
        "post",
        f"{_get_llm_url()}/api/v1/parse",
        json={"text": text},
        timeout=120,
    )
    return r.json()


# ═══════════════════════════════════════════════════════════════
# GENERATE → routes to Blender Service
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/generate")
async def generate_proxy(
    req: dict,
    _rl: None = Depends(rate_limit_middleware),
):
    """Proxy generate request to Blender Service (with failover).
    Returns binary GLB file or JSON with output_path."""
    r = await blender_request_with_fallback(
        "post",
        "/api/v1/generate",
        json=req,
        timeout=300,
    )
    # Check if response is binary (GLB file) or JSON
    content_type = r.headers.get("content-type", "")
    if "model/gltf-binary" in content_type or "application/octet-stream" in content_type:
        # Binary GLB file — stream it back
        return StreamingResponse(
            r.aiter_bytes(),
            media_type=content_type,
            headers={"content-disposition": f"attachment; filename=archai_{uuid.uuid4().hex[:8]}.glb"},
        )
    # JSON response
    return r.json()


# ═══════════════════════════════════════════════════════════════
# PREVIEW → routes to Blender Service (with failover)
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/preview")
async def preview_proxy(
    req: dict,
    api_key: str = Depends(get_api_key_required),
    _rl: None = Depends(rate_limit_middleware),
):
    """Proxy preview request to Blender Service (with failover)."""
    r = await blender_request_with_fallback(
        "post",
        "/api/v1/preview",
        json=req,
        timeout=120,
    )
    return StreamingResponse(r.aiter_bytes(), media_type="image/png")


# ═══════════════════════════════════════════════════════════════
# FAST GENERATE → trimesh GLB (no Blender needed)
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/generate/fast")
async def generate_fast_proxy(
    req: dict,
    _rl: None = Depends(rate_limit_middleware),
):
    """v13.4.0: Fast GLB generation via trimesh (no Blender needed)."""
    r = await blender_request_with_fallback(
        "post",
        "/api/v1/generate/fast",
        json=req,
        timeout=60,
    )
    content_type = r.headers.get("content-type", "")
    if "model/gltf-binary" in content_type:
        return StreamingResponse(
            r.aiter_bytes(),
            media_type=content_type,
            headers={"content-disposition": f"attachment; filename=archai_{uuid.uuid4().hex[:8]}.glb"},
        )
    return r.json()


# ═══════════════════════════════════════════════════════════════
# CHAT → routes to LLM Service
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/chat")
async def chat_proxy(
    req: dict,
    _rl: None = Depends(rate_limit_middleware),
):
    """Proxy chat to LLM Service."""
    r = await request_with_retry(
        "post",
        f"{_get_llm_url()}/api/v1/chat/completions",
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
    session_id = req.get("session_id", "")

    job_id = uuid.uuid4().hex[:8]

    _blender_urls = _get_blender_urls()
    orch = Orchestrator(
        blender_service_url=_blender_urls[0] if _blender_urls else settings.BLENDER_SERVICE_URL,
        llm_service_url=_get_llm_url(),
        output_dir=settings.OUTPUT_DIR,
        blender_service_urls=_blender_urls,
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
                session_id=session_id,
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
        "session_id": session_id,
        "status": result["status"],
        "error": result.get("error"),
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


@app.post("/api/v1/orchestrator/resume")
async def orchestrator_resume(
    req: dict,
    _rl: None = Depends(rate_limit_middleware),
):
    """Resume a clarification-needed job with user answers."""
    from shared.agents import Orchestrator

    job_id = req.get("job_id", "")
    answers = req.get("answers", {})
    if not job_id:
        raise HTTPException(400, "No job_id provided")
    if not answers:
        raise HTTPException(400, "No answers provided")

    quality = req.get("quality", "standard")
    export_formats = req.get("export_formats", ["glb"])
    pipeline_profile = req.get("pipeline_profile", "standard")

    _blender_urls = _get_blender_urls()
    orch = Orchestrator(
        blender_service_url=_blender_urls[0] if _blender_urls else settings.BLENDER_SERVICE_URL,
        llm_service_url=_get_llm_url(),
        output_dir=settings.OUTPUT_DIR,
        blender_service_urls=_blender_urls,
    )

    # Retrieve stored job from Redis/memory
    stored = _get_job(job_id)
    if stored:
        orch.jobs[job_id] = stored

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: orch.resume_with_answers(
                job_id=job_id,
                answers=answers,
                quality=quality,
                export_formats=export_formats,
                pipeline_profile=pipeline_profile,
            ),
        )
    except Exception as e:
        logger.error("Orchestrator resume error: %s: %s", type(e).__name__, str(e)[:500], exc_info=True)
        raise HTTPException(500, detail={"error": "resume_failed", "message": str(e)[:500]})

    result_job_id = result.get("job_id", job_id)
    _store_job(result_job_id, result)

    r = result.get("result") or {}
    return {
        "job_id": result_job_id,
        "status": result["status"],
        "gen_type": r.get("gen_type"),
        "quality": quality,
        "params": r.get("params"),
        "render": r.get("render"),
        "exports": r.get("exports", {}),
        "confidence": r.get("confidence"),
        "duration_ms": result.get("duration_ms", 0),
        "steps": result.get("steps", []),
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


@app.get("/api/v1/stats")
async def stats_endpoint(
    api_key: str = Depends(get_api_key_required),
):
    """Return cache, cost, and circuit breaker statistics."""
    from shared.parser import get_cache_stats, get_cost_stats

    return {
        "cache": get_cache_stats(),
        "cost": get_cost_stats(),
        "circuit_breakers": _get_circuit_stats(),
    }


# ═══════════════════════════════════════════════════════════════
# CLARIFICATION — уточняющие вопросы
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/clarify")
async def clarify_endpoint(
    req: dict,
    _rl: None = Depends(rate_limit_middleware),
):
    """Analyze prompt and return clarification questions if needed."""
    from shared.clarification import ClarificationEngine

    prompt = req.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "No prompt provided")

    # Parse first
    r = await request_with_retry(
        "post",
        f"{_get_llm_url()}/api/v1/parse",
        json={"text": prompt},
        timeout=60,
    )
    parsed = r.json()
    params = parsed.get("params", parsed)
    confidence = parsed.get("confidence", 0.5)

    engine = ClarificationEngine()
    result = engine.analyze(prompt, params, confidence)

    return {
        "needs_clarification": result.needs_clarification,
        "questions": [
            {
                "field": q.field_name,
                "text": q.text,
                "options": q.options,
                "priority": q.priority,
            }
            for q in result.questions
        ],
        "confidence": result.confidence,
        "partial_params": result.partial_params,
    }


@app.post("/api/v1/clarify/answer")
async def clarify_answer_endpoint(
    req: dict,
    _rl: None = Depends(rate_limit_middleware),
):
    """Apply clarification answers and return updated params."""
    from shared.clarification import ClarificationEngine

    params = req.get("params", {})
    answers = req.get("answers", {})

    engine = ClarificationEngine()
    updated = engine.apply_answers(params, answers)

    return {"params": updated}


# ═══════════════════════════════════════════════════════════════
# COMPLIANCE — проверка нормативов (без генерации)
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/compliance/check")
async def compliance_check(
    req: dict,
    _rl: None = Depends(rate_limit_middleware),
):
    """Проверка соответствия нормативам без генерации."""
    from shared.compliance import ComplianceChecker
    from shared.norms_reference import get_applicable_norms
    from shared.structural_analysis import StructuralEngine

    params = req.get("params", {})
    prompt = req.get("prompt", "")

    # Если нет params — парсим промт
    if not params and prompt:
        r = await request_with_retry(
            "post",
            f"{_get_llm_url()}/api/v1/parse",
            json={"text": prompt},
            timeout=60,
        )
        parsed = r.json()
        params = parsed.get("params", parsed)

    building_params = {
        "floors": params.get("floors", 2),
        "W": params.get("width_m", 10),
        "L": params.get("length_m", 12),
        "fH": params.get("height_m", 3.0),
        "mat": params.get("material", "brick"),
        "rooms": [],
    }

    # Compliance check
    checker = ComplianceChecker()
    result = checker.check_building(params, building_params)

    # Norms
    norms = get_applicable_norms(
        params.get("building_type", params.get("type", "house")),
        params.get("floors", 2),
        params.get("height_m", 6.0),
        params.get("material", "brick"),
    )

    # Structural analysis
    engine = StructuralEngine()
    structural = {}
    try:
        dead = params.get("dead_load_kN_m2", 5.0)
        live = params.get("live_load_kN_m2", 2.0)
        snow = params.get("snow_load_kN_m2", 1.8)
        wind = params.get("wind_load_kN_m2", 0.4)
        structural["load_combinations"] = engine.loads.basic_combination(dead, live, snow, wind)

        seismic_zone = int(params.get("seismic_zone", 0) or 0)
        if seismic_zone > 0:
            structural["response_spectrum"] = engine.dynamics.response_spectrum(
                0.5, soil_type=params.get("soil_type", "II"), seismic_zone=seismic_zone
            )
            mass = building_params["W"] * building_params["L"] * building_params["floors"] * 15000
            structural["seismic_force"] = engine.dynamics.seismic_force(mass)

        soil = params.get("soil_type", "III")
        structural["foundation"] = engine.foundation.bearing_capacity_sand(
            soil, params.get("foundation_depth_m", 1.2), building_params["W"]
        )
    except Exception as e:
        structural["error"] = str(e)

    return {
        "compliance": result.to_dict(),
        "applicable_norms": norms,
        "structural": structural,
        "params": params,
    }


# ═══════════════════════════════════════════════════════════════
# PDF / DWG ANALYSIS — файловый анализ
# ═══════════════════════════════════════════════════════════════

import tempfile
import shutil
from fastapi import UploadFile, File as FastAPIFile


@app.post("/api/v1/analyze/pdf")
async def analyze_pdf_endpoint(
    file: UploadFile = FastAPIFile(...),
    _rl: None = Depends(rate_limit_middleware),
):
    """Upload PDF and get structured architectural analysis."""
    from shared.agents.pdf_analysis_agent import analyze_pdf

    # Save uploaded file
    suffix = os.path.splitext(file.filename or "upload.pdf")[1] or ".pdf"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        shutil.copyfileobj(file.file, tmp)
        tmp.close()
        result = analyze_pdf(tmp.name)
        return result.to_dict()
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


@app.post("/api/v1/analyze/dwg")
async def analyze_dwg_endpoint(
    file: UploadFile = FastAPIFile(...),
    _rl: None = Depends(rate_limit_middleware),
):
    """Upload DWG/DXF and get structured architectural analysis."""
    from shared.agents.dwg_analysis_agent import analyze_dxf, convert_dwg_to_dxf

    suffix = os.path.splitext(file.filename or "upload.dxf")[1] or ".dxf"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        shutil.copyfileobj(file.file, tmp)
        tmp.close()
        file_path = tmp.name

        # Convert DWG to DXF if needed
        if suffix.lower() == ".dwg":
            dxf_path = convert_dwg_to_dxf(tmp.name)
            if dxf_path:
                file_path = dxf_path
            else:
                return {"error": "Cannot convert DWG to DXF. Install ODA File Converter."}

        result = analyze_dxf(file_path)
        return result.to_dict()
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


# ═══════════════════════════════════════════════════════════════
# VARIANTS — варианты реализации
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/variants")
async def variants_endpoint(
    req: dict,
    api_key: str = Depends(get_api_key_required),
    _rl: None = Depends(rate_limit_middleware),
):
    """Generate multiple design variants with preview images."""
    prompt = req.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "No prompt provided")

    num_variants = min(req.get("num_variants", 3), 5)

    # Parse prompt first
    r = await request_with_retry(
        "post",
        f"{_get_llm_url()}/api/v1/parse",
        json={"text": prompt},
        timeout=60,
    )
    base_params = r.json()

    # Generate variant params by varying style/material/roof
    styles = ["modern", "classic", "minimalist"]
    materials = ["brick", "plaster", "wood"]
    roofs = ["gabled", "flat", "hip"]

    variants = []
    for i in range(num_variants):
        variant_params = dict(base_params)
        variant_params["style"] = styles[i % len(styles)]
        variant_params["material"] = materials[i % len(materials)]
        variant_params["roof_type"] = roofs[i % len(roofs)]
        variants.append(
            {
                "id": i + 1,
                "style": variant_params["style"],
                "material": variant_params["material"],
                "roof_type": variant_params["roof_type"],
                "params": variant_params,
            }
        )

    return {
        "prompt": prompt,
        "variants": variants,
        "base_params": base_params,
    }


# ═══════════════════════════════════════════════════════════════
# SESSION CONTEXT — multi-turn dialog management
# ═══════════════════════════════════════════════════════════════


@app.get("/api/v1/context/{session_id}")
async def get_context(
    session_id: str,
    api_key: str = Depends(get_api_key_required),
):
    """Get project context for a session."""
    from shared.context import get_context_store

    store = get_context_store(redis_url=settings.REDIS_URL)
    ctx = store.get(session_id)
    if not ctx:
        raise HTTPException(404, "Session not found")
    return ctx.to_dict()


@app.get("/api/v1/context")
async def list_contexts(
    api_key: str = Depends(get_api_key_required),
):
    """List recent sessions."""
    from shared.context import get_context_store

    store = get_context_store(redis_url=settings.REDIS_URL)
    return {"sessions": store.list_sessions()}


@app.delete("/api/v1/context/{session_id}")
async def delete_context(
    session_id: str,
    api_key: str = Depends(get_api_key_required),
):
    """Delete a session context."""
    from shared.context import get_context_store

    store = get_context_store(redis_url=settings.REDIS_URL)
    store.delete(session_id)
    return {"deleted": session_id}


# ═══════════════════════════════════════════════════════════════
# KAGGLE POLLING — for notebooks without ngrok
# ═══════════════════════════════════════════════════════════════

_kaggle_queue: list[dict] = []  # pending render tasks
_kaggle_results: dict[str, dict] = {}  # completed results by task_id


@app.post("/api/v1/kaggle/enqueue")
async def kaggle_enqueue(
    req: dict,
    api_key: str = Depends(get_api_key_required),
):
    """Add a render task to Kaggle queue."""
    task_id = uuid.uuid4().hex[:8]
    task = {
        "id": task_id,
        "prompt": req.get("prompt", ""),
        "params": req.get("params", {}),
        "status": "pending",
        "created_at": time.time(),
    }
    _kaggle_queue.append(task)
    logger.info("Kaggle task enqueued: %s", task_id)
    return {"task_id": task_id, "status": "pending"}


@app.get("/api/v1/kaggle/pending")
async def kaggle_pending():
    """Poll endpoint: Kaggle notebook calls this to get next task."""
    if not _kaggle_queue:
        return {}  # no tasks
    task = _kaggle_queue.pop(0)
    task["status"] = "processing"
    return task


@app.post("/api/v1/kaggle/result")
async def kaggle_result(req: dict):
    """Kaggle notebook posts result here."""
    task_id = req.get("task_id", "")
    if not task_id:
        raise HTTPException(400, "Missing task_id")
    _kaggle_results[task_id] = {
        "task_id": task_id,
        "status": "completed",
        "result": req.get("result"),
        "completed_at": time.time(),
    }
    logger.info("Kaggle result received: %s", task_id)
    return {"status": "ok"}


@app.get("/api/v1/kaggle/status/{task_id}")
async def kaggle_status(task_id: str):
    """Check Kaggle task status."""
    result = _kaggle_results.get(task_id)
    if result:
        return result
    # Check if still in queue
    for task in _kaggle_queue:
        if task["id"] == task_id:
            return {"task_id": task_id, "status": "pending"}
    return {"task_id": task_id, "status": "not_found"}


@app.get("/api/v1/kaggle/health")
async def kaggle_health():
    """Kaggle integration status."""
    kaggle_url = os.environ.get("KAGGLE_RENDERER_URL", "")
    return {
        "kaggle_configured": bool(kaggle_url),
        "kaggle_url": kaggle_url or "not_configured",
        "pending_tasks": len(_kaggle_queue),
        "completed_results": len(_kaggle_results),
        "blender_urls": _get_blender_urls(),
    }


# Aliases for Kaggle notebook compatibility
# (notebook uses /api/v1/orchestrator/pending-kaggle and /kaggle-result)
@app.get("/api/v1/orchestrator/pending-kaggle")
async def kaggle_pending_alias():
    return await kaggle_pending()


@app.post("/api/v1/orchestrator/kaggle-result")
async def kaggle_result_alias(req: dict):
    return await kaggle_result(req)


# ═══════════════════════════════════════════════════════════════
# FILE PROXY — serve rendered/exported files from Blender service
# The actual files (GLB, PNG) are written on the blender-service
# container's disk, not the gateway's. The frontend only talks to
# the gateway (API_BASE), so without this proxy any file the
# orchestrator points to (exports.output_path, render.image_path)
# is unreachable and 3D models / renders never load in the UI.
# ═══════════════════════════════════════════════════════════════
from fastapi.responses import Response as _RawResponse


@app.get("/api/v1/files/{file_path:path}")
async def proxy_output_file(file_path: str):
    filename = os.path.basename(file_path)
    if not filename:
        raise HTTPException(404, "File not found")
    r = await blender_request_with_fallback("get", f"/api/v1/files/{filename}", timeout=60)
    if r.status_code != 200:
        raise HTTPException(r.status_code, "File not found on Blender service")
    media_type = r.headers.get("content-type", "application/octet-stream")
    return _RawResponse(content=r.content, media_type=media_type)


# ═══════════════════════════════════════════════════════════════
# FRONTEND SERVING — serve index.html for all non-API routes
# ═══════════════════════════════════════════════════════════════
import os
from fastapi.responses import FileResponse

FRONTEND_DIR = os.environ.get("FRONTEND_DIR", "") or os.path.join(os.path.dirname(__file__), "..", "frontend")
if not os.path.isdir(FRONTEND_DIR):
    FRONTEND_DIR = os.path.join("/", "app", "frontend")

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

@app.get("/{path:path}")
async def serve_frontend(path: str):
    file_path = os.path.join(FRONTEND_DIR, path)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
