"""
Blender Microservice — генерация и выполнение bpy-скриптов [FastAPI]

Endpoints:
  POST /api/v1/execute             — Выполнить произвольный bpy-скрипт
  POST /api/v1/generate            — Промт → GLB/PNG (единый endpoint)
  POST /api/v1/generate/building   — Промт → GLB файл
  POST /api/v1/render/interior     — Промт → PNG файл
  POST /api/v1/preview             — Сгенерировать превью + скриншот
  GET  /health
"""

import sys
import os
import uuid
import subprocess

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
    description="Выполнение bpy-скриптов, генерация зданий и интерьеров через Blender CLI",
    version="4.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════
# CORE: Execute arbitrary bpy script
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/execute")
async def execute_script(req: dict):
    """
    Выполняет произвольный bpy-скрипт в Blender.
    Используется оркестратором и агентами.

    Body: { "script": "...", "output_path": "/app/output/file.glb", "timeout": 300 }
    """
    script = req.get("script", "")
    output_path = req.get("output_path", "")
    timeout = req.get("timeout", settings.BLENDER_TIMEOUT)

    if not script:
        raise HTTPException(400, "No script provided")

    job_id = uuid.uuid4().hex[:8]
    script_path = os.path.join(settings.OUTPUT_DIR, f"{job_id}_exec.py")

    # Validate syntax
    try:
        compile(script, f"<{job_id}>", "exec")
    except SyntaxError as e:
        raise HTTPException(400, f"Script syntax error: {e}")

    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
    with open(script_path, "w") as f:
        f.write(script)

    try:
        # Use Xvfb for headless rendering
        env = os.environ.copy()
        env.setdefault("DISPLAY", ":99")

        result = subprocess.run(
            [settings.BLENDER_PATH, "--background", "--factory-startup",
             "--log-level", "0", "--python", script_path],
            capture_output=True, text=True, timeout=timeout, env=env,
        )

        if result.returncode != 0:
            stderr_tail = (result.stderr or "")[-1000:]
            raise HTTPException(500, detail={
                "error": "Blender execution failed",
                "returncode": result.returncode,
                "stderr": stderr_tail,
            })

        # Check if output file was created
        output_exists = os.path.exists(output_path) if output_path else False
        output_size = os.path.getsize(output_path) if output_exists else 0

        return {
            "status": "ok",
            "output_path": output_path if output_exists else None,
            "output_size": output_size,
            "stdout_tail": (result.stdout or "")[-500:],
        }

    except subprocess.TimeoutExpired:
        raise HTTPException(504, detail=f"Blender timeout ({timeout}s)")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=str(e))
    finally:
        if os.path.exists(script_path):
            try:
                os.remove(script_path)
            except OSError:
                pass


# ═══════════════════════════════════════════════════════════════
# PREVIEW: Generate preview + screenshot
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/preview")
async def generate_preview(req: dict):
    """
    Генерирует превью 3D-модели (PNG скриншот).
    Быстрый рендер на низком качестве для предпросмотра.

    Body: { "prompt": "...", "quality": "preview" }
    """
    prompt = req.get("prompt", "")
    quality = req.get("quality", "preview")

    if not prompt:
        raise HTTPException(400, "No prompt provided")

    # Parse prompt
    params = fallback_regex_parse(prompt)
    gen_type = get_generation_type(params)

    # Generate geometry script
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

    # Add preview render settings (fast, low quality)
    job_id = uuid.uuid4().hex[:8]
    output_file = os.path.join(settings.OUTPUT_DIR, f"{job_id}_preview.png")

    script += f"""
import bpy, math

# Preview render settings (fast)
bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT'
bpy.context.scene.render.resolution_x = 1920
bpy.context.scene.render.resolution_y = 1080
bpy.context.scene.render.resolution_percentage = 100
try:
    bpy.context.scene.eevee.taa_render_samples = 32
except:
    pass
bpy.context.scene.render.image_settings.file_format = 'PNG'
bpy.context.scene.render.filepath = r'{output_file}'
bpy.ops.render.render(write_still=True)
"""

    # Execute
    script_path = os.path.join(settings.OUTPUT_DIR, f"{job_id}_preview.py")
    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
    with open(script_path, "w") as f:
        f.write(script)

    try:
        env = os.environ.copy()
        env.setdefault("DISPLAY", ":99")

        result = subprocess.run(
            [settings.BLENDER_PATH, "--background", "--factory-startup",
             "--log-level", "0", "--python", script_path],
            capture_output=True, text=True, timeout=60, env=env,
        )

        if result.returncode != 0:
            raise HTTPException(500, detail=f"Preview render failed: {result.stderr[-500:]}")

        if os.path.exists(output_file):
            return FileResponse(
                output_file,
                media_type="image/png",
                filename=f"preview_{job_id}.png",
            )
        raise HTTPException(500, "Preview file not created")

    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Preview render timeout (60s)")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        if os.path.exists(script_path):
            try:
                os.remove(script_path)
            except OSError:
                pass


# ═══════════════════════════════════════════════════════════════
# LEGACY: Generate building / Render interior
# ═══════════════════════════════════════════════════════════════

async def _parse_via_shared(prompt: str) -> dict:
    from shared.parser import parse_prompt_sync
    return parse_prompt_sync(prompt)


@app.get("/health")
async def health():
    return HealthResponse(status="ok", service="blender-service", version="4.0.0")


@app.post("/api/v1/generate")
async def generate(req: GenerateRequest):
    """Единый endpoint: промт → парсинг → роутинг → генерация."""
    params = await _parse_via_shared(req.prompt)
    gen_type = get_generation_type(params)

    if gen_type == "interior":
        return await _generate_interior(params)
    else:
        return await _generate_building(params)


@app.post("/api/v1/generate/building")
async def generate_building_legacy(req: GenerateRequest):
    params = await _parse_via_shared(req.prompt)
    return await _generate_building(params)


@app.post("/api/v1/render/interior")
async def render_interior_legacy(req: GenerateRequest):
    params = await _parse_via_shared(req.prompt)
    return await _generate_interior(params)


# ═══════════════════════════════════════════════════════════════
# HELPERS
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
        run_blender(script + export_cmd, output_file)
    except TimeoutError as e:
        raise HTTPException(504, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(500, detail={"error": str(e)})

    if os.path.exists(output_file):
        return FileResponse(output_file, media_type="model/gltf-binary", filename=f"archai_{job_id}.glb")
    raise HTTPException(500, detail="Export failed")


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
# STARTUP
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8082))
    print(f"Blender Service starting on port {port}")
    print(f"Blender: {settings.BLENDER_PATH}")
    uvicorn.run(app, host="0.0.0.0", port=port)
