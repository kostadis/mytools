"""Contract tests for RecordingMetaSchema (spec 005, T005)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from notetaker.contracts.recording_meta import (
    CURRENT_SCHEMA_VERSION,
    RecordingMetaSchema,
)


VALID_V2 = {
    "schema_version": "2",
    "recording_url": "https://zoom.us/rec/share/abc",
    "created_at": "2026-05-10T08:30:00+00:00",
    "meeting_title": "Q2 Planning Sync",
    "recording_date": "2026-04-15",
    "summary": "Roadmap, headcount",
}


def test_default_construction_emits_current_version():
    meta = RecordingMetaSchema(
        recording_url="https://zoom.us/rec/share/abc",
        created_at="2026-05-10T08:30:00+00:00",
    )
    assert meta.schema_version == CURRENT_SCHEMA_VERSION
    assert meta.model_dump()["schema_version"] == CURRENT_SCHEMA_VERSION


def test_recording_url_required():
    bad = {k: v for k, v in VALID_V2.items() if k != "recording_url"}
    with pytest.raises(ValidationError):
        RecordingMetaSchema.model_validate(bad)


def test_created_at_required():
    bad = {k: v for k, v in VALID_V2.items() if k != "created_at"}
    with pytest.raises(ValidationError):
        RecordingMetaSchema.model_validate(bad)


def test_unknown_schema_version_rejected():
    bad = {**VALID_V2, "schema_version": "3"}
    with pytest.raises(ValidationError):
        RecordingMetaSchema.model_validate(bad)


def test_v1_schema_version_accepted_on_validate():
    """Direct model_validate also tolerates schema_version=1 (the lenient mode)."""
    payload = {**VALID_V2, "schema_version": "1"}
    meta = RecordingMetaSchema.model_validate(payload)
    assert meta.schema_version == "1"
