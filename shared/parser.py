"""
shared/parser.py — единый LLM + regex парсер архитектурных промтов.

Использование:
    from shared.parser import parse_prompt_sync, parse_prompt_async, fallback_regex_parse, get_generation_type

    # Синхронный (для blender-service)
    params = parse_prompt_sync("двухэтажный кирпичный дом", api_key="sk-or-...")

    # Асинхронный (для gateway/llm-service)
    params = await parse_prompt_async("двухэтажный кирпичный дом", api_key="sk-or-...")

    # Regex fallback (без LLM)
    params = fallback_regex_parse("двухэтажный кирпичный дом")
"""

import json
import re

import httpx

from shared.config import settings
from shared.validation import (
    validate_params,
    DEFAULTS,
    DEFAULT_FURNITURE,
)

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
# JSON EXTRACTION HELPER
# ═══════════════════════════════════════════════════════════════

def _extract_json(text: str) -> dict | None:
    """Извлекает JSON из ответа LLM, игнорируя markdown-обёртки."""
    # Попытка 1: найти JSON-блок в markdown
    md_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if md_match:
        try:
            return json.loads(md_match.group(1))
        except json.JSONDecodeError:
            pass

    # Попытка 2: найти первый JSON-объект
    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    # Попытка 3: попробовать весь текст как JSON
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    return None


# ═══════════════════════════════════════════════════════════════
# LLM PARSER
# ═══════════════════════════════════════════════════════════════

def _build_llm_headers(api_key: str) -> dict:
    """Строит заголовки для OpenRouter API."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _build_llm_payload(text: str, model: str) -> dict:
    """Строит payload для OpenRouter API."""
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": PARSE_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "max_tokens": 300,
        "temperature": 0.1,
    }


def parse_prompt_sync(text: str, api_key: str = "", model: str = "") -> dict:
    """
    Синхронный вызов LLM для парсинга промта.
    Возвращает валидированный dict с параметрами.
    Fallback на regex при ошибке.
    """
    if not text or not text.strip():
        return {**DEFAULTS, "features": [], "furniture": []}

    if not model:
        model = settings.LLM_MODEL
    if not api_key:
        api_key = settings.OPENROUTER_API_KEY

    headers = _build_llm_headers(api_key)
    payload = _build_llm_payload(text, model)

    try:
        r = httpx.post(
            f"{settings.OPENROUTER_BASE}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30.0,
        )

        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"]
            raw_params = _extract_json(content)
            if raw_params:
                return validate_params(raw_params)
    except Exception as e:
        print(f"[parser] LLM sync error: {e}, falling back to regex")

    return fallback_regex_parse(text)


async def parse_prompt_async(text: str, api_key: str = "", model: str = "") -> dict:
    """
    Асинхронный вызов LLM для парсинга промта.
    Возвращает валидированный dict с параметрами.
    Fallback на regex при ошибке.
    """
    if not text or not text.strip():
        return {**DEFAULTS, "features": [], "furniture": []}

    if not model:
        model = settings.LLM_MODEL
    if not api_key:
        api_key = settings.OPENROUTER_API_KEY

    headers = _build_llm_headers(api_key)
    payload = _build_llm_payload(text, model)

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{settings.OPENROUTER_BASE}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30.0,
            )

        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"]
            raw_params = _extract_json(content)
            if raw_params:
                return validate_params(raw_params)
    except Exception as e:
        print(f"[parser] LLM async error: {e}, falling back to regex")

    return fallback_regex_parse(text)


# ═══════════════════════════════════════════════════════════════
# REGEX FALLBACK PARSER
# ═══════════════════════════════════════════════════════════════

def fallback_regex_parse(text: str) -> dict:
    """
    Улучшенный regex-парсер. Используется как fallback при недоступности LLM.
    """
    if not text or not text.strip():
        return {**DEFAULTS, "features": [], "furniture": []}

    t = text.lower().strip()
    p = {**DEFAULTS, "features": [], "furniture": []}

    # ═══ Определение типа объекта ═══
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
        "база": "cottage",
        "гостиниц": "cottage",
        "отель": "cottage",
        "хостел": "cottage",
        "санаторий": "cottage",
        "пансионат": "cottage",
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
        "премиальн": "classic",
        "элитн": "classic",
        "люкс": "classic",
    }
    for word, style in style_map.items():
        if word in t:
            p["style"] = style
            break

    # ═══ Фичи ═══
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
