"""
shared/preview.py — Модуль превью, анализа и проверки качества рендеров.

Функции:
    generate_preview()     — Генерация превью через Blender
    analyze_render()       — Анализ рендера через mimo-omni
    check_quality_16k()    — Проверка разрешения ≥16K
    detect_visual_bugs()   — Поиск визуальных багов
    take_screenshot_of_render() — Скриншот с аннотацией
"""

import os
import re
import uuid
import json
import subprocess
from typing import Optional

from shared.config import settings
from shared.parser import fallback_regex_parse, get_generation_type
from shared.blender import generate_bpy_script, generate_interior_script
from shared.validation import DEFAULT_FURNITURE


def generate_preview(prompt: str, output_dir: str = "", quality: str = "preview") -> str:
    """Генерирует превью-скриншот для промта."""
    if not output_dir:
        output_dir = settings.OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    params = fallback_regex_parse(prompt)
    gen_type = get_generation_type(params)

    if gen_type == "interior":
        room_type = params.get("room_type", "living")
        furniture = params.get("furniture") or DEFAULT_FURNITURE.get(room_type, ["sofa", "table", "chandelier"])
        script = generate_interior_script({
            "width": params.get("width_m", 6),
            "length": params.get("length_m", 8),
            "height": params.get("height_m", 3),
            "style": params.get("style", "modern"),
            "furniture": furniture,
        })
    else:
        script = generate_bpy_script({
            "width": params.get("width_m", 10),
            "length": params.get("length_m", 12),
            "floors": params.get("floors", 2),
            "roof_type": params.get("roof_type", "gabled"),
            "facade_material": params.get("material", "plaster"),
            "has_balcony": "balcony" in params.get("features", []),
        })

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


# ═══════════════════════════════════════════════════════════════
# ANALYSIS
# ═══════════════════════════════════════════════════════════════

def analyze_render(image_path: str, question: str = "") -> dict:
    """
    Анализирует рендер через mimo-omni.

    Returns:
        {
            "description": "...",
            "matches_prompt": True/False,
            "match_score": 0.0-1.0,
            "has_bugs": True/False,
            "bugs": ["..."],
            "quality_ok": True/False,
            "resolution": "WxH",
            "source": "mimo-omni" | "pil_info"
        }
    """
    if not os.path.exists(image_path):
        return {"error": f"Image not found: {image_path}"}

    analysis_prompt = question or (
        "Проанализируй этот архитектурный рендер. Ответь СТРОГО в JSON:\n"
        "{\n"
        '  "description": "краткое описание",\n'
        '  "matches_prompt": true/false,\n'
        '  "match_score": 0.0-1.0,\n'
        '  "has_bugs": true/false,\n'
        '  "bugs": ["описание визуального бага"],\n'
        '  "quality_issues": ["проблема качества"]\n'
        "}\n"
    )

    result = {"source": "none", "image": image_path}

    # Try mimo-omni
    parsed = _call_mimo_omni(image_path, analysis_prompt)
    if parsed:
        result.update(parsed)
        result["source"] = "mimo-omni"

        # Добавляем PIL-инфо
        try:
            from PIL import Image
            img = Image.open(image_path)
            result["resolution"] = f"{img.width}x{img.height}"
            result["quality_ok"] = img.width >= 15360 and img.height >= 8640
        except ImportError:
            pass

        return result

    # Fallback: PIL info only
    try:
        from PIL import Image
        img = Image.open(image_path)
        result["description"] = f"Изображение {img.width}x{img.height}, формат: {img.format}"
        result["resolution"] = f"{img.width}x{img.height}"
        result["source"] = "pil_info"
    except ImportError:
        result["description"] = "Анализ недоступен"

    return result


def check_quality_16k(image_path: str) -> dict:
    """
    Проверяет что рендер соответствует качеству ≥16K (15360×8640).

    Returns:
        {"quality_ok": bool, "resolution": str, "megapixels": float}
    """
    try:
        from PIL import Image
        img = Image.open(image_path)
        w, h = img.width, img.height
    except Exception:
        return {"quality_ok": False, "error": "Cannot read image"}

    min_w, min_h = 15360, 8640
    return {
        "quality_ok": w >= min_w and h >= min_h,
        "resolution": f"{w}x{h}",
        "expected_min": f"{min_w}x{min_h}",
        "actual": (w, h),
        "megapixels": round(w * h / 1_000_000, 1),
    }


def detect_visual_bugs(image_path: str) -> dict:
    """
    Определяет визуальные баги 3D-модели через mimo-omni.

    Ищет: clipping, missing textures, proportions, artifacts, z-fighting, black areas.

    Returns:
        {
            "has_bugs": True/False,
            "bugs": [{"type": "...", "description": "...", "severity": "..."}],
            "overall_quality": "good|acceptable|poor"
        }
    """
    if not os.path.exists(image_path):
        return {"has_bugs": False, "error": "Image not found"}

    bug_prompt = (
        "Найди визуальные баги на этом архитектурном рендере. Ответь СТРОГО в JSON:\n"
        "{\n"
        '  "has_bugs": true/false,\n'
        '  "bugs": [\n'
        '    {"type": "clipping|missing_texture|proportion|artifact|z_fighting|black_area",\n'
        '     "description": "описание",\n'
        '     "severity": "critical|major|minor"}\n'
        '  ],\n'
        '  "overall_quality": "good|acceptable|poor"\n'
        "}\n"
    )

    parsed = _call_mimo_omni(image_path, bug_prompt)
    if parsed:
        return parsed

    return {"has_bugs": False, "details": "mimo-omni unavailable"}


def validate_render_matches_prompt(image_path: str, prompt: str) -> dict:
    """
    Проверяет что рендер соответствует оригинальному промту.

    Returns:
        {
            "matches_prompt": True/False,
            "match_score": 0.0-1.0,
            "details": "..."
        }
    """
    if not os.path.exists(image_path):
        return {"matches_prompt": False, "error": "Image not found"}

    match_prompt = (
        f"Оригинальный промт пользователя: {prompt}\n\n"
        "Соответствует ли этот рендер промту? Ответь СТРОГО в JSON:\n"
        "{\n"
        '  "matches_prompt": true/false,\n'
        '  "match_score": 0.0-1.0,\n'
        '  "details": "объяснение почему да/нет"\n'
        "}\n"
    )

    parsed = _call_mimo_omni(image_path, match_prompt)
    if parsed:
        return parsed

    return {"matches_prompt": False, "details": "mimo-omni unavailable"}


# ═══════════════════════════════════════════════════════════════
# SCREENSHOT
# ═══════════════════════════════════════════════════════════════

def take_screenshot_of_render(render_path: str, output_path: str = "") -> str:
    """Создаёт скриншот ренда с аннотацией (info bar)."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return render_path

    if not output_path:
        base, ext = os.path.splitext(render_path)
        output_path = f"{base}_screenshot{ext}"

    img = Image.open(render_path)
    draw = ImageDraw.Draw(img)

    # Info bar
    bar_height = 40
    overlay = Image.new("RGBA", (img.width, bar_height), (0, 0, 0, 180))
    img_rgba = img.convert("RGBA")
    img_rgba.paste(overlay, (0, img.height - bar_height), overlay)
    draw = ImageDraw.Draw(img_rgba)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except (OSError, IOError):
        font = ImageFont.load_default()

    info = f"ArchAI | {img.width}x{img.height} | {os.path.basename(render_path)}"
    draw.text((10, img.height - 30), info, fill="white", font=font)

    img_rgba.convert("RGB").save(output_path, "PNG", quality=95)
    return output_path


# ═══════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════

def _call_mimo_omni(image_path: str, prompt: str) -> dict | None:
    """Вызывает mimo-omni и парсит JSON ответ."""
    try:
        mimo_script = os.path.expanduser("~/.openclaw/skills/mimo-omni/mimo_api.sh")
        if not os.path.exists(mimo_script):
            return None

        proc = subprocess.run(
            ["bash", mimo_script, "image", image_path, prompt],
            capture_output=True, text=True, timeout=60,
        )
        if proc.returncode == 0:
            return _parse_json_response(proc.stdout)
    except Exception:
        pass
    return None


def _parse_json_response(response: str) -> dict:
    """Извлекает JSON из ответа mimo-omni."""
    try:
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except (json.JSONDecodeError, ValueError):
        pass
    return {"description": response[:500]}
