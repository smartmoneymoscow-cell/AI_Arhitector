"""
shared/llm_schemas.py — Pydantic models for LLM response validation.

3-level validation strategy:
  Level 1: Pydantic structural validation (types, ranges, enums)
  Level 2: Auto-retry with fix prompt on ValidationError
  Level 3: Clarification questions to user
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("archai.llm_schemas")


class ReasoningStep(BaseModel):
    icon: str = "»"
    text: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class DecompositionItem(BaseModel):
    name: str
    description: str = ""
    service: str = ""


class ComparisonItem(BaseModel):
    name: str
    emoji: str = "◆"
    description: str = ""
    pros: list[str] = []
    cons: list[str] = []
    price: str = ""
    recommended: bool = False


class ParsedParams(BaseModel):
    """Strict schema for LLM parse response. All fields validated."""

    object_type: Literal["building", "interior", "room", "landscape", "structure", "element"] = "building"
    building_type: str = Field(default="house", min_length=1, max_length=100)
    building_description: str = ""
    room_type: str | None = None
    floors: int = Field(default=2, ge=1, le=50)
    width_m: float = Field(default=10.0, gt=0, le=500)
    length_m: float = Field(default=12.0, gt=0, le=500)
    height_m: float = Field(default=3.0, gt=0, le=50)
    style: str = Field(default="modern", min_length=1, max_length=50)
    material: str = Field(default="plaster", min_length=1, max_length=50)
    roof_type: str = Field(default="gabled", min_length=1, max_length=50)
    features: list[str] = []
    furniture: list[str] = []
    special_requirements: list[str] = []
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reasoning: str = ""

    # Premium fields (optional)
    type: str | None = None
    reasoning_steps: list[ReasoningStep] = []
    decomposition: list[DecompositionItem] = []
    comparison: list[ComparisonItem] = []

    @field_validator("building_type", mode="before")
    @classmethod
    def validate_building_type(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return "house"
        return str(v).strip().lower()

    @field_validator("style", mode="before")
    @classmethod
    def validate_style(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return "modern"
        return str(v).strip().lower()

    @field_validator("material", mode="before")
    @classmethod
    def validate_material(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return "plaster"
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
        return str(v).strip().lower()

    @field_validator("roof_type", mode="before")
    @classmethod
    def validate_roof_type(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return "none"
        return str(v).strip().lower()

    @field_validator("object_type", mode="before")
    @classmethod
    def validate_object_type(cls, v):
        if v is None:
            return "building"
        v = str(v).strip().lower()
        # Map common aliases
        aliases = {"room": "interior", "house": "building", "landscape": "landscape"}
        return aliases.get(v, v)

    @field_validator("floors", mode="before")
    @classmethod
    def validate_floors(cls, v):
        try:
            v = int(float(v))
            return max(1, min(50, v))
        except (TypeError, ValueError):
            return 2

    @field_validator("width_m", "length_m", "height_m", mode="before")
    @classmethod
    def validate_dimension(cls, v):
        try:
            v = float(v)
            if v <= 0 or v > 500:
                return 3.0  # use safe default instead of None
            return v
        except (TypeError, ValueError):
            return 3.0  # use safe default instead of None

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, v):
        try:
            v = float(v)
            # Handle 0-100 range (normalize to 0-1)
            if v > 1.0:
                v = v / 100.0
            return max(0.0, min(1.0, v))
        except (TypeError, ValueError):
            return 0.5


def validate_llm_response(data: dict | None) -> tuple[ParsedParams | None, list[str]]:
    """
    Validate LLM response against Pydantic schema.

    Returns:
        (parsed_params, errors) — parsed_params is None if validation fails,
        errors is list of human-readable error descriptions.
    """
    if data is None:
        return None, ["LLM returned null or unparseable response"]

    if not isinstance(data, dict):
        return None, [f"LLM returned {type(data).__name__} instead of dict"]

    errors = []
    try:
        parsed = ParsedParams.model_validate(data)
        return parsed, []
    except Exception as e:
        # Collect all validation errors
        if hasattr(e, "errors"):
            for err in e.errors():
                field = " → ".join(str(loc) for loc in err["loc"])
                errors.append(f"{field}: {err['msg']}")
        else:
            errors.append(str(e))
        return None, errors


def build_fix_prompt(original_prompt: str, errors: list[str], schema_json: str = "") -> str:
    """Build a prompt asking LLM to fix its invalid response."""
    if not schema_json:
        schema_json = json.dumps(ParsedParams.model_json_schema(), ensure_ascii=False, indent=2)[:2000]

    errors_text = "\n".join(f"  - {e}" for e in errors[:10])

    return (
        f"Ты вернул невалидный JSON. Исправь ошибки и верни СТРОГО валидный JSON.\n\n"
        f"Ошибки валидации:\n{errors_text}\n\n"
        f"Оригинальный запрос: {original_prompt}\n\n"
        f"Схема (должна строго соответствовать):\n{schema_json}\n\n"
        f"Верни ТОЛЬКО исправленный JSON, без пояснений."
    )
