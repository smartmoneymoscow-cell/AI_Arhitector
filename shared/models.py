"""
shared/models.py — общие Pydantic-модели для всех сервисов.
"""

from typing import Optional
from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    """Запрос на генерацию 3D-модели."""
    prompt: str = Field(..., min_length=1, description="Текстовый промт")
    object_type: Optional[str] = Field(None, description="building|interior|room")
    building_type: str = "house"
    room_type: Optional[str] = None
    floors: int = 2
    width_m: int = 10
    length_m: int = 12
    height_m: int = 3
    style: str = "modern"
    material: str = "plaster"
    roof_type: str = "gabled"
    features: list[str] = []
    furniture: list[str] = []


class ParseRequest(BaseModel):
    """Запрос на парсинг промта."""
    text: str = Field(..., min_length=1, description="Промт для парсинга")
    model: Optional[str] = None


class ParsedParams(BaseModel):
    """Результат парсинга промта."""
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
    features: list[str] = []
    furniture: list[str] = []


class ChatMessage(BaseModel):
    """Сообщение в чате."""
    role: str = "user"
    content: str = ""


class ChatRequest(BaseModel):
    """Запрос к чат-модели."""
    messages: list[ChatMessage] = Field(..., description="Messages array")
    max_tokens: int = Field(400, ge=1, le=4096)
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    model: Optional[str] = None


class ChatResponse(BaseModel):
    """Ответ чат-модели."""
    choices: list[dict]


class HealthResponse(BaseModel):
    """Ответ health-check."""
    status: str = "ok"
    service: str = ""
    version: str = ""
    model: Optional[str] = None
    services: Optional[dict[str, str]] = None
