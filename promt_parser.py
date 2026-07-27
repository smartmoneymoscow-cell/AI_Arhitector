"""
promt_parser.py — LLM-based парсер архитектурных промтов.

Заменяет regex-based parse_building_params().
Использует OpenRouter API для извлечения структурированных параметров
из естественного языка. Fallback на улучшенный regex при недоступности LLM.

Использование:
    from promt_parser import parse_prompt_sync, fallback_regex_parse

    params = parse_prompt_sync("спальня в стиле хайтек", api_key="sk-or-...")
    # → {"object_type": "room", "room_type": "bedroom", "style": "hitech", ...}
"""

import json
import re
import httpx

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════

OR_BASE = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "nvidia/nemotron-3-nano-30b-a3b:free"

# ═══════════════════════════════════════════════════════════════
# VALID VALUES
# ═══════════════════════════════════════════════════════════════

VALID_OBJECT_TYPES = {"building", "interior", "room"}
VALID_BUILDING_TYPES = {"house", "office", "cottage", "villa", "apartment", "townhouse"}
VALID_ROOM_TYPES = {"bedroom", "kitchen", "living", "bathroom", "children", "study", "dining"}
VALID_STYLES = {"modern", "classic", "loft", "scandinavian", "minimalist", "hitech"}
VALID_MATERIALS = {"brick", "wood", "glass", "stone", "concrete", "plaster"}
VALID_ROOF_TYPES = {"gabled", "flat", "hip"}

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

# ═══════════════════════════════════════════════════════════════
# LLM SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════

PARSE_SYSTEM_PROMPT = """Ты — парсер архитектурных описаний для 3D-генератора.
Отвечай ТОЛЬКО валидным JSON. Пояснения, markdown, кодовые блоки — запрещены.

Формат ответа (строго JSON, без ```json```):
{
  "object_type": "building | interior | room",
  "building_type": "house | office | cottage | villa | apartment | townhouse",
  "room_type": "bedroom | kitchen | living | bathroom | children | study | dining | null",
  "floors": 2,
  "width_m": 10,
  "length_m": 12,
  "height_m": 3,
  "style": "modern | classic | loft | scandinavian | minimalist | hitech",
  "material": "brick | wood | glass | stone | concrete | plaster",
  "roof_type": "gabled | flat | hip",
  "features": ["balcony", "terrace", "garage"],
  "furniture": ["sofa", "table", "bed", "chandelier"]
}

Правила:
- "детская", "спальня", "кухня", "гостиная", "ванная" → object_type="room"
- "интерьер", "дизайн интерьера" → object_type="interior"
- "дом", "здание", "коттедж", "офис", "таунхаус" → object_type="building"
- "хайтек", "hi-tech" → style="hitech"
- "лофт" → style="loft"
- "минимализм" → style="minimalist"
- "скандинавский" → style="scandinavian"
- "классический" → style="classic"
- Размеры в метрах. Если не указаны → null
- "64 кв метра" → width_m=8, length_m=8 (примерный корень из площади)
- Если указаны features (балкон, терраса, гараж) → добавить в массив
- Если room_type определён, а furniture не указан → подобрать дефолтную мебель
  bedroom→["bed","wardrobe","nightstand"],
  children→["bed","desk","bookshelf"],
  kitchen→["table","sink","stove"],
  living→["sofa","table","chandelier"]
"""


# ═══════════════════════════════════════════════════════════════
# RESULT VALIDATION
# ═══════════════════════════════════════════════════════════════

def validate_params(params: dict) -> dict:
    """Валидация и нормализация параметров парсера."""
    result = {**DEFAULTS, "features": [], "furniture": []}

    # object_type
    ot = params.get("object_type", "building")
    if ot not in VALID_OBJECT_TYPES:
        ot = "building"
    result["object_type"] = ot

    # building_type
    bt = params.get("building_type", "house")
    if bt not in VALID_BUILDING_TYPES:
        bt = "house"
    result["building_type"] = bt

    # room_type
    rt = params.get("room_type")
    if rt and rt in VALID_ROOM_TYPES:
        result["room_type"] = rt
    elif ot == "room":
        result["room_type"] = rt if rt in VALID_ROOM_TYPES else "living"
    else:
        result["room_type"] = None

    # floors
    floors = params.get("floors", 2)
    if isinstance(floors, int) and 1 <= floors <= 20:
        result["floors"] = floors
    else:
        result["floors"] = 2

    # dimensions
    for key in ("width_m", "length_m", "height_m"):
        val = params.get(key, DEFAULTS[key])
        if isinstance(val, (int, float)) and 1 <= val <= 200:
            result[key] = int(val)
        else:
            result[key] = DEFAULTS[key]

    # style
    style = params.get("style", "modern")
    if style not in VALID_STYLES:
        style = "modern"
    result["style"] = style

    # material
    mat = params.get("material", "plaster")
    if mat not in VALID_MATERIALS:
        mat = "plaster"
    result["material"] = mat

    # roof_type
    roof = params.get("roof_type", "gabled")
    if roof not in VALID_ROOF_TYPES:
        roof = "gabled"
    result["roof_type"] = roof

    # features
    features = params.get("features", [])
    if isinstance(features, list):
        valid_features = {"balcony", "terrace", "garage"}
        result["features"] = [f for f in features if f in valid_features]
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


# ═══════════════════════════════════════════════════════════════
# LLM PARSER
# ═══════════════════════════════════════════════════════════════

def parse_prompt_sync(text: str, api_key: str = "", model: str = DEFAULT_MODEL) -> dict:
    """
    Синхронный вызов LLM для парсинга промта.
    Возвращает валидированный dict с параметрами.
    Fallback на regex при ошибке.
    """
    if not text or not text.strip():
        return {**DEFAULTS, "features": [], "furniture": []}

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        r = httpx.post(
            f"{OR_BASE}/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": PARSE_SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                "max_tokens": 300,
                "temperature": 0.1,
            },
            timeout=30.0,
        )

        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"]
            # Извлечь JSON из ответа (игнорируем markdown-обёртки)
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
            if json_match:
                raw_params = json.loads(json_match.group())
                return validate_params(raw_params)
    except Exception as e:
        print(f"[promt_parser] LLM error: {e}, falling back to regex")

    return fallback_regex_parse(text)


async def parse_prompt_async(text: str, api_key: str = "", model: str = DEFAULT_MODEL) -> dict:
    """
    Асинхронный вызов LLM для парсинга промта.
    Возвращает валидированный dict с параметрами.
    Fallback на regex при ошибке.
    """
    if not text or not text.strip():
        return {**DEFAULTS, "features": [], "furniture": []}

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{OR_BASE}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": PARSE_SYSTEM_PROMPT},
                        {"role": "user", "content": text},
                    ],
                    "max_tokens": 300,
                    "temperature": 0.1,
                },
                timeout=30.0,
            )

        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"]
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
            if json_match:
                raw_params = json.loads(json_match.group())
                return validate_params(raw_params)
    except Exception as e:
        print(f"[promt_parser] LLM async error: {e}, falling back to regex")

    return fallback_regex_parse(text)


# ═══════════════════════════════════════════════════════════════
# REGEX FALLBACK PARSER (улучшенная версия)
# ═══════════════════════════════════════════════════════════════

def fallback_regex_parse(text: str) -> dict:
    """
    Улучшенный regex-парсер. Используется как fallback при недоступности LLM.
    Понимает больше паттернов чем оригинальный parse_building_params().
    """
    if not text or not text.strip():
        return {**DEFAULTS, "features": [], "furniture": []}

    t = text.lower().strip()
    p = {**DEFAULTS, "features": [], "furniture": []}

    # ═══ Определение типа объекта ═══
    # Сначала проверяем комнаты (более специфичные)
    room_words = {
        "спальн": "bedroom",
        "детск": "children",
        "кухн": "kitchen",
        "гостин": "living",
        "ванн": "bathroom",
        "кабинет": "study",
        "салон": "living",
        "столов": "dining",
    }
    for word, room_type in room_words.items():
        if word in t:
            p["object_type"] = "room"
            p["room_type"] = room_type
            break

    # Если не комната — проверяем интерьер
    if p["object_type"] == "building":
        interior_words = ["интерьер", "дизайн интерьера", "внутри помещения"]
        if any(w in t for w in interior_words):
            p["object_type"] = "interior"

    # ═══ Тип здания ═══
    type_map = {
        "офис": "office",
        "коттедж": "cottage",
        "вилл": "villa",
        "таунхаус": "townhouse",
        "квартир": "apartment",
    }
    for word, btype in type_map.items():
        if word in t:
            p["building_type"] = btype
            break

    # ═══ Этажи ═══
    floor_words = {
        "одно": 1, "одну": 1,
        "двух": 2, "дву": 2,
        "трёх": 3, "трех": 3,
        "четыр": 4,
        "пяти": 5,
        "шести": 6,
    }
    for word, n in floor_words.items():
        if word in t and ("этаж" in t or "уровн" in t):
            p["floors"] = n
            break

    fm = re.search(r"(\d+)\s*(?:этаж|floor)", t)
    if fm:
        p["floors"] = int(fm.group(1))

    # ═══ Размеры ═══
    dm = re.search(r"(\d+)\s*[×xх]\s*(\d+)", t)
    if dm:
        p["width_m"] = int(dm.group(1))
        p["length_m"] = int(dm.group(2))
    else:
        # "64 кв метра" → примерный корень
        sqm = re.search(r"(\d+)\s*(?:кв|м2|м²)", t)
        if sqm:
            area = int(sqm.group(1))
            side = max(3, int(area ** 0.5))
            p["width_m"] = side
            p["length_m"] = side

    # ═══ Высота ═══
    hm = re.search(r"высот[аеи]+\s*(\d+(?:\.\d+)?)", t)
    if hm:
        p["height_m"] = float(hm.group(1))

    # ═══ Кровля ═══
    if "плоск" in t:
        p["roof_type"] = "flat"
    elif "вальм" in t:
        p["roof_type"] = "hip"
    elif "двускат" in t or "скатн" in t:
        p["roof_type"] = "gabled"

    # ═══ Материал ═══
    mat_map = {
        "кирпич": "brick",
        "дерев": "wood",
        "стекл": "glass",
        "камен": "stone",
        "бетон": "concrete",
        "штукатурк": "plaster",
    }
    for word, mat in mat_map.items():
        if word in t:
            p["material"] = mat
            break

    # ═══ Стиль ═══
    # Порядок важен: более специфичные стили ПЕРЕД общими
    style_map = {
        "хайтек": "hitech",
        "hi-tech": "hitech",
        "hitech": "hitech",
        "минималист": "minimalist",
        "минимализм": "minimalist",
        "лофт": "loft",
        "loft": "loft",
        "классич": "classic",
        "скандинав": "scandinavian",
        "современн": "modern",
        "модерн": "modern",
    }
    for word, style in style_map.items():
        if word in t:
            p["style"] = style
            break

    # ═══ Фичи (точное слово, не подстрока) ═══
    if re.search(r'\bбалкон\w*', t):
        p["features"].append("balcony")
    if re.search(r'\bтеррас\w*', t):
        p["features"].append("terrace")
    if re.search(r'\bгараж\w*', t):
        p["features"].append("garage")

    # ═══ Мебель по умолчанию для комнат ═══
    if p["room_type"] and not p["furniture"]:
        p["furniture"] = DEFAULT_FURNITURE.get(p["room_type"], ["sofa", "table"])

    return p


# ═══════════════════════════════════════════════════════════════
# ROUTING HELPER
# ═══════════════════════════════════════════════════════════════

def get_generation_type(params: dict) -> str:
    """
    Определяет тип генерации по параметрам.
    Возвращает: 'building' или 'interior'
    """
    obj_type = params.get("object_type", "building")
    if obj_type in ("interior", "room"):
        return "interior"
    return "building"


# ═══════════════════════════════════════════════════════════════
# CLI ТЕСТ
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    test_prompts = [
        "сделай дизайн коттеджа",
        "сделай дизайн интерьера детской",
        "красивую спальню в стиле хайтек",
        "интерьерный дизайн квартиры на 64 кв метра",
        "офис 5 этажей стекло плоская кровля 20×24",
        "двухэтажный кирпичный дом 10×12 с балконом",
        "деревянный коттедж 2 этажа терраса гараж 12×15",
        "построй что-нибудь красивое",
        "кухня в стиле лофт 4×5",
        "современный таунхаус 3 этажа минимализм",
    ]

    api_key = sys.argv[1] if len(sys.argv) > 1 else ""

    for prompt in test_prompts:
        print(f"\n{'='*60}")
        print(f"Промт: {prompt}")

        if api_key:
            params = parse_prompt_sync(prompt, api_key)
            print(f"LLM:   {json.dumps(params, ensure_ascii=False, indent=2)}")

        fb = fallback_regex_parse(prompt)
        print(f"Regex: {json.dumps(fb, ensure_ascii=False, indent=2)}")
        print(f"Тип генерации: {get_generation_type(fb)}")
