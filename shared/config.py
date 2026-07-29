"""
shared/config.py — единая конфигурация для всех сервисов.
"""

import os


class Settings:
    """Глобальные настройки, читаемые из env."""

    # OpenRouter
    OPENROUTER_API_KEY: str = os.environ.get("OPENROUTER_API_KEY", "")
    OPENROUTER_BASE: str = "https://openrouter.ai/api/v1"
    LLM_MODEL: str = os.environ.get("LLM_MODEL", "nvidia/nemotron-3-nano-30b-a3b:free")

    # Blender
    BLENDER_PATH: str = os.environ.get("BLENDER_PATH", "blender")
    OUTPUT_DIR: str = os.environ.get("OUTPUT_DIR", "/app/output")
    BLENDER_TIMEOUT: int = int(os.environ.get("BLENDER_TIMEOUT", "120"))
    RENDER_INTERIOR_TIMEOUT: int = int(os.environ.get("RENDER_INTERIOR_TIMEOUT", "300"))

    # Service URLs (for microservice mode)
    LLM_SERVICE_URL: str = os.environ.get("LLM_SERVICE_URL", "http://localhost:8081")
    BLENDER_SERVICE_URL: str = os.environ.get("BLENDER_SERVICE_URL", "http://localhost:8082")
    GEOMETRY_SERVICE_URL: str = os.environ.get("GEOMETRY_SERVICE_URL", "")
    IFC_SERVICE_URL: str = os.environ.get("IFC_SERVICE_URL", "")
    ML_SERVICE_URL: str = os.environ.get("ML_SERVICE_URL", "")
    DATA_SERVICE_URL: str = os.environ.get("DATA_SERVICE_URL", "")
    CAD_SERVICE_URL: str = os.environ.get("CAD_SERVICE_URL", "")
    FREECAD_SERVICE_URL: str = os.environ.get("FREECAD_SERVICE_URL", "")
    VECTORDB_SERVICE_URL: str = os.environ.get("VECTORDB_SERVICE_URL", "")
    GRAPHDB_SERVICE_URL: str = os.environ.get("GRAPHDB_SERVICE_URL", "")

    # Server
    PORT: int = int(os.environ.get("PORT", "8080"))
    FRONTEND_DIR: str = os.environ.get("FRONTEND_DIR", "")

    # Retry
    MAX_RETRIES: int = 2
    RETRY_DELAY_BASE: float = 5.0
    REQUEST_TIMEOUT: float = 120.0

    def get_all_service_urls(self) -> dict[str, str]:
        """Возвращает словарь {name: url} для всех сервисов."""
        return {
            "llm": self.LLM_SERVICE_URL,
            "blender": self.BLENDER_SERVICE_URL,
            "geometry": self.GEOMETRY_SERVICE_URL,
            "ifc": self.IFC_SERVICE_URL,
            "ml": self.ML_SERVICE_URL,
            "data": self.DATA_SERVICE_URL,
            "cad": self.CAD_SERVICE_URL,
            "freecad": self.FREECAD_SERVICE_URL,
            "vectordb": self.VECTORDB_SERVICE_URL,
            "graphdb": self.GRAPHDB_SERVICE_URL,
        }


settings = Settings()
