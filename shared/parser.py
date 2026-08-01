"""
shared/parser.py — LLM-only парсер архитектурных промтов.

v6.0 — БЕЗ REGEX FALLBACK.
Каскад: сильная модель → средняя → слабая → бесплатные (7 моделей).
Кеш: Redis (L2, 24h) + in-memory (L1, 5min).
Если ВСЕ модели недоступны + кеш пуст → AllModelsFailedError (HTTP 503).
"""

import hashlib
import json
import logging
import os
import re
import time
from typing import Optional

import httpx

logger = logging.getLogger("archai.parser")

OPENROUTER_BASE = os.environ.get("OPENROUTER_BASE", "https://openrouter.ai/api/v1")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/1")

# ═══════════════════════════════════════════════════════════════
# LLM CASCADE — 7 моделей, от сильной к бесплатным
# ═══════════════════════════════════════════════════════════════

LLM_CASCADE = [
    {"model": "google/gemini-2.5-pro", "tier": 1, "timeout": 20},
    {"model": "anthropic/claude-sonnet-4", "tier": 1, "timeout": 20},
    {"model": "google/gemini-2.5-flash", "tier": 2, "timeout": 15},
    {"model": "openai/gpt-4o-mini", "tier": 2, "timeout": 15},
    {"model": "meta-llama/llama-4-maverick:free", "tier": 3, "timeout": 30},
    {"model": "qwen/qwen3-235b-a22b:free", "tier": 3, "timeout": 30},
    {"model": "deepseek/deepseek-chat-v3-0324:free", "tier": 3, "timeout": 30},
]

# ═══════════════════════════════════════════════════════════════
# L1 CACHE — in-memory
# ═══════════════════════════════════════════════════════════════

_l1: dict[str, tuple[float, dict]] = {}
_L1_TTL = 300
_L1_MAX = 1000


def _key(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode()).hexdigest()[:16]


def _l1_get(text: str) -> Optional[dict]:
    k = _key(text)
    if k in _l1:
        ts, val = _l1[k]
        if time.time() - ts < _L1_TTL:
            return val
        del _l1[k]
    return None


def _l1_set(text: str, val: dict) -> None:
    if len(_l1) >= _L1_MAX:
        oldest = min(_l1, key=lambda k: _l1[k][0])
        del _l1[oldest]
    _l1[_key(text)] = (time.time(), val)


# ═══════════════════════════════════════════════════════════════
# L2 CACHE — Redis
# ═══════════════════════════════════════════════════════════════

_redis = None


def _get_redis():
    global _redis
    if _redis is not None:
        return _redis
    try:
        import redis
        _redis = redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=2)
        _redis.ping()
        return _redis
    except Exception:
        _redis = None
        return None


def _l2_get(text: str) -> Optional[dict]:
    r = _get_redis()
    if r is None:
        return None
    try:
        raw = r.get(f"parse:{_key(text)}")
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _l2_set(text: str, val: dict) -> None:
    r = _get_redis()
    if r is None:
        return
    try:
        r.setex(f"parse:{_key(text)}", 86400, json.dumps(val, ensure_ascii=False))
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# JSON EXTRACTION
# ═══════════════════════════════════════════════════════════════

def _extract_json(text: str) -> Optional[dict]:
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'<reasoning>.*?</reasoning>', '', text, flags=re.DOTALL)

    md = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if md:
        try:
            return json.loads(md.group(1))
        except json.JSONDecodeError:
            pass

    depth, start = 0, -1
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    start = -1

    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


# ═══════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """Ты — парсер архитектурных описаний для 3D-генератора.
Отвечай ТОЛЬКО валидным JSON. Никаких рассуждений, пояснений, markdown.

Формат (строго JSON):
{
  "object_type": "building|interior|room",
  "building_type": "house|office|cottage|villa|apartment|townhouse|hotel|warehouse|school",
  "room_type": "bedroom|kitchen|living|bathroom|children|study|dining|hall|laundry|null",
  "floors": 2,
  "width_m": 10,
  "length_m": 12,
  "height_m": 3,
  "style": "modern|classic|loft|scandinavian|minimalist|hitech|art_deco|baroque|brutalism|japandi|biophilic|industrial|colonial|mediterranean|provence",
  "material": "brick|wood|glass|stone|concrete|plaster|marble|granite|ceramic|metal|composite|aerated_concrete|foam_block|sip_panel|timber_frame",
  "roof_type": "gabled|flat|hip|mansard|shed|dome",
  "features": ["balcony","terrace","garage","pool","garden","basement","attic","chimney","bay_window"],
  "furniture": ["sofa","table","bed","chandelier","wardrobe","bookshelf"],
  "confidence": 0.0-1.0
}

Правила:
- "детская/спальня/кухня/гостиная/ванная/прихожая" → object_type="room"
- "интерьер/дизайн интерьера" → object_type="interior"
- "дом/здание/коттедж/офис/таунхаус" → object_type="building"
- Размеры в метрах. "64 кв м" → width_m=8, length_m=8
- Если room_type определён, а furniture не указан → подобрать дефолтную мебель
- confidence: 1.0 если все параметры явны, 0.3 если додумываешь
"""


# ═══════════════════════════════════════════════════════════════
# VALIDATION
# ═══════════════════════════════════════════════════════════════

_VALID = {
    "object_type": {"building", "interior", "room"},
    "building_type": {"house", "office", "cottage", "villa", "apartment", "townhouse", "hotel", "warehouse", "school"},
    "room_type": {"bedroom", "kitchen", "living", "bathroom", "children", "study", "dining", "hall", "laundry"},
    "style": {"modern", "classic", "loft", "scandinavian", "minimalist", "hitech",
              "art_deco", "baroque", "brutalism", "japandi", "biophilic",
              "industrial", "colonial", "mediterranean", "provence"},
    "material": {"brick", "wood", "glass", "stone", "concrete", "plaster",
                 "marble", "granite", "ceramic", "metal", "composite",
                 "aerated_concrete", "foam_block", "sip_panel", "timber_frame"},
    "roof_type": {"gabled", "flat", "hip", "mansard", "shed", "dome"},
    "features": {"balcony", "terrace", "garage", "pool", "garden", "basement", "attic", "chimney", "bay_window"},
}

_DEFAULTS = {
    "object_type": "building", "building_type": "house", "room_type": None,
    "floors": 2, "width_m": 10, "length_m": 12, "height_m": 3,
    "style": "modern", "material": "plaster", "roof_type": "gabled",
    "features": [], "furniture": [], "confidence": 0.5,
}

_FURNITURE = {
    "bedroom": ["bed", "wardrobe", "nightstand"],
    "children": ["bed", "desk", "bookshelf"],
    "kitchen": ["table", "sink", "stove"],
    "living": ["sofa", "table", "chandelier"],
    "bathroom": ["sink", "bathtub"],
    "study": ["desk", "bookshelf", "chair"],
    "dining": ["table", "chairs"],
    "hall": ["wardrobe", "bench"],
    "laundry": ["washing_machine", "shelf"],
}


def _validate(raw: dict) -> dict:
    result = {**_DEFAULTS, "features": [], "furniture": []}
    for field, valid in _VALID.items():
        val = raw.get(field)
        if field == "features":
            result["features"] = [f for f in (val or []) if f in valid] if isinstance(val, list) else []
        elif field == "room_type":
            result["room_type"] = val if val and val in valid else ("living" if raw.get("object_type") == "room" else None)
        else:
            result[field] = val if val in valid else _DEFAULTS[field]
    floors = raw.get("floors", 2)
    result["floors"] = floors if isinstance(floors, int) and 1 <= floors <= 20 else 2
    for key in ("width_m", "length_m", "height_m"):
        val = raw.get(key, _DEFAULTS[key])
        result[key] = (int if key != "height_m" else float)(val) if isinstance(val, (int, float)) and 1 <= val <= 200 else _DEFAULTS[key]
    furniture = raw.get("furniture", [])
    result["furniture"] = furniture if isinstance(furniture, list) and furniture else _FURNITURE.get(result["room_type"], ["sofa", "table"]) if result["room_type"] else []
    conf = raw.get("confidence", 0.5)
    result["confidence"] = max(0.0, min(1.0, conf)) if isinstance(conf, (int, float)) else 0.5
    return result


# ═══════════════════════════════════════════════════════════════
# LLM CALLS
# ═══════════════════════════════════════════════════════════════

def _call_llm(text: str, cfg: dict) -> Optional[dict]:
    if not OPENROUTER_API_KEY:
        return None
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {OPENROUTER_API_KEY}"}
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}],
        "max_tokens": 500, "temperature": 0.1,
    }
    try:
        r = httpx.post(f"{OPENROUTER_BASE}/chat/completions", headers=headers, json=payload, timeout=cfg.get("timeout", 15))
        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"]
            parsed = _extract_json(content)
            if parsed:
                logger.info(f"LLM ok: {cfg['model']}")
                return parsed
            logger.warning(f"LLM non-JSON: {cfg['model']}: {content[:200]}")
        elif r.status_code == 429:
            logger.warning(f"LLM rate limited: {cfg['model']}")
        else:
            logger.warning(f"LLM {cfg['model']}: HTTP {r.status_code}")
    except httpx.TimeoutException:
        logger.warning(f"LLM timeout: {cfg['model']}")
    except Exception as e:
        logger.warning(f"LLM error ({cfg['model']}): {e}")
    return None


async def _call_llm_async(text: str, cfg: dict) -> Optional[dict]:
    if not OPENROUTER_API_KEY:
        return None
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {OPENROUTER_API_KEY}"}
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}],
        "max_tokens": 500, "temperature": 0.1,
    }
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{OPENROUTER_BASE}/chat/completions", headers=headers, json=payload, timeout=cfg.get("timeout", 15))
        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"]
            parsed = _extract_json(content)
            if parsed:
                logger.info(f"LLM async ok: {cfg['model']}")
                return parsed
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════════════
# MAIN — LLM-ONLY, NO REGEX
# ═══════════════════════════════════════════════════════════════

class AllModelsFailedError(Exception):
    pass


def parse_prompt(text: str) -> dict:
    if not text or not text.strip():
        return {**_DEFAULTS, "features": [], "furniture": []}
    cached = _l1_get(text)
    if cached:
        return cached
    cached = _l2_get(text)
    if cached:
        _l1_set(text, cached)
        return cached
    for cfg in LLM_CASCADE:
        raw = _call_llm(text, cfg)
        if raw:
            val = _validate(raw)
            _l1_set(text, val)
            _l2_set(text, val)
            return val
    raise AllModelsFailedError(
        "Все 7 LLM-моделей недоступны и кеш парсинга пуст. "
        "Проверьте OPENROUTER_API_KEY и доступность openrouter.ai"
    )


async def parse_prompt_async(text: str) -> dict:
    if not text or not text.strip():
        return {**_DEFAULTS, "features": [], "furniture": []}
    cached = _l1_get(text)
    if cached:
        return cached
    cached = _l2_get(text)
    if cached:
        _l1_set(text, cached)
        return cached
    for cfg in LLM_CASCADE:
        raw = await _call_llm_async(text, cfg)
        if raw:
            val = _validate(raw)
            _l1_set(text, val)
            _l2_set(text, val)
            return val
    raise AllModelsFailedError("Все 7 LLM-моделей недоступны и кеш парсинга пуст.")


# ═══════════════════════════════════════════════════════════════
# COMPATIBILITY ALIASES (для существующего кода)
# ═══════════════════════════════════════════════════════════════

parse_prompt_sync = parse_prompt  # sync alias


def get_generation_type(params: dict) -> str:
    obj_type = params.get("object_type", "building")
    return "interior" if obj_type in ("interior", "room") else "building"


def get_cache_stats() -> dict:
    r = _get_redis()
    redis_keys = 0
    if r:
        try:
            redis_keys = len(r.keys("parse:*"))
        except Exception:
            pass
    return {
        "l1_entries": len(_l1), "l1_max": _L1_MAX, "l1_ttl": _L1_TTL,
        "l2_redis_entries": redis_keys, "l2_ttl": 86400,
        "llm_cascade": [m["model"] for m in LLM_CASCADE],
        "redis_connected": r is not None,
    }
