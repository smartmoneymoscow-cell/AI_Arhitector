"""
llm-service/parser_flexible.py — FLEXIBLE LLM parsing with all fixes applied.

═══════════════════════════════════════════════════════════════
  СТРОГОЕ ПРАВИЛО: Парсер РАБОТАЕТ ТОЛЬКО ЧЕРЕЗ LLM.
  Никаких regex fallback, хардкода, локальных парсеров.
  Если все LLM ключи упали → AllModelsFailedError.
  НИКОГДА не добавлять regex/local fallback в этот модуль.
═══════════════════════════════════════════════════════════════

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
  "suggestions": ["подсказка1", "подсказка2", "подсказка3"],
  "references": ["ключевое_слово1", "ключевое_слово2"],
  "decomposition": [{"name":"Этап","description":"что делаем"}],
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

7. reasoning — кратко почему решил именно так (2-3 предложения).

8. suggestions — массив 3-5 строк-подсказок для развития проекта. Релевантны промту.
   Для ванной: ["Добавить банные принадлежности", "Выбрать плитку", "Добавить полотенцесушитель"].
   Для детской: ["Добавить игрушки", "Выбрать обои", "Добавить ночник"].

9. references — массив 2-4 ключевых слов для поиска референсов.
   Для ванной хайтек: ["ванная хайтек дизайн", "джакузи интерьер"].

10. decomposition — массив этапов: [{"name":"Название","description":"что делаем"}].
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
# KEY HEALTH TRACKER — единый реестр "остывания" ключей
# (общий для Gemini и OpenRouter, ключи различаются по префиксу,
#  так что коллизий между провайдерами не будет).
#
# Логика:
#   - RPM-лимит (429 без признаков дневной квоты)         → короткий cooldown (по умолчанию 60с)
#   - Дневная квота / нет кредитов (402, "quota", "RESOURCE_EXHAUSTED") → длинный cooldown (по умолчанию 24ч)
#   - Ключ помечается "мёртвым" сразу после ошибки и исключается
#     из перебора в ЭТОМ и ВСЕХ СЛЕДУЮЩИХ запросах, пока не остынет.
#   - Опционально дублируется в Redis, чтобы cooldown переживал
#     рестарт/передеплой сервиса (важно на Render — контейнер часто
#     пересоздаётся, а in-memory состояние теряется).
# ═══════════════════════════════════════════════════════════════

_KEY_COOLDOWN: dict[str, float] = {}          # key -> unix ts, до которого ключ не трогаем
_KEY_COOLDOWN_LOCK = threading.Lock()

_COOLDOWN_RATE_LIMIT = int(os.environ.get("KEY_COOLDOWN_RATE_LIMIT_SEC", "60"))
_COOLDOWN_QUOTA_EXHAUSTED = int(os.environ.get("KEY_COOLDOWN_QUOTA_SEC", str(24 * 3600)))


def _mask_key(key: str) -> str:
    if len(key) <= 10:
        return "***"
    return f"{key[:6]}…{key[-4:]}"


def _key_redis_field(key: str) -> str:
    return f"keycd:{hashlib.sha256(key.encode()).hexdigest()[:16]}"


def _is_key_cooling(key: str) -> bool:
    """True если ключ сейчас 'остывает' и его нужно пропустить."""
    now = time.time()
    with _KEY_COOLDOWN_LOCK:
        until = _KEY_COOLDOWN.get(key)
    if until and now < until:
        return True
    # Проверяем Redis (переживает рестарт процесса)
    r = _get_redis()
    if r is not None:
        try:
            raw = r.get(_key_redis_field(key))
            if raw and now < float(raw):
                return True
        except Exception:
            pass
    return False


def _mark_key_dead(key: str, seconds: int, reason: str) -> None:
    """Помечает ключ как исчерпанный на `seconds` секунд."""
    until = time.time() + seconds
    with _KEY_COOLDOWN_LOCK:
        _KEY_COOLDOWN[key] = until
    r = _get_redis()
    if r is not None:
        try:
            r.setex(_key_redis_field(key), seconds, str(until))
        except Exception:
            pass
    logger.warning(
        "Key %s marked EXHAUSTED (%s) for %ds (until %s)",
        _mask_key(key), reason, seconds, time.strftime("%H:%M:%S", time.localtime(until)),
    )


def _filter_alive(keys: list[str]) -> list[str]:
    """Возвращает ключи, которые сейчас не 'остывают'.
    Если ВСЕ ключи остывают — возвращает исходный список целиком
    (лучше попробовать 'протухший' ключ, чем не пробовать вообще)."""
    alive = [k for k in keys if not _is_key_cooling(k)]
    return alive if alive else keys


def _looks_like_quota_exhausted(status_code: int, body: str) -> bool:
    """Отличает 'подожди немного' (RPM) от 'на сегодня всё' (дневная квота/нет денег)."""
    if status_code == 402:
        return True
    low = (body or "").lower()
    return any(s in low for s in (
        "resource_exhausted", "quota", "insufficient_quota", "daily limit", "no credits",
    ))


# ═══════════════════════════════════════════════════════════════
# L4: OLLAMA LOCAL FALLBACK
# ═══════════════════════════════════════════════════════════════

OLLAMA_URL = os.environ.get("OLLAMA_URL", "")  # e.g. "http://host.docker.internal:11434"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")


# ═══════════════════════════════════════════════════════════════
# LLM CASCADE
# ═══════════════════════════════════════════════════════════════

LLM_CASCADE = [
    {"model": "google/gemma-4-26b-a4b-it:free", "tier": 1, "timeout": 30},
    {"model": "google/gemma-4-31b-it:free", "tier": 1, "timeout": 30},
    {"model": "nvidia/nemotron-3-ultra-550b-a55b:free", "tier": 1, "timeout": 30},
    {"model": "openai/gpt-oss-20b:free", "tier": 1, "timeout": 30},
    {"model": "nvidia/nemotron-3-super-120b-a12b:free", "tier": 2, "timeout": 30},
    {"model": "nvidia/nemotron-3-nano-30b-a3b:free", "tier": 2, "timeout": 30},
    {"model": "poolside/laguna-s-2.1:free", "tier": 2, "timeout": 30},
    {"model": "cohere/north-mini-code:free", "tier": 3, "timeout": 30},
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
    "openrouter/free",
    "deepseek/deepseek-r1-0528:free",  # thinking model, outputs <think> tags
    "nvidia/nemotron-3.5-content-safety:free",  # safety model, not text gen
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",  # reasoning, slow
    "nvidia/nemotron-nano-12b-v2-vl:free",  # vision-language
    "nvidia/nemotron-nano-9b-v2:free",  # too small
    "inclusionai/ling-3.0-flash:free",  # inconsistent JSON
    "inclusionai/ling-3.0-tiny:free",  # returns None
    "google/lyria-3-clip-preview",  # music model
    "google/lyria-3-pro-preview",  # music model
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
    """Query OpenRouter for available free models. Persists to Redis so
    the freshly discovered list is shared across all worker processes /
    service restarts, not just kept in this process's memory."""
    global _DISCOVERED_MODELS, _DISCOVER_TS

    with _DISCOVER_LOCK:
        if _DISCOVERED_MODELS and (time.time() - _DISCOVER_TS) < _DISCOVER_TTL:
            return _DISCOVERED_MODELS

    base_url = os.environ.get("OPENROUTER_BASE", "https://openrouter.ai/api/v1")

    try:
        # FIX: stream + body size limit — на Render free tier огромный JSON (400+ моделей
        # с бенчмарками) вызывает зависание httpx при чтении ответа. Стриминг с лимитом
        # предотвращает это и даёт predictablый timeout.
        _MAX_BODY_BYTES = 2 * 1024 * 1024  # 2 MB
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "GET",
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=httpx.Timeout(connect=5, read=10, write=5, pool=5),
            ) as r:
                if r.status_code != 200:
                    await r.aread()
                    logger.warning("OpenRouter /models returned %d", r.status_code)
                    return []
                body = b""
                async for chunk in r.aiter_bytes(chunk_size=65536):
                    body += chunk
                    if len(body) > _MAX_BODY_BYTES:
                        logger.warning("OpenRouter /models response too large (%d bytes), truncating", len(body))
                        break

        data = json.loads(body.decode("utf-8", errors="replace"))
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

            # Filter: skip models that are clearly not for text generation
            mid_lower = mid.lower()
            skip_keywords = ["lyria", "imagen", "dall-e", "stable-diffusion", "midjourney", "tts", "whisper", "embed", "rerank", "content-safety"]
            if any(kw in mid_lower for kw in skip_keywords):
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

        if not free_models:
            # OpenRouter вернул 200, но НИ ОДНОЙ подходящей бесплатной модели —
            # не затираем предыдущий рабочий список (вдруг это временный глюк API).
            logger.warning("OpenRouter /models returned 0 usable free models — keeping previous cascade")
            return _DISCOVERED_MODELS

        with _DISCOVER_LOCK:
            _DISCOVERED_MODELS = free_models
            _DISCOVER_TS = time.time()

        # Персистим в Redis, чтобы остальные воркеры/инстансы не долбили
        # /models каждый по отдельности и переживали рестарт процесса.
        _save_discovery_to_redis(free_models, _DISCOVER_TS)

        logger.info(
            "Discovered %d free/cheap models from OpenRouter (was %d in cascade): %s",
            len(free_models),
            len(LLM_CASCADE),
            [m["model"] for m in free_models[:5]],
        )
        return free_models

    except Exception as e:
        logger.warning("Free model discovery failed: %s", e)
        return []


_DISCOVERY_REDIS_KEY = "or:discovered_models:v1"


def _save_discovery_to_redis(models: list[dict], ts: float) -> None:
    r = _get_redis()
    if r is None:
        return
    try:
        r.setex(_DISCOVERY_REDIS_KEY, _DISCOVER_TTL * 6, json.dumps({"models": models, "ts": ts}))
    except Exception:
        pass


def _load_discovery_from_redis() -> tuple[list[dict], float] | None:
    """Читает список, обнаруженный ДРУГИМ воркером/процессом, если он свежее нашего."""
    r = _get_redis()
    if r is None:
        return None
    try:
        raw = r.get(_DISCOVERY_REDIS_KEY)
        if not raw:
            return None
        data = json.loads(raw)
        return data.get("models") or [], float(data.get("ts") or 0)
    except Exception:
        return None


def _cascade_is_stale() -> bool:
    with _DISCOVER_LOCK:
        return (not _DISCOVERED_MODELS) or (time.time() - _DISCOVER_TS) >= _DISCOVER_TTL


def get_active_cascade(api_key: str = "") -> list[dict]:
    """Return the active cascade: discovered models (preferred, even if
    slightly stale) > another worker's fresher Redis snapshot > hardcoded
    fallback (only if we've NEVER discovered anything, e.g. cold start
    with OpenRouter unreachable)."""
    global _DISCOVERED_MODELS, _DISCOVER_TS

    with _DISCOVER_LOCK:
        have_local = bool(_DISCOVERED_MODELS)
        local_fresh = have_local and (time.time() - _DISCOVER_TS) < _DISCOVER_TTL

    if local_fresh:
        return _DISCOVERED_MODELS

    # Наш локальный список устарел (или его ещё нет) — проверяем,
    # не обновил ли его уже другой воркер через Redis.
    remote = _load_discovery_from_redis()
    if remote:
        remote_models, remote_ts = remote
        if remote_models and remote_ts > _DISCOVER_TS:
            with _DISCOVER_LOCK:
                _DISCOVERED_MODELS = remote_models
                _DISCOVER_TS = remote_ts
            if (time.time() - remote_ts) < _DISCOVER_TTL:
                return remote_models
            have_local = True  # remote тоже устарел, но лучше, чем совсем ничего

    # Отдаём то, что есть (пусть и не первой свежести) — свежий список
    # реальных free-моделей лучше жёстко зашитого хардкода. Обновление
    # запустится отдельно (см. _maybe_trigger_discovery ниже).
    if have_local:
        return _DISCOVERED_MODELS

    # Совсем ничего не находили ни разу — последний резерв.
    return LLM_CASCADE


async def _maybe_trigger_discovery(api_key: str) -> None:
    """Вызывать перед каждым обращением к каскаду: если список устарел —
    обновляет его (не блокируя надолго, TTL/models запрос лёгкий)."""
    if not api_key:
        return
    if _cascade_is_stale():
        try:
            await discover_free_models(api_key)
        except Exception as e:
            logger.warning("Discovery refresh failed, keeping current cascade: %s", e)


def invalidate_discovery() -> None:
    """Force re-discovery on next call."""
    global _DISCOVERED_MODELS, _DISCOVER_TS
    with _DISCOVER_LOCK:
        _DISCOVERED_MODELS = []
        _DISCOVER_TS = 0
    r = _get_redis()
    if r is not None:
        try:
            r.delete(_DISCOVERY_REDIS_KEY)
        except Exception:
            pass


def get_discovery_stats() -> dict:
    """Return discovery stats for health endpoint."""
    with _DISCOVER_LOCK:
        return {
            "discovered_count": len(_DISCOVERED_MODELS),
            "discovered_models": [m["model"] for m in _DISCOVERED_MODELS[:10]],
            "last_discover_ago": int(time.time() - _DISCOVER_TS) if _DISCOVER_TS else None,
            "ttl": _DISCOVER_TTL,
            "is_stale": _cascade_is_stale(),
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
_redis_unavailable_until = 0.0  # unix ts; while now < this, skip retrying connection
_REDIS_RETRY_COOLDOWN_SEC = 30  # how long to wait before trying again after a failed connect


def _get_redis():
    global _redis, _redis_unavailable_until
    now = time.time()
    if now < _redis_unavailable_until:
        # We already know Redis is unreachable — don't pay a fresh connect
        # attempt (up to socket_connect_timeout=5s) on every single call.
        return None
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
        _redis_unavailable_until = now + _REDIS_RETRY_COOLDOWN_SEC
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
    """All LLM models failed.

    ═══════ СТРОГОЕ ПРАВИЛО ═══════
    Это единственный допустимый ответ при недоступности LLM.
    НИКОГДА не добавлять regex/local fallback вместо этого исключения.
    Парсер работает ТОЛЬКО через LLM (Gemini / OpenRouter / Ollama).
    ════════════════════════════════
    """
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


async def _call_openrouter(
    model: str, prompt: str, timeout: int, api_key: str
) -> tuple[dict | None, int | None, str]:
    """Call a single LLM model via OpenRouter with given key.

    Returns (parsed_json_or_None, http_status_or_None, raw_body_snippet).
    Caller uses status/body to decide whether the KEY is exhausted
    (→ cooldown + switch account) vs the MODEL is just bad for this prompt.
    """
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
        "max_tokens": 800,
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
            logger.warning("LLM %s rate-limited (key %s), trying next key/model", model, _mask_key(api_key))
            return None, 429, r.text[:300]

        if r.status_code == 402:
            logger.error("LLM %s: 402 — key %s has no credits", model, _mask_key(api_key))
            return None, 402, r.text[:300]

        if r.status_code != 200:
            logger.warning("LLM %s returned %d: %s", model, r.status_code, r.text[:200])
            return None, r.status_code, r.text[:300]

        data = r.json()
        # Cost tracking: extract token usage
        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)
        if tokens_in or tokens_out:
            _track_cost(model, tokens_in, tokens_out)
            logger.info("LLM %s tokens: %d in / %d out", model, tokens_in, tokens_out)
        content = data["choices"][0]["message"]["content"]
        return _extract_json(content), 200, ""

    except httpx.TimeoutException:
        logger.warning("LLM %s timeout (%ds)", model, timeout)
        return None, None, "timeout"
    except Exception as e:
        logger.warning("LLM %s error: %s", model, e)
        return None, None, str(e)


def _get_google_keys() -> list[str]:
    """Get all Google API keys (primary + fallbacks)."""
    keys = []
    primary = os.environ.get("GOOGLE_API_KEY", "")
    if primary:
        keys.append(primary)
    fallback = os.environ.get("GOOGLE_FALLBACK_KEYS", "")
    if fallback:
        for k in fallback.split(","):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)
    return keys


_GEMINI_KEY_IDX = 0
_OR_KEY_IDX = 0  # round-robin для OpenRouter ключей


async def _call_gemini(prompt: str, timeout: int = 30) -> dict | None:
    """Call Google Gemini API — БЕСПЛАТНО (free tier, 15 RPM per key).

    Перебирает ВСЕ живые (не остывающие) Gemini-ключи по кругу, начиная
    со следующего после последнего использованного (round-robin), а не
    ограничивается фиксированным числом попыток — раньше при 4 ключах и
    max_retries=3 четвёртый ключ вообще никогда не пробовался.
    Каждый исчерпанный ключ помечается через _mark_key_dead и пропускается
    во всех следующих запросах, пока не остынет.
    """
    global _GEMINI_KEY_IDX
    all_keys = _get_google_keys()
    if not all_keys:
        logger.warning("Gemini: NO GOOGLE_API_KEY configured!")
        return None

    keys = _filter_alive(all_keys)
    if not keys:
        logger.warning("Gemini: all %d keys are cooling down, skipping to OpenRouter", len(all_keys))
        return None

    payload = {
        "system_instruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "contents": [
            {"parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 2048,
            "responseMimeType": "application/json"
        }
    }

    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
    # Fallback models if primary is deleted (404)
    _GEMINI_MODELS = [
        model_name,
        "gemini-flash-lite-latest",
        "gemini-2.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash-lite",
    ]
    # Deduplicate while preserving order
    seen = set()
    _GEMINI_MODELS = [m for m in _GEMINI_MODELS if not (m in seen or seen.add(m))]

    _model_404: set[str] = set()  # модели, которые вернули404

    # Пробуем КАЖДЫЙ живой ключ ровно один раз (round-robin), а не только 3.
    for attempt in range(len(keys)):
        key = keys[_GEMINI_KEY_IDX % len(keys)]
        _GEMINI_KEY_IDX = (_GEMINI_KEY_IDX + 1) % len(keys)

        # Выбираем модель: primary → fallbacks, пропускаем 404
        chosen_model = None
        for m in _GEMINI_MODELS:
            if m not in _model_404:
                chosen_model = m
                break
        if not chosen_model:
            logger.error("Gemini: all models returned 404, giving up")
            return None

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{chosen_model}:generateContent"

        try:
            async with httpx.AsyncClient() as client:
                # FIX: пробуем x-goog-api-key (AIza) И Authorization: Bearer (AQ.Ab)
                r = None
                for auth_headers in [
                    {"x-goog-api-key": key},
                    {"Authorization": f"Bearer {key}"},
                ]:
                    try:
                        r = await client.post(
                            url, json=payload,
                            headers=auth_headers,
                            timeout=timeout,
                        )
                        if r.status_code != 401:
                            break
                        # Проверяем reason
                        try:
                            reason = r.json().get("error", {}).get("details", [{}])[0].get("reason", "")
                        except Exception:
                            reason = ""
                        if reason == "API_KEY_SERVICE_BLOCKED":
                            break  # Не пробуем второй header — проблема в проекте
                    except Exception:
                        continue

            if r.status_code == 404:
                # Модель удалена — пробуем следующую модель, ключ НЕ наказываем
                _model_404.add(chosen_model)
                logger.warning("Gemini model %s deleted (404), trying next model", chosen_model)
                continue

            if r.status_code == 401:
                try:
                    _reason = r.json().get("error", {}).get("details", [{}])[0].get("reason", "")
                except Exception:
                    _reason = ""
                if _reason == "API_KEY_SERVICE_BLOCKED":
                    logger.error(
                        "Gemini API BLOCKED (key %s). Enable 'Generative Language API' in Google Cloud Console. "
                        "All keys from same project — skipping Gemini entirely.",
                        _mask_key(key),
                    )
                    return None  # Все ключи из одного проекта — быстрый fail
                _mark_key_dead(key, _COOLDOWN_QUOTA_EXHAUSTED, "gemini_401_invalid")
                logger.warning(
                    "Gemini key %s invalid (401, reason=%s). Check https://aistudio.google.com/apikey",
                    _mask_key(key), _reason,
                )
                continue

            if r.status_code == 429:
                body = r.text[:300]
                if _looks_like_quota_exhausted(429, body):
                    _mark_key_dead(key, _COOLDOWN_QUOTA_EXHAUSTED, "gemini_quota_exhausted")
                else:
                    _mark_key_dead(key, _COOLDOWN_RATE_LIMIT, "gemini_rpm_limit")
                logger.warning(
                    "Gemini rate-limited (key %d/%d) — switching to next account", attempt + 1, len(keys)
                )
                continue

            if r.status_code in (400, 403):
                _mark_key_dead(key, _COOLDOWN_QUOTA_EXHAUSTED, f"gemini_http_{r.status_code}")
                logger.error("Gemini key invalid/blocked (%d): %s", r.status_code, r.text[:300])
                continue

            if r.status_code != 200:
                logger.error("Gemini FAILED %d (key %d/%d): %s", r.status_code, attempt + 1, len(keys), r.text[:300])
                continue

            data = r.json()
            content = data["candidates"][0]["content"]["parts"][0]["text"]
            return _extract_json(content)

        except httpx.TimeoutException:
            logger.warning("Gemini timeout (%ds) on key %d/%d", timeout, attempt + 1, len(keys))
            continue
        except Exception as e:
            logger.warning("Gemini error on key %d/%d: %s", attempt + 1, len(keys), e)
            continue

    logger.error("Gemini: all %d live keys failed (of %d total)", len(keys), len(all_keys))
    return None




# ═══════════════════════════════════════════════════════════════
# DEEPSEEK DIRECT API — fallback между Gemini и OpenRouter
# ═══════════════════════════════════════════════════════════════

def _get_deepseek_keys() -> list[str]:
    """Get DeepSeek API keys from environment."""
    keys = []
    primary = os.environ.get("DEEPSEEK_API_KEY", "")
    if primary:
        keys.append(primary)
    fallback = os.environ.get("DEEPSEEK_FALLBACK_KEYS", "")
    if fallback:
        for k in fallback.split(","):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)
    return keys


async def _call_deepseek(prompt: str, timeout: int = 30) -> dict | None:
    """Call DeepSeek API directly as fallback between Gemini and OpenRouter."""
    keys = _get_deepseek_keys()
    if not keys:
        return None

    import json as _json

    for key in keys:
        masked = _mask_key(key)
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    "https://api.deepseek.com/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={
                        "model": "deepseek-chat",
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 1024,
                        "temperature": 0.1,
                    },
                    timeout=timeout,
                )

            if r.status_code == 200:
                content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                try:
                    return _json.loads(content)
                except _json.JSONDecodeError:
                    import re
                    match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
                    if match:
                        return _json.loads(match.group())
                    logger.warning("DeepSeek: could not extract JSON from response")
                    continue
            elif r.status_code == 402:
                logger.warning("DeepSeek key %s: insufficient balance", masked)
            elif r.status_code == 401:
                logger.warning("DeepSeek key %s: invalid", masked)
            else:
                logger.warning("DeepSeek key %s: HTTP %d", masked, r.status_code)
        except httpx.TimeoutException:
            logger.warning("DeepSeek timeout %ds", timeout)
        except Exception as e:
            logger.warning("DeepSeek error: %s", e)

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
                timeout=3,
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
    global _OR_KEY_IDX
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

    # ═══ 0. Google Gemini — БЕСПЛАТНО (пробуем ВСЕ живые ключи) ═══
    google_keys_all = _get_google_keys()
    or_keys_all = _get_api_keys()
    total_accounts = len(google_keys_all) + len(or_keys_all)
    logger.info(
        "Parse: key pool = %d Gemini + %d OpenRouter = %d accounts total (%d Gemini alive, %d OR alive)",
        len(google_keys_all), len(or_keys_all), total_accounts,
        len(_filter_alive(google_keys_all)), len(_filter_alive(or_keys_all)),
    )
    gemini_result = await _call_gemini(text)
    if gemini_result:
        validated = _validate_and_fix(gemini_result, text)
        if isinstance(validated, dict):
            _l1_set(text, validated)
            _l2_set(text, validated)
            logger.info("Gemini parsed successfully: %s", validated.get("building_type"))
            return validated

    # ═══ 0.5. DeepSeek — direct API (between Gemini and OpenRouter) ═══
    deepseek_result = await _call_deepseek(text)
    if deepseek_result:
        validated = _validate_and_fix(deepseek_result, text)
        if isinstance(validated, dict):
            _l1_set(text, validated)
            _l2_set(text, validated)
            logger.info("DeepSeek parsed: %s", validated.get("building_type"))
            return validated

    # L3: Get all available keys, skip ones currently cooling down
    api_keys = _filter_alive(_get_api_keys())
    if not api_keys:
        logger.error("No OPENROUTER_API_KEY configured")
        # L4: Try Ollama as last resort
        result = await _call_ollama(text)
        if result and _validate_result(result):
            _l1_set(text, result)
            _l2_set(text, result)
            return result
        raise AllModelsFailedError("No API keys configured and Ollama unavailable")

    # Auto-discover free models from OpenRouter (обновляем, если список устарел —
    # не только если он пуст; раньше после первого протухания TTL кэш молча
    # переставал обновляться и система навсегда откатывалась на хардкод).
    if api_keys:
        await _maybe_trigger_discovery(api_keys[0])
    cascade = get_active_cascade(api_keys[0] if api_keys else "")

    # LLM cascade with key rotation (L3) + Pydantic validation
    for model_config in cascade:
        model: str = model_config["model"]  # type: ignore[assignment]
        timeout: int = model_config["timeout"]  # type: ignore[assignment]
        tier: int = model_config["tier"]  # type: ignore[assignment]

        # Re-filter перед каждой моделью: за время предыдущих попыток
        # какие-то ключи могли только что "умереть".
        live_keys = _filter_alive(api_keys)
        model_removed = False

        # Round-robin: начинаем со следующего ключа
        for attempt in range(len(live_keys)):
            api_key = live_keys[_OR_KEY_IDX % len(live_keys)]
            _OR_KEY_IDX = (_OR_KEY_IDX + 1) % len(live_keys)
            key_idx = attempt
            logger.info("Trying LLM: %s (key %d/%d)", model, key_idx + 1, len(live_keys))
            result, status, body = await _call_openrouter(model, text, timeout, api_key)

            if status == 404:
                # OpenRouter больше не знает эту модель — её убрали из каталога.
                # Это проблема МОДЕЛИ, а не ключа: не наказываем ключ, а форсируем
                # обновление списка бесплатных моделей на следующий запрос и
                # сразу переходим к следующей модели в каскаде.
                logger.warning("Model %s no longer exists on OpenRouter (404) — invalidating discovery cache", model)
                invalidate_discovery()
                model_removed = True
                break

            if status in (429, 402) or (status is not None and status >= 500):
                if _looks_like_quota_exhausted(status, body):
                    _mark_key_dead(api_key, _COOLDOWN_QUOTA_EXHAUSTED, f"http_{status}_quota")
                else:
                    _mark_key_dead(api_key, _COOLDOWN_RATE_LIMIT, f"http_{status}_rate_limit")
                continue  # switch to next account automatically

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
                    fix_result, fix_status, fix_body = await _call_openrouter(model, validated, timeout, api_key)
                    if fix_status in (429, 402):
                        if _looks_like_quota_exhausted(fix_status, fix_body):
                            _mark_key_dead(api_key, _COOLDOWN_QUOTA_EXHAUSTED, f"http_{fix_status}_quota")
                        else:
                            _mark_key_dead(api_key, _COOLDOWN_RATE_LIMIT, f"http_{fix_status}_rate_limit")
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

        if model_removed:
            continue  # к следующей модели каскада

    # L4: All OpenRouter models failed → try Ollama
    logger.warning("All %d OR models failed (keys: %d). Trying Ollama...", len(cascade), len(api_keys))
    result = await _call_ollama(text)
    if result:
        validated = _validate_and_fix(result, text)
        if isinstance(validated, dict):
            _l1_set(text, validated)
            _l2_set(text, validated)
            logger.info("Ollama fallback succeeded: %s", validated.get("building_type"))
            return validated

    google_count = len(_get_google_keys())
    or_count = len(api_keys)
    raise AllModelsFailedError(
        f"All {len(cascade)} models failed. Google: {google_count}, OR: {or_count}. "
        f"FIX: Set GOOGLE_API_KEY in Render env. Prompt: {text[:80]}..."
    )


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


# ═══════════════════════════════════════════════════════════════
# PROACTIVE KEY HEALTH CHECK — фоновая проверка всех ключей
# Раз в _HEALTH_CHECK_INTERVAL секунд проходит по ВСЕМ ключам
# (Google + OpenRouter) через дешёвые эндпоинты, обновляет
# состояние cooldown в Redis. Если ключ восстановился — снимает
# cooldown раньше срока.
# ═══════════════════════════════════════════════════════════════

_HEALTH_CHECK_INTERVAL = int(os.environ.get("KEY_HEALTH_CHECK_INTERVAL_SEC", "1800"))


async def _check_openrouter_key_health(api_key: str) -> tuple[str, str]:
    """Проверка OpenRouter ключа через бесплатный /auth/key endpoint."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://openrouter.ai/api/v1/auth/key",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
        if r.status_code == 200:
            data = r.json().get("data", {})
            return "ok", f"usage={data.get('usage')} free_tier={data.get('is_free_tier')}"
        if r.status_code == 401:
            return "invalid", "401"
        if r.status_code == 402:
            return "quota_exhausted", "402"
        if r.status_code == 429:
            return "rate_limit", "429"
        return "error", f"HTTP {r.status_code}"
    except Exception as e:
        return "error", str(e)[:80]


async def _check_gemini_key_health(api_key: str) -> tuple[str, str]:
    """Проверка Gemini ключа через /v1beta/models endpoint (легковесный)."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": api_key},
                timeout=10,
            )
        if r.status_code == 200:
            return "ok", "200"
        if r.status_code == 401:
            return "invalid", "401 — key rejected"
        if r.status_code == 403:
            return "invalid", "403 — forbidden"
        if r.status_code == 429:
            body = r.text.lower()
            if "quota" in body or "daily" in body:
                return "quota_exhausted", "429 quota"
            return "rate_limit", "429 rpm"
        return "error", f"HTTP {r.status_code}"
    except Exception as e:
        return "error", str(e)[:80]


async def proactive_health_loop():
    """Фоновый цикл проверки ключей.

    ВАЖНО: НЕ помечаем ключи как мёртвые при ошибках health check —
    это может быть временный сбой API. Помечаем мёртвыми ТОЛЬКО при
    явном 401 (невалидный ключ) И ТОЛЬКО после 3 последовательных
    неудач. Восстанавливаем ключи сразу при успешной проверке.
    """
    await asyncio.sleep(10)
    _or_fail_count: dict[str, int] = {}  # key -> consecutive failures
    _gm_fail_count: dict[str, int] = {}
    while True:
        try:
            logger.info("Proactive health check: starting...")
            or_keys = _get_api_keys()
            gm_keys = _get_google_keys()

            for key in or_keys:
                was_alive = not _is_key_cooling(key)
                kind, detail = await _check_openrouter_key_health(key)
                if kind == "ok":
                    _or_fail_count.pop(key, None)
                    if not was_alive:
                        _mark_key_dead(key, 0, "health_check_recovered")
                        logger.info("OR key %s RECOVERED", _mask_key(key))
                elif kind == "invalid":
                    # Невалидный ключ — помечаем мёртвым ТОЛЬКО после 3 подряд неудач
                    _or_fail_count[key] = _or_fail_count.get(key, 0) + 1
                    if _or_fail_count[key] >= 3:
                        _mark_key_dead(key, 30 * 24 * 3600, f"health_check_{kind}_x3")
                        logger.warning("OR key %s → DEAD (3x invalid): %s", _mask_key(key), detail)
                    else:
                        logger.info("OR key %s invalid (%d/3): %s", _mask_key(key), _or_fail_count[key], detail)
                # rate_limit, quota_exhausted, error — НЕ помечаем мёртвым (временно)
                await asyncio.sleep(0.5)

            for key in gm_keys:
                was_alive = not _is_key_cooling(key)
                kind, detail = await _check_gemini_key_health(key)
                if kind == "ok":
                    _gm_fail_count.pop(key, None)
                    if not was_alive:
                        _mark_key_dead(key, 0, "health_check_recovered")
                        logger.info("Gemini key %s RECOVERED", _mask_key(key))
                elif kind == "invalid":
                    _gm_fail_count[key] = _gm_fail_count.get(key, 0) + 1
                    if _gm_fail_count[key] >= 3:
                        _mark_key_dead(key, 30 * 24 * 3600, f"health_check_{kind}_x3")
                        logger.warning("Gemini key %s → DEAD (3x invalid): %s", _mask_key(key), detail)
                    else:
                        logger.info("Gemini key %s invalid (%d/3): %s", _mask_key(key), _gm_fail_count[key], detail)
                await asyncio.sleep(0.5)

            or_alive = sum(1 for k in or_keys if not _is_key_cooling(k))
            gm_alive = sum(1 for k in gm_keys if not _is_key_cooling(k))
            logger.info("Health check done: OR %d/%d, Gemini %d/%d", or_alive, len(or_keys), gm_alive, len(gm_keys))
        except Exception as e:
            logger.warning("Health check error: %s", e)
        await asyncio.sleep(_HEALTH_CHECK_INTERVAL)


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
