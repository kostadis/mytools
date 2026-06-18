"""
Golden fixture integration test.

Uses synthetic in-memory artifacts to run the Extraction → Understanding → Notes
pipeline without browser capture or paid API calls.

Run with --live-api to enable real Claude API calls.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from notetaker.config import Config
from notetaker.contracts.frames_manifest import FrameEntry, FramesManifestSchema
from notetaker.contracts.transcript import TranscriptSchema, Utterance
from notetaker.contracts.slide_timeline import SlideTimelineSchema
from notetaker.contracts.slide_content import SlideContentSchema

URL = "https://zoom.us/rec/play/golden-fixture-001"


@pytest.fixture
def synthetic_cache(tmp_path) -> tuple[Path, Config]:
    """Set up a synthetic cache with frames_manifest.json and transcript.json."""
    cfg = Config()
    cfg.cache.cache_dir = str(tmp_path)
    cfg.understanding.budget_ceiling_usd = 0.0  # Force OCR fallback — no real API calls

    from notetaker.cache import Cache
    cache = Cache(tmp_path, URL)
    cache.initialise()

    # Create two synthetic JPEG frames (different solid colours → two slides)
    frames_dir = cache.stage_dir("capture") / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    frames = []
    for i, colour in enumerate([(200, 200, 200), (50, 100, 150)]):
        img = Image.new("RGB", (800, 600), color=colour)
        frame_path = frames_dir / f"{i * 5000}.jpg"
        img.save(str(frame_path), "JPEG")
        frames.append(FrameEntry(timestamp_ms=i * 5000, file_path=str(frame_path)))

    manifest = FramesManifestSchema(recording_url=URL, frames=frames)
    manifest_path = cache.artifact_path("capture", "frames_manifest.json")
    manifest_path.write_text(manifest.model_dump_json(indent=2))

    transcript = TranscriptSchema(
        recording_url=URL,
        captured_at="2026-05-08T10:00:00Z",
        utterances=[
            Utterance(start_seconds=1.0, end_seconds=4.0, speaker="Alice", text="Welcome to the Q1 review."),
            Utterance(start_seconds=6.0, end_seconds=9.0, speaker="Bob", text="Revenue is up 15%."),
            Utterance(start_seconds=11.0, end_seconds=14.0, speaker="Alice", text="Let's action the growth plan."),
        ],
    )
    transcript_path = cache.artifact_path("capture", "transcript.json")
    transcript_path.write_text(transcript.model_dump_json(indent=2))

    return tmp_path, cfg


@pytest.mark.asyncio
async def test_extraction_produces_slide_timeline(synthetic_cache):
    """Extraction stage produces valid slide_timeline.json from synthetic frames."""
    cache_root, cfg = synthetic_cache
    import asyncio
    from notetaker.stages.extraction import run as run_extraction

    result = await run_extraction(URL, cfg)
    assert result.total_slides >= 1

    from notetaker.cache import Cache
    cache = Cache(cache_root, URL)
    timeline_path = cache.artifact_path("extraction", "slide_timeline.json")
    assert timeline_path.exists()

    timeline = SlideTimelineSchema.model_validate(json.loads(timeline_path.read_text()))
    assert len(timeline.slides) >= 1


@pytest.mark.asyncio
async def test_understanding_produces_slide_content(synthetic_cache):
    """Understanding stage produces valid slide_content.json (OCR fallback, no API calls)."""
    cache_root, cfg = synthetic_cache

    from notetaker.stages.extraction import run as run_extraction
    from notetaker.stages.understanding import run as run_understanding

    await run_extraction(URL, cfg)
    result = await run_understanding(URL, cfg)

    assert result.ocr_count >= 1

    from notetaker.cache import Cache
    cache = Cache(cache_root, URL)
    content_path = cache.artifact_path("understanding", "slide_content.json")
    assert content_path.exists()

    content = SlideContentSchema.model_validate(json.loads(content_path.read_text()))
    assert len(content.slides) >= 1


@pytest.mark.asyncio
async def test_notes_produces_markdown(synthetic_cache):
    """
    Full post-capture pipeline: extraction → understanding (OCR) → notes (mocked).

    Asserts notes.md and working_doc.md are written to <cache>/<hash>/notes/
    and that the notes file contains the mocked LLM render output.
    """
    cache_root, cfg = synthetic_cache

    from notetaker.stages.extraction import run as run_extraction
    from notetaker.stages.understanding import run as run_understanding
    from notetaker.notes import NotesMode, run_notes

    await run_extraction(URL, cfg)
    await run_understanding(URL, cfg)

    # Mock anthropic.Anthropic. The mocked client must distinguish the render
    # prompt (returns Markdown) from the post-render summary prompt (returns
    # JSON {"summary": "..."}).
    mock_notes_text = (
        "# Synthetic Q1 Review\n\n"
        "## Attendees\n\n- Alice\n- Bob\n\n"
        "## Decisions\n\n- Approved Q1 budget.\n\n"
        "## Action items\n\n- Execute the growth plan.\n"
    )
    fixture_summary = "Q1 review, growth plan"

    def _create(**kwargs):
        prompt = kwargs.get("messages", [{}])[0].get("content", "")
        if "Read the meeting notes" in prompt:
            return SimpleNamespace(
                content=[SimpleNamespace(
                    text=json.dumps({"summary": fixture_summary})
                )],
                usage=SimpleNamespace(input_tokens=80, output_tokens=10),
            )
        return SimpleNamespace(
            content=[SimpleNamespace(text=mock_notes_text)],
            usage=SimpleNamespace(input_tokens=120, output_tokens=60),
        )

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = _create

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = run_notes(
            recording_arg=URL,
            transcript_path=None,  # Use the cached transcript.json from the fixture.
            mode=NotesMode.FULL,
            config=cfg,
            force=False,
            output_path=None,
        )

    import re
    assert result.working_doc_path.exists()
    assert result.notes_path is not None and result.notes_path.exists()
    assert result.notes_path.read_text() == mock_notes_text
    # Spec 005: the notes file lives at the human-readable path, not notes.md.
    assert re.match(r"^\d{4}-\d{2}-\d{2}--.+--.+\.md$", result.notes_path.name)
    assert result.render is not None
    # Combined render + summary tokens.
    assert result.render.total_input_tokens == 120 + 80
    assert result.render.total_output_tokens == 60 + 10

    # Spec 005: meta.json must be v2 with summary populated after the run.
    from notetaker.cache import Cache
    from notetaker.contracts.recording_meta import (
        CURRENT_SCHEMA_VERSION,
        RecordingMetaSchema,
    )
    cache = Cache(cache_root, URL)
    meta = RecordingMetaSchema.from_path(cache.root / "meta.json")
    assert meta.schema_version == CURRENT_SCHEMA_VERSION
    assert meta.summary == fixture_summary
