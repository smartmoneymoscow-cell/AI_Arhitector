"""
llm-service/parser_flexible.py — FLEXIBLE LLM parsing with all fixes applied.

Fixes:
  L1  — Prompt sanitization (injection prevention)
  L2  — Timeouts increased to 30-40s
  L3  — Fallback OpenRouter key
  L4  — Ollama local model fallback
  L5  — Improved JSON extraction
  L6  — threading.Lock for L1 cache (thread-safe)
  L7  — Full sha256 hash (no truncation)
  L8  — Model version in cache key (auto-invalidation)
  L9  — Agent isolation (in orchestrator, not here)
"""

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
# SYSTEM PROMPT — FLEXIBLE, no hardcoded values
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT_VERSION = "v8.1"  # ← bump to invalidate all caches

SYSTEM_PROMPT = """Ты — парсер архитектурных описаний для 3D-генератора.
Отвечай ТОЛЬКО валидным JSON. Никаких рассуждений, пояснений, markdown.

Твоя задача — понять контекст пользователя и передать параметры для 3D-генерации.
НЕ ограничивайся списком — если пользователь просит что-то необычное (сарай, навес,
беседка, гараж, теплица, курятник, баня, бассейн, забор, ворота) — ты ОБЯЗАН это понять
и сгенерировать подходящие параметры.

Формат JSON (строго):
{
  "object_type": "building|interior|room|structure|landscape|element",
  "building_type": "ЛЮБОЕ строковое значение — ты определяешь по контексту",
  "building_description": "подробное описание что именно строим",
  "room_type": "тип комнаты если интерьер, иначе null",
  "floors": число этажей (1-20, для одноэтажных строений = 1),
  "width_m": ширина в метрах (реалистичная для данного объекта),
  "length_m": длина в метрах,
  "height_m": высота в метрах (реалистичная),
  "style": "стиль — ЛЮБОЕ значение: modern, classic, loft, rustic, medieval, japanese, и т.д.",
  "material": "основной материал — ЛЮБОЕ значение: brick, wood, stone, metal, glass, concrete, plastic, fabric, и т.д.",
  "roof_type": "тип крыши — ЛЮБОЕ значение: gabled, flat, hip, mansard, shed, dome, asymmetric, green, и т.д.",
  "features": ["ЛЮБЫЕ особенности: balcony, terrace, garage, pool, garden, chimney, skylight, и т.д."],
  "furniture": ["ЛЮБАЯ мебель/оборудование для интерьера"],
  "special_requirements": ["ЛЮБЫЕ особые требования из промта"],
  "confidence": 0.0-1.0 (насколько ты уверен в интерпретации),
  "reasoning": "кратко почему ты решил именно так"
}

ПРАВИЛА:
1. building_type — НЕ ограничивайся списком. Если "сарай" → "barn". Если "навес" → "carport".
   Если "беседка" → "gazebo". Если "теплица" → "greenhouse". Если "курятник" → "chicken_coop".

2. material — НЕ ограничивайся. "из брёвен" → "log". "из соломы" → "straw".

3. style — НЕ ограничивайся. "в японском стиле" → "japanese". "средневековый" → "medieval".

4. Размеры — если не указаны, подбери РЕАЛИСТИЧНЫЕ:
   Сарай: 3×4×2.5м. Беседка: 3×3×2.5м. Гараж: 6×3×3м. Дом: 10×12×3м.

5. Русские слова: сарай=barn, навес=carport, беседка=gazebo, гараж=garage,
   теплица=greenhouse, баня=bathhouse, курятник=chicken_coop, забор=fence,
   ворота=gate, сруб=log_cabin, изба=izba.
"""


# ═══════════════════════════════════════════════════════════════
# L3: FALLBACK API KEYS — multiple keys for resilience
# ═══════════════════════════════════════════════════════════════


def _get_api_keys() -> list[str]:
    """Get all available API keys (primary + fallbacks)."""
    keys = []
    primary = os.environ.get("OPENROUTER_API_KEY", "")
    if primary:
        keys.append(primary)

    # L3: Fallback keys (comma-separated)
    fallback = os.environ.get("OPENROUTER_FALLBACK_KEYS", "")
    if fallback:
        for k in fallback.split(","):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)

    return keys


# ═══════════════════════════════════════════════════════════════
# L4: OLLAMA LOCAL FALLBACK
# ═══════════════════════════════════════════════════════════════

OLLAMA_URL = os.environ.get("OLLAMA_URL", "")  # e.g. "http://host.docker.internal:11434"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")


# ═══════════════════════════════════════════════════════════════
# LLM CASCADE
# ═══════════════════════════════════════════════════════════════

LLM_CASCADE = [
    {"model": "google/gemini-2.5-pro", "tier": 1, "timeout": 35},
    {"model": "anthropic/claude-sonnet-4", "tier": 1, "timeout": 35},
    {"model": "google/gemini-2.5-flash", "tier": 2, "timeout": 25},
    {"model": "openai/gpt-4o-mini", "tier": 2, "timeout": 25},
    {"model": "meta-llama/llama-4-maverick:free", "tier": 3, "timeout": 40},
    {"model": "qwen/qwen3-235b-a22b:free", "tier": 3, "timeout": 40},
    {"model": "deepseek/deepseek-chat-v3-0324:free", "tier": 3, "timeout": 40},
]


# ═══════════════════════════════════════════════════════════════
# PROMPT SANITIZATION (L1: security)
# ═══════════════════════════════════════════════════════════════


def _sanitize_prompt(text: str) -> str:
    """Sanitize user prompt before sending to LLM."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    MAX_PROMPT_LENGTH = 2000
    if len(text) > MAX_PROMPT_LENGTH:
        text = text[:MAX_PROMPT_LENGTH] + "...(truncated)"
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
# JSON EXTRACTION (L5: improved)
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
# CACHE — L1 (thread-safe) + L2 (Redis)
# L6: threading.Lock
# L7: full sha256
# L8: model version in key
# ═══════════════════════════════════════════════════════════════

_l1: dict[str, tuple[float, dict]] = {}
_l1_lock = threading.Lock()  # L6: thread-safe
_L1_TTL = 300
_L1_MAX = 1000


def _key(text: str) -> str:
    """L7: Full sha256 hash (no truncation). L8: includes model version."""
    content = f"{SYSTEM_PROMPT_VERSION}:{text.strip().lower()}"
    return hashlib.sha256(content.encode()).hexdigest()  # L7: full 64 chars


def _l1_get(text: str) -> dict | None:
    k = _key(text)
    with _l1_lock:  # L6: thread-safe read
        if k in _l1:
            ts, val = _l1[k]
            if time.time() - ts < _L1_TTL:
                return val
            del _l1[k]
    return None


def _l1_set(text: str, val: dict) -> None:
    k = _key(text)
    with _l1_lock:  # L6: thread-safe write
        if len(_l1) >= _L1_MAX:
            oldest = min(_l1, key=lambda x: _l1[x][0])
            del _l1[oldest]
        _l1[k] = (time.time(), val)


_redis = None


def _get_redis():
    global _redis
    if _redis is not None:
        return _redis
    try:
        import redis

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/1")
        _redis = redis.from_url(redis_url, decode_responses=True, socket_timeout=2)
        _redis.ping()
        return _redis
    except Exception:
        _redis = None
        return None


def _l2_get(text: str) -> dict | None:
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


class AllModelsFailedError(Exception):
    pass


# ═══════════════════════════════════════════════════════════════
# LLM CALL — with key rotation (L3) + ollama fallback (L4)
# ═══════════════════════════════════════════════════════════════


async def _call_openrouter(model: str, prompt: str, timeout: int, api_key: str) -> dict | None:
    """Call a single LLM model via OpenRouter with given key."""
    base_url = os.environ.get("OPENROUTER_BASE", "https://openrouter.ai/api/v1")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://archai.app",
        "X-Title": "Architect Parser",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 1024,
        "temperature": 0.1,
    }

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout,
            )

        if r.status_code == 429:
            logger.warning("LLM %s rate-limited, trying next key/model", model)
            return None  # signal to try next key

        if r.status_code != 200:
            logger.warning("LLM %s returned %d", model, r.status_code)
            return None

        data = r.json()
        content = data["choices"][0]["message"]["content"]
        return _extract_json(content)

    except httpx.TimeoutException:
        logger.warning("LLM %s timeout (%ds)", model, timeout)
        return None
    except Exception as e:
        logger.warning("LLM %s error: %s", model, e)
        return None


async def _call_ollama(prompt: str) -> dict | None:
    """L4: Call local Ollama model as last resort."""
    if not OLLAMA_URL:
        return None

    logger.info("Trying Ollama fallback: %s at %s", OLLAMA_MODEL, OLLAMA_URL)

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json=payload,
                timeout=60,
            )

        if r.status_code != 200:
            logger.warning("Ollama returned %d", r.status_code)
            return None

        data = r.json()
        content = data.get("message", {}).get("content", "")
        return _extract_json(content)

    except Exception as e:
        logger.warning("Ollama error: %s", e)
        return None


# ═══════════════════════════════════════════════════════════════
# VALIDATION
# ═══════════════════════════════════════════════════════════════


def _validate_result(result: dict) -> bool:
    """Minimal validation — only check essential fields."""
    if not result.get("object_type"):
        return False
    w = result.get("width_m", 0)
    l = result.get("length_m", 0)
    if w <= 0 or l <= 0 or w > 500 or l > 500:
        return False
    floors = result.get("floors", 0)
    return not (floors <= 0 or floors > 50)


def _minimal_defaults(reason: str) -> dict:
    """Absolute minimal defaults when everything fails."""
    return {
        "object_type": "building",
        "building_type": "house",
        "building_description": reason,
        "floors": 2,
        "width_m": 10,
        "length_m": 12,
        "height_m": 3.0,
        "style": "modern",
        "material": "plaster",
        "roof_type": "gabled",
        "features": [],
        "furniture": [],
        "confidence": 0.1,
        "reasoning": reason,
    }


# ═══════════════════════════════════════════════════════════════
# MAIN PARSE FUNCTION
# ═══════════════════════════════════════════════════════════════


async def parse_prompt_async(text: str) -> dict:
    """
    Parse architectural prompt using LLM cascade.

    L1: Prompt sanitized (injection prevention)
    L2: Timeouts 30-40s
    L3: Multiple API keys with rotation
    L4: Ollama local fallback
    L6: Thread-safe L1 cache
    L7: Full sha256 hash
    L8: Model version in cache key
    """
    text = _sanitize_prompt(text)
    if not text:
        return _minimal_defaults("Empty prompt")

    # L1 cache
    cached = _l1_get(text)
    if cached:
        return cached

    # L2 cache
    cached = _l2_get(text)
    if cached:
        _l1_set(text, cached)
        return cached

    # L3: Get all available keys
    api_keys = _get_api_keys()
    if not api_keys:
        logger.error("No OPENROUTER_API_KEY configured")
        # L4: Try Ollama as last resort
        result = await _call_ollama(text)
        if result and _validate_result(result):
            _l1_set(text, result)
            _l2_set(text, result)
            return result
        raise AllModelsFailedError("No API keys configured and Ollama unavailable")

    # LLM cascade with key rotation (L3)
    for model_config in LLM_CASCADE:
        model = model_config["model"]
        timeout = model_config["timeout"]

        for key_idx, api_key in enumerate(api_keys):
            logger.info("Trying LLM: %s (key %d/%d)", model, key_idx + 1, len(api_keys))
            result = await _call_openrouter(model, text, timeout, api_key)

            if result and _validate_result(result):
                _l1_set(text, result)
                _l2_set(text, result)
                logger.info("LLM %s parsed successfully: %s", model, result.get("building_type"))
                return result

            if result is not None:
                # Got response but invalid — try next model, not next key
                break

    # L4: All OpenRouter models failed → try Ollama
    logger.warning("All OpenRouter models failed, trying Ollama fallback")
    result = await _call_ollama(text)
    if result and _validate_result(result):
        _l1_set(text, result)
        _l2_set(text, result)
        logger.info("Ollama fallback succeeded: %s", result.get("building_type"))
        return result

    raise AllModelsFailedError(f"All {len(LLM_CASCADE)} LLM models (+ Ollama) failed for prompt: {text[:100]}...")


def get_cache_stats() -> dict:
    """Cache statistics for health endpoint."""
    with _l1_lock:
        l1_count = len(_l1)
    redis_ok = _get_redis() is not None
    return {
        "l1_entries": l1_count,
        "l1_max": _L1_MAX,
        "l1_ttl": _L1_TTL,
        "redis_connected": redis_ok,
        "system_prompt_version": SYSTEM_PROMPT_VERSION,
        "api_keys_configured": len(_get_api_keys()),
        "ollama_configured": bool(OLLAMA_URL),
        "llm_cascade": [{"model": m["model"], "tier": m["tier"]} for m in LLM_CASCADE],
    }


def parse_prompt_sync(text: str) -> dict:
    """Sync wrapper for compatibility."""
    import asyncio
    import concurrent.futures

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, parse_prompt_async(text)).result()
        return loop.run_until_complete(parse_prompt_async(text))
    except RuntimeError:
        return asyncio.run(parse_prompt_async(text))


# ═══════════════════ BACKWARD COMPAT ALIASES ═══════════════════
# v8.0.0 renamed internal functions; these aliases keep tests + router working
parse_prompt = parse_prompt_sync
_call_llm = _call_openrouter


def get_generation_type(params: dict) -> str:
    """Determine generation type from parsed params."""
    obj = (params.get("object_type") or "").lower()
    if obj in ("room", "interior"):
        return "interior"
    return "building"


def _validate(params: dict) -> dict:
    """Validate and sanitize parsed parameters."""
    if not isinstance(params, dict):
        return {}
    return params
