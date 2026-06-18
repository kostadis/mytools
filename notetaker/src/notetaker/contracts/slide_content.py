from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, field_validator


SCHEMA_VERSION = "1.0"


class ExtractionMethod(str, Enum):
    vision = "vision"
    ocr = "ocr"


class SlideContent(BaseModel):
    slide_id: str
    title: str
    bullets: list[str]
    visual_description: str
    raw_ocr: str
    extraction_method: ExtractionMethod
    estimated_cost_usd: float

    @field_validator("estimated_cost_usd")
    @classmethod
    def cost_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("estimated_cost_usd must be >= 0")
        return v


class SlideContentSchema(BaseModel):
    schema_version: str = SCHEMA_VERSION
    recording_url: str
    total_cost_usd: float
    budget_ceiling_usd: float
    slides: list[SlideContent]

    @field_validator("schema_version")
    @classmethod
    def version_must_match(cls, v: str) -> str:
        if v != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be '{SCHEMA_VERSION}', got '{v}'")
        return v

    @field_validator("total_cost_usd", "budget_ceiling_usd")
    @classmethod
    def non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("cost/budget fields must be >= 0")
        return v
