from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from notetaker.stages.capture.adapters.zoom_transcript_parsers import (
    UnsupportedTranscriptFormatError,
    detect_format,
    parse_transcript_file,
)

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "notes"
RECORDING_URL = "https://example.invalid/rec/play/synthetic-fixture-12345"


def _utterance_signature(transcript) -> list[tuple[float, str, str]]:
    return [(u.start_seconds, u.speaker, u.text) for u in transcript.utterances]


def test_three_shapes_produce_identical_signature():
    block = parse_transcript_file(FIXTURE_DIR / "transcript_block.txt", recording_url=RECORDING_URL)
    vtt = parse_transcript_file(FIXTURE_DIR / "transcript.vtt", recording_url=RECORDING_URL)
    js = parse_transcript_file(FIXTURE_DIR / "transcript.json")

    sig_block = _utterance_signature(block)
    sig_vtt = _utterance_signature(vtt)
    sig_json = _utterance_signature(js)

    assert sig_block == sig_vtt == sig_json
    assert len(sig_block) == 12


def test_block_continuation_inherits_speaker_and_start():
    transcript = parse_transcript_file(
        FIXTURE_DIR / "transcript_block.txt", recording_url=RECORDING_URL
    )
    # First two utterances are Alex at 0:02 — second one is a continuation.
    u0, u1 = transcript.utterances[0], transcript.utterances[1]
    assert u0.speaker == u1.speaker == "Alex"
    assert u0.start_seconds == u1.start_seconds == 2.0


def test_vtt_no_voice_tag_defaults_to_unknown(tmp_path):
    src = (FIXTURE_DIR / "transcript.vtt").read_text()
    # Strip every <v ...> wrapper.
    stripped = src.replace("<v Alex>", "").replace("<v Bo>", "").replace("<v Cam>", "")
    out = tmp_path / "no_voice.vtt"
    out.write_text(stripped)
    transcript = parse_transcript_file(out, recording_url=RECORDING_URL)
    assert all(u.speaker == "Unknown" for u in transcript.utterances)
    assert len(transcript.utterances) == 12


def test_detection_is_content_first_not_extension(tmp_path):
    # A .txt file that contains valid VTT content must still be parsed as VTT.
    misnamed = tmp_path / "actually_vtt.txt"
    shutil.copy(FIXTURE_DIR / "transcript.vtt", misnamed)
    assert detect_format(misnamed) == "vtt"
    transcript = parse_transcript_file(misnamed, recording_url=RECORDING_URL)
    assert len(transcript.utterances) == 12


def test_unrecognised_input_raises_with_documented_message(tmp_path):
    unknown = tmp_path / "garbage.dat"
    unknown.write_text("just some random words with no structure at all\n")
    with pytest.raises(UnsupportedTranscriptFormatError) as exc:
        parse_transcript_file(unknown)
    msg = str(exc.value)
    assert "Unsupported transcript format" in msg
    assert "browser-scrape block format" in msg
    assert "WebVTT" in msg
    assert "transcript.json" in msg
    assert "HOWTO.md" in msg


def test_trailing_whitespace_tolerated(tmp_path):
    src = (FIXTURE_DIR / "transcript_block.txt").read_text()
    out = tmp_path / "trailing.txt"
    out.write_text(src + "\n\n\n----\n\n\n   \n")
    transcript = parse_transcript_file(out, recording_url=RECORDING_URL)
    assert len(transcript.utterances) == 12


def test_transcript_json_passthrough_preserves_recording_url():
    transcript = parse_transcript_file(FIXTURE_DIR / "transcript.json")
    # transcript.json carries its own recording_url; the recording_url arg is ignored.
    assert transcript.recording_url == RECORDING_URL


def test_block_format_with_no_separator_but_speaker_header_detected(tmp_path):
    # Single-block file; no separator, but first non-blank line is followed by a timestamp.
    src = "Alex\n00:00:02\nHello world.\n"
    out = tmp_path / "single_block.txt"
    out.write_text(src)
    transcript = parse_transcript_file(out, recording_url=RECORDING_URL)
    assert len(transcript.utterances) == 1
    assert transcript.utterances[0].speaker == "Alex"
    assert transcript.utterances[0].start_seconds == 2.0


def test_block_format_accepts_mm_ss_timestamps(tmp_path):
    # Zoom's transcript panel emits MM:SS for sub-1h recordings; the documented
    # browser snippet harvests that shape verbatim. Parser must accept it and
    # treat the leading group as minutes (zero hours).
    src = (
        "Alex\n00:02\nHello.\n\n----\n\n"
        "Continuation line under Alex.\n\n----\n\n"
        "Bo\n00:30\nHi back.\n"
    )
    out = tmp_path / "mmss.txt"
    out.write_text(src)
    transcript = parse_transcript_file(out, recording_url=RECORDING_URL)
    assert [(u.start_seconds, u.speaker, u.text) for u in transcript.utterances] == [
        (2.0, "Alex", "Hello."),
        (2.0, "Alex", "Continuation line under Alex."),
        (30.0, "Bo", "Hi back."),
    ]


def test_json_that_does_not_validate_falls_through_to_refusal(tmp_path):
    # Valid JSON but not the TranscriptSchema shape.
    out = tmp_path / "wrong_shape.json"
    out.write_text(json.dumps({"hello": "world"}))
    with pytest.raises(UnsupportedTranscriptFormatError):
        parse_transcript_file(out)
