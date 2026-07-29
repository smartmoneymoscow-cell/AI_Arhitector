"""
shared/validation.py — единая валидация параметров для всех сервисов.
"""

# ═══════════════════════════════════════════════════════════════
# VALID VALUES
# ═══════════════════════════════════════════════════════════════

VALID_OBJECT_TYPES = {"building", "interior", "room"}
VALID_BUILDING_TYPES = {"house", "office", "cottage", "villa", "apartment", "townhouse"}
VALID_ROOM_TYPES = {"bedroom", "kitchen", "living", "bathroom", "children", "study", "dining"}
VALID_STYLES = {"modern", "classic", "loft", "scandinavian", "minimalist", "hitech"}
VALID_MATERIALS = {"brick", "wood", "glass", "stone", "concrete", "plaster"}
VALID_ROOF_TYPES = {"gabled", "flat", "hip"}
VALID_FEATURES = {"balcony", "terrace", "garage"}

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
    "children": ["bed", "desk", "bookshelf"],
    "kitchen": ["table", "sink", "stove"],
    "living": ["sofa", "table", "chandelier"],
    "bathroom": ["sink", "bathtub"],
    "study": ["desk", "bookshelf", "chair"],
    "dining": ["table", "chairs"],
}


def validate_params(params: dict) -> dict:
    """
    Валидация и нормализация параметров парсера.
    Единая функция, используемая всеми сервисами.
    """
    result = {**DEFAULTS, "features": [], "furniture": []}

    # object_type
    ot = params.get("object_type", "building")
    result["object_type"] = ot if ot in VALID_OBJECT_TYPES else "building"

    # building_type
    bt = params.get("building_type", "house")
    result["building_type"] = bt if bt in VALID_BUILDING_TYPES else "house"

    # room_type
    rt = params.get("room_type")
    if rt and rt in VALID_ROOM_TYPES:
        result["room_type"] = rt
    elif result["object_type"] == "room":
        result["room_type"] = rt if rt in VALID_ROOM_TYPES else "living"
    else:
        result["room_type"] = None

    # floors
    floors = params.get("floors", 2)
    result["floors"] = floors if isinstance(floors, int) and 1 <= floors <= 20 else 2

    # dimensions
    for key in ("width_m", "length_m", "height_m"):
        val = params.get(key, DEFAULTS[key])
        result[key] = int(val) if isinstance(val, (int, float)) and 1 <= val <= 200 else DEFAULTS[key]

    # style
    style = params.get("style", "modern")
    result["style"] = style if style in VALID_STYLES else "modern"

    # material
    mat = params.get("material", "plaster")
    result["material"] = mat if mat in VALID_MATERIALS else "plaster"

    # roof_type
    roof = params.get("roof_type", "gabled")
    result["roof_type"] = roof if roof in VALID_ROOF_TYPES else "gabled"

    # features
    features = params.get("features", [])
    if isinstance(features, list):
        result["features"] = [f for f in features if f in VALID_FEATURES]
    else:
        result["features"] = []

    # furniture
    furniture = params.get("furniture", [])
    if isinstance(furniture, list) and furniture:
        result["furniture"] = furniture
    elif result["room_type"]:
        result["furniture"] = DEFAULT_FURNITURE.get(result["room_type"], ["sofa", "table"])
    else:
        result["furniture"] = []

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
