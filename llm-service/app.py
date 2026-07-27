"""
LLM Microservice — proxy to OpenRouter + prompt parsing

Endpoints:
  GET  /health                        — Health check
  POST /api/v1/chat/completions       — Chat proxy to OpenRouter
  POST /api/v1/parse                  — Prompt → structured params (LLM + regex fallback)
"""
import os
import re
import json
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

OR_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OR_BASE = "https://openrouter.ai/api/v1"
MODEL = os.environ.get("LLM_MODEL", "nvidia/nemotron-3-nano-30b-a3b:free")


# ═══════════════════════════════════════════════════════════════
# VALID VALUES & DEFAULTS
# ═══════════════════════════════════════════════════════════════

VALID_OBJECT_TYPES = {"building", "interior", "room"}
VALID_BUILDING_TYPES = {"house", "office", "cottage", "villa", "apartment", "townhouse"}
VALID_ROOM_TYPES = {"bedroom", "kitchen", "living", "bathroom", "children", "study", "dining"}
VALID_STYLES = {"modern", "classic", "loft", "scandinavian", "minimalist", "hitech"}
VALID_MATERIALS = {"brick", "wood", "glass", "stone", "concrete", "plaster"}
VALID_ROOF_TYPES = {"gabled", "flat", "hip"}

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
# LLM SYSTEM PROMPT FOR PARSING
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
- Если room_type определён, а furniture не указан → подобрать дефолтную мебель"""


# ═══════════════════════════════════════════════════════════════
# VALIDATION
# ═══════════════════════════════════════════════════════════════

def validate_params(params):
    """Валидация и нормализация параметров парсера."""
    result = {**DEFAULTS, "features": [], "furniture": []}

    ot = params.get("object_type", "building")
    result["object_type"] = ot if ot in VALID_OBJECT_TYPES else "building"

    bt = params.get("building_type", "house")
    result["building_type"] = bt if bt in VALID_BUILDING_TYPES else "house"

    rt = params.get("room_type")
    if rt and rt in VALID_ROOM_TYPES:
        result["room_type"] = rt
    elif result["object_type"] == "room":
        result["room_type"] = rt if rt in VALID_ROOM_TYPES else "living"
    else:
        result["room_type"] = None

    floors = params.get("floors", 2)
    result["floors"] = floors if isinstance(floors, int) and 1 <= floors <= 20 else 2

    for key in ("width_m", "length_m", "height_m"):
        val = params.get(key, DEFAULTS[key])
        result[key] = int(val) if isinstance(val, (int, float)) and 1 <= val <= 200 else DEFAULTS[key]

    style = params.get("style", "modern")
    result["style"] = style if style in VALID_STYLES else "modern"

    mat = params.get("material", "plaster")
    result["material"] = mat if mat in VALID_MATERIALS else "plaster"

    roof = params.get("roof_type", "gabled")
    result["roof_type"] = roof if roof in VALID_ROOF_TYPES else "gabled"

    features = params.get("features", [])
    if isinstance(features, list):
        result["features"] = [f for f in features if f in {"balcony", "terrace", "garage"}]
    else:
        result["features"] = []

    furniture = params.get("furniture", [])
    if isinstance(furniture, list) and furniture:
        result["furniture"] = furniture
    elif result["room_type"]:
        result["furniture"] = DEFAULT_FURNITURE.get(result["room_type"], ["sofa", "table"])
    else:
        result["furniture"] = []

    return result


# ═══════════════════════════════════════════════════════════════
# REGEX FALLBACK PARSER
# ═══════════════════════════════════════════════════════════════

def fallback_regex_parse(text):
    """Улучшенный regex-парсер. Fallback при недоступности LLM."""
    if not text or not text.strip():
        return {**DEFAULTS, "features": [], "furniture": []}

    t = text.lower().strip()
    p = dict(DEFAULTS)

    # Определение типа объекта
    room_words = {
        "спальн": "bedroom", "детск": "children", "кухн": "kitchen",
        "гостин": "living", "ванн": "bathroom", "кабинет": "study",
        "салон": "living", "столов": "dining",
    }
    for word, room_type in room_words.items():
        if word in t:
            p["object_type"] = "room"
            p["room_type"] = room_type
            break

    if p["object_type"] == "building":
        if any(w in t for w in ["интерьер", "дизайн интерьера", "внутри помещения"]):
            p["object_type"] = "interior"

    # Тип здания
    type_map = {"офис": "office", "коттедж": "cottage", "вилл": "villa",
                "таунхаус": "townhouse", "квартир": "apartment"}
    for word, btype in type_map.items():
        if word in t:
            p["building_type"] = btype
            break

    # Этажи
    floor_words = {"одно": 1, "двух": 2, "трёх": 3, "трех": 3, "четыр": 4, "пяти": 5, "шести": 6}
    for word, n in floor_words.items():
        if word in t and ("этаж" in t or "уровн" in t):
            p["floors"] = n
            break
    fm = re.search(r"(\d+)\s*(?:этаж|floor)", t)
    if fm:
        p["floors"] = int(fm.group(1))

    # Размеры
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

    # Кровля
    if "плоск" in t:
        p["roof_type"] = "flat"
    elif "вальм" in t:
        p["roof_type"] = "hip"
    elif "двускат" in t or "скатн" in t:
        p["roof_type"] = "gabled"

    # Материал
    mat_map = {"кирпич": "brick", "дерев": "wood", "стекл": "glass",
               "камен": "stone", "бетон": "concrete", "штукатурк": "plaster"}
    for word, mat in mat_map.items():
        if word in t:
            p["material"] = mat
            break

    # Стиль (специфичные перед общими)
    style_map = {"хайтек": "hitech", "hi-tech": "hitech", "минималист": "minimalist",
                 "лофт": "loft", "классич": "classic", "скандинав": "scandinavian",
                 "современн": "modern", "модерн": "modern"}
    for word, style in style_map.items():
        if word in t:
            p["style"] = style
            break

    # Фичи
    if re.search(r'\bбалкон\w*', t):
        p["features"].append("balcony")
    if re.search(r'\bтеррас\w*', t):
        p["features"].append("terrace")
    if re.search(r'\bгараж\w*', t):
        p["features"].append("garage")

    # Мебель по умолчанию для комнат
    if p["room_type"] and not p["furniture"]:
        p["furniture"] = DEFAULT_FURNITURE.get(p["room_type"], ["sofa", "table"])

    return p


# ═══════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "llm-service", "model": MODEL})


@app.route("/api/v1/chat/completions", methods=["POST"])
def chat_completions():
    """Chat proxy to OpenRouter."""
    data = request.json or {}
    messages = data.get("messages", [])
    max_tokens = data.get("max_tokens", 400)
    temperature = data.get("temperature", 0.7)
    model = data.get("model", MODEL)

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "HTTP-Referer": "https://archai.app",
        "X-Title": "Architect LLM",
    }
    if OR_KEY:
        headers["Authorization"] = f"Bearer {OR_KEY}"

    try:
        payload = json.dumps(
            {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature},
            ensure_ascii=False,
        )
        r = requests.post(f"{OR_BASE}/chat/completions", headers=headers,
                         data=payload.encode("utf-8"), timeout=60)
        r.encoding = "utf-8"
        if r.status_code == 200:
            return jsonify(r.json()), 200
        try:
            return jsonify(r.json()), r.status_code
        except Exception:
            return jsonify({"error": "OpenRouter API error", "status": r.status_code}), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/v1/parse", methods=["POST"])
def parse_prompt():
    """
    Парсинг промта → структурированные параметры.
    Использует LLM для извлечения, fallback на regex.
    """
    data = request.json or {}
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "text required"}), 400

    # Попытка LLM-парсинга
    try:
        headers = {"Content-Type": "application/json"}
        if OR_KEY:
            headers["Authorization"] = f"Bearer {OR_KEY}"

        payload = json.dumps({
            "model": data.get("model", MODEL),
            "messages": [
                {"role": "system", "content": PARSE_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "max_tokens": 300,
            "temperature": 0.1,
        }, ensure_ascii=False)

        r = requests.post(f"{OR_BASE}/chat/completions", headers=headers,
                         data=payload.encode("utf-8"), timeout=30)

        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"]
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
            if json_match:
                raw_params = json.loads(json_match.group())
                result = validate_params(raw_params)
                return jsonify(result), 200
    except Exception as e:
        print(f"[llm-service] LLM parse error: {e}, falling back to regex")

    # Fallback на regex
    result = fallback_regex_parse(text)
    return jsonify(result), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8081))
    print(f"LLM Service starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
