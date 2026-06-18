import json
import pytest
from pydantic import ValidationError

from notetaker.contracts.slide_timeline import SlideTimelineSchema, SlideOccurrence, SCHEMA_VERSION

VALID_OCCURRENCE = {
    "slide_id": "s001",
    "start_seconds": 0.0,
    "end_seconds": 30.0,
    "frame_path": "capture/frames/0.jpg",
    "frame_hash": "abcdef1234567890",
    "frame_sha256": "a" * 64,
}

VALID_TIMELINE = {
    "schema_version": SCHEMA_VERSION,
    "recording_url": "https://zoom.us/rec/play/abc123",
    "slides": [VALID_OCCURRENCE],
}


def test_round_trip_valid():
    obj = SlideTimelineSchema.model_validate(VALID_TIMELINE)
    restored = SlideTimelineSchema.model_validate(json.loads(obj.model_dump_json()))
    assert restored == obj


def test_schema_version_const():
    with pytest.raises(ValidationError):
        SlideTimelineSchema.model_validate({**VALID_TIMELINE, "schema_version": "2.0"})


def test_frame_sha256_pattern():
    bad = {**VALID_OCCURRENCE, "frame_sha256": "short"}
    with pytest.raises(ValidationError):
        SlideOccurrence.model_validate(bad)


def test_frame_sha256_uppercase_rejected():
    bad = {**VALID_OCCURRENCE, "frame_sha256": "A" * 64}
    with pytest.raises(ValidationError):
        SlideOccurrence.model_validate(bad)


def test_end_before_start_rejected():
    bad = {**VALID_OCCURRENCE, "start_seconds": 30.0, "end_seconds": 10.0}
    with pytest.raises(ValidationError):
        SlideOccurrence.model_validate(bad)


def test_slide_id_pattern():
    bad = {**VALID_OCCURRENCE, "slide_id": "slide1"}
    with pytest.raises(ValidationError):
        SlideOccurrence.model_validate(bad)


def test_empty_slides_allowed():
    obj = SlideTimelineSchema.model_validate({**VALID_TIMELINE, "slides": []})
    assert obj.slides == []
