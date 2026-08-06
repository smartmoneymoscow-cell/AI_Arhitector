"""
shared/agents/render_agent.py — Агент рендеринга.

Вызывает blender-service для реального выполнения bpy-скриптов.
Поддерживает качество до 16K (15360×8640).
"""

import os
import time

import httpx

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

# Пресеты качества рендера
QUALITY_PRESETS = {
    "preview": {
        "engine": "CYCLES", "device": "CPU", "samples": 16,
        "resolution_x": 1280,
        "resolution_y": 720,
        "samples": 64,
        "use_denoising": False,
        "tile_size": 64,
    },
    "standard": {
        "engine": "CYCLES", "device": "CPU", "samples": 16,
        "resolution_x": 3840,
        "resolution_y": 2160,
        "samples": 128,
        "use_denoising": False,
        "tile_size": 128,
    },
    "high": {
        "engine": "CYCLES", "device": "CPU", "samples": 16,
        "resolution_x": 7680,
        "resolution_y": 4320,
        "samples": 256,
        "use_denoising": False,
        "tile_size": 256,
    },
    "ultra": {
        "engine": "CYCLES", "device": "CPU", "samples": 16,
        "resolution_x": 15360,
        "resolution_y": 8640,
        "samples": 1024,
        "use_denoising": False,
        "use_adaptive_sampling": True,
        "adaptive_threshold": 0.01,
        "tile_size": 64,
        "use_motion_blur": False,
        "use_bloom": True,
    },
    "16k": {
        "engine": "CYCLES", "device": "CPU", "samples": 16,
        "resolution_x": 15360,
        "resolution_y": 8640,
        "samples": 2048,
        "use_denoising": False,
        "use_adaptive_sampling": True,
        "adaptive_threshold": 0.005,
        "tile_size": 64,
        "max_bounces": 12,
        "diffuse_bounces": 4,
        "glossy_bounces": 4,
        "transmission_bounces": 8,
        "use_motion_blur": True,
        "use_bloom": True,
    },
}


def build_render_script(preset: dict, output_path: str, camera_params: dict | None = None) -> str:
    """Генерирует bpy-скрипт настройки рендера."""
    engine = preset["engine"]
    rx = preset["resolution_x"]
    ry = preset["resolution_y"]
    samples = preset["samples"]
    denoise = preset.get("use_denoising", True)

    script = f"""
import bpy, os

# Render settings
bpy.context.scene.render.engine = '{engine}'
bpy.context.scene.cycles.device = 'CPU'
bpy.context.scene.cycles.samples = 16
bpy.context.scene.cycles.use_denoising = False
bpy.context.scene.render.resolution_x = {rx}
bpy.context.scene.render.resolution_y = {ry}
bpy.context.scene.render.resolution_percentage = 100
bpy.context.scene.render.film_transparent = False
bpy.context.scene.render.image_settings.file_format = 'PNG'
bpy.context.scene.render.image_settings.color_mode = 'RGBA'
bpy.context.scene.render.image_settings.compression = 0
bpy.context.scene.render.filepath = r'{output_path}'
"""

    if engine == "CYCLES":
        script += f"""
# Cycles settings
bpy.context.scene.cycles.samples = {samples}
bpy.context.scene.cycles.use_denoising = {denoise}
bpy.context.scene.cycles.denoiser = 'OPTIX'  # OIDN not available on Render free tier
bpy.context.scene.cycles.use_adaptive_sampling = {preset.get("use_adaptive_sampling", True)}
bpy.context.scene.cycles.adaptive_threshold = {preset.get("adaptive_threshold", 0.01)}
bpy.context.scene.cycles.tile_x = {preset.get("tile_size", 64)}
bpy.context.scene.cycles.tile_y = {preset.get("tile_size", 64)}
bpy.context.scene.cycles.max_bounces = {preset.get("max_bounces", 8)}
bpy.context.scene.cycles.diffuse_bounces = {preset.get("diffuse_bounces", 4)}
bpy.context.scene.cycles.glossy_bounces = {preset.get("glossy_bounces", 4)}
bpy.context.scene.cycles.transmission_bounces = {preset.get("transmission_bounces", 8)}
bpy.context.scene.cycles.transparent_max_bounces = 8
"""
        if preset.get("use_motion_blur"):
            script += "bpy.context.scene.render.use_motion_blur = True\n"
    else:
        # EEVEE / EEVEE Next
        script += f"""
# EEVEE settings
try:
    bpy.context.scene.eevee.taa_render_samples = {samples}
except:
    pass
try:
    bpy.context.scene.eevee.use_gtao = True
    bpy.context.scene.eevee.gtao_distance = 0.5
except:
    pass
try:
    bpy.context.scene.eevee.use_bloom = {preset.get("use_bloom", True)}
except:
    pass
try:
    bpy.context.scene.eevee.use_ssr = True
    bpy.context.scene.eevee.use_ssr_refraction = True
except:
    pass
"""

    # Camera setup
    if camera_params:
        script += f"""
# Camera setup
cam = bpy.data.cameras.new("RenderCam")
cam.lens = {camera_params.get("focal_length", 35)}
cam.clip_start = 0.1
cam.clip_end = 1000
cam_obj = bpy.data.objects.new("RenderCam", cam)
bpy.context.scene.collection.objects.link(cam_obj)
bpy.context.scene.camera = cam_obj
cam_obj.location = ({camera_params.get("x", 0)}, {camera_params.get("y", -20)}, {camera_params.get("z", 15)})
cam_obj.rotation_euler = ({camera_params.get("rx", 1.1)}, {camera_params.get("ry", 0)}, {camera_params.get("rz", 0)})
"""

    # Lighting
    script += """
# Enhanced lighting
# Key light (Sun)
if "Sun" not in bpy.data.objects:
    sun = bpy.data.lights.new("Sun", "SUN")
    sun.energy = 5
    sun.color = (1.0, 0.95, 0.9)
    sun.angle = 0.02
    sun_obj = bpy.data.objects.new("Sun", sun)
    bpy.context.collection.objects.link(sun_obj)
    sun_obj.rotation_euler = (0.785, 0.262, 0.524)

# Fill light (Area)
if "FillLight" not in bpy.data.objects:
    fill = bpy.data.lights.new("Fill", "AREA")
    fill.energy = 300
    fill.size = 15
    fill.color = (0.9, 0.95, 1.0)
    fill_obj = bpy.data.objects.new("FillLight", fill)
    bpy.context.collection.objects.link(fill_obj)
    fill_obj.location = (-15, 15, 20)
    fill_obj.rotation_euler = (1.047, 0, -2.356)

# Rim light
if "RimLight" not in bpy.data.objects:
    rim = bpy.data.lights.new("Rim", "AREA")
    rim.energy = 150
    rim.size = 5
    rim.color = (1.0, 0.9, 0.8)
    rim_obj = bpy.data.objects.new("RimLight", rim)
    bpy.context.collection.objects.link(rim_obj)
    rim_obj.location = (10, -10, 12)
    rim_obj.rotation_euler = (0.785, 0, 0.785)
"""

    # World
    script += """
# World setup
world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs["Color"].default_value = (0.5, 0.7, 1.0, 1.0)
    bg.inputs["Strength"].default_value = 1.2
"""

    script += """
# Render
bpy.ops.render.render(write_still=True)
print(f"RENDER_DONE: {0}".format(r'{output_path}'))
"""
    return script


class RenderAgent(BaseAgent):
    """Агент рендеринга — вызывает blender-service для выполнения."""

    name = "render"

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            quality = task.params.get("quality", "standard")
            script = task.params.get("script", "")
            output_path = task.params.get("output_path", "")
            blender_service_url = task.params.get("blender_service_url", "")
            camera_params = task.params.get("camera_params")

            preset = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["standard"])

            if not output_path:
                import uuid

                job_id = uuid.uuid4().hex[:8]
                output_dir = task.params.get("output_dir", "/app/output")
                output_path = os.path.join(output_dir, f"{job_id}_render.png")

            render_script = build_render_script(preset, output_path, camera_params)
            full_script = script + "\n" + render_script

            if blender_service_url:
                # Вызов blender-service через HTTP
                result = self._call_blender_service(blender_service_url, full_script, output_path)
            else:
                # Локальный вызов (для монолита)
                result = self._run_local(full_script, output_path)

            return TaskResult(
                status=TaskStatus.DONE,
                data={
                    "output_path": output_path,
                    "quality": quality,
                    "resolution": f"{preset['resolution_x']}x{preset['resolution_y']}",
                    "engine": preset["engine"],
                    "samples": preset["samples"],
                    **result,
                },
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _call_blender_service(self, base_url: str, script: str, output_path: str) -> dict:
        """Вызывает blender-service через HTTP для рендера."""
        try:
            with httpx.Client(timeout=600.0) as client:
                r = client.post(
                    f"{base_url}/api/v1/execute",
                    json={"script": script, "output_path": output_path},
                )
                if r.status_code == 200:
                    return r.json()
                raise RuntimeError(f"Blender service returned {r.status_code}: {r.text[:500]}")
        except httpx.TimeoutException:
            raise TimeoutError("Blender service render timeout (600s)")
        except Exception as e:
            raise RuntimeError(f"Blender service call failed: {e}")

    def _run_local(self, script: str, output_path: str) -> dict:
        """Локальный запуск Blender."""
        import subprocess

        job_id = os.path.basename(output_path).split("_")[0]
        script_path = os.path.join(os.path.dirname(output_path) or "/tmp", f"{job_id}_render.py")

        try:
            compile(script, f"<{job_id}_render>", "exec")
        except SyntaxError as e:
            raise ValueError(f"Render script syntax error: {e}")

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(script_path, "w") as f:
            f.write(script)

        try:
            result = subprocess.run(
                ["blender", "--background", "--factory-startup", "--log-level", "0", "--python", script_path],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Blender render failed: {result.stderr[-500:]}")
            return {"blender_output": result.stdout[-200:]}
        except subprocess.TimeoutExpired:
            raise TimeoutError("Blender render timeout (600s)")
        finally:
            if os.path.exists(script_path):
                try:
                    os.remove(script_path)
                except OSError:
                    pass
