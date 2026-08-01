"""
shared/tiled_render.py — Tiled rendering для 16K через Blender Cycles.

Проблема: 15360×8640 @ 2048 samples требует >16 GB VRAM.
Решение: разбиваем на тайлы (4×3 = 12 тайлов по 3840×2880),
рендерим каждый отдельно, собираем финальное изображение.
"""

import os
import uuid
import subprocess
import logging

from PIL import Image

logger = logging.getLogger("archai.tiled_render")


def render_16k_tiled(
    scene_script: str,
    output_path: str,
    total_x: int = 15360,
    total_y: int = 8640,
    tiles_x: int = 4,
    tiles_y: int = 3,
    samples: int = 2048,
    blender_path: str = "blender",
    output_dir: str = "/app/output",
    timeout_per_tile: int = 600,
) -> str:
    tile_w = total_x // tiles_x
    tile_h = total_y // tiles_y
    job_id = uuid.uuid4().hex[:8]
    tile_paths = []

    logger.info(f"16K tiled render: {tiles_x}x{tiles_y} tiles, {tile_w}x{tile_h} each, {samples} samples")

    for ty in range(tiles_y):
        for tx in range(tiles_x):
            tile_idx = ty * tiles_x + tx
            tile_path = os.path.join(output_dir, f"{job_id}_tile_{ty}_{tx}.png")
            tile_script = _build_tile_script(scene_script, tile_path, total_x, total_y,
                                              tx * tile_w, ty * tile_h, tile_w, tile_h, samples)
            script_path = os.path.join(output_dir, f"{job_id}_tile_{ty}_{tx}.py")
            with open(script_path, "w") as f:
                f.write(tile_script)

            try:
                env = os.environ.copy()
                env.setdefault("DISPLAY", ":99")
                logger.info(f"Tile {tile_idx + 1}/{tiles_x * tiles_y}: ({tx},{ty})")
                result = subprocess.run(
                    [blender_path, "--background", "--factory-startup", "--log-level", "0", "--python", script_path],
                    capture_output=True, text=True, timeout=timeout_per_tile, env=env,
                )
                if result.returncode != 0:
                    raise RuntimeError(f"Tile {tile_idx} failed: {result.stderr[-500:]}")
                if os.path.exists(tile_path):
                    tile_paths.append((tx, ty, tile_path))
                else:
                    raise RuntimeError(f"Tile {tile_idx} output not created")
            except subprocess.TimeoutExpired:
                raise TimeoutError(f"Tile {tile_idx} timeout ({timeout_per_tile}s)")
            finally:
                if os.path.exists(script_path):
                    try:
                        os.remove(script_path)
                    except OSError:
                        pass

    _assemble_tiles(tile_paths, output_path, total_x, total_y, tile_w, tile_h)

    for _, _, path in tile_paths:
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    if os.path.exists(output_path):
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"16K done: {output_path} ({size_mb:.1f} MB)")
    else:
        raise RuntimeError("Final image not created")
    return output_path


def _build_tile_script(scene_script, output_path, total_x, total_y, tile_x, tile_y, tile_w, tile_h, samples):
    return f"""import bpy, os

{scene_script}

bpy.context.scene.render.engine = 'CYCLES'
bpy.context.scene.cycles.device = 'CPU'
bpy.context.scene.cycles.samples = {samples}
bpy.context.scene.cycles.use_denoising = True
bpy.context.scene.cycles.denoiser = 'OPENIMAGEDENOISE'
bpy.context.scene.cycles.use_adaptive_sampling = True
bpy.context.scene.cycles.adaptive_threshold = 0.005
bpy.context.scene.render.resolution_x = {total_x}
bpy.context.scene.render.resolution_y = {total_y}
bpy.context.scene.render.resolution_percentage = 100
bpy.context.scene.render.use_border = True
bpy.context.scene.render.border_min_x = {tile_x / total_x:.6f}
bpy.context.scene.render.border_max_x = {(tile_x + tile_w) / total_x:.6f}
bpy.context.scene.render.border_min_y = {1.0 - (tile_y + tile_h) / total_y:.6f}
bpy.context.scene.render.border_max_y = {1.0 - tile_y / total_y:.6f}
bpy.context.scene.render.use_crop_to_border = True
bpy.context.scene.cycles.tile_x = 256
bpy.context.scene.cycles.tile_y = 256
bpy.context.scene.cycles.max_bounces = 12
bpy.context.scene.cycles.diffuse_bounces = 4
bpy.context.scene.cycles.glossy_bounces = 4
bpy.context.scene.cycles.transmission_bounces = 8
bpy.context.scene.render.image_settings.file_format = 'PNG'
bpy.context.scene.render.image_settings.color_mode = 'RGBA'
bpy.context.scene.render.image_settings.compression = 0
bpy.context.scene.render.filepath = r'{output_path}'
bpy.ops.render.render(write_still=True)
"""


def _assemble_tiles(tile_paths, output_path, total_x, total_y, tile_w, tile_h):
    final = Image.new("RGB", (total_x, total_y))
    for tx, ty, path in tile_paths:
        tile_img = Image.open(path)
        tile_img = tile_img.crop((0, 0, tile_w, tile_h))
        final.paste(tile_img, (tx * tile_w, ty * tile_h))
        tile_img.close()
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    final.save(output_path, "PNG", compress_level=1)
    final.close()
