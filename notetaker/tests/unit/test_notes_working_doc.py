"""
Tests for the deterministic working-doc builder. See contracts/working_doc.md
for the invariants this asserts.
"""

from __future__ import annotations

import json
from pathlib import Path

from notetaker.contracts.slide_content import SlideContent, SlideContentSchema
from notetaker.contracts.transcript import TranscriptSchema, Utterance
from notetaker.notes.working_doc import build_working_doc


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "notes"


def _load_fixture():
    sc = SlideContentSchema.model_validate(
        json.loads((FIXTURE_DIR / "slide_content.json").read_text())
    )
    ts = TranscriptSchema.model_validate(
        json.loads((FIXTURE_DIR / "transcript.json").read_text())
    )
    return sc, ts


def test_byte_for_byte_match_against_golden():
    sc, ts = _load_fixture()
    out = build_working_doc(sc, ts)
    expected = (FIXTURE_DIR / "working_doc.expected.md").read_text()
    assert out == expected


def test_idempotence():
    sc, ts = _load_fixture()
    a = build_working_doc(sc, ts)
    b = build_working_doc(sc, ts)
    assert a == b


def test_raw_ocr_fallback_for_empty_structure_slides():
    sc, ts = _load_fixture()
    out = build_working_doc(sc, ts)
    # s003 has empty title/bullets/visual but populated raw_ocr.
    assert "_Raw text on slide:_" in out
    assert "Block diagram showing capture -> extract -> understand -> synthesise" in out


def test_consecutive_same_speaker_same_start_share_one_header():
    """The two Alex utterances at 00:00:02 must collapse into a single
    `**Alex [00:00:02]**` header followed by both lines."""
    sc, ts = _load_fixture()
    out = build_working_doc(sc, ts)
    # Count occurrences of the Alex 00:00:02 header.
    assert out.count("**Alex [00:00:02]**") == 1
    # Both lines must appear in order under that header. Use substrings unique
    # to the transcript (the slide bullet text shares prefix words).
    idx_kick = out.index("Welcome everyone")
    idx_continuation = out.index("We're aiming to ship Phase 1")
    assert idx_kick < idx_continuation


def test_file_ends_with_exactly_one_newline():
    sc, ts = _load_fixture()
    out = build_working_doc(sc, ts)
    assert out.endswith("\n")
    assert not out.endswith("\n\n")


def test_no_slide_silently_dropped():
    sc, ts = _load_fixture()
    out = build_working_doc(sc, ts)
    for slide in sc.slides:
        # Every slide_id should appear in the working doc.
        assert f"`{slide.slide_id}`" in out


def test_no_utterance_silently_dropped():
    sc, ts = _load_fixture()
    out = build_working_doc(sc, ts)
    for u in ts.utterances:
        assert u.text in out


def test_slide_with_only_title_renders_without_empty_bullet_block():
    sc = SlideContentSchema(
        recording_url="x",
        total_cost_usd=0.0,
        budget_ceiling_usd=0.0,
        slides=[
            SlideContent(
                slide_id="s001",
                title="Just a title",
                bullets=[],
                visual_description="",
                raw_ocr="Just a title",
                extraction_method="vision",
                estimated_cost_usd=0.0,
            )
        ],
    )
    ts = TranscriptSchema(
        recording_url="x",
        captured_at="2026-01-01T00:00:00+00:00",
        utterances=[
            Utterance(start_seconds=0.0, end_seconds=5.0, speaker="A", text="hi.")
        ],
    )
    out = build_working_doc(sc, ts)
    # Should NOT contain "_Raw text on slide:_" or "_Visual:_" or any empty bullet line.
    assert "_Raw text on slide:_" not in out
    assert "_Visual:_" not in out
    assert "\n- \n" not in out
