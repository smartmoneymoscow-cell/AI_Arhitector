"""
shared/config.py — единая конфигурация для всех сервисов.

v7.0: удалены неиспользуемые сервисы, добавлен REDIS_URL.
"""

import os


class Settings:
    """Глобальные настройки, читаемые из env."""

    # OpenRouter
    GOOGLE_API_KEY: str = os.environ.get("GOOGLE_API_KEY", "")
    OPENROUTER_API_KEY: str = os.environ.get("OPENROUTER_API_KEY", "")
    OPENROUTER_BASE: str = "https://openrouter.ai/api/v1"
    LLM_MODEL: str = os.environ.get("LLM_MODEL", "google/gemini-flash-latest")

    # Redis
    REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # Blender
    BLENDER_PATH: str = os.environ.get("BLENDER_PATH", "blender")
    OUTPUT_DIR: str = os.environ.get("OUTPUT_DIR", "/app/output")
    BLENDER_TIMEOUT: int = int(os.environ.get("BLENDER_TIMEOUT", "120"))
    RENDER_INTERIOR_TIMEOUT: int = int(os.environ.get("RENDER_INTERIOR_TIMEOUT", "300"))

    # Service URLs (only active services)
    LLM_SERVICE_URL: str = os.environ.get("LLM_SERVICE_URL", "http://localhost:8081")
    BLENDER_SERVICE_URL: str = os.environ.get("BLENDER_SERVICE_URL", "http://localhost:8082")

    # Server
    PORT: int = int(os.environ.get("PORT", "8080"))
    FRONTEND_DIR: str = os.environ.get("FRONTEND_DIR", "")

    # Auth
    ARCH_API_KEYS: str = os.environ.get("ARCH_API_KEYS", "")
    CORS_ORIGINS: str = os.environ.get("CORS_ORIGINS", "*")

    # Retry
    MAX_RETRIES: int = 2
    RETRY_DELAY_BASE: float = 5.0
    REQUEST_TIMEOUT: float = 120.0

    def get_all_service_urls(self) -> dict[str, str]:
        """Возвращает словарь {name: url} для активных сервисов."""
        return {
            "llm": self.LLM_SERVICE_URL,
            "blender": self.BLENDER_SERVICE_URL,
        }


settings = Settings()
