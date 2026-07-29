"""
Architect — Monolith Server (FastAPI)
Serves frontend + proxies LLM API + generates Blender scripts.

Use for LOCAL DEVELOPMENT. For production, use docker-compose with microservices.

Uses shared-пакет — нет дублирования кода.

Endpoints:
    GET  /                           — Web interface
    GET  /health                     — Health check
    POST /api/v1/generate            — Unified: text → GLB/PNG (with routing)
    POST /api/v1/generate/building   — Text → GLB (legacy)
    POST /api/v1/render/interior     — Interior → PNG (legacy)
    POST /api/v1/proxy/claude        — Chat proxy
    GET  /docs                       — OpenAPI documentation
"""

import os
import uuid
import sys

# Добавить корень проекта в path для импорта shared
sys.path.insert(0, os.path.dirname(__file__))

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from shared.config import settings
from shared.models import GenerateRequest, HealthResponse
from shared.parser import (
    parse_prompt_sync,
    fallback_regex_parse,
    get_generation_type,
)
from shared.validation import DEFAULT_FURNITURE
from shared.blender import generate_bpy_script, generate_interior_script, run_blender

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════
FRONTEND_DIR = os.path.dirname(__file__)
OUTPUT_DIR = settings.OUTPUT_DIR
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# APP
# ═══════════════════════════════════════════════════════════════
app = FastAPI(
    title="Architect Server",
    description="Монолитный сервер для локальной разработки (shared)",
    version="3.0.0",
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
@app.get("/api/v1/health")
async def health():
    return HealthResponse(
        status="ok",
        service="archai-server",
        version="3.0.0",
        model=settings.LLM_MODEL,
    )


@app.post("/api/v1/generate")
async def generate(req: GenerateRequest):
    """Единый endpoint: промт → парсинг (LLM + fallback) → роутинг → генерация."""
    try:
        params = parse_prompt_sync(req.prompt)
    except Exception:
        params = fallback_regex_parse(req.prompt)

    gen_type = get_generation_type(params)

    if gen_type == "interior":
        return await _generate_interior(params)
    else:
        return await _generate_building(params)


@app.post("/api/v1/generate/building")
async def generate_building_legacy(req: GenerateRequest):
    params = fallback_regex_parse(req.prompt)
    return await _generate_building(params)


@app.post("/api/v1/render/interior")
async def render_interior_legacy(req: GenerateRequest):
    params = fallback_regex_parse(req.prompt)
    return await _generate_interior(params)


@app.post("/api/v1/proxy/claude")
async def proxy_claude(req: dict):
    """Chat proxy — forward to OpenRouter."""
    messages = req.get("messages", [])
    max_tokens = req.get("max_tokens", 400)

    headers = {"Content-Type": "application/json"}
    if settings.OPENROUTER_API_KEY:
        headers["Authorization"] = f"Bearer {settings.OPENROUTER_API_KEY}"

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{settings.OPENROUTER_BASE}/chat/completions",
                headers=headers,
                json={
                    "model": settings.LLM_MODEL,
                    "messages": messages,
                    "max_tokens": max_tokens,
                },
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


# ═══════════════════════════════════════════════════════════════
# GENERATION HELPERS
# ═══════════════════════════════════════════════════════════════

async def _generate_building(params: dict):
    """Генерация здания → GLB файл."""
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
        result = run_blender(script + export_cmd, output_file)
    except TimeoutError as e:
        raise HTTPException(504, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(500, detail={"error": str(e)})

    if os.path.exists(output_file):
        return FileResponse(
            output_file,
            media_type="model/gltf-binary",
            filename=f"archai_{job_id}.glb",
        )

    raise HTTPException(
        500,
        detail={"error": "Export failed", "stderr": (result.stderr or "")[-500:]},
    )


async def _generate_interior(params: dict):
    """Генерация интерьера → PNG файл."""
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
        "\nbpy.context.scene.render.engine = 'BLENDER_EEVEE'"
        "\nbpy.context.scene.render.resolution_x = 640"
        "\nbpy.context.scene.render.resolution_y = 480"
        "\nbpy.ops.render.render(write_still=True)"
    )

    try:
        run_blender(script + render_cmd, output_file, timeout=settings.RENDER_INTERIOR_TIMEOUT)
    except TimeoutError as e:
        raise HTTPException(504, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(500, detail=str(e))

    if os.path.exists(output_file):
        return FileResponse(
            output_file,
            media_type="image/png",
            filename=f"archai_interior_{job_id}.png",
        )

    raise HTTPException(500, detail="Render failed")


# ═══════════════════════════════════════════════════════════════
# IFC GENERATION
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/ifc/generate-local")
async def ifc_generate_local(req: GenerateRequest):
    """Генерация IFC-файла из параметров."""
    try:
        from shared.ifc_generator import generate_ifc_building
        from shared.parser import parse_prompt_sync
        params = parse_prompt_sync(req.prompt)
        job_id = uuid.uuid4().hex[:8]
        output_file = os.path.join(OUTPUT_DIR, f"{job_id}.ifc")
        generate_ifc_building(params, output_file)
        if os.path.exists(output_file):
            return FileResponse(output_file, media_type="application/x-step", filename=f"archai_{job_id}.ifc")
        raise HTTPException(500, "IFC generation failed")
    except ImportError as e:
        raise HTTPException(503, f"ifcopenshell not installed: {e}")
    except Exception as e:
        raise HTTPException(500, str(e))


# ═══════════════════════════════════════════════════════════════
# FLOOR PLAN
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/floorplan/svg-local")
async def floorplan_svg_local(req: dict):
    """Генерация SVG плана этажа."""
    try:
        from shared.floorplan import generate_floorplan_svg
        floor = req.pop("floor", 1)
        svg = generate_floorplan_svg(req, floor)
        return Response(content=svg, media_type="image/svg+xml")
    except Exception as e:
        raise HTTPException(500, str(e))


# ═══════════════════════════════════════════════════════════════
# BUILDING GRAPH
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/graph/building-local")
async def graph_building_local(req: dict):
    """Анализ графа здания."""
    try:
        from shared.graph import BuildingGraph
        bg = BuildingGraph.from_params(req)
        return {
            "rooms": bg.rooms,
            "edges": bg.edges,
            "adjacency": bg.get_adjacency_list(),
            "stats": bg.get_room_stats(),
        }
    except Exception as e:
        raise HTTPException(500, str(e))


# ═══════════════════════════════════════════════════════════════
# TASK QUEUE (Celery)
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/tasks/generate")
async def task_generate(req: GenerateRequest):
    """Запуск async генерации через Celery."""
    try:
        from shared.celery_app import generate_building_task
        params = fallback_regex_parse(req.prompt)
        result = generate_building_task.delay(params)
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
# STATIC FILES
# ═══════════════════════════════════════════════════════════════

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    port = settings.PORT
    print(f"Architect Server starting on port {port}")
    print(f"Model: {settings.LLM_MODEL}")
    print(f"Blender: {settings.BLENDER_PATH}")
    uvicorn.run(app, host="0.0.0.0", port=port)
