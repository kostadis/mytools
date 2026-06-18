"""Tests for RecordingMetaSchema (spec 005, T004)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from notetaker.contracts.recording_meta import (
    CURRENT_SCHEMA_VERSION,
    RecordingMetaSchema,
)


def test_lenient_v1_read(tmp_path):
    """A legacy meta.json with only {recording_url, created_at} loads as v1."""
    p = tmp_path / "meta.json"
    p.write_text(json.dumps({
        "recording_url": "https://zoom.us/rec/share/abc",
        "created_at": "2026-04-15T10:00:00+00:00",
    }))

    meta = RecordingMetaSchema.from_path(p)

    assert meta.schema_version == "1"
    assert meta.recording_url == "https://zoom.us/rec/share/abc"
    assert meta.meeting_title is None
    assert meta.recording_date is None
    assert meta.summary is None


def test_v2_round_trip(tmp_path):
    p = tmp_path / "meta.json"
    original = RecordingMetaSchema(
        recording_url="https://zoom.us/rec/share/xyz",
        created_at="2026-05-10T08:30:00+00:00",
        meeting_title="Q2 Planning Sync",
        recording_date="2026-04-15",
        summary="Roadmap, headcount, OKRs",
    )
    original.write(p)

    reloaded = RecordingMetaSchema.from_path(p)
    assert reloaded.schema_version == CURRENT_SCHEMA_VERSION
    assert reloaded.meeting_title == "Q2 Planning Sync"
    assert reloaded.recording_date == "2026-04-15"
    assert reloaded.summary == "Roadmap, headcount, OKRs"


def test_write_upgrades_v1_to_v2(tmp_path):
    """Reading a legacy v1 file then writing produces a v2 on disk."""
    p = tmp_path / "meta.json"
    p.write_text(json.dumps({
        "recording_url": "https://zoom.us/rec/share/abc",
        "created_at": "2026-04-15T10:00:00+00:00",
    }))

    meta = RecordingMetaSchema.from_path(p)
    assert meta.schema_version == "1"

    meta.write(p)

    on_disk = json.loads(p.read_text())
    assert on_disk["schema_version"] == CURRENT_SCHEMA_VERSION
    assert on_disk["meeting_title"] is None


def test_unknown_schema_version_raises(tmp_path):
    p = tmp_path / "meta.json"
    p.write_text(json.dumps({
        "schema_version": "3",
        "recording_url": "https://zoom.us/rec/share/abc",
        "created_at": "2026-04-15T10:00:00+00:00",
    }))

    with pytest.raises(ValidationError):
        RecordingMetaSchema.from_path(p)


def test_malformed_recording_date_raises():
    with pytest.raises(ValidationError):
        RecordingMetaSchema(
            recording_url="https://zoom.us/rec/share/abc",
            created_at="2026-04-15T10:00:00+00:00",
            recording_date="2026/04/15",
        )


def test_empty_meeting_title_normalised_to_none():
    meta = RecordingMetaSchema(
        recording_url="https://zoom.us/rec/share/abc",
        created_at="2026-04-15T10:00:00+00:00",
        meeting_title="   ",
    )
    assert meta.meeting_title is None


def test_empty_summary_normalised_to_none():
    meta = RecordingMetaSchema(
        recording_url="https://zoom.us/rec/share/abc",
        created_at="2026-04-15T10:00:00+00:00",
        summary="",
    )
    assert meta.summary is None


def test_recording_url_required():
    with pytest.raises(ValidationError):
        RecordingMetaSchema(
            recording_url="",
            created_at="2026-04-15T10:00:00+00:00",
        )
