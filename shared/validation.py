"""
shared/validation.py — единая валидация параметров для всех сервисов.

v8.0 — FLEXIBLE validation: LLM is source of truth.
Не ограничиваем значения — LLM может вернуть ЛЮБОЕ осмысленное значение.
Валидируем только структуру и безопасность, а НЕ содержание.
"""

# ═══════════════════════════════════════════════════════════════
# KNOWN VALUES (for reference, NOT for rejection)
# ═══════════════════════════════════════════════════════════════

KNOWN_OBJECT_TYPES = {"building", "interior", "room", "landscape", "structure", "element"}

KNOWN_BUILDING_TYPES = {
    "house",
    "office",
    "cottage",
    "villa",
    "apartment",
    "townhouse",
    "hotel",
    "hostel",
    "barn",
    "garage",
    "gazebo",
    "greenhouse",
    "bathhouse",
    "pool",
    "fence",
    "gate",
    "log_cabin",
    "izba",
    "chicken_coop",
    "carport",
    "warehouse",
    "restaurant",
    "school",
    "hospital",
    "shop",
    "mall",
    "factory",
    "church",
    "mosque",
    "stadium",
    "bridge",
    "tower",
    "skyscraper",
    "duplex",
}
KNOWN_ROOM_TYPES = {
    "bedroom",
    "kitchen",
    "living",
    "bathroom",
    "children",
    "study",
    "dining",
    "hallway",
    "nursery",
    "laundry",
    "pantry",
    "attic",
    "basement",
    "garage_interior",
    "sauna",
    "pool_interior",
    "office_interior",
    "lobby",
    "corridor",
    "wc",
    "dressing",
}
KNOWN_STYLES = {
    "modern",
    "classic",
    "loft",
    "scandinavian",
    "minimalist",
    "hitech",
    "japanese",
    "medieval",
    "rustic",
    "colonial",
    "art_deco",
    "baroque",
    "empire",
    "provence",
    "tropical",
    "industrial",
    "bohemian",
    "gothic",
    "constructivist",
    "futuristic",
    "eco",
    "arabic",
    "chinese",
    "indian",
}
KNOWN_MATERIALS = {
    "brick",
    "wood",
    "glass",
    "stone",
    "concrete",
    "plaster",
    "metal",
    "log",
    "straw",
    "adobe",
    "marble",
    "granite",
    "slate",
    "ceramic",
    "steel",
    "aluminum",
    "copper",
    "zinc",
    "titanium",
    "composite",
    "sip_panel",
    "lstk",
    "foam_block",
    "gas_silicate",
    "timber_frame",
}
KNOWN_ROOF_TYPES = {
    "gabled",
    "flat",
    "hip",
    "mansard",
    "shed",
    "dome",
    "asymmetric",
    "green",
    "butterfly",
    "curved",
    "gambrel",
    "saltbox",
    "bonnet",
}
KNOWN_FEATURES = {
    "balcony",
    "terrace",
    "garage",
    "pool",
    "garden",
    "chimney",
    "skylight",
    "basement",
    "attic",
    "veranda",
    "porch",
    "deck",
    "pergola",
    "fountain",
    "pond",
    "greenhouse",
    "workshop",
    "wine_cellar",
    "home_theater",
    "gym",
    "spa",
    "sauna",
}

# Backward-compatible aliases (for existing tests/imports)
VALID_OBJECT_TYPES = KNOWN_OBJECT_TYPES
VALID_BUILDING_TYPES = KNOWN_BUILDING_TYPES
VALID_ROOM_TYPES = KNOWN_ROOM_TYPES
VALID_STYLES = KNOWN_STYLES
VALID_MATERIALS = KNOWN_MATERIALS
VALID_ROOF_TYPES = KNOWN_ROOF_TYPES
VALID_FEATURES = KNOWN_FEATURES


# ═══════════════════════════════════════════════════════════════
# DEFAULTS
# ═══════════════════════════════════════════════════════════════

DEFAULTS = {
    "object_type": "building",
    "building_type": "house",
    "room_type": None,
    "floors": 2,
    "width_m": 10,
    "length_m": 12,
    "height_m": 3,
    "style": "modern",
    "material": "plaster",
    "roof_type": "gabled",
    "features": [],
    "furniture": [],
}

DEFAULT_FURNITURE = {
    "bedroom": ["bed", "wardrobe", "nightstand"],
    "children": ["bed", "desk", "bookshelf", "toy_box"],
    "nursery": ["crib", "changing_table", "rocking_chair"],
    "kitchen": ["table", "sink", "stove", "refrigerator"],
    "living": ["sofa", "table", "chandelier", "tv_stand"],
    "bathroom": ["sink", "bathtub", "toilet", "shower", "jacuzzi", "mirror", "cabinet"],
    "study": ["desk", "bookshelf", "chair"],
    "dining": ["table", "chairs"],
    "hallway": ["coat_rack", "shoe_cabinet", "mirror"],
    "sauna": ["stove", "benches", "bucket"],
    "pool_interior": ["pool", "loungers", "towel_rack"],
    "wc": ["toilet", "sink"],
    "dressing": ["wardrobe", "mirror", "vanity"],
    "laundry": ["washing_machine", "dryer", "sink"],
}


# ═══════════════════════════════════════════════════════════════
# VALIDATION — FLEXIBLE (accept LLM values)
# ═══════════════════════════════════════════════════════════════


def _safe_str(val, default: str = "") -> str:
    """Safely convert to string, strip whitespace."""
    if val is None:
        return default
    s = str(val).strip()
    return s if s else default


def _safe_int(val, default: int, min_val: int = 1, max_val: int = 100) -> int:
    """Safely convert to int within range."""
    try:
        v = int(float(val))
        return max(min_val, min(max_val, v))
    except (TypeError, ValueError):
        return default


def _safe_float(val, default: float, min_val: float = 0.1, max_val: float = 500.0) -> float:
    """Safely convert to float within range."""
    try:
        v = float(val)
        return max(min_val, min(max_val, v))
    except (TypeError, ValueError):
        return default


def _safe_list(val) -> list:
    """Safely convert to list of strings."""
    if isinstance(val, list):
        return [str(item).strip() for item in val if item]
    return []


def validate_params(params: dict) -> dict:
    """
    FLEXIBLE валидация: принимает ЛЮБЫЕ значения от LLM.
    Валидирует только структуру и безопасность.
    НЕ заменяет значения на дефолтные — доверяем LLM.
    """
    if not isinstance(params, dict):
        return dict(DEFAULTS)

    result = {}

    # object_type — принимаем ЛЮБОЕ непустое значение
    ot = _safe_str(params.get("object_type"), DEFAULTS["object_type"])
    result["object_type"] = ot if ot else DEFAULTS["object_type"]

    # building_type — принимаем ЛЮБОЕ непустое значение
    bt = _safe_str(params.get("building_type"), DEFAULTS["building_type"])
    result["building_type"] = bt if bt else DEFAULTS["building_type"]

    # building_description — принимаем как есть
    result["building_description"] = _safe_str(params.get("building_description"), "")

    # room_type — принимаем ЛЮБОЕ значение или None
    rt = _safe_str(params.get("room_type"), "")
    result["room_type"] = rt if rt else None

    # floors — валидируем диапазон
    result["floors"] = _safe_int(params.get("floors"), DEFAULTS["floors"], 1, 50)

    # dimensions — валидируем диапазон
    result["width_m"] = _safe_float(params.get("width_m"), DEFAULTS["width_m"], 0.5, 500)
    result["length_m"] = _safe_float(params.get("length_m"), DEFAULTS["length_m"], 0.5, 500)
    result["height_m"] = _safe_float(params.get("height_m"), DEFAULTS["height_m"], 1.0, 50)

    # style — принимаем ЛЮБОЕ значение
    result["style"] = _safe_str(params.get("style"), DEFAULTS["style"])

    # material — принимаем ЛЮБОЕ значение
    result["material"] = _safe_str(params.get("material"), DEFAULTS["material"])

    # roof_type — принимаем ЛЮБОЕ значение
    result["roof_type"] = _safe_str(params.get("roof_type"), DEFAULTS["roof_type"])

    # features — принимаем ЛЮБЫЕ значения
    result["features"] = _safe_list(params.get("features"))

    # furniture — принимаем ЛЮБЫЕ значения
    furniture = _safe_list(params.get("furniture"))
    if not furniture and result.get("room_type"):
        furniture = DEFAULT_FURNITURE.get(result["room_type"], [])
    result["furniture"] = furniture

    # special_requirements — принимаем как есть
    result["special_requirements"] = _safe_list(params.get("special_requirements"))

    # confidence — принимаем как есть
    result["confidence"] = _safe_float(params.get("confidence"), 0.5, 0.0, 1.0)

    # reasoning — принимаем как есть
    result["reasoning"] = _safe_str(params.get("reasoning"), "")

    return result


def safe_val(value, default, valid_values=None):
    """
    Безопасное получение значения с валидацией.
    Используется в bpy-скриптах.
    """
    if value is None:
        return default
    if valid_values is not None and value not in valid_values:
        return default
    return value
