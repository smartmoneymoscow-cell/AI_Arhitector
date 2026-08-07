"""
shared/config.py — единая конфигурация для всех сервисов.

v8.0: Model Manager integration — 8 OpenRouter keys + 8 Gemini keys,
      auto-discovery free models, key rotation, circuit breaker.
"""

import os


class Settings:
    """Глобальные настройки, читаемые из env."""

    # ═══ OpenRouter (4 keys) ═══════════════════════════════════
    OPENROUTER_API_KEY: str = os.environ.get("OPENROUTER_API_KEY", "")
    OPENROUTER_FALLBACK_KEYS: str = os.environ.get("OPENROUTER_FALLBACK_KEYS", "")
    OPENROUTER_BASE: str = os.environ.get("OPENROUTER_BASE", "https://openrouter.ai/api/v1")

    # Numbered keys (alternative format): OPENROUTER_KEY_1..8
    # Parsed by ModelManager from env directly

    # ═══ Google Gemini (8 keys) ════════════════════════════════
    GOOGLE_API_KEY: str = os.environ.get("GOOGLE_API_KEY", "")
    GOOGLE_API_KEYS: str = os.environ.get("GOOGLE_API_KEYS", "")
    # Numbered keys: GEMINI_KEY_1..8 — parsed by ModelManager

    # ═══ Model Manager ═════════════════════════════════════════
    LLM_MODEL: str = os.environ.get("LLM_MODEL", "auto")  # "auto" = use ModelManager
    MODEL_DISCOVERY_INTERVAL: int = int(os.environ.get("MODEL_DISCOVERY_INTERVAL", "14400"))  # 4h
    MODEL_MAX_CASCADE: int = int(os.environ.get("MODEL_MAX_CASCADE", "12"))
    MODEL_TIMEOUT: int = int(os.environ.get("MODEL_TIMEOUT", "30"))
    CB_FAILURES: int = int(os.environ.get("CB_FAILURES", "3"))
    CB_COOLDOWN: int = int(os.environ.get("CB_COOLDOWN", "300"))

    # Gemini model (free tier)
    GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

    # ═══ Redis ═════════════════════════════════════════════════
    REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # ═══ Blender ═══════════════════════════════════════════════
    BLENDER_PATH: str = os.environ.get("BLENDER_PATH", "blender")
    OUTPUT_DIR: str = os.environ.get("OUTPUT_DIR", "/app/output")
    BLENDER_TIMEOUT: int = int(os.environ.get("BLENDER_TIMEOUT", "120"))
    RENDER_INTERIOR_TIMEOUT: int = int(os.environ.get("RENDER_INTERIOR_TIMEOUT", "300"))

    # ═══ Service URLs ══════════════════════════════════════════
    LLM_SERVICE_URL: str = os.environ.get("LLM_SERVICE_URL", "http://localhost:8081")
    BLENDER_SERVICE_URL: str = os.environ.get("BLENDER_SERVICE_URL", "http://localhost:8082")

    # ═══ Server ════════════════════════════════════════════════
    PORT: int = int(os.environ.get("PORT", "8080"))
    FRONTEND_DIR: str = os.environ.get("FRONTEND_DIR", "")

    # ═══ Auth ══════════════════════════════════════════════════
    ARCH_API_KEYS: str = os.environ.get("ARCH_API_KEYS", "")
    CORS_ORIGINS: str = os.environ.get("CORS_ORIGINS", "*")

    # ═══ Retry ═════════════════════════════════════════════════
    MAX_RETRIES: int = 2
    RETRY_DELAY_BASE: float = 5.0
    REQUEST_TIMEOUT: float = 120.0

    def get_all_service_urls(self) -> dict[str, str]:
        """Возвращает словарь {name: url} для активных сервисов."""
        return {
            "llm": self.LLM_SERVICE_URL,
            "blender": self.BLENDER_SERVICE_URL,
        }

    def get_openrouter_key_count(self) -> int:
        """Estimate number of configured OpenRouter keys."""
        count = 0
        if self.OPENROUTER_API_KEY:
            count += 1
        if self.OPENROUTER_FALLBACK_KEYS:
            count += len([k for k in self.OPENROUTER_FALLBACK_KEYS.split(",") if k.strip()])
        for i in range(1, 9):
            if os.environ.get(f"OPENROUTER_KEY_{i}", "").strip():
                count += 1
        return count

    def get_gemini_key_count(self) -> int:
        """Estimate number of configured Gemini keys."""
        count = 0
        if self.GOOGLE_API_KEY:
            count += 1
        if self.GOOGLE_API_KEYS:
            count += len([k for k in self.GOOGLE_API_KEYS.split(",") if k.strip()])
        for i in range(1, 9):
            if os.environ.get(f"GEMINI_KEY_{i}", "").strip():
                count += 1
        return count


settings = Settings()
