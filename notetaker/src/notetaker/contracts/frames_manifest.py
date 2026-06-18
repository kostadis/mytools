from __future__ import annotations

from pydantic import BaseModel, field_validator


SCHEMA_VERSION = "1.0"


class FrameEntry(BaseModel):
    timestamp_ms: int
    file_path: str

    @field_validator("timestamp_ms")
    @classmethod
    def non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("timestamp_ms must be >= 0")
        return v


class FramesManifestSchema(BaseModel):
    schema_version: str = SCHEMA_VERSION
    recording_url: str
    frames: list[FrameEntry]

    @field_validator("schema_version")
    @classmethod
    def version_must_match(cls, v: str) -> str:
        if v != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be '{SCHEMA_VERSION}', got '{v}'")
        return v
