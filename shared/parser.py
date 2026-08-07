"""
shared/parser.py — LLM парсинг архитектурных промтов.

v10.0 — Интеграция с ModelManager:
  - Все LLM вызовы через ModelManager (auto-discovery + key rotation)
  - Только бесплатные модели OpenRouter + Gemini fallback
  - Кеширование: Redis L2 + in-memory L1
  - Pydantic валидация ответов
  - Prompt sanitization

НЕТ regex fallback — LLM only.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import threading
import time

import httpx

logger = logging.getLogger("archai.parser")


# ═══════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT_VERSION = "v10.0"

SYSTEM_PROMPT = """Ты — парсер архитектурных описаний для 3D-генератора.
Отвечай ТОЛЬКО валидным JSON. Никаких рассуждений, пояснений, markdown.

Твоя задача — понять контекст пользователя и передать параметры для 3D-генерации.
НЕ ограничивайся списком — если пользователь просит что-то необычное — ты ОБЯЗАН это понять.

═══ КРИТИЧЕСКИ ВАЖНОЕ ПРАВИЛО ОПРЕДЕЛЕНИЯ ТИПА ═══

object_type определяет ЧТО генерировать:
- "interior" = внутреннее помещение (комната, квартира)
- "building" = здание/сооружение снаружи
- "landscape" = ландшафтный дизайн участка

ПРАВИЛА ОПРЕДЕЛЕНИЯ object_type:

1. ИНТЕРЬЕР (object_type="interior") — когда пользователь хочет ДИЗАЙН ВНУТРИ:
   Ключевые слова: "ванная", "кухня", "спальня", "гостиная", "детская", "интерьер",
   "дизайн комнаты", "дизайн кухни", "оформление", "мебель", "обстановка"
   → object_type="interior", room_type=тип комнаты

2. ЗДАНИЕ (object_type="building") — когда пользователь хочет ПОСТРОИТЬ ЗДАНИЕ:
   Ключевые слова: "построить дом", "здание", "офис", "коттедж", "отель",
   "построй", "сделай дом", "таунхаус", "здание", "сооружение"
   → object_type="building"

3. ЛАНДШАФТ (object_type="landscape") — когда пользователь хочет ЛАНДШАФТ:
   Ключевые слова: "ландшафт", "сад", "двор", "участок", "ландшафтный дизайн"
   → object_type="landscape"
   НЕ ГЕНЕРИРУЙ ЗДАНИЕ если просят ландшафт!

═══ ФОРМАТ JSON (строго) ═══
{
  "object_type": "building|interior|landscape|structure",
  "building_type": "ЛЮБОЕ строковое значение",
  "building_description": "подробное описание что именно делаем",
  "room_type": "тип комнаты если интерьер, иначе null",
  "floors": число (1-50),
  "width_m": ширина в метрах (реалистичная),
  "length_m": длина в метрах,
  "height_m": высота в метрах,
  "style": "ЛЮБОЕ значение стиля",
  "material": "ЛЮБОЕ значение материала",
  "roof_type": "ЛЮБОЕ значение типа крыши",
  "features": ["ЛЮБЫЕ особенности"],
  "furniture": ["ЛЮБАЯ мебель для интерьера"],
  "special_requirements": ["ЛЮБЫЕ особые требования"],
  "confidence": 0.0-1.0,
  "reasoning": "кратко почему решил именно так",
  "suggestions": ["подсказка1", "подсказка2", "подсказка3"],
  "references": ["ключевое_слово1", "ключевое_слово2"],
  "decomposition": [{"name":"Этап","description":"что делаем"}],
}

═══ ПРАВИЛА ═══
1. building_type — НЕ ограничивайся. Сарай→barn, навес→carport, беседка→gazebo.
2. material — НЕ ограничивайся. Из брёвен→log, из соломы→straw, из кирпича→brick.
3. style — НЕ ограничивайся. Японский→japanese, средневековый→medieval, лофт→loft.
4. Размеры по умолчанию (если не указаны):
   Сарай: 3×4×2.5м. Беседка: 3×3×2.5м. Гараж: 6×3×3м. Дом: 10×12×3м.
   Ванная: 2.5×3×2.8м. Кухня: 4×5×2.8м.
5. Для интерьера — перечисли мебель в поле furniture.
6. Если запрос неясен — confidence < 0.5, в reasoning объясни что неясно.
7. reasoning — кратко почему решил именно так (2-3 предложения).
8. suggestions — массив 3-5 строк-подсказок для развития проекта.
9. references — массив 2-4 ключевых слов для поиска референсов.
10. decomposition — массив этапов: [{"name":"Название","description":"что делаем"}].
"""


# ═══════════════════════════════════════════════════════════════
# BACKWARD COMPATIBILITY: LLM_CASCADE
# ═══════════════════════════════════════════════════════════════

def _get_fallback_cascade() -> list[dict]:
    """Hardcoded fallback — only used if ModelManager not initialized."""
    return [
        {"model": "meta-llama/llama-3.3-70b-instruct:free", "tier": 1, "timeout": 30},
        {"model": "mistralai/mistral-small-3.2-24b:free", "tier": 1, "timeout": 30},
        {"model": "google/gemma-4-26b-a4b-it:free", "tier": 1, "timeout": 30},
        {"model": "qwen/qwen3-235b-a22b:free", "tier": 1, "timeout": 30},
        {"model": "deepseek/deepseek-chat-v3-0324:free", "tier": 2, "timeout": 30},
        {"model": "google/gemma-4-31b-it:free", "tier": 2, "timeout": 30},
    ]

LLM_CASCADE = _get_fallback_cascade()


# ═══════════════════════════════════════════════════════════════
# PROMPT SANITIZATION
# ═══════════════════════════════════════════════════════════════

def _sanitize_prompt(text: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    if len(text) > 2000:
        text = text[:2000] + "...(truncated)"
    injection_patterns = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"you\s+are\s+now\s+",
        r"system\s*:\s*",
        r"<\|im_start\|>",
        r"<\|im_end\|>",
        r"###\s*System",
        r"forget\s+(all\s+)?instructions",
    ]
    for pattern in injection_patterns:
        text = re.sub(pattern, "[FILTERED]", text, flags=re.IGNORECASE)
    return text.strip()


# ═══════════════════════════════════════════════════════════════
# JSON EXTRACTION
# ═══════════════════════════════════════════════════════════════

def _extract_json(text: str) -> dict | None:
    """Extract JSON from LLM response, handling various formats."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<reasoning>.*?</reasoning>", "", text, flags=re.DOTALL)

    md = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if md:
        try:
            return json.loads(md.group(1))
        except json.JSONDecodeError:
            pass

    depth, start = 0, -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    start = -1

    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


# ═══════════════════════════════════════════════════════════════
# CACHE — L1 (in-memory) + L2 (Redis)
# ═══════════════════════════════════════════════════════════════

_l1_cache: dict[str, tuple[float, dict]] = {}
_l1_lock = threading.Lock()
L1_TTL = 300  # 5 min
L1_MAX = 500

_redis_client = None


def _key(text: str) -> str:
    """Generate cache key from prompt text + system prompt version."""
    return hashlib.sha256(f"{SYSTEM_PROMPT_VERSION}:{text}".encode()).hexdigest()


def _l1_get(text: str) -> dict | None:
    """L1 cache get (thread-safe)."""
    k = _key(text)
    with _l1_lock:
        if k in _l1_cache:
            ts, val = _l1_cache[k]
            if time.time() - ts < L1_TTL:
                return val
            del _l1_cache[k]
    return None


def _l1_set(text: str, val: dict) -> None:
    """L1 cache set (thread-safe)."""
    k = _key(text)
    with _l1_lock:
        if len(_l1_cache) >= L1_MAX:
            oldest = min(_l1_cache.items(), key=lambda x: x[1][0])
            del _l1_cache[oldest[0]]
        _l1_cache[k] = (time.time(), val)


def _get_redis():
    """Get Redis client (lazy init)."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis.asyncio as aioredis
        redis_url = os.environ.get("REDIS_URL", "")
        if redis_url:
            _redis_client = aioredis.from_url(redis_url, decode_responses=True)
            return _redis_client
    except Exception:
        pass
    return None


async def _l2_get(text: str) -> dict | None:
    """L2 (Redis) cache get."""
    redis = _get_redis()
    if not redis:
        return None
    try:
        raw = await redis.get(f"parse:{_key(text)}")
        if raw:
            data = json.loads(raw)
            _l1_set(text, data)
            return data
    except Exception:
        pass
    return None


async def _l2_set(text: str, val: dict) -> None:
    """L2 (Redis) cache set."""
    redis = _get_redis()
    if not redis:
        return
    try:
        await redis.setex(f"parse:{_key(text)}", 86400, json.dumps(val, ensure_ascii=False))
    except Exception:
        pass


def get_cache_stats() -> dict:
    with _l1_lock:
        l1_count = len(_l1_cache)
    return {
        "l1_size": l1_count,
        "l1_max": L1_MAX,
        "l1_ttl": L1_TTL,
        "redis_connected": _get_redis() is not None,
    }


# ═══════════════════════════════════════════════════════════════
# COST TRACKING
# ═══════════════════════════════════════════════════════════════

_cost_data: dict[str, dict] = {"total_tokens_in": 0, "total_tokens_out": 0, "by_model": {}}


def _track_cost(model: str, tokens_in: int, tokens_out: int) -> None:
    _cost_data["total_tokens_in"] += tokens_in
    _cost_data["total_tokens_out"] += tokens_out
    if model not in _cost_data["by_model"]:
        _cost_data["by_model"][model] = {"in": 0, "out": 0, "calls": 0}
    _cost_data["by_model"][model]["in"] += tokens_in
    _cost_data["by_model"][model]["out"] += tokens_out
    _cost_data["by_model"][model]["calls"] += 1


def get_cost_stats() -> dict:
    return dict(_cost_data)


# ═══════════════════════════════════════════════════════════════
# VALIDATION
# ═══════════════════════════════════════════════════════════════

def _validate(params: dict) -> dict:
    """Validate and normalize parsed parameters (backward compat)."""
    if "object_type" not in params:
        params["object_type"] = "building"
    obj = str(params.get("object_type", "building")).lower().strip()
    if obj in ("room", "apartment"):
        obj = "interior"
    params["object_type"] = obj
    for field in ("floors", "width_m", "length_m", "height_m"):
        val = params.get(field)
        if val is not None:
            try:
                params[field] = float(val)
            except (ValueError, TypeError):
                params[field] = None
    for field in ("features", "furniture", "special_requirements", "suggestions", "references", "decomposition"):
        if not isinstance(params.get(field), list):
            params[field] = []
    try:
        params["confidence"] = max(0.0, min(1.0, float(params.get("confidence", 0.5))))
    except (ValueError, TypeError):
        params["confidence"] = 0.5
    return params


def _validate_and_fix(result: dict | None, text: str) -> dict | None:
    """Validate LLM result, fix common issues (backward compat)."""
    if result is None:
        return None
    return _validate(result)


def _validate_result(result: dict) -> bool:
    """Check if result has minimum required fields."""
    return bool(result and result.get("object_type"))


def _minimal_defaults(reason: str) -> dict:
    """Return minimal valid params when LLM fails."""
    return {
        "object_type": "building",
        "building_type": "house",
        "building_description": reason,
        "floors": 2,
        "width_m": 10,
        "length_m": 12,
        "height_m": 6,
        "style": "modern",
        "material": "brick",
        "roof_type": "gabled",
        "features": [],
        "furniture": [],
        "special_requirements": [],
        "confidence": 0.1,
        "reasoning": reason,
        "suggestions": [],
        "references": [],
        "decomposition": [],
    }


# ═══════════════════════════════════════════════════════════════
# GET GENERATION TYPE
# ═══════════════════════════════════════════════════════════════

def get_generation_type(params: dict) -> str:
    """Detect generation type from parsed params."""
    obj = (params.get("object_type") or "").strip().lower()
    if obj in ("interior", "room"):
        return "interior"
    if obj == "landscape":
        return "landscape"
    if params.get("room_type"):
        return "interior"
    return "building"


# ═══════════════════════════════════════════════════════════════
# MAIN PARSE FUNCTION — uses ModelManager
# ═══════════════════════════════════════════════════════════════

async def parse_prompt_async(text: str) -> dict:
    """
    Parse architectural prompt → structured parameters.
    Uses ModelManager for LLM calls (free OpenRouter models + Gemini fallback).
    """
    from shared.model_manager import get_model_manager, AllModelsFailedError

    sanitized = _sanitize_prompt(text)
    if not sanitized:
        raise ValueError("Empty prompt after sanitization")

    # Check cache L1 → L2
    cached = _l1_get(sanitized)
    if cached:
        return cached
    cached = await _l2_get(sanitized)
    if cached:
        return cached

    manager = get_model_manager()
    messages = [{"role": "user", "content": sanitized}]

    try:
        result = await manager.send_request(
            messages=messages,
            max_tokens=500,
            temperature=0.1,
            system_prompt=SYSTEM_PROMPT,
        )
    except AllModelsFailedError:
        raise
    except Exception as e:
        raise AllModelsFailedError(f"Unexpected error: {e}") from e

    content = result.get("content", "")
    parsed = _extract_json(content)

    if parsed is None:
        # Retry with stricter prompt
        try:
            retry = await manager.send_request(
                messages=[{"role": "user", "content": f"Ответь ТОЛЬКО валидным JSON без пояснений.\n\n{sanitized}"}],
                max_tokens=500,
                temperature=0.0,
                system_prompt=SYSTEM_PROMPT,
            )
            parsed = _extract_json(retry.get("content", ""))
        except Exception:
            pass

    if parsed is None:
        raise AllModelsFailedError(f"All models returned non-JSON. Last: {content[:300]}")

    parsed = _validate(parsed)
    parsed["_model"] = result.get("model", "unknown")
    parsed["_provider"] = result.get("provider", "unknown")

    # Cache
    _l1_set(sanitized, parsed)
    await _l2_set(sanitized, parsed)

    logger.info(
        "Parsed: type=%s, confidence=%.2f, model=%s/%s",
        parsed.get("object_type"), parsed.get("confidence", 0),
        result.get("provider"), result.get("model"),
    )
    return parsed


def parse_prompt_sync(text: str) -> dict:
    """Synchronous wrapper for parse_prompt_async (backward compat)."""
    return asyncio.run(parse_prompt_async(text))


# Alias for backward compat
parse_prompt = parse_prompt_async


# ═══════════════════════════════════════════════════════════════
# BACKWARD COMPAT: discovery functions used by llm-service
# ═══════════════════════════════════════════════════════════════

async def discover_free_models(api_key: str = "") -> list[dict]:
    from shared.model_manager import get_model_manager
    manager = get_model_manager()
    models = await manager.discover_free_models(force=True)
    return [m.to_dict() for m in models]


def get_active_cascade(api_key: str = "") -> list[dict]:
    from shared.model_manager import get_model_manager
    manager = get_model_manager()
    models = manager.get_active_models()
    if not models:
        return _get_fallback_cascade()
    return [{"model": m.model_id, "tier": m.tier, "timeout": 30} for m in models]


def get_discovery_stats() -> dict:
    from shared.model_manager import get_model_manager
    manager = get_model_manager()
    stats = manager.get_stats()
    return {
        "discovered_count": stats["free_models_count"],
        "discovered_models": [m["model"] for m in stats["free_models"][:10]],
        "last_discover_ago": stats["last_discovery_ago"],
        "ttl": stats["discovery_interval"],
        "hardcoded_fallback": [m["model"] for m in _get_fallback_cascade()],
        "openrouter_keys": stats["openrouter_keys"],
        "gemini_keys": stats["gemini_keys"],
    }


def invalidate_discovery() -> None:
    from shared.model_manager import get_model_manager
    manager = get_model_manager()
    manager._free_models = []
    manager._last_discovery = 0.0


# ═══════════════════════════════════════════════════════════════
# ALL MODELS FAILED ERROR (must be importable from here)
# ═══════════════════════════════════════════════════════════════

# Re-export from model_manager for backward compat
try:
    from shared.model_manager import AllModelsFailedError
except ImportError:
    class AllModelsFailedError(Exception):
        pass
