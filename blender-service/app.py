"""
Blender Microservice — генерация и выполнение bpy-скриптов [FastAPI]

v6.0 — Парсинг ТОЛЬКО через LLM-service (HTTP).
Локальный regex fallback УДАЛЁН.
Tiled rendering для 16K.
"""

import logging
import os
import subprocess
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from shared.blender import generate_bpy_script, generate_interior_script, run_blender
from shared.config import settings
from shared.logging_config import setup_logging
from shared.models import GenerateRequest, HealthResponse
from shared.validation import DEFAULT_FURNITURE

setup_logging("blender-service")
logger = logging.getLogger("archai.blender")

app = FastAPI(
    title="Architect Blender Service",
    description="Blender CLI: генерация 3D, рендер (до 16K tiled), экспорт",
    version="7.0.0",
)

_cors_origins = os.environ.get("CORS_ORIGINS", "*")
_origins_list = [o.strip() for o in _cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════
# PARSE HELPER — вызов LLM-service (НЕ regex)
# ═══════════════════════════════════════════════════════════════


async def _parse_via_llm_service(prompt: str) -> dict:
    """Парсинг промта через LLM-service. Если LLM-service недоступен — 503."""
    llm_url = settings.LLM_SERVICE_URL
    if not llm_url:
        raise HTTPException(503, "LLM service not configured")

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{llm_url}/api/v1/parse",
                json={"text": prompt},
                timeout=60.0,
            )
        if r.status_code == 200:
            return r.json()
        elif r.status_code == 503:
            raise HTTPException(503, "LLM service unavailable — all models failed")
        else:
            raise HTTPException(r.status_code, r.text)
    except httpx.TimeoutException:
        raise HTTPException(504, "LLM service timeout")
    except httpx.ConnectError:
        raise HTTPException(503, "LLM service unreachable")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"LLM service error: {e}")


def _detect_gen_type(params: dict) -> str:
    """Detect generation type from LLM-parsed params.
    
    LLM is the source of truth for object_type.
    Only falls back if LLM didn't provide object_type.
    
    Returns: 'interior', 'landscape', or 'building'
    """
    obj_type = (params.get("object_type") or "").strip().lower()
    room_type = (params.get("room_type") or "").strip().lower()
    building_type = (params.get("building_type") or "").strip().lower()
    
    # LLM is the source of truth — trust its object_type
    if obj_type in ("interior", "room"):
        return "interior"
    if obj_type == "landscape":
        return "landscape"
    if obj_type == "building":
        return "building"
    
    # If LLM set room_type but not object_type — it's interior
    if room_type:
        return "interior"
    
    # If building_type explicitly says landscape
    if building_type == "landscape":
        return "landscape"
    
    # Fallback: object_type missing from LLM response — default to building
    return "building"


# ═══════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════


@app.get("/health")
async def health():
    return HealthResponse(status="ok", service="blender-service", version="6.0.0")


# ═══════════════════════════════════════════════════════════════
# EXECUTE — произвольный bpy-скрипт
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/execute")
async def execute_script(req: dict):
    """Выполняет bpy-скрипт в Blender."""
    script = req.get("script", "")
    output_path = req.get("output_path", "")
    timeout = req.get("timeout", settings.BLENDER_TIMEOUT)

    if not script:
        raise HTTPException(400, "No script provided")

    job_id = uuid.uuid4().hex[:8]
    script_path = os.path.join(settings.OUTPUT_DIR, f"{job_id}_exec.py")

    try:
        compile(script, f"<{job_id}>", "exec")
    except SyntaxError as e:
        raise HTTPException(400, f"Script syntax error: {e}")

    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
    with open(script_path, "w") as f:
        f.write(script)

    try:
        env = os.environ.copy()
        env.setdefault("DISPLAY", ":99")

        result = subprocess.run(
            [settings.BLENDER_PATH, "--background", "--factory-startup", "--log-level", "0", "--python", script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

        if result.returncode != 0:
            raise HTTPException(
                500,
                detail={
                    "error": "Blender execution failed",
                    "returncode": result.returncode,
                    "stderr": (result.stderr or "")[-1000:],
                },
            )

        output_exists = os.path.exists(output_path) if output_path else False
        return {
            "status": "ok",
            "output_path": output_path if output_exists else None,
            "output_size": os.path.getsize(output_path) if output_exists else 0,
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
# PREVIEW — быстрое превью (LLM-only парсинг)
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/preview")
async def generate_preview(req: dict):
    """Быстрое превью. Парсинг ТОЛЬКО через LLM-service."""
    prompt = req.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "No prompt provided")

    # Парсинг через LLM-service
    params = await _parse_via_llm_service(prompt)
    gen_type = _detect_gen_type(params)

    if gen_type == "interior":
        room_type = params.get("room_type", "living")
        furniture = params.get("furniture") or DEFAULT_FURNITURE.get(room_type, ["sofa", "table", "chandelier"])
        script = generate_interior_script(
            {
                "width": params.get("width_m", 6),
                "length": params.get("length_m", 8),
                "height": params.get("height_m", 3),
                "style": params.get("style", "modern"),
                "furniture": furniture,
            }
        )
    else:
        script = generate_bpy_script(
            {
                "width": params.get("width_m", 10),
                "length": params.get("length_m", 12),
                "floors": params.get("floors", 2),
                "roof_type": params.get("roof_type", "gabled"),
                "facade_material": params.get("material", "plaster"),
                "has_balcony": "balcony" in params.get("features", []),
            }
        )

    job_id = uuid.uuid4().hex[:8]
    output_file = os.path.join(settings.OUTPUT_DIR, f"{job_id}_preview.png")

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

    script_path = os.path.join(settings.OUTPUT_DIR, f"{job_id}_preview.py")
    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
    with open(script_path, "w") as f:
        f.write(script)

    try:
        env = os.environ.copy()
        env.setdefault("DISPLAY", ":99")
        result = subprocess.run(
            [settings.BLENDER_PATH, "--background", "--factory-startup", "--log-level", "0", "--python", script_path],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        if result.returncode != 0:
            raise HTTPException(500, detail=f"Preview failed: {result.stderr[-500:]}")
        if os.path.exists(output_file):
            return FileResponse(output_file, media_type="image/png", filename=f"preview_{job_id}.png")
        raise HTTPException(500, "Preview file not created")
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Preview timeout (60s)")
    except HTTPException:
        raise
    finally:
        if os.path.exists(script_path):
            try:
                os.remove(script_path)
            except OSError:
                pass


# ═══════════════════════════════════════════════════════════════
# GENERATE — полная генерация (LLM-only парсинг)
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/generate")
async def generate(req: GenerateRequest):
    """Генерация: промт → LLM парсинг → Blender → GLB/PNG."""
    params = await _parse_via_llm_service(req.prompt)
    gen_type = _detect_gen_type(params)
    quality = getattr(req, 'quality', '16k') or '16k'

    if gen_type == "interior":
        return await _generate_interior(params, quality=quality)
    elif gen_type == "landscape":
        return await _generate_building(params, quality=quality)
    else:
        return await _generate_building(params, quality=quality)


@app.post("/api/v1/generate/building")
async def generate_building_endpoint(req: GenerateRequest):
    params = await _parse_via_llm_service(req.prompt)
    return await _generate_building(params)


@app.post("/api/v1/render/interior")
async def render_interior_endpoint(req: GenerateRequest):
    params = await _parse_via_llm_service(req.prompt)
    return await _generate_interior(params)


# ═══════════════════════════════════════════════════════════════
# 16K TILED RENDER
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/render/16k")
async def render_16k(req: dict):
    """
    Рендер 16K через tiled rendering.
    Body: { "prompt": "...", "tiles_x": 4, "tiles_y": 3, "samples": 2048 }
    """
    prompt = req.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "No prompt provided")

    tiles_x = req.get("tiles_x", 4)
    tiles_y = req.get("tiles_y", 3)
    samples = req.get("samples", 2048)

    # Парсинг через LLM-service
    params = await _parse_via_llm_service(prompt)
    gen_type = _detect_gen_type(params)

    if gen_type == "interior":
        room_type = params.get("room_type", "living")
        furniture = params.get("furniture") or DEFAULT_FURNITURE.get(room_type, ["sofa", "table"])
        scene_script = generate_interior_script(
            {
                "width": params.get("width_m", 6),
                "length": params.get("length_m", 8),
                "height": params.get("height_m", 3),
                "style": params.get("style", "modern"),
                "furniture": furniture,
            }
        )
    else:
        scene_script = generate_bpy_script(
            {
                "width": params.get("width_m", 10),
                "length": params.get("length_m", 12),
                "floors": params.get("floors", 2),
                "roof_type": params.get("roof_type", "gabled"),
                "facade_material": params.get("material", "plaster"),
                "has_balcony": "balcony" in params.get("features", []),
            }
        )

    job_id = uuid.uuid4().hex[:8]
    output_path = os.path.join(settings.OUTPUT_DIR, f"{job_id}_16k.png")

    try:
        from shared.tiled_render import render_16k_tiled

        result_path = render_16k_tiled(
            scene_script=scene_script,
            output_path=output_path,
            total_x=15360,
            total_y=8640,
            tiles_x=tiles_x,
            tiles_y=tiles_y,
            samples=samples,
            blender_path=settings.BLENDER_PATH,
            output_dir=settings.OUTPUT_DIR,
            timeout_per_tile=600,
        )
        return FileResponse(result_path, media_type="image/png", filename=f"archai_16k_{job_id}.png")
    except TimeoutError as e:
        raise HTTPException(504, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(500, detail=str(e))
    except Exception as e:
        raise HTTPException(500, detail=f"16K render failed: {e}")


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════


async def _generate_building(params: dict, quality: str = "16k"):
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

    # Always export GLB
    export_cmd = f"\nimport bpy\nbpy.ops.export_scene.gltf(filepath=r'{output_file}', export_format='GLB')"

    if quality == "16k":
        # 16K tiled render (Cycles) — default
        output_png = os.path.join(settings.OUTPUT_DIR, f"{job_id}_16k.png")
        try:
            run_blender(script + export_cmd, output_file, timeout=300)
        except TimeoutError as e:
            raise HTTPException(504, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(500, detail={"error": str(e)})

        # 16K tiled render
        try:
            from shared.tiled_render import render_16k_tiled
            render_16k_tiled(
                scene_script=script,
                output_path=output_png,
                total_x=15360,
                total_y=8640,
                tiles_x=4,
                tiles_y=3,
                samples=512,
                blender_path=settings.BLENDER_PATH,
                output_dir=settings.OUTPUT_DIR,
                timeout_per_tile=300,
            )
            logger.info("16K render done: %s", output_png)
        except Exception as e:
            logger.warning("16K tiled render failed: %s, falling back to EEVEE 4K", e)
            _render_eevee_4k(script, job_id, output_png)
    else:
        # Fast EEVEE 4K preview
        output_png = os.path.join(settings.OUTPUT_DIR, f"{job_id}_render.png")
        try:
            run_blender(script + export_cmd, output_file, timeout=300)
        except TimeoutError as e:
            raise HTTPException(504, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(500, detail={"error": str(e)})
        _render_eevee_4k(script, job_id, output_png)

    # Quality check
    if os.path.exists(output_png):
        try:
            from PIL import Image
            img = Image.open(output_png)
            w, h = img.size
            logger.info("Render quality: %dx%d", w, h)
            if w < 3840 or h < 2160:
                logger.warning("Render below 4K: %dx%d", w, h)
        except Exception as e:
            logger.warning("Quality check failed: %s", e)

    if os.path.exists(output_file):
        return FileResponse(output_file, media_type="model/gltf-binary", filename=f"archai_{job_id}.glb")
    raise HTTPException(500, detail="Export failed")


def _render_eevee_4k(script: str, job_id: str, output_png: str):
    """Fast EEVEE 4K render as fallback."""
    render_cmd = f"""
import bpy
bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT'
bpy.context.scene.render.resolution_x = 3840
bpy.context.scene.render.resolution_y = 2160
bpy.context.scene.render.resolution_percentage = 100
try:
    bpy.context.scene.eevee.taa_render_samples = 64
except:
    pass
bpy.context.scene.render.image_settings.file_format = 'PNG'
bpy.context.scene.render.filepath = r'{output_png}'
bpy.ops.render.render(write_still=True)
"""
    try:
        run_blender(script + render_cmd, output_png, timeout=120)
    except Exception as e:
        logger.warning("EEVEE 4K fallback failed: %s", e)


async def _generate_interior(params: dict, quality: str = "16k"):
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

    if quality == "16k":
        # 16K tiled render for interior
        try:
            from shared.tiled_render import render_16k_tiled
            render_16k_tiled(
                scene_script=script,
                output_path=output_file,
                total_x=15360,
                total_y=8640,
                tiles_x=4,
                tiles_y=3,
                samples=512,
                blender_path=settings.BLENDER_PATH,
                output_dir=settings.OUTPUT_DIR,
                timeout_per_tile=300,
            )
            logger.info("Interior 16K render done: %s", output_file)
        except Exception as e:
            logger.warning("Interior 16K failed: %s, falling back to EEVEE 4K", e)
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
    else:
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


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8082))
    print(f"Blender Service starting on port {port}")
    print(f"Blender: {settings.BLENDER_PATH}")
    uvicorn.run(app, host="0.0.0.0", port=port)
