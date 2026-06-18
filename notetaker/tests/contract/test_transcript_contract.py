import json
import pytest
from pydantic import ValidationError

from notetaker.contracts.transcript import TranscriptSchema, Utterance, SCHEMA_VERSION

VALID_UTTERANCE = {
    "start_seconds": 0.0,
    "end_seconds": 5.0,
    "speaker": "Alice",
    "text": "Hello everyone.",
}

VALID_TRANSCRIPT = {
    "schema_version": SCHEMA_VERSION,
    "recording_url": "https://zoom.us/rec/play/abc123",
    "captured_at": "2026-05-08T10:00:00Z",
    "utterances": [VALID_UTTERANCE],
    "transcript_unavailable": False,
}


def test_round_trip_valid():
    obj = TranscriptSchema.model_validate(VALID_TRANSCRIPT)
    serialised = json.loads(obj.model_dump_json())
    restored = TranscriptSchema.model_validate(serialised)
    assert restored == obj


def test_schema_version_const():
    bad = {**VALID_TRANSCRIPT, "schema_version": "2.0"}
    with pytest.raises(ValidationError):
        TranscriptSchema.model_validate(bad)


def test_missing_required_field():
    bad = {k: v for k, v in VALID_TRANSCRIPT.items() if k != "recording_url"}
    with pytest.raises(ValidationError):
        TranscriptSchema.model_validate(bad)


def test_end_before_start_rejected():
    bad_utt = {**VALID_UTTERANCE, "start_seconds": 5.0, "end_seconds": 2.0}
    with pytest.raises(ValidationError):
        Utterance.model_validate(bad_utt)


def test_equal_start_end_rejected():
    bad_utt = {**VALID_UTTERANCE, "start_seconds": 3.0, "end_seconds": 3.0}
    with pytest.raises(ValidationError):
        Utterance.model_validate(bad_utt)


def test_empty_text_rejected():
    bad_utt = {**VALID_UTTERANCE, "text": "   "}
    with pytest.raises(ValidationError):
        Utterance.model_validate(bad_utt)


def test_empty_utterances_allowed():
    payload = {**VALID_TRANSCRIPT, "utterances": [], "transcript_unavailable": True}
    obj = TranscriptSchema.model_validate(payload)
    assert obj.utterances == []
    assert obj.transcript_unavailable is True
