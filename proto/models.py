"""
proto/models.py — SHARED API models (protocol only).

ONLY request/response types. NO business logic.
NO dependencies on httpx, redis, blender, or any service.
"""

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    prompt: str
    quality: str = "standard"
    export_formats: list[str] = Field(default_factory=lambda: ["glb"])


class ParseRequest(BaseModel):
    text: str = Field(alias="prompt")

    class Config:
        populate_by_name = True


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage]
    max_tokens: int = 2048
    temperature: float = 0.7


class ChatResponse(BaseModel):
    choices: list[dict]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    model: str | None = None
    services: dict = Field(default_factory=dict)


class ParsedParams(BaseModel):
    object_type: str = "building"
    building_type: str = "house"
    room_type: str | None = None
    floors: int = 2
    width_m: float = 10
    length_m: float = 12
    height_m: float = 3.0
    style: str = "modern"
    material: str = "plaster"
    roof_type: str = "gabled"
    features: list[str] = Field(default_factory=list)
    furniture: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    # LLM fills these freely — no hardcoded enum restriction
    building_description: str | None = None
    special_requirements: list[str] = Field(default_factory=list)
    raw_llm_response: str | None = None
