"""
LLM Microservice — proxy to OpenRouter + prompt parsing (FastAPI)

Endpoints:
  GET  /health                        — Health check
  POST /api/v1/chat/completions       — Chat proxy to OpenRouter
  POST /api/v1/parse                  — Prompt → structured params (LLM + regex fallback)
  GET  /docs                          — OpenAPI documentation
"""
import os
import re
import json
from typing import Optional, List

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="Architect LLM Service",
    description="Прокси к OpenRouter + парсинг архитектурных промтов",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════

OR_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OR_BASE = "https://openrouter.ai/api/v1"
MODEL = os.environ.get("LLM_MODEL", "nvidia/nemotron-3-nano-30b-a3b:free")


# ═══════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════

class ChatMessage(BaseModel):
    role: str = "user"
    content: str = ""


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., description="Messages array")
    max_tokens: int = Field(400, ge=1, le=4096)
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    model: Optional[str] = None


class ChatResponse(BaseModel):
    choices: List[dict]


class ParseRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Промт для парсинга")
    model: Optional[str] = None


class ParsedParams(BaseModel):
    object_type: str = "building"
    building_type: str = "house"
    room_type: Optional[str] = None
    floors: int = 2
    width_m: int = 10
    length_m: int = 12
    height_m: int = 3
    style: str = "modern"
    material: str = "plaster"
    roof_type: str = "gabled"
    features: List[str] = []
    furniture: List[str] = []


# ═══════════════════════════════════════════════════════════════
# VALID VALUES
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
- "64 кв метра" → width_m=8, length_m=8 (примерный корень из площади)"""


# ═══════════════════════════════════════════════════════════════
# VALIDATION
# ═══════════════════════════════════════════════════════════════

def validate_params(params: dict) -> dict:
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

    furniture = params.get("furniture", [])
    if isinstance(furniture, list) and furniture:
        result["furniture"] = furniture
    elif result["room_type"]:
        result["furniture"] = DEFAULT_FURNITURE.get(result["room_type"], ["sofa", "table"])

    return result


# ═══════════════════════════════════════════════════════════════
# REGEX FALLBACK
# ═══════════════════════════════════════════════════════════════

def fallback_regex_parse(text: str) -> dict:
    if not text or not text.strip():
        return {**DEFAULTS, "features": [], "furniture": []}

    t = text.lower().strip()
    p = {**DEFAULTS, "features": [], "furniture": []}

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
        if any(w in t for w in ["интерьер", "дизайн интерьера"]):
            p["object_type"] = "interior"

    type_map = {"офис": "office", "коттедж": "cottage", "вилл": "villa",
                "таунхаус": "townhouse", "квартир": "apartment"}
    for word, btype in type_map.items():
        if word in t:
            p["building_type"] = btype
            break

    floor_words = {"одно": 1, "двух": 2, "трёх": 3, "трех": 3, "четыр": 4, "пяти": 5}
    for word, n in floor_words.items():
        if word in t and ("этаж" in t or "уровн" in t):
            p["floors"] = n
            break
    fm = re.search(r"(\d+)\s*(?:этаж|floor)", t)
    if fm:
        p["floors"] = int(fm.group(1))

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

    if "плоск" in t:
        p["roof_type"] = "flat"
    elif "вальм" in t:
        p["roof_type"] = "hip"
    elif "двускат" in t or "скатн" in t:
        p["roof_type"] = "gabled"

    mat_map = {"кирпич": "brick", "дерев": "wood", "стекл": "glass",
               "камен": "stone", "бетон": "concrete", "штукатурк": "plaster"}
    for word, mat in mat_map.items():
        if word in t:
            p["material"] = mat
            break

    style_map = {"хайтек": "hitech", "hi-tech": "hitech", "минималист": "minimalist",
                 "минимализм": "minimalist", "лофт": "loft", "классич": "classic",
                 "скандинав": "scandinavian", "современн": "modern", "модерн": "modern"}
    for word, style in style_map.items():
        if word in t:
            p["style"] = style
            break

    if re.search(r'\bбалкон\w*', t):
        p["features"].append("balcony")
    if re.search(r'\bтеррас\w*', t):
        p["features"].append("terrace")
    if re.search(r'\bгараж\w*', t):
        p["features"].append("garage")

    if p["room_type"] and not p["furniture"]:
        p["furniture"] = DEFAULT_FURNITURE.get(p["room_type"], ["sofa", "table"])

    return p


# ═══════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {"status": "ok", "service": "llm-service", "model": MODEL}


@app.post("/api/v1/chat/completions", response_model=ChatResponse)
async def chat_completions(req: ChatRequest):
    """Chat proxy to OpenRouter."""
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "HTTP-Referer": "https://archai.app",
        "X-Title": "Architect LLM",
    }
    if OR_KEY:
        headers["Authorization"] = f"Bearer {OR_KEY}"

    payload = {
        "model": req.model or MODEL,
        "messages": [m.model_dump() for m in req.messages],
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
    }

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{OR_BASE}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60.0,
            )
        if r.status_code == 200:
            return r.json()
        raise HTTPException(status_code=r.status_code, detail=r.text)
    except httpx.TimeoutException:
        raise HTTPException(504, "OpenRouter timeout")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, str(e))


@app.post("/api/v1/parse", response_model=ParsedParams)
async def parse_prompt(req: ParseRequest):
    """
    Парсинг промта → структурированные параметры.
    Использует LLM для извлечения, fallback на regex.
    """
    text = req.text

    # Попытка LLM-парсинга
    try:
        headers = {"Content-Type": "application/json"}
        if OR_KEY:
            headers["Authorization"] = f"Bearer {OR_KEY}"

        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{OR_BASE}/chat/completions",
                headers=headers,
                json={
                    "model": req.model or MODEL,
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
        print(f"[llm-service] LLM parse error: {e}, falling back to regex")

    # Fallback на regex
    return fallback_regex_parse(text)


# ═══════════════════════════════════════════════════════════════
# STARTUP
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8081))
    print(f"LLM Service starting on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
