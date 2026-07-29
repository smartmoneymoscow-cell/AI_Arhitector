"""
API Gateway — routes requests to microservices (FastAPI)

Использует shared-пакет для конфигурации и моделей.
Единый retry-механизм.

Endpoints:
  GET  /health, /api/v1/health  — Health check (all services)
  POST /api/v1/generate         — Unified: text → GLB/PNG
  POST /api/v1/parse            — Text → structured params
  POST /api/v1/proxy/claude     — Chat proxy (legacy)

  POST /api/v1/analyze/graph    — Spatial graph analysis
  POST /api/v1/floorplan/svg    — Generate SVG floor plan
  POST /api/v1/ifc/generate     — Generate IFC file
  POST /api/v1/ml/classify-style — Style classification
  POST /api/v1/projects         — Project management
  POST /api/v1/search           — Semantic search
  GET  /api/v1/templates        — Building templates
"""

import sys
import os
import asyncio

# Добавить корень проекта в path для импорта shared
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse

from shared.config import settings
from shared.models import GenerateRequest, ParseRequest, HealthResponse

app = FastAPI(
    title="Architect Gateway",
    description="API Gateway — маршрутизация к микросервисам (shared)",
    version="4.0.0",
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
    method: str,
    url: str,
    max_retries: int = 0,
    timeout: float = 0,
    **kwargs,
) -> httpx.Response:
    """Retry с exponential backoff для Render cold start."""
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
    raise HTTPException(502, f"Service unavailable after {max_retries + 1} attempts: {last_error}")


async def proxy_request(request: Request, target_base: str, path: str):
    """Generic proxy: forward request to target service."""
    if not target_base:
        raise HTTPException(503, f"Service not configured for path: {path}")
    data = await request.json()
    r = await request_with_retry("post", f"{target_base}{path}", json=data, timeout=60.0)
    if r.status_code == 200:
        ct = r.headers.get("content-type", "application/json")
        return Response(content=r.content, media_type=ct)
    raise HTTPException(r.status_code, detail=r.text)


# ═══════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════

ALL_SERVICES = [
    (name, url) for name, url in settings.get_all_service_urls().items() if url
]


@app.get("/health")
@app.get("/api/v1/health")
async def health():
    services = {}
    async with httpx.AsyncClient() as client:
        for name, url in ALL_SERVICES:
            try:
                r = await client.get(f"{url}/health", timeout=5.0)
                services[name] = "ok" if r.status_code == 200 else "error"
            except Exception:
                services[name] = "unreachable"
    return {
        "status": "ok",
        "service": "gateway",
        "version": "4.0.0",
        "services": services,
    }


# ═══════════════════════════════════════════════════════════════
# CORE GENERATE
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
    gen_type = _detect_gen_type(req.prompt, req.object_type)
    target_url = (
        f"{settings.BLENDER_SERVICE_URL}/api/v1/render/interior"
        if gen_type == "interior"
        else f"{settings.BLENDER_SERVICE_URL}/api/v1/generate/building"
    )

    r = await request_with_retry(
        "post", target_url, json=req.model_dump(), timeout=180.0, max_retries=2,
    )
    if r.status_code == 200:
        return Response(
            content=r.content,
            media_type=r.headers.get("content-type", "application/octet-stream"),
        )
    raise HTTPException(r.status_code, detail=r.text)


@app.post("/api/v1/parse")
async def parse(req: ParseRequest):
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                f"{settings.LLM_SERVICE_URL}/api/v1/parse",
                json=req.model_dump(),
                timeout=30.0,
            )
            if r.status_code == 200:
                return r.json()
            raise HTTPException(r.status_code, detail=r.text)
        except httpx.TimeoutException:
            raise HTTPException(504, "LLM parse timeout")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(502, str(e))


@app.post("/api/v1/proxy/claude")
async def proxy_claude(request: Request):
    data = await request.json()
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                f"{settings.LLM_SERVICE_URL}/api/v1/chat/completions",
                json=data,
                timeout=60.0,
            )
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
    r = await request_with_retry(
        "post",
        f"{settings.BLENDER_SERVICE_URL}/api/v1/generate/building",
        json=req.model_dump(),
        timeout=180.0,
        max_retries=2,
    )
    if r.status_code == 200:
        return Response(
            content=r.content,
            media_type=r.headers.get("content-type", "application/octet-stream"),
        )
    raise HTTPException(r.status_code, detail=r.text)


@app.post("/api/v1/render/interior")
async def render_interior_legacy(req: GenerateRequest):
    r = await request_with_retry(
        "post",
        f"{settings.BLENDER_SERVICE_URL}/api/v1/render/interior",
        json=req.model_dump(),
        timeout=180.0,
        max_retries=2,
    )
    if r.status_code == 200:
        return Response(
            content=r.content,
            media_type=r.headers.get("content-type", "application/octet-stream"),
        )
    raise HTTPException(r.status_code, detail=r.text)


# ═══════════════════════════════════════════════════════════════
# GEOMETRY SERVICE PROXY
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/analyze/graph")
async def analyze_graph(request: Request):
    return await proxy_request(request, settings.GEOMETRY_SERVICE_URL, "/api/v1/analyze/graph")


@app.post("/api/v1/analyze/full")
async def analyze_full(request: Request):
    return await proxy_request(request, settings.GEOMETRY_SERVICE_URL, "/api/v1/analyze/full")


@app.post("/api/v1/floorplan/svg")
async def floorplan_svg(request: Request):
    return await proxy_request(request, settings.GEOMETRY_SERVICE_URL, "/api/v1/floorplan/svg")


@app.post("/api/v1/analyze/path")
async def analyze_path(request: Request):
    return await proxy_request(request, settings.GEOMETRY_SERVICE_URL, "/api/v1/analyze/path")


# ═══════════════════════════════════════════════════════════════
# IFC SERVICE PROXY
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/ifc/generate")
async def ifc_generate(request: Request):
    return await proxy_request(request, settings.IFC_SERVICE_URL, "/api/v1/ifc/generate")


@app.post("/api/v1/ifc/parse")
async def ifc_parse(request: Request):
    return await proxy_request(request, settings.IFC_SERVICE_URL, "/api/v1/ifc/parse")


@app.post("/api/v1/ifc/convert")
async def ifc_convert(request: Request):
    return await proxy_request(request, settings.IFC_SERVICE_URL, "/api/v1/ifc/convert")


# ═══════════════════════════════════════════════════════════════
# ML SERVICE PROXY
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/ml/classify-style")
async def ml_classify_style(request: Request):
    return await proxy_request(request, settings.ML_SERVICE_URL, "/api/v1/ml/classify-style")


@app.post("/api/v1/ml/classify-room")
async def ml_classify_room(request: Request):
    return await proxy_request(request, settings.ML_SERVICE_URL, "/api/v1/ml/classify-room")


@app.post("/api/v1/ml/generate-floorplan")
async def ml_generate_floorplan(request: Request):
    return await proxy_request(request, settings.ML_SERVICE_URL, "/api/v1/ml/generate-floorplan")


@app.post("/api/v1/ml/pointcloud")
async def ml_pointcloud(request: Request):
    return await proxy_request(request, settings.ML_SERVICE_URL, "/api/v1/ml/pointcloud")


@app.post("/api/v1/ml/analyze-image")
async def ml_analyze_image(request: Request):
    return await proxy_request(request, settings.ML_SERVICE_URL, "/api/v1/ml/analyze-image")


# ═══════════════════════════════════════════════════════════════
# DATA SERVICE PROXY
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/projects")
async def create_project(request: Request):
    return await proxy_request(request, settings.DATA_SERVICE_URL, "/api/v1/projects")


@app.get("/api/v1/projects/{project_id}")
async def get_project(project_id: str):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{settings.DATA_SERVICE_URL}/api/v1/projects/{project_id}", timeout=15.0)
        if r.status_code == 200:
            return r.json()
        raise HTTPException(r.status_code, detail=r.text)


@app.get("/api/v1/projects")
async def list_projects(limit: int = 50, offset: int = 0):
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.DATA_SERVICE_URL}/api/v1/projects?limit={limit}&offset={offset}",
            timeout=15.0,
        )
        if r.status_code == 200:
            return r.json()
        raise HTTPException(r.status_code, detail=r.text)


@app.put("/api/v1/projects/{project_id}")
async def update_project(project_id: str, request: Request):
    data = await request.json()
    async with httpx.AsyncClient() as client:
        r = await client.put(
            f"{settings.DATA_SERVICE_URL}/api/v1/projects/{project_id}",
            json=data,
            timeout=15.0,
        )
        if r.status_code == 200:
            return r.json()
        raise HTTPException(r.status_code, detail=r.text)


@app.delete("/api/v1/projects/{project_id}")
async def delete_project(project_id: str):
    async with httpx.AsyncClient() as client:
        r = await client.delete(
            f"{settings.DATA_SERVICE_URL}/api/v1/projects/{project_id}",
            timeout=15.0,
        )
        if r.status_code == 200:
            return r.json()
        raise HTTPException(r.status_code, detail=r.text)


@app.post("/api/v1/search")
async def search_projects(request: Request):
    return await proxy_request(request, settings.DATA_SERVICE_URL, "/api/v1/search")


@app.get("/api/v1/templates")
async def list_templates():
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{settings.DATA_SERVICE_URL}/api/v1/templates", timeout=15.0)
        if r.status_code == 200:
            return r.json()
        raise HTTPException(r.status_code, detail=r.text)


# ═══════════════════════════════════════════════════════════════
# CAD SERVICE PROXY
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/cad/primitive")
async def cad_primitive(request: Request):
    return await proxy_request(request, settings.CAD_SERVICE_URL, "/api/v1/cad/primitive")


@app.post("/api/v1/cad/boolean")
async def cad_boolean(request: Request):
    return await proxy_request(request, settings.CAD_SERVICE_URL, "/api/v1/cad/boolean")


@app.post("/api/v1/cad/fillet")
async def cad_fillet(request: Request):
    return await proxy_request(request, settings.CAD_SERVICE_URL, "/api/v1/cad/fillet")


@app.post("/api/v1/cad/building")
async def cad_building(request: Request):
    return await proxy_request(request, settings.CAD_SERVICE_URL, "/api/v1/cad/building")


@app.post("/api/v1/cad/export")
async def cad_export(request: Request):
    return await proxy_request(request, settings.CAD_SERVICE_URL, "/api/v1/cad/export")


# ═══════════════════════════════════════════════════════════════
# FREECAD SERVICE PROXY
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/freecad/building")
async def freecad_building(request: Request):
    return await proxy_request(request, settings.FREECAD_SERVICE_URL, "/api/v1/freecad/building")


@app.post("/api/v1/freecad/execute")
async def freecad_execute(request: Request):
    return await proxy_request(request, settings.FREECAD_SERVICE_URL, "/api/v1/freecad/execute")


# ═══════════════════════════════════════════════════════════════
# VECTOR DB SERVICE PROXY
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/vectordb/collections")
async def vectordb_create_collection(request: Request):
    return await proxy_request(request, settings.VECTORDB_SERVICE_URL, "/api/v1/vectordb/collections")


@app.get("/api/v1/vectordb/collections")
async def vectordb_list_collections():
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{settings.VECTORDB_SERVICE_URL}/api/v1/vectordb/collections", timeout=15.0)
        if r.status_code == 200:
            return r.json()
        raise HTTPException(r.status_code, detail=r.text)


@app.post("/api/v1/vectordb/upsert")
async def vectordb_upsert(request: Request):
    return await proxy_request(request, settings.VECTORDB_SERVICE_URL, "/api/v1/vectordb/upsert")


@app.post("/api/v1/vectordb/search")
async def vectordb_search(request: Request):
    return await proxy_request(request, settings.VECTORDB_SERVICE_URL, "/api/v1/vectordb/search")


# ═══════════════════════════════════════════════════════════════
# GRAPH DB SERVICE PROXY
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/graph/cypher")
async def graph_cypher(request: Request):
    return await proxy_request(request, settings.GRAPHDB_SERVICE_URL, "/api/v1/graph/cypher")


@app.post("/api/v1/graph/building")
async def graph_building(request: Request):
    return await proxy_request(request, settings.GRAPHDB_SERVICE_URL, "/api/v1/graph/building")


@app.post("/api/v1/graph/path")
async def graph_path(request: Request):
    return await proxy_request(request, settings.GRAPHDB_SERVICE_URL, "/api/v1/graph/path")


@app.get("/api/v1/graph/building/{building_id}/rooms")
async def graph_building_rooms(building_id: str):
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.GRAPHDB_SERVICE_URL}/api/v1/graph/building/{building_id}/rooms",
            timeout=15.0,
        )
        if r.status_code == 200:
            return r.json()
        raise HTTPException(r.status_code, detail=r.text)


# ═══════════════════════════════════════════════════════════════
# IFC GENERATION (shared)
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/ifc/generate-local")
async def ifc_generate_local(request: Request):
    """Генерация IFC через shared.ifc_generator (локально, без микросервиса)."""
    data = await request.json()
    try:
        import uuid
        from shared.ifc_generator import generate_ifc_building
        job_id = uuid.uuid4().hex[:8]
        output_file = os.path.join("/app/output", f"{job_id}.ifc")
        generate_ifc_building(data, output_file)
        if os.path.exists(output_file):
            return FileResponse(output_file, media_type="application/x-step", filename=f"archai_{job_id}.ifc")
        raise HTTPException(500, "IFC generation failed")
    except ImportError as e:
        raise HTTPException(503, f"ifcopenshell not installed: {e}")
    except Exception as e:
        raise HTTPException(500, str(e))


# ═══════════════════════════════════════════════════════════════
# FLOOR PLAN (shared)
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/floorplan/svg-local")
async def floorplan_svg_local(request: Request):
    """Генерация SVG плана через shared.floorplan (локально)."""
    data = await request.json()
    floor = data.pop("floor", 1)
    try:
        from shared.floorplan import generate_floorplan_svg
        svg = generate_floorplan_svg(data, floor)
        return Response(content=svg, media_type="image/svg+xml")
    except Exception as e:
        raise HTTPException(500, str(e))


# ═══════════════════════════════════════════════════════════════
# BUILDING GRAPH (shared)
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/graph/building-local")
async def graph_building_local(request: Request):
    """Анализ графа здания через shared.graph (локально)."""
    data = await request.json()
    try:
        from shared.graph import BuildingGraph
        bg = BuildingGraph.from_params(data)
        return {
            "rooms": bg.rooms,
            "edges": bg.edges,
            "adjacency": bg.get_adjacency_list(),
            "stats": bg.get_room_stats(),
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/v1/graph/building-local/svg")
async def graph_building_svg_local(request: Request):
    """Визуализация графа здания в SVG."""
    data = await request.json()
    try:
        from shared.graph import BuildingGraph
        bg = BuildingGraph.from_params(data)
        svg = bg.to_svg_graph()
        return Response(content=svg, media_type="image/svg+xml")
    except Exception as e:
        raise HTTPException(500, str(e))


# ═══════════════════════════════════════════════════════════════
# TASK QUEUE (Celery)
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/tasks/generate")
async def task_generate(request: Request):
    """Запуск async генерации через Celery."""
    data = await request.json()
    try:
        from shared.celery_app import generate_building_task
        result = generate_building_task.delay(data)
        return {"task_id": result.id, "status": "queued"}
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@app.get("/api/v1/tasks/{task_id}")
async def task_status(task_id: str):
    """Проверка статуса async задачи."""
    try:
        from shared.celery_app import celery_app
        if celery_app is None:
            raise HTTPException(503, "Celery not available")
        result = celery_app.AsyncResult(task_id)
        response = {"task_id": task_id, "status": result.status}
        if result.status == "PROGRESS":
            response["progress"] = result.info
        elif result.status == "SUCCESS":
            response["result"] = result.result
        elif result.status == "FAILURE":
            response["error"] = str(result.result)
        return response
    except Exception as e:
        raise HTTPException(500, str(e))


# ═══════════════════════════════════════════════════════════════
# ORCHESTRATOR (multi-agent pipeline)
# ═══════════════════════════════════════════════════════════════

# In-memory job store (для single-instance; в production → Redis)
_orchestrator_jobs: dict = {}


@app.post("/api/v1/orchestrator/execute")
async def orchestrator_execute(req: GenerateRequest):
    """Полный цикл генерации через multi-agent оркестратор."""
    import asyncio
    from shared.agents import Orchestrator

    orch = Orchestrator()

    # Run in thread pool (orchestrator is sync)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, orch.execute, req.prompt)

    job_id = result["job_id"]
    _orchestrator_jobs[job_id] = result

    return {
        "job_id": job_id,
        "status": result["status"],
        "gen_type": result.get("result", {}).get("gen_type"),
        "params": result.get("result", {}).get("params"),
        "steps": [
            {"name": s["name"], "status": s["status"], "duration_ms": s.get("duration_ms", 0)}
            for s in result.get("steps", [])
        ],
        "duration_ms": result.get("duration_ms", 0),
    }


@app.get("/api/v1/orchestrator/jobs/{job_id}")
async def orchestrator_job_status(job_id: str):
    """Статус задачи оркестратора."""
    job = _orchestrator_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.get("/api/v1/orchestrator/jobs/{job_id}/progress")
async def orchestrator_job_progress(job_id: str):
    """Прогресс задачи оркестратора (для polling)."""
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
    from fastapi.responses import StreamingResponse

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


@app.post("/api/v1/orchestrator/clarify")
async def orchestrator_clarify(req: dict):
    """Применить ответы на уточняющие вопросы и продолжить генерацию."""
    from shared.agents import Orchestrator
    from shared.clarification import ClarificationEngine

    job_id = req.get("job_id", "")
    answers = req.get("answers", {})

    job = _orchestrator_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("status") != "clarification_needed":
        raise HTTPException(400, "Job is not waiting for clarification")

    # Apply answers to partial params
    engine = ClarificationEngine()
    partial = job.get("clarification", {}).get("partial_params", {})
    updated_params = engine.apply_answers(partial, answers)

    # Re-run orchestrator with updated params
    prompt = job.get("prompt", "")
    orch = Orchestrator()
    result = orch.execute(prompt, llm_params=updated_params, skip_clarification=True)

    # Update job in-place
    _orchestrator_jobs[job_id].update(result)
    _orchestrator_jobs[job_id]["job_id"] = job_id  # preserve original ID

    return _orchestrator_jobs[job_id]


@app.post("/api/v1/parse-local")
async def parse_local(req: GenerateRequest):
    """Локальный парсинг промта (без LLM, только regex)."""
    from shared.parser import fallback_regex_parse
    from shared.router import route_generation

    params = fallback_regex_parse(req.prompt)
    plan = route_generation(req.prompt, params)

    return {
        "params": params,
        "gen_type": plan.gen_type,
        "building_params": plan.params.get("building", {}),
        "steps": [{"name": s.name, "service": s.service} for s in plan.steps],
    }


@app.post("/api/v1/generate-orchestrated")
async def generate_orchestrated(req: GenerateRequest):
    """Генерация через оркестратор с возвратом GLB."""
    import asyncio
    from shared.agents import Orchestrator
    from shared.blender import generate_bpy_script, run_blender
    from shared.router import route_generation

    # Parse
    plan = route_generation(req.prompt)
    params = plan.params.get("parsed", {})
    building_params = plan.params.get("building", {})

    if plan.gen_type == "interior":
        from shared.blender import generate_interior_script
        from shared.validation import DEFAULT_FURNITURE
        room_type = params.get("room_type", "living")
        furniture = params.get("furniture") or DEFAULT_FURNITURE.get(room_type, ["sofa", "table", "chandelier"])
        interior_params = {
            "width": params.get("width_m", 6),
            "length": params.get("length_m", 8),
            "height": params.get("height_m", 3),
            "style": params.get("style", "modern"),
            "furniture": furniture,
        }
        script = generate_interior_script(interior_params)
    else:
        script = generate_bpy_script(building_params)

    # Execute
    import uuid
    job_id = uuid.uuid4().hex[:8]
    output_file = os.path.join("/app/output", f"{job_id}.glb")
    export_cmd = f"\nimport bpy\nbpy.ops.export_scene.gltf(filepath=r'{output_file}', export_format='GLB')"

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, run_blender, script + export_cmd, output_file)
    except Exception as e:
        raise HTTPException(500, detail=str(e))

    if os.path.exists(output_file):
        return FileResponse(
            output_file,
            media_type="model/gltf-binary",
            filename=f"archai_{job_id}.glb",
        )
    raise HTTPException(500, "Generation failed")


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
    port = settings.PORT
    print(f"Gateway starting on port {port}")
    print(f"Services: LLM={settings.LLM_SERVICE_URL}, Blender={settings.BLENDER_SERVICE_URL}")
    uvicorn.run(app, host="0.0.0.0", port=port)
