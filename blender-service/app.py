"""
Blender Microservice — генерация зданий (GLB) и интерьеров (PNG) [FastAPI]

Использует shared-пакет для парсинга, валидации и генерации bpy-скриптов.

Endpoints:
  POST /api/v1/generate           → GLB или PNG (единый endpoint с роутингом)
  POST /api/v1/generate/building  → GLB файл (legacy)
  POST /api/v1/render/interior    → PNG файл (legacy)
  GET  /health
  GET  /docs                      — OpenAPI documentation
"""

import sys
import os
import uuid

# Добавить корень проекта в path для импорта shared
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from shared.config import settings
from shared.models import GenerateRequest, HealthResponse
from shared.parser import fallback_regex_parse, get_generation_type
from shared.validation import DEFAULT_FURNITURE
from shared.blender import generate_bpy_script, generate_interior_script, run_blender

app = FastAPI(
    title="Architect Blender Service",
    description="Генерация 3D-моделей зданий (GLB) и интерьеров (PNG) через Blender CLI (shared)",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

async def _parse_via_llm(prompt: str) -> dict | None:
    """Попытка парсинга через LLM-сервис."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{settings.LLM_SERVICE_URL}/api/v1/parse",
                json={"text": prompt},
                timeout=15.0,
            )
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        print(f"[blender-service] LLM parse unavailable: {e}")
    return None


def _parse_prompt(prompt: str) -> dict:
    """Парсинг промта: LLM → fallback regex."""
    # Сначала через shared parser (который сам делает LLM + fallback)
    from shared.parser import parse_prompt_sync
    return parse_prompt_sync(prompt)


# ═══════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return HealthResponse(
        status="ok",
        service="blender-service",
        version="3.0.0",
    )


@app.post("/api/v1/generate")
async def generate(req: GenerateRequest):
    """Единый endpoint: промт → парсинг → роутинг → генерация."""
    params = _parse_prompt(req.prompt)
    gen_type = get_generation_type(params)

    if gen_type == "interior":
        return await _generate_interior(params)
    else:
        return await _generate_building(params)


@app.post("/api/v1/generate/building")
async def generate_building_legacy(req: GenerateRequest):
    """Legacy endpoint для генерации здания."""
    params = _parse_prompt(req.prompt)
    return await _generate_building(params)


@app.post("/api/v1/render/interior")
async def render_interior_legacy(req: GenerateRequest):
    """Legacy endpoint для рендеринга интерьера."""
    params = _parse_prompt(req.prompt)
    return await _generate_interior(params)


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
    output_file = os.path.join(settings.OUTPUT_DIR, f"{job_id}.glb")
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
    output_file = os.path.join(settings.OUTPUT_DIR, f"{job_id}_int.png")

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
# STARTUP
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8082))
    print(f"Blender Service starting on port {port}")
    print(f"Blender: {settings.BLENDER_PATH}")
    print(f"LLM Service: {settings.LLM_SERVICE_URL}")
    uvicorn.run(app, host="0.0.0.0", port=port)
