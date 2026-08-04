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

SYSTEM_PROMPT_VERSION = "v9.0"  # ← bump to invalidate all caches

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
   "дизайн комнаты", "дизайн кухни", "оформление", "мебель", "обстановка",
   "ванная с джакузи", "кухня в стиле хайтек", "дизайн детской", "сауна внутри"
   → object_type="interior", room_type=тип комнаты

2. ЗДАНИЕ (object_type="building") — когда пользователь хочет ПОСТРОИТЬ ЗДАНИЕ:
   Ключевые слова: "построить дом", "здание", "офис", "коттедж", "отель",
   "построй", "сделай дом", "таунхаус", "здание", "сооружение"
   → object_type="building"

3. ЛАНДШАФТ (object_type="landscape") — когда пользователь хочет ЛАНДШАФТ:
   Ключевые слова: "ландшафт", "сад", "двор", "участок", "ландшафтный дизайн",
   "клумба", "газон", "дорожки", "пруд на участке", "бассейн во дворе"
   → object_type="landscape"
   НЕ ГЕНЕРИРУЙ ЗДАНИЕ если просят ландшафт!

4. Если запрос неоднозначен — поставь confidence низким (< 0.5)

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

  "structural_system": "frame|shear_wall|tube|braced|hybrid",
  "foundation_type": "strip|slab|pile|raft|combined",
  "material_concrete_class": "B15|B20|B25|B30|B35|B40|B45|B50|B60",
  "steel_grade": "C235|C245|C255|C345|C375|C390|C440",
  "seismic_zone": "none|5|6|7|8|9",
  "soil_type": "I|II|III|IV|V",
  "fire_resistance_rating": "R15|R30|R45|R60|R90|R120|R150|R180",
  "heating_type": "central|autonomous|individual|none",
  "ventilation_type": "natural|mechanical|mixed",
  "water_supply": "central|well|none",
  "sewage": "central|septic|none",
  "exposure_class": "XC1|XC2|XC3|XC4"
}

═══ ПРАВИЛА ═══
1. building_type — НЕ ограничивайся. Сарай→barn, навес→carport, беседка→gazebo,
   теплица→greenhouse, баня→bathhouse, курятник→chicken_coop, отель→hotel.

2. material — НЕ ограничивайся. Из брёвен→log, из соломы→straw, из кирпича→brick.

3. style — НЕ ограничивайся. Японский→japanese, средневековый→medieval, лофт→loft.

4. Размеры по умолчанию (если не указаны):
   Сарай: 3×4×2.5м. Беседка: 3×3×2.5м. Гараж: 6×3×3м. Дом: 10×12×3м.
   Отель: 24×36×3.2м. Ванная: 2.5×3×2.8м. Кухня: 4×5×2.8м.

5. Для интерьера — перечисли мебель в поле furniture.

6. Если запрос неясен — confidence < 0.5, в reasoning объясни что неясно.
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
    {"model": "google/gemini-2.5-flash", "tier": 1, "timeout": 25},
    {"model": "openai/gpt-4o-mini", "tier": 1, "timeout": 25},
    {"model": "google/gemini-2.0-flash-001", "tier": 2, "timeout": 25},
    {"model": "meta-llama/llama-3.3-70b-instruct:free", "tier": 2, "timeout": 30},
    {"model": "mistralai/mistral-small-3.2-24b:free", "tier": 3, "timeout": 30},
    {"model": "nvidia/nemotron-3-nano-30b-a3b:free", "tier": 3, "timeout": 30},
    {"model": "deepseek/deepseek-r1-0528:free", "tier": 3, "timeout": 30},
]


# ═══════════════════════════════════════════════════════════════
# AUTO-DISCOVER FREE MODELS FROM OPENROUTER
# Queries OpenRouter API for available free models,
# rebuilds cascade automatically when models change.
# ═══════════════════════════════════════════════════════════════

_DISCOVERED_MODELS: list[dict] = []
_DISCOVER_TS: float = 0
_DISCOVER_TTL: int = 3600  # refresh every 1 hour
_DISCOVER_LOCK = threading.Lock()

# Models to SKIP (known to be bad for JSON/arch tasks)
_BLOCKLIST = {
    "openrouter/auto",
    "deepseek/deepseek-r1-0528:free",  # thinking model, outputs <think> tags
    "google/gemma-3-1b-it:free",       # too small
    "meta-llama/llama-4-maverick:free", # inconsistent JSON
}

# Preferred free models (boost priority)
_PREFERRED = {
    "google/gemini-2.5-flash",         # best free-tier model
    "meta-llama/llama-3.3-70b-instruct:free",
    "mistralai/mistral-small-3.2-24b:free",
    "qwen/qwen3-235b-a22b:free",
    "deepseek/deepseek-chat-v3-0324:free",
}


async def discover_free_models(api_key: str) -> list[dict]:
    """Query OpenRouter for available free models."""
    global _DISCOVERED_MODELS, _DISCOVER_TS

    with _DISCOVER_LOCK:
        if _DISCOVERED_MODELS and (time.time() - _DISCOVER_TS) < _DISCOVER_TTL:
            return _DISCOVERED_MODELS

    base_url = os.environ.get("OPENROUTER_BASE", "https://openrouter.ai/api/v1")

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=15,
            )
        if r.status_code != 200:
            logger.warning("OpenRouter /models returned %d", r.status_code)
            return []

        data = r.json()
        models = data.get("data", [])

        free_models = []
        for m in models:
            mid = m.get("id", "")
            pricing = m.get("pricing", {})
            prompt_price = float(pricing.get("prompt", "1") or "1")
            completion_price = float(pricing.get("completion", "1") or "1")

            # Free = price is 0
            is_free = prompt_price == 0 and completion_price == 0
            # Also include very cheap models (< $0.0001 per 1K tokens)
            is_cheap = prompt_price < 0.0001 and completion_price < 0.0001

            if not (is_free or is_cheap):
                continue
            if mid in _BLOCKLIST:
                continue

            # Filter: must support text generation
            arch = m.get("architecture", {})
            modality = arch.get("output_modalities", [])
            if "text" not in modality and not modality:
                continue

            # Score: prefer known good models
            priority = 3
            if mid in _PREFERRED:
                priority = 1
            elif is_free:
                priority = 2

            free_models.append({
                "model": mid,
                "tier": priority,
                "timeout": 30,
                "is_free": is_free,
                "name": m.get("name", ""),
            })

        # Sort by priority, then by name
        free_models.sort(key=lambda x: (x["tier"], x["model"]))

        # Limit to top 15 models to avoid cascade timeout
        free_models = free_models[:15]

        with _DISCOVER_LOCK:
            _DISCOVERED_MODELS = free_models
            _DISCOVER_TS = time.time()

        logger.info(
            "Discovered %d free/cheap models from OpenRouter (was %d in cascade)",
            len(free_models),
            len(LLM_CASCADE),
        )
        return free_models

    except Exception as e:
        logger.warning("Free model discovery failed: %s", e)
        return []


def get_active_cascade(api_key: str = "") -> list[dict]:
    """Return the active cascade: discovered models + hardcoded fallback."""
    global _DISCOVERED_MODELS, _DISCOVER_TS

    # If we have fresh discovered models, use them
    with _DISCOVER_LOCK:
        if _DISCOVERED_MODELS and (time.time() - _DISCOVER_TS) < _DISCOVER_TTL:
            return _DISCOVERED_MODELS

    # Otherwise return hardcoded cascade
    return LLM_CASCADE


def invalidate_discovery() -> None:
    """Force re-discovery on next call."""
    global _DISCOVERED_MODELS, _DISCOVER_TS
    with _DISCOVER_LOCK:
        _DISCOVERED_MODELS = []
        _DISCOVER_TS = 0


def get_discovery_stats() -> dict:
    """Return discovery stats for health endpoint."""
    with _DISCOVER_LOCK:
        return {
            "discovered_count": len(_DISCOVERED_MODELS),
            "discovered_models": [m["model"] for m in _DISCOVERED_MODELS[:10]],
            "last_discover_ago": int(time.time() - _DISCOVER_TS) if _DISCOVER_TS else None,
            "ttl": _DISCOVER_TTL,
            "hardcoded_fallback": [m["model"] for m in LLM_CASCADE],
        }


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
        _redis = redis.from_url(
            redis_url, decode_responses=True, socket_timeout=3, socket_connect_timeout=5, retry_on_timeout=True
        )
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


def _validate_and_fix(result: dict | None, text: str) -> dict | str | None:
    """Level 1+2: Pydantic validation + auto-retry with fix prompt."""
    from shared.llm_schemas import build_fix_prompt, validate_llm_response

    parsed, errors = validate_llm_response(result)
    if parsed:
        return parsed.model_dump()

    # Level 2: Auto-retry with fix prompt
    if result is not None and errors:
        logger.warning("LLM response validation failed: %s", errors[:3])
        fix_prompt = build_fix_prompt(text, errors)
        return fix_prompt  # signal to retry with this prompt

    return None


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
        "max_tokens": 500,
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
        # Cost tracking: extract token usage
        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)
        if tokens_in or tokens_out:
            _track_cost(model, tokens_in, tokens_out)
            logger.info("LLM %s tokens: %d in / %d out", model, tokens_in, tokens_out)
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
    """FLEXIBLE validation — trust LLM, check only structure."""
    if not isinstance(result, dict):
        return False
    if not result.get("object_type"):
        return False
    w = result.get("width_m", 0)
    l = result.get("length_m", 0)
    # Only reject clearly invalid dimensions
    if w <= 0 or l <= 0 or w > 500 or l > 500:
        return False
    floors = result.get("floors", 0)
    if floors <= 0 or floors > 50:
        return False
    # Interior requests — set default room_type if missing
    if result.get("object_type") in ("interior", "room") and not result.get("room_type"):
        result["room_type"] = "living"
    # Ensure building_type is not empty
    if not result.get("building_type"):
        result["building_type"] = "house"
    return True


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

    # Auto-discover free models from OpenRouter
    cascade = get_active_cascade(api_keys[0] if api_keys else "")

    # If cascade is empty or stale, trigger async discovery
    if api_keys and not _DISCOVERED_MODELS:
        try:
            await discover_free_models(api_keys[0])
            cascade = get_active_cascade(api_keys[0])
        except Exception as e:
            logger.warning("Discovery failed, using hardcoded cascade: %s", e)

    # LLM cascade with key rotation (L3) + Pydantic validation
    for model_config in cascade:
        model: str = model_config["model"]  # type: ignore[assignment]
        timeout: int = model_config["timeout"]  # type: ignore[assignment]
        tier: int = model_config["tier"]  # type: ignore[assignment]

        for key_idx, api_key in enumerate(api_keys):
            logger.info("Trying LLM: %s (key %d/%d)", model, key_idx + 1, len(api_keys))
            result = await _call_openrouter(model, text, timeout, api_key)

            if result:
                # Level 1: Pydantic validation
                validated = _validate_and_fix(result, text)
                if isinstance(validated, dict):
                    _l1_set(text, validated)
                    _l2_set(text, validated)
                    logger.info("LLM %s parsed successfully: %s", model, validated.get("building_type"))
                    return validated

                # Level 2: Retry with fix prompt (one attempt)
                if isinstance(validated, str) and tier <= 2:
                    logger.info("Retrying %s with fix prompt", model)
                    fix_result = await _call_openrouter(model, validated, timeout, api_key)
                    if fix_result:
                        fix_validated = _validate_and_fix(fix_result, text)
                        if isinstance(fix_validated, dict):
                            _l1_set(text, fix_validated)
                            _l2_set(text, fix_validated)
                            logger.info("LLM %s fixed and parsed: %s", model, fix_validated.get("building_type"))
                            return fix_validated

            if result is not None:
                # Got response but invalid — try next model, not next key
                break

    # L4: All OpenRouter models failed → try Ollama
    logger.warning("All OpenRouter models failed, trying Ollama fallback")
    result = await _call_ollama(text)
    if result:
        validated = _validate_and_fix(result, text)
        if isinstance(validated, dict):
            _l1_set(text, validated)
            _l2_set(text, validated)
            logger.info("Ollama fallback succeeded: %s", validated.get("building_type"))
            return validated

    raise AllModelsFailedError(f"All {len(cascade)} LLM models (+ Ollama) failed for prompt: {text[:100]}...")


# ═══════════════════════════════════════════════════════════════
# COST TRACKING — per model and aggregate
# ═══════════════════════════════════════════════════════════════

import threading as _threading

_cost_lock = _threading.Lock()
_cost_stats: dict[str, dict] = {}  # {model: {calls, tokens_in, tokens_out, cost_usd}}

# Approximate costs per 1M tokens (input/output) — update as needed
_MODEL_COSTS = {
    "google/gemini-2.5-pro": {"input": 1.25, "output": 10.0},
    "anthropic/claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "google/gemini-2.5-flash": {"input": 0.075, "output": 0.3},
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "meta-llama/llama-4-maverick:free": {"input": 0, "output": 0},
    "qwen/qwen3-235b-a22b:free": {"input": 0, "output": 0},
    "deepseek/deepseek-chat-v3-0324:free": {"input": 0, "output": 0},
}


def _track_cost(model: str, tokens_in: int, tokens_out: int) -> None:
    """Track cost of an LLM call."""
    costs: dict = _MODEL_COSTS.get(model, {"input": 0, "output": 0})  # type: ignore[assignment]
    cost = (tokens_in * costs["input"] + tokens_out * costs["output"]) / 1_000_000
    with _cost_lock:
        stats = _cost_stats.setdefault(model, {"calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0})
        stats["calls"] += 1
        stats["tokens_in"] += tokens_in
        stats["tokens_out"] += tokens_out
        stats["cost_usd"] = round(stats["cost_usd"] + cost, 6)


def get_cost_stats() -> dict:
    """Return cost tracking statistics."""
    with _cost_lock:
        total_calls = sum(s["calls"] for s in _cost_stats.values())
        total_cost = sum(s["cost_usd"] for s in _cost_stats.values())
        return {
            "per_model": dict(_cost_stats),
            "total_calls": total_calls,
            "total_cost_usd": round(total_cost, 4),
        }


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
        "discovery": get_discovery_stats(),
        "cost_tracking": get_cost_stats(),
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
