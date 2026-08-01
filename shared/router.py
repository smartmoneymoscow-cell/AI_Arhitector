"""
shared/router.py — единый роутер генерации на бэкенде.

Заменяет логику parseLocal() + applyParams() из фронтенда.
Все решения о маршрутизации принимаются здесь.

Использование:
    from shared.router import route_generation, GenerationPlan

    plan = route_generation("двухэтажный кирпичный дом 10×12")
    # → GenerationPlan(type='building', params={...}, steps=[...])
"""

import time
import uuid
from dataclasses import dataclass, field

from shared.parser import parse_prompt
from shared.validation import DEFAULT_FURNITURE, validate_params

# ═══════════════════════════════════════════════════════════════
# TYPES
# ═══════════════════════════════════════════════════════════════


@dataclass
class GenerationStep:
    """Один этап генерации."""

    name: str
    service: str  # 'local' | 'blender' | 'geometry' | 'ifc' | 'ml'
    params: dict = field(default_factory=dict)
    status: str = "pending"  # pending | running | done | failed
    result: dict | None = None
    error: str | None = None
    duration_ms: float = 0


@dataclass
class GenerationPlan:
    """Полный план генерации."""

    job_id: str
    prompt: str
    gen_type: str  # 'building' | 'interior'
    params: dict
    steps: list  # list[GenerationStep]
    status: str = "pending"
    created_at: float = field(default_factory=time.time)
    progress: int = 0
    result_url: str | None = None
    error: str | None = None


# ═══════════════════════════════════════════════════════════════
# TEMPLATES (перенесены из фронтенда TPLS)
# ═══════════════════════════════════════════════════════════════

BUILDING_TEMPLATES = {
    "house": {
        "label": "Жилой дом",
        "floors": 2,
        "W": 10,
        "L": 12,
        "fH": 2.8,
        "roof": "gabled",
        "mat": "brick",
        "fc": "#c87040",
        "rc": "#6b3510",
        "tc": "#f8f4ef",
        "dc": "#3d2010",
        "balcony": True,
        "rooms": [
            {"n": "Гостиная", "a": 24, "fl": 1, "tag": "l", "x": -2, "z": 1, "w": 5.5, "d": 4.2},
            {"n": "Кухня", "a": 14, "fl": 1, "tag": "k", "x": 3.5, "z": 1, "w": 3.5, "d": 3.5},
            {"n": "Спальня 1", "a": 18, "fl": 2, "tag": "s", "x": -2, "z": 1, "w": 4.5, "d": 4},
            {"n": "Спальня 2", "a": 13, "fl": 2, "tag": "s", "x": 3, "z": 1, "w": 3.5, "d": 3.7},
            {"n": "Ванная", "a": 6, "fl": 1, "tag": "b", "x": -4, "z": -3, "w": 2.4, "d": 2.5},
            {"n": "Коридор", "a": 7, "fl": 1, "tag": "h", "x": 0, "z": -3, "w": 3, "d": 1.5},
        ],
    },
    "office": {
        "label": "Офисный центр",
        "floors": 5,
        "W": 20,
        "L": 24,
        "fH": 3.2,
        "roof": "flat",
        "mat": "glass",
        "fc": "#7ec8e3",
        "rc": "#455a64",
        "tc": "#eceff1",
        "dc": "#263238",
        "balcony": False,
        "rooms": [
            {"n": "Open Space", "a": 320, "fl": 1, "tag": "l", "x": 0, "z": 2, "w": 16, "d": 18},
            {"n": "Переговорная A", "a": 30, "fl": 1, "tag": "h", "x": -7, "z": -8, "w": 6, "d": 5},
            {"n": "Санузел М", "a": 8, "fl": 1, "tag": "b", "x": -8, "z": 9, "w": 3, "d": 2.7},
        ],
    },
    "cottage": {
        "label": "Загородный коттедж",
        "floors": 2,
        "W": 12,
        "L": 15,
        "fH": 2.9,
        "roof": "gabled",
        "mat": "wood",
        "fc": "#b8864e",
        "rc": "#3e2005",
        "tc": "#fdf5e6",
        "dc": "#2d1505",
        "balcony": True,
        "rooms": [
            {"n": "Гостиная", "a": 36, "fl": 1, "tag": "l", "x": -2, "z": 1, "w": 7, "d": 5},
            {"n": "Кухня", "a": 20, "fl": 1, "tag": "k", "x": 4, "z": 1, "w": 5, "d": 4},
            {"n": "Мастер-спальня", "a": 24, "fl": 2, "tag": "s", "x": -2, "z": 1, "w": 5.5, "d": 4.4},
            {"n": "Детская", "a": 15, "fl": 2, "tag": "s", "x": 3.5, "z": 1, "w": 4, "d": 3.75},
            {"n": "Ванная", "a": 8, "fl": 1, "tag": "b", "x": 4, "z": -4, "w": 3, "d": 2.7},
        ],
    },
    "modern": {
        "label": "Таунхаус",
        "floors": 3,
        "W": 8,
        "L": 16,
        "fH": 3.0,
        "roof": "flat",
        "mat": "plaster",
        "fc": "#f0f0ee",
        "rc": "#1a1a1a",
        "tc": "#111",
        "dc": "#050505",
        "balcony": True,
        "rooms": [
            {"n": "Гостиная+кухня", "a": 45, "fl": 1, "tag": "l", "x": 0, "z": 2, "w": 7, "d": 6},
            {"n": "Мастер-спальня", "a": 28, "fl": 2, "tag": "s", "x": 0, "z": 2, "w": 6, "d": 4.7},
            {"n": "Детская", "a": 18, "fl": 3, "tag": "s", "x": -1, "z": 2, "w": 4.5, "d": 4},
            {"n": "Ванная", "a": 10, "fl": 2, "tag": "b", "x": 0, "z": -4, "w": 3.3, "d": 3},
        ],
    },
}

MATERIAL_COLORS = {
    "brick": {"fc": "#c87040", "rc": "#6b3510"},
    "wood": {"fc": "#b8864e", "rc": "#3e2005"},
    "glass": {"fc": "#7ec8e3", "rc": "#455a64"},
    "plaster": {"fc": "#f0ece4", "rc": "#555"},
    "stone": {"fc": "#8a8278", "rc": "#444"},
}

INTERIOR_KEYWORDS = [
    "спальн",
    "детск",
    "кухн",
    "гостин",
    "ванн",
    "кабинет",
    "салон",
    "столов",
    "интерьер",
    "дизайн интерьера",
    "комнат",
]


# ═══════════════════════════════════════════════════════════════
# CORE ROUTER
# ═══════════════════════════════════════════════════════════════


def route_generation(prompt: str, llm_params: dict | None = None) -> GenerationPlan:
    """
    Главная функция роутинга. Принимает промт, возвращает план генерации.

    Args:
        prompt: текстовый промт пользователя
        llm_params: параметры от LLM (опционально, если уже распарсены)

    Returns:
        GenerationPlan с полным списком шагов
    """
    job_id = uuid.uuid4().hex[:8]

    # Step1: Parse (LLM params优先, fallback to regex)
    if llm_params:
        raw_params = llm_params
    else:
        raw_params = parse_prompt(prompt)  # LLM-only, no regex

    params = validate_params(raw_params)

    # Step2: Determine generation type
    gen_type = _detect_type(prompt, params)

    # Step3: Build building params from template
    building_params = _build_building_params(prompt, params)

    # Step4: Determine steps based on type
    if gen_type == "interior":
        steps = _plan_interior_steps(params)
    else:
        steps = _plan_building_steps(params, building_params)

    return GenerationPlan(
        job_id=job_id,
        prompt=prompt,
        gen_type=gen_type,
        params={
            "parsed": params,
            "building": building_params,
        },
        steps=steps,
    )


def _detect_type(prompt: str, params: dict) -> str:
    """Определяет тип генерации из промта и параметров."""
    obj_type = params.get("object_type", "building")
    if obj_type in ("interior", "room"):
        return "interior"

    t = prompt.lower()
    for kw in INTERIOR_KEYWORDS:
        if kw in t:
            return "interior"
    return "building"


def _build_building_params(prompt: str, params: dict) -> dict:
    """
    Строит полные параметры здания из шаблона + парсинга.
    Перенесено из фронтенд-функции applyParams().
    """
    tpl_key = params.get("building_type", "house")
    if tpl_key not in BUILDING_TEMPLATES:
        tpl_key = "house"

    import copy

    b = copy.deepcopy(BUILDING_TEMPLATES[tpl_key])

    # Override from parsed params
    if params.get("floors"):
        b["floors"] = max(1, min(50, int(params["floors"])))
    if params.get("width_m"):
        b["W"] = float(params["width_m"])
    if params.get("length_m"):
        b["L"] = float(params["length_m"])
    if params.get("roof_type"):
        b["roof"] = params["roof_type"]
    if params.get("material"):
        b["mat"] = params["material"]
    if params.get("features"):
        b["balcony"] = "balcony" in params["features"]
        b["has_terrace"] = "terrace" in params["features"]
        b["has_garage"] = "garage" in params["features"]

    # Auto-colors per material
    mat = b.get("mat", "plaster")
    if mat in MATERIAL_COLORS:
        b["fc"] = MATERIAL_COLORS[mat]["fc"]
        b["rc"] = MATERIAL_COLORS[mat]["rc"]

    # Style overrides
    style = params.get("style", "")
    if style == "hitech":
        b["mat"] = b.get("mat") or "glass"
        b["roof"] = b.get("roof") or "flat"
    elif style == "classic":
        b["mat"] = b.get("mat") or "stone"
    elif style == "scandi":
        b["mat"] = b.get("mat") or "wood"

    b["desc"] = prompt
    return b


def _plan_building_steps(params: dict, building_params: dict) -> list:
    """Планирует шаги генерации здания."""
    steps = [
        GenerationStep(name="parse", service="local", params={"prompt": params}),
        GenerationStep(name="generate_geometry", service="blender", params=building_params),
        GenerationStep(name="export_glb", service="blender", params={"format": "GLB"}),
    ]

    # Optional IFC export
    steps.append(GenerationStep(name="export_ifc", service="ifc", params=building_params))

    # Optional floorplan
    steps.append(GenerationStep(name="generate_floorplan", service="geometry", params=building_params))

    return steps


def _plan_interior_steps(params: dict) -> list:
    """Планирует шаги генерации интерьера."""
    room_type = params.get("room_type", "living")
    furniture = params.get("furniture") or DEFAULT_FURNITURE.get(room_type, ["sofa", "table", "chandelier"])

    interior_params = {
        "width": params.get("width_m", 6),
        "length": params.get("length_m", 8),
        "height": params.get("height_m", 3),
        "style": params.get("style", "modern"),
        "furniture": furniture,
        "room_type": room_type,
    }

    return [
        GenerationStep(name="parse", service="local", params={"prompt": params}),
        GenerationStep(name="render_interior", service="blender", params=interior_params),
        GenerationStep(name="upscale", service="local", params={"scale": 4}),
    ]
