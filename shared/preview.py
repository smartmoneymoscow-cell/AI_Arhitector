"""
shared/preview.py — Модуль превью и анализа рендеров.

Генерирует превью-скриншоты и анализирует их через mimo-omni.

Использование:
    from shared.preview import generate_preview, analyze_render

    # Сгенерировать превью
    preview_path = generate_preview(prompt="двухэтажный дом", output_dir="/app/output")

    # Проанализировать рендер
    analysis = analyze_render("/app/output/render.png")
"""

import os
import uuid
import subprocess
import json
from typing import Optional

from shared.config import settings
from shared.parser import fallback_regex_parse, get_generation_type
from shared.blender import generate_bpy_script, generate_interior_script
from shared.validation import DEFAULT_FURNITURE


def generate_preview(prompt: str, output_dir: str = "", quality: str = "preview") -> str:
    """
    Генерирует превью-скриншот для промта.

    Args:
        prompt: текстовый промт
        output_dir: директория для сохранения
        quality: качество (preview/standard)

    Returns:
        Путь к сгенерированному превью (PNG)
    """
    if not output_dir:
        output_dir = settings.OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    params = fallback_regex_parse(prompt)
    gen_type = get_generation_type(params)

    # Generate geometry script
    if gen_type == "interior":
        room_type = params.get("room_type", "living")
        furniture = params.get("furniture") or DEFAULT_FURNITURE.get(
            room_type, ["sofa", "table", "chandelier"]
        )
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

    # Quality presets
    presets = {
        "preview": {"engine": "BLENDER_EEVEE_NEXT", "res_x": 1920, "res_y": 1080, "samples": 32, "timeout": 60},
        "standard": {"engine": "BLENDER_EEVEE_NEXT", "res_x": 3840, "res_y": 2160, "samples": 128, "timeout": 120},
    }
    p = presets.get(quality, presets["preview"])

    job_id = uuid.uuid4().hex[:8]
    output_file = os.path.join(output_dir, f"{job_id}_preview.png")

    script += f"""
import bpy
bpy.context.scene.render.engine = '{p["engine"]}'
bpy.context.scene.render.resolution_x = {p["res_x"]}
bpy.context.scene.render.resolution_y = {p["res_y"]}
try:
    bpy.context.scene.eevee.taa_render_samples = {p["samples"]}
except:
    pass
bpy.context.scene.render.image_settings.file_format = 'PNG'
bpy.context.scene.render.filepath = r'{output_file}'
bpy.ops.render.render(write_still=True)
"""

    # Execute Blender
    script_path = os.path.join(output_dir, f"{job_id}_preview.py")
    with open(script_path, "w") as f:
        f.write(script)

    try:
        env = os.environ.copy()
        env.setdefault("DISPLAY", ":99")

        result = subprocess.run(
            [settings.BLENDER_PATH, "--background", "--factory-startup",
             "--log-level", "0", "--python", script_path],
            capture_output=True, text=True, timeout=p["timeout"], env=env,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Preview render failed: {result.stderr[-500:]}")

        if os.path.exists(output_file):
            return output_file
        raise RuntimeError("Preview file not created")

    except subprocess.TimeoutExpired:
        raise TimeoutError(f"Preview render timeout ({p['timeout']}s)")
    finally:
        if os.path.exists(script_path):
            try:
                os.remove(script_path)
            except OSError:
                pass


def analyze_render(image_path: str, question: str = "") -> dict:
    """
    Анализирует рендер через mimo-omni (если доступен).

    Args:
        image_path: путь к изображению
        question: вопрос об изображении (опционально)

    Returns:
        dict с анализом: {"description": "...", "quality": "...", "issues": [...]}
    """
    if not os.path.exists(image_path):
        return {"error": f"Image not found: {image_path}"}

    default_question = (
        "Проанализируй этот архитектурный рендер. "
        "Оцени качество (геометрия, текстуры, освещение, композиция). "
        "Укажи проблемы если есть. Отвечай на русском."
    )

    analysis_prompt = question or default_question

    # Try mimo-omni via shell script
    try:
        mimo_script = os.path.expanduser("~/.openclaw/skills/mimo-omni/mimo_api.sh")
        if os.path.exists(mimo_script):
            result = subprocess.run(
                ["bash", mimo_script, "image", image_path, analysis_prompt],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                return {
                    "description": result.stdout.strip(),
                    "source": "mimo-omni",
                    "image": image_path,
                }
    except Exception as e:
        pass

    # Fallback: basic file info
    try:
        from PIL import Image
        img = Image.open(image_path)
        return {
            "description": f"Изображение {img.width}×{img.height}, формат: {img.format}",
            "source": "pil_info",
            "image": image_path,
            "note": "mimo-omni недоступен для полного анализа",
        }
    except ImportError:
        return {
            "description": "Анализ недоступен (нет PIL и mimo-omni)",
            "source": "none",
            "image": image_path,
        }


def take_screenshot_of_render(render_path: str, output_path: str = "") -> str:
    """
    Создаёт скриншот/превью рендера с аннотациями.

    Args:
        render_path: путь к рендеру
        output_path: путь для сохранения скриншота

    Returns:
        Путь к скриншоту
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return render_path  # No PIL, return original

    if not output_path:
        base, ext = os.path.splitext(render_path)
        output_path = f"{base}_screenshot{ext}"

    img = Image.open(render_path)
    draw = ImageDraw.Draw(img)

    # Add info bar at bottom
    bar_height = 40
    bar = Image.new("RGBA", (img.width, bar_height), (0, 0, 0, 180))
    img.paste(bar, (0, img.height - bar_height), bar)

    # Add text
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except (OSError, IOError):
        font = ImageFont.load_default()

    info_text = f"ArchAI Preview | {img.width}×{img.height} | {os.path.basename(render_path)}"
    draw.text((10, img.height - 30), info_text, fill="white", font=font)

    img.save(output_path, "PNG", quality=95)
    return output_path
