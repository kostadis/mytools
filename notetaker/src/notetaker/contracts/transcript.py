from __future__ import annotations

from pydantic import BaseModel, field_validator, model_validator


SCHEMA_VERSION = "1.0"


class Utterance(BaseModel):
    start_seconds: float
    end_seconds: float
    speaker: str
    text: str

    @model_validator(mode="after")
    def end_after_start(self) -> "Utterance":
        if self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds must be greater than start_seconds")
        return self

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text may not be blank")
        return v


class TranscriptSchema(BaseModel):
    schema_version: str = SCHEMA_VERSION
    recording_url: str
    captured_at: str
    utterances: list[Utterance]
    transcript_unavailable: bool = False

    @field_validator("schema_version")
    @classmethod
    def version_must_match(cls, v: str) -> str:
        if v != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be '{SCHEMA_VERSION}', got '{v}'")
        return v
