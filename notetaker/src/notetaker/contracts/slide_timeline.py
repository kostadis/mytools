from __future__ import annotations

import re

from pydantic import BaseModel, field_validator, model_validator


SCHEMA_VERSION = "1.0"

_SLIDE_ID_RE = re.compile(r"^s[0-9]{3,}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class SlideOccurrence(BaseModel):
    slide_id: str
    start_seconds: float
    end_seconds: float
    frame_path: str
    frame_hash: str
    frame_sha256: str

    @field_validator("slide_id")
    @classmethod
    def valid_slide_id(cls, v: str) -> str:
        if not _SLIDE_ID_RE.match(v):
            raise ValueError(f"slide_id must match pattern s[0-9]{{3,}}, got '{v}'")
        return v

    @field_validator("frame_sha256")
    @classmethod
    def valid_sha256(cls, v: str) -> str:
        if not _SHA256_RE.match(v):
            raise ValueError(f"frame_sha256 must be a 64-char lowercase hex string, got '{v}'")
        return v

    @model_validator(mode="after")
    def end_after_start(self) -> "SlideOccurrence":
        if self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds must be greater than start_seconds")
        return self


class SlideTimelineSchema(BaseModel):
    schema_version: str = SCHEMA_VERSION
    recording_url: str
    slides: list[SlideOccurrence]

    @field_validator("schema_version")
    @classmethod
    def version_must_match(cls, v: str) -> str:
        if v != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be '{SCHEMA_VERSION}', got '{v}'")
        return v
