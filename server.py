"""
Architect — Monolith Server (FastAPI)

⚠️  DEV ONLY — For local development. ⚠️
For production, use docker-compose with microservices.

Serves frontend + LLM parsing + Blender execution + Orchestrator.
"""

import os
import uuid
import sys
import logging

sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse

from shared.config import settings
from shared.logging_config import setup_logging

setup_logging("server-monolith")
logger = logging.getLogger("archai.server")
from shared.models import GenerateRequest, HealthResponse
from shared.parser import parse_prompt_sync, get_generation_type, get_cache_stats, AllModelsFailedError
from shared.validation import DEFAULT_FURNITURE
from shared.blender import generate_bpy_script, generate_interior_script, run_blender
from shared.auth import get_api_key_optional, rate_limit_middleware

OUTPUT_DIR = settings.OUTPUT_DIR
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = FastAPI(
    title="Architect Server",
    description="Монолитный сервер для локальной разработки",
    version="5.0.0",
)
# CORS: configurable via CORS_ORIGINS env (comma-separated)
_cors_origins = os.environ.get("CORS_ORIGINS", "*")
_origins_list = [o.strip() for o in _cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins_list,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization"],
)


# ═══════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════

@app.get("/health")
@app.get("/api/v1/health")
async def health():
    return HealthResponse(
        status="ok",
        service="archai-server",
        version="5.1.0",
        model=settings.LLM_MODEL,
        services={
            "llm": settings.LLM_SERVICE_URL,
            "blender": settings.BLENDER_SERVICE_URL,
            "cache_entries": str(get_cache_stats()["cached_entries"]),
        },
    )


# ═══════════════════════════════════════════════════════════════
# QUICK GENERATE (legacy, fast)
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/generate")
async def generate(req: GenerateRequest):
    """Быстрая генерация: промт → парсинг → Blender → GLB/PNG."""
    try:
        params = parse_prompt_sync(req.prompt)
    except AllModelsFailedError:
        raise HTTPException(503, detail="Все LLM-модели недоступны. Проверьте OPENROUTER_API_KEY.")

    gen_type = get_generation_type(params)

    if gen_type == "interior":
        return await _generate_interior(params)
    else:
        return await _generate_building(params)


# ═══════════════════════════════════════════════════════════════
# ORCHESTRATOR (full pipeline)
# ═══════════════════════════════════════════════════════════════

_orchestrator_jobs: dict = {}


@app.post("/api/v1/orchestrator/execute")
async def orchestrator_execute(req: dict):
    """
    Полный pipeline через multi-agent оркестратор.

    Body: { "prompt": "...", "quality": "standard", "export_formats": ["glb"] }
    """
    from shared.agents import Orchestrator

    prompt = req.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "No prompt provided")

    quality = req.get("quality", "standard")
    export_formats = req.get("export_formats", ["glb"])
    skip_clarification = req.get("skip_clarification", False)

    orch = Orchestrator(
        blender_service_url="",  # пусто = локальный вызов
        output_dir=OUTPUT_DIR,
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
    """SSE stream прогресса."""
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


@app.post("/api/v1/orchestrator/clarify")
async def orchestrator_clarify(req: dict):
    """Применить ответы на уточняющие вопросы."""
    from shared.agents import Orchestrator
    from shared.clarification import ClarificationEngine

    job_id = req.get("job_id", "")
    answers = req.get("answers", {})
    quality = req.get("quality", "standard")

    job = _orchestrator_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("status") != "clarification_needed":
        raise HTTPException(400, "Job is not waiting for clarification")

    engine = ClarificationEngine()
    partial = job.get("clarification", {}).get("partial_params", {})
    updated_params = engine.apply_answers(partial, answers)

    prompt = job.get("prompt", "")
    orch = Orchestrator(output_dir=OUTPUT_DIR)
    result = orch.execute(prompt, llm_params=updated_params, skip_clarification=True, quality=quality)

    _orchestrator_jobs[job_id].update(result)
    _orchestrator_jobs[job_id]["job_id"] = job_id

    return _orchestrator_jobs[job_id]


# ═══════════════════════════════════════════════════════════════
# PREVIEW (fast, low quality)
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/preview")
async def preview(req: dict):
    """Быстрое превью (1920×1080, EEVEE, 32 samples)."""
    prompt = req.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "No prompt provided")

    try:
        params = parse_prompt_sync(prompt)
    except AllModelsFailedError:
        params = {"width_m": 10, "length_m": 12, "floors": 2, "roof_type": "gabled",
                  "material": "plaster", "features": [], "room_type": "living"}
    gen_type = get_generation_type(params)

    if gen_type == "interior":
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
        building_params = {
            "width": params.get("width_m", 10),
            "length": params.get("length_m", 12),
            "floors": params.get("floors", 2),
            "roof_type": params.get("roof_type", "gabled"),
            "facade_material": params.get("material", "plaster"),
            "has_balcony": "balcony" in params.get("features", []),
        }
        script = generate_bpy_script(building_params)

    job_id = uuid.uuid4().hex[:8]
    output_file = os.path.join(OUTPUT_DIR, f"{job_id}_preview.png")

    script += f"""
import bpy
bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT'
bpy.context.scene.render.resolution_x = 1920
bpy.context.scene.render.resolution_y = 1080
try:
    bpy.context.scene.eevee.taa_render_samples = 32
except:
    pass
bpy.context.scene.render.image_settings.file_format = 'PNG'
bpy.context.scene.render.filepath = r'{output_file}'
bpy.ops.render.render(write_still=True)
"""

    try:
        result = run_blender(script, output_file, timeout=60)
    except TimeoutError as e:
        raise HTTPException(504, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(500, detail=str(e))

    if os.path.exists(output_file):
        return FileResponse(output_file, media_type="image/png", filename=f"preview_{job_id}.png")
    raise HTTPException(500, "Preview failed")


# ═══════════════════════════════════════════════════════════════
# PARSE
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/parse")
async def parse_endpoint(req: dict):
    """Парсинг промта."""
    from shared.router import route_generation
    text = req.get("text", req.get("prompt", ""))
    try:
        params = parse_prompt_sync(text)
    except AllModelsFailedError:
        raise HTTPException(503, detail="LLM parsing unavailable")
    plan = route_generation(text, params)
    return {
        "params": params,
        "gen_type": plan.gen_type,
        "building_params": plan.params.get("building", {}),
    }


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

async def _generate_building(params: dict):
    building_params = {
        "width": params.get("width_m", 10),
        "length": params.get("length_m", 12),
        "floors": params.get("floors", 2),
        "roof_type": params.get("roof_type", "gabled"),
        "facade_material": params.get("material", "plaster"),
        "has_balcony": "balcony" in params.get("features", []),
        "has_terrace": "terrace" in params.get("features", []),
        "has_garage": "garage" in params.get("features", []),
    }

    script = generate_bpy_script(building_params)
    job_id = uuid.uuid4().hex[:8]
    output_file = os.path.join(OUTPUT_DIR, f"{job_id}.glb")
    export_cmd = f"\nimport bpy\nbpy.ops.export_scene.gltf(filepath=r'{output_file}', export_format='GLB')"

    try:
        run_blender(script + export_cmd, output_file)
    except TimeoutError as e:
        raise HTTPException(504, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(500, detail={"error": str(e)})

    if os.path.exists(output_file):
        return FileResponse(output_file, media_type="model/gltf-binary", filename=f"archai_{job_id}.glb")
    raise HTTPException(500, detail="Export failed")


async def _generate_interior(params: dict):
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
    job_id = uuid.uuid4().hex[:8]
    output_file = os.path.join(OUTPUT_DIR, f"{job_id}_int.png")

    render_cmd = (
        "\nimport bpy"
        f"\nbpy.context.scene.render.filepath = r'{output_file}'"
        "\nbpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT'"
        "\nbpy.context.scene.render.resolution_x = 3840"
        "\nbpy.context.scene.render.resolution_y = 2160"
        "\nbpy.ops.render.render(write_still=True)"
    )

    try:
        run_blender(script + render_cmd, output_file, timeout=settings.RENDER_INTERIOR_TIMEOUT)
    except TimeoutError as e:
        raise HTTPException(504, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(500, detail=str(e))

    if os.path.exists(output_file):
        return FileResponse(output_file, media_type="image/png", filename=f"archai_interior_{job_id}.png")
    raise HTTPException(500, detail="Render failed")


# ═══════════════════════════════════════════════════════════════
# STATIC FILES
# ═══════════════════════════════════════════════════════════════

FRONTEND_DIR = os.path.dirname(__file__)


@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    print(f"Architect Server starting on port {settings.PORT}")
    print(f"Model: {settings.LLM_MODEL}")
    print(f"Blender: {settings.BLENDER_PATH}")
    print(f"Output: {OUTPUT_DIR}")
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
