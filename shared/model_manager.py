"""
shared/model_manager.py — Центральный менеджер LLM моделей.

Версия: 1.0.0

Функции:
  1. Auto-discovery бесплатных моделей OpenRouter каждые 4 часа
  2. Ротация 8 OpenRouter API ключей (round-robin + health tracking)
  3. Каскадный fallback: OpenRouter free models → Gemini (8 ключей)
  4. Приоритет моделей: сильные → слабые
  5. Circuit breaker per-key и per-model
  6. Кеширование результатов discovery в Redis

Архитектура:
  OpenRouter Request:
    [Key 1] → [Free Model Tier 1] → fail → [Free Model Tier 2] → fail → ...
    [Key 2] → ... (rotated on 429/error)
    ...
    [Key 8] → ...

  Gemini Fallback (when ALL OpenRouter keys/models fail):
    [Gemini Key 1] → fail → [Gemini Key 2] → ... → [Gemini Key 8]
"""

import asyncio
import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum

import httpx

logger = logging.getLogger("archai.model_manager")


# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

# How often to re-discover free models (4 hours as requested)
DISCOVERY_INTERVAL = int(os.environ.get("MODEL_DISCOVERY_INTERVAL", "14400"))  # 4h = 14400s

# Max models in cascade (avoid timeout on too many retries)
MAX_CASCADE_SIZE = int(os.environ.get("MODEL_MAX_CASCADE", "12"))

# OpenRouter base URL
OPENROUTER_BASE = os.environ.get("OPENROUTER_BASE", "https://openrouter.ai/api/v1")

# Gemini base URL
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Gemini model (free tier)
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

# Request timeout per model attempt
MODEL_TIMEOUT = int(os.environ.get("MODEL_TIMEOUT", "30"))

# Circuit breaker: failures before disabling
CB_FAILURES = int(os.environ.get("CB_FAILURES", "3"))
CB_COOLDOWN = int(os.environ.get("CB_COOLDOWN", "300"))  # 5 minutes


# ═══════════════════════════════════════════════════════════════
# MODEL BLOCKLIST — known bad models for JSON/arch tasks
# ═══════════════════════════════════════════════════════════════

BLOCKLIST = {
    "openrouter/auto",
    "deepseek/deepseek-r1-0528:free",           # thinking model, outputs <think> tags
    "google/gemma-3-1b-it:free",                 # too small
    "meta-llama/llama-4-maverick:free",          # inconsistent JSON
    "google/lyria-3-clip-preview",               # music model
    "google/lyria-3-pro-preview",                # music model
    "nvidia/nemotron-3-nano-30b-a3b:free",       # reasoning model, slow
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",  # reasoning, slow
    "nvidia/nemotron-3.5-content-safety:free",   # safety model, not text gen
    "nvidia/nemotron-nano-12b-v2-vl:free",       # vision-language, not ideal for JSON
    "nvidia/nemotron-nano-9b-v2:free",           # too small
    "inclusionai/ling-3.0-flash:free",           # unknown quality
}

# Keywords that indicate non-text models
SKIP_KEYWORDS = [
    "lyria", "imagen", "dall-e", "stable-diffusion", "midjourney",
    "tts", "whisper", "embed", "rerank", "content-safety", "guard",
    "audio", "speech", "music", "image-gen",
]

# Preferred models — boosted to Tier 1
PREFERRED_MODELS = {
    "meta-llama/llama-3.3-70b-instruct:free",
    "mistralai/mistral-small-3.2-24b:free",
    "qwen/qwen3-235b-a22b:free",
    "deepseek/deepseek-chat-v3-0324:free",
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-4-31b-it:free",
}


# ═══════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════

class Provider(str, Enum):
    OPENROUTER = "openrouter"
    GEMINI = "gemini"


@dataclass
class ApiKey:
    """Single API key with health tracking."""
    key: str
    provider: Provider
    index: int  # position in key list
    failures: int = 0
    last_failure: float = 0.0
    last_success: float = 0.0
    total_requests: int = 0
    total_failures: int = 0
    disabled_until: float = 0.0  # circuit breaker

    @property
    def is_available(self) -> bool:
        if self.disabled_until and time.time() < self.disabled_until:
            return False
        return True

    def record_success(self):
        self.failures = 0
        self.last_success = time.time()
        self.total_requests += 1
        self.disabled_until = 0.0

    def record_failure(self):
        self.failures += 1
        self.last_failure = time.time()
        self.total_requests += 1
        self.total_failures += 1
        if self.failures >= CB_FAILURES:
            self.disabled_until = time.time() + CB_COOLDOWN
            logger.warning(
                "Key %s[%d] circuit breaker OPEN — disabled for %ds (failures=%d)",
                self.provider.value, self.index, CB_COOLDOWN, self.failures,
            )

    def reset_circuit_breaker(self):
        self.failures = 0
        self.disabled_until = 0.0

    def to_dict(self) -> dict:
        masked = self.key[:8] + "..." + self.key[-4:] if len(self.key) > 12 else "***"
        return {
            "provider": self.provider.value,
            "index": self.index,
            "key_masked": masked,
            "failures": self.failures,
            "total_requests": self.total_requests,
            "total_failures": self.total_failures,
            "is_available": self.is_available,
            "disabled_until": self.disabled_until,
            "last_success_ago": int(time.time() - self.last_success) if self.last_success else None,
        }


@dataclass
class FreeModel:
    """Discovered free model with priority."""
    model_id: str
    name: str
    tier: int  # 1=strong, 2=medium, 3=weak
    is_preferred: bool = False
    context_length: int = 0
    discovered_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "model": self.model_id,
            "name": self.name,
            "tier": self.tier,
            "is_preferred": self.is_preferred,
            "context_length": self.context_length,
        }


# ═══════════════════════════════════════════════════════════════
# MODEL MANAGER — singleton
# ═══════════════════════════════════════════════════════════════

class ModelManager:
    """
    Центральный менеджер LLM моделей.

    Responsibilities:
    - Управление пулом API ключей (OpenRouter + Gemini)
    - Auto-discovery бесплатных моделей каждые 4 часа
    - Round-robin ротация ключей с health tracking
    - Каскадный fallback: OpenRouter → Gemini
    - Circuit breaker per-key
    """

    def __init__(self):
        self._lock = threading.Lock()

        # API Keys
        self._openrouter_keys: list[ApiKey] = []
        self._gemini_keys: list[ApiKey] = []
        self._or_key_index: int = 0  # round-robin pointer
        self._gemini_key_index: int = 0

        # Discovered models
        self._free_models: list[FreeModel] = []
        self._last_discovery: float = 0.0
        self._discovery_in_progress: bool = False

        # Stats
        self._stats = {
            "total_requests": 0,
            "openrouter_successes": 0,
            "openrouter_failures": 0,
            "gemini_successes": 0,
            "gemini_failures": 0,
            "discovery_runs": 0,
            "last_discovery_time": None,
            "last_discovery_count": 0,
        }

        # Load keys from environment
        self._load_keys()

    # ─── Key Loading ──────────────────────────────────────────

    def _load_keys(self):
        """Load API keys from environment variables."""

        # OpenRouter keys: PRIMARY + FALLBACK (comma-separated)
        or_keys = []
        primary = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if primary:
            or_keys.append(primary)
        fallback = os.environ.get("OPENROUTER_FALLBACK_KEYS", "").strip()
        if fallback:
            for k in fallback.split(","):
                k = k.strip()
                if k and k not in or_keys:
                    or_keys.append(k)

        # Also check numbered keys: OPENROUTER_KEY_1 .. OPENROUTER_KEY_8
        for i in range(1, 9):
            k = os.environ.get(f"OPENROUTER_KEY_{i}", "").strip()
            if k and k not in or_keys:
                or_keys.append(k)

        self._openrouter_keys = [
            ApiKey(key=k, provider=Provider.OPENROUTER, index=i)
            for i, k in enumerate(or_keys)
        ]

        # Gemini keys: GEMINI_API_KEY + GEMINI_API_KEYS (comma-separated)
        gem_keys = []
        gem_primary = os.environ.get("GOOGLE_API_KEY", "").strip()
        if gem_primary:
            gem_keys.append(gem_primary)
        gem_fallback = os.environ.get("GOOGLE_API_KEYS", "").strip()
        if gem_fallback:
            for k in gem_fallback.split(","):
                k = k.strip()
                if k and k not in gem_keys:
                    gem_keys.append(k)
        # Also check numbered: GEMINI_KEY_1 .. GEMINI_KEY_8
        for i in range(1, 9):
            k = os.environ.get(f"GEMINI_KEY_{i}", "").strip()
            if k and k not in gem_keys:
                gem_keys.append(k)

        self._gemini_keys = [
            ApiKey(key=k, provider=Provider.GEMINI, index=i)
            for i, k in enumerate(gem_keys)
        ]

        logger.info(
            "ModelManager initialized: %d OpenRouter keys, %d Gemini keys",
            len(self._openrouter_keys), len(self._gemini_keys),
        )

    # ─── Key Rotation ─────────────────────────────────────────

    def _get_next_openrouter_key(self) -> ApiKey | None:
        """Get next available OpenRouter key (round-robin with health)."""
        with self._lock:
            if not self._openrouter_keys:
                return None

            n = len(self._openrouter_keys)
            for _ in range(n):
                key = self._openrouter_keys[self._or_key_index % n]
                self._or_key_index += 1
                if key.is_available:
                    return key

            # All keys circuit-broken — reset the oldest one
            oldest = min(self._openrouter_keys, key=lambda k: k.disabled_until)
            oldest.reset_circuit_breaker()
            logger.warning("All OpenRouter keys circuit-broken — reset key[%d]", oldest.index)
            return oldest

    def _get_next_gemini_key(self) -> ApiKey | None:
        """Get next available Gemini key (round-robin with health)."""
        with self._lock:
            if not self._gemini_keys:
                return None

            n = len(self._gemini_keys)
            for _ in range(n):
                key = self._gemini_keys[self._gemini_key_index % n]
                self._gemini_key_index += 1
                if key.is_available:
                    return key

            # All circuit-broken — reset oldest
            oldest = min(self._gemini_keys, key=lambda k: k.disabled_until)
            oldest.reset_circuit_breaker()
            logger.warning("All Gemini keys circuit-broken — reset key[%d]", oldest.index)
            return oldest

    def _try_all_openrouter_keys(self) -> ApiKey | None:
        """Try all OpenRouter keys, return first available."""
        with self._lock:
            for key in self._openrouter_keys:
                if key.is_available:
                    return key
            # Reset oldest
            if self._openrouter_keys:
                oldest = min(self._openrouter_keys, key=lambda k: k.disabled_until)
                oldest.reset_circuit_breaker()
                return oldest
        return None

    # ─── Free Model Discovery ─────────────────────────────────

    async def discover_free_models(self, force: bool = False) -> list[FreeModel]:
        """
        Query OpenRouter API for available free models.
        Runs automatically every 4 hours (DISCOVERY_INTERVAL).
        """
        with self._lock:
            if self._discovery_in_progress:
                logger.debug("Discovery already in progress, skipping")
                return self._free_models
            if not force and self._free_models and (time.time() - self._last_discovery) < DISCOVERY_INTERVAL:
                return self._free_models
            self._discovery_in_progress = True

        try:
            # Use first available key for discovery
            key = self._try_all_openrouter_keys()
            if not key:
                logger.error("No OpenRouter keys available for discovery")
                return self._free_models

            models = await self._query_openrouter_models(key.key)
            if models:
                with self._lock:
                    self._free_models = models
                    self._last_discovery = time.time()
                    self._stats["discovery_runs"] += 1
                    self._stats["last_discovery_time"] = time.time()
                    self._stats["last_discovery_count"] = len(models)
                key.record_success()
                logger.info(
                    "Discovered %d free models from OpenRouter (tier1=%d, tier2=%d, tier3=%d)",
                    len(models),
                    sum(1 for m in models if m.tier == 1),
                    sum(1 for m in models if m.tier == 2),
                    sum(1 for m in models if m.tier == 3),
                )
            return self._free_models

        except Exception as e:
            logger.error("Free model discovery failed: %s", e)
            return self._free_models
        finally:
            with self._lock:
                self._discovery_in_progress = False

    async def _query_openrouter_models(self, api_key: str) -> list[FreeModel]:
        """Query OpenRouter /models endpoint for free models."""
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{OPENROUTER_BASE}/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=15,
                )
            if r.status_code != 200:
                logger.warning("OpenRouter /models returned %d", r.status_code)
                return []

            data = r.json()
            raw_models = data.get("data", [])

            free_models = []
            for m in raw_models:
                mid = m.get("id", "")
                pricing = m.get("pricing", {})
                prompt_price = float(pricing.get("prompt", "1") or "1")
                completion_price = float(pricing.get("completion", "1") or "1")

                # Free = price is exactly 0
                is_free = prompt_price == 0 and completion_price == 0
                if not is_free:
                    continue

                # Skip blocklisted
                if mid in BLOCKLIST:
                    continue

                # Skip non-text models
                mid_lower = mid.lower()
                if any(kw in mid_lower for kw in SKIP_KEYWORDS):
                    continue

                # Must support text output
                arch = m.get("architecture", {})
                modality = arch.get("output_modalities", [])
                if modality and "text" not in modality:
                    continue

                # Determine tier based on model quality
                is_preferred = mid in PREFERRED_MODELS
                if is_preferred:
                    tier = 1
                else:
                    # Heuristic: larger models = better
                    ctx = m.get("context_length", 0) or 0
                    name_lower = m.get("name", "").lower()
                    # Tier 2: known good families or large context
                    if any(kw in mid_lower for kw in ["qwen", "deepseek", "llama-3", "mistral", "gemma"]):
                        tier = 2
                    elif ctx >= 32000:
                        tier = 2
                    else:
                        tier = 3

                free_models.append(FreeModel(
                    model_id=mid,
                    name=m.get("name", ""),
                    tier=tier,
                    is_preferred=is_preferred,
                    context_length=m.get("context_length", 0) or 0,
                ))

            # Sort: tier 1 first, then by name
            free_models.sort(key=lambda x: (x.tier, x.model_id))

            # Limit cascade size
            return free_models[:MAX_CASCADE_SIZE]

        except Exception as e:
            logger.warning("OpenRouter model query failed: %s", e)
            return []

    # ─── Core: Send LLM Request ───────────────────────────────

    async def send_request(
        self,
        messages: list[dict],
        max_tokens: int = 500,
        temperature: float = 0.1,
        system_prompt: str = "",
    ) -> dict:
        """
        Send LLM request with full cascade:
        1. Try each free model on OpenRouter (rotating keys)
        2. If all OpenRouter fail → try Gemini (rotating keys)
        3. If all fail → raise AllModelsFailedError

        Returns: {"content": str, "model": str, "provider": str, "key_index": int}
        """
        self._stats["total_requests"] += 1

        # Build message list with system prompt
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        # ─── Phase 1: OpenRouter free models ──────────────────
        models = self.get_active_models()
        if not models:
            logger.warning("No free models discovered — triggering emergency discovery")
            await self.discover_free_models(force=True)
            models = self.get_active_models()

        last_error = None

        for model in models:
            key = self._get_next_openrouter_key()
            if not key:
                logger.warning("No OpenRouter keys available")
                break

            try:
                result = await self._call_openrouter(
                    api_key=key.key,
                    model_id=model.model_id,
                    messages=full_messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=MODEL_TIMEOUT,
                )
                key.record_success()
                self._stats["openrouter_successes"] += 1
                return {
                    "content": result,
                    "model": model.model_id,
                    "provider": "openrouter",
                    "key_index": key.index,
                }
            except Exception as e:
                key.record_failure()
                self._stats["openrouter_failures"] += 1
                last_error = e
                logger.debug("OpenRouter %s with key[%d] failed: %s", model.model_id, key.index, e)
                continue

        # ─── Phase 2: Gemini fallback ─────────────────────────
        logger.warning("All OpenRouter models failed — trying Gemini fallback")

        for attempt in range(len(self._gemini_keys)):
            key = self._get_next_gemini_key()
            if not key:
                break

            try:
                result = await self._call_gemini(
                    api_key=key.key,
                    messages=full_messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=MODEL_TIMEOUT,
                )
                key.record_success()
                self._stats["gemini_successes"] += 1
                return {
                    "content": result,
                    "model": GEMINI_MODEL,
                    "provider": "gemini",
                    "key_index": key.index,
                }
            except Exception as e:
                key.record_failure()
                self._stats["gemini_failures"] += 1
                last_error = e
                logger.debug("Gemini key[%d] failed: %s", key.index, e)
                continue

        # ─── All failed ───────────────────────────────────────
        raise AllModelsFailedError(
            f"All models failed. OpenRouter: {len(models)} models tried. "
            f"Gemini: {len(self._gemini_keys)} keys tried. "
            f"Last error: {last_error}"
        )

    # ─── OpenRouter API Call ───────────────────────────────────

    async def _call_openrouter(
        self,
        api_key: str,
        model_id: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
        timeout: int,
    ) -> str:
        """Call OpenRouter chat completions API."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://archai.app",
            "X-Title": "Architect LLM",
        }
        payload = {
            "model": model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{OPENROUTER_BASE}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout,
            )

        if r.status_code == 200:
            data = r.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                raise ValueError("Empty response from OpenRouter")
            return content.strip()

        if r.status_code == 429:
            raise RateLimitError(f"OpenRouter rate limit (429) for model {model_id}")

        if r.status_code == 402:
            raise PaymentError(f"OpenRouter payment required (402) for model {model_id}")

        raise ApiError(f"OpenRouter HTTP {r.status_code}: {r.text[:200]}")

    # ─── Gemini API Call ──────────────────────────────────────

    async def _call_gemini(
        self,
        api_key: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
        timeout: int,
    ) -> str:
        """Call Google Gemini API."""
        # Convert messages to Gemini format
        gemini_contents = self._messages_to_gemini_format(messages)

        url = f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent?key={api_key}"
        payload = {
            "contents": gemini_contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }

        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, timeout=timeout)

        if r.status_code == 200:
            data = r.json()
            # Extract text from Gemini response
            candidates = data.get("candidates", [])
            if not candidates:
                raise ValueError("No candidates in Gemini response")
            parts = candidates[0].get("content", {}).get("parts", [])
            text_parts = [p.get("text", "") for p in parts if "text" in p]
            content = "\n".join(text_parts).strip()
            if not content:
                raise ValueError("Empty response from Gemini")
            return content

        if r.status_code == 429:
            raise RateLimitError(f"Gemini rate limit (429)")

        if r.status_code == 403:
            raise ApiError(f"Gemini forbidden (403) — key may be invalid or quota exceeded")

        raise ApiError(f"Gemini HTTP {r.status_code}: {r.text[:200]}")

    def _messages_to_gemini_format(self, messages: list[dict]) -> list[dict]:
        """Convert OpenAI-format messages to Gemini format."""
        gemini_contents = []
        system_instruction = None

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_instruction = content
            elif role == "assistant":
                gemini_contents.append({
                    "role": "model",
                    "parts": [{"text": content}],
                })
            else:
                gemini_contents.append({
                    "role": "user",
                    "parts": [{"text": content}],
                })

        # If there's a system instruction, prepend it to the first user message
        if system_instruction and gemini_contents:
            for i, c in enumerate(gemini_contents):
                if c["role"] == "user":
                    gemini_contents[i]["parts"][0]["text"] = (
                        f"[System: {system_instruction}]\n\n{c['parts'][0]['text']}"
                    )
                    break

        return gemini_contents

    # ─── Public API ───────────────────────────────────────────

    def get_active_models(self) -> list[FreeModel]:
        """Get current cascade of free models, sorted by tier."""
        with self._lock:
            return list(self._free_models)

    def get_cascade_list(self) -> list[str]:
        """Get model IDs in cascade order."""
        return [m.model_id for m in self.get_active_models()]

    def get_stats(self) -> dict:
        """Get manager statistics."""
        with self._lock:
            return {
                **self._stats,
                "openrouter_keys": len(self._openrouter_keys),
                "gemini_keys": len(self._gemini_keys),
                "openrouter_keys_available": sum(1 for k in self._openrouter_keys if k.is_available),
                "gemini_keys_available": sum(1 for k in self._gemini_keys if k.is_available),
                "free_models_count": len(self._free_models),
                "free_models": [m.to_dict() for m in self._free_models],
                "last_discovery_ago": int(time.time() - self._last_discovery) if self._last_discovery else None,
                "discovery_interval": DISCOVERY_INTERVAL,
            }

    def get_keys_health(self) -> list[dict]:
        """Get health status of all keys."""
        with self._lock:
            return [k.to_dict() for k in self._openrouter_keys + self._gemini_keys]

    def force_key_rotation(self, provider: str = "openrouter"):
        """Force reset to first key of given provider."""
        with self._lock:
            if provider == "openrouter":
                self._or_key_index = 0
            elif provider == "gemini":
                self._gemini_key_index = 0

    def reset_all_circuit_breakers(self):
        """Reset all circuit breakers — use with caution."""
        with self._lock:
            for k in self._openrouter_keys + self._gemini_keys:
                k.reset_circuit_breaker()
            logger.info("All circuit breakers reset")


# ═══════════════════════════════════════════════════════════════
# EXCEPTIONS
# ═══════════════════════════════════════════════════════════════

class AllModelsFailedError(Exception):
    """Raised when all models in cascade (OpenRouter + Gemini) fail."""
    pass


class RateLimitError(Exception):
    """Raised on 429 rate limit."""
    pass


class PaymentError(Exception):
    """Raised on 402 payment required."""
    pass


class ApiError(Exception):
    """Raised on API errors."""
    pass


# ═══════════════════════════════════════════════════════════════
# SINGLETON INSTANCE
# ═══════════════════════════════════════════════════════════════

_manager: ModelManager | None = None
_manager_lock = threading.Lock()


def get_model_manager() -> ModelManager:
    """Get singleton ModelManager instance."""
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = ModelManager()
    return _manager


def reset_model_manager():
    """Reset singleton (for testing)."""
    global _manager
    with _manager_lock:
        _manager = None
