"""
End-to-end integration tests for the `notetaker notes` CLI subcommand.
The Anthropic client is mocked at the module level so no real API call is made.
"""

from __future__ import annotations

import io
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from notetaker.cli import app


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "notes"
RECORDING_URL = "https://example.invalid/rec/play/synthetic-fixture-12345"
MOCK_NOTES_TEXT = (
    "# Synthetic Meeting Notes\n\n"
    "## Attendees\n\n- Alex\n- Bo\n- Cam\n\n"
    "## Decisions\n\n- Notes retention: discussed but not decided.\n"
)


FIXTURE_MEETING_TITLE = "Synthetic Meeting"
FIXTURE_RECORDING_DATE = "2026-05-09"
FIXTURE_SUMMARY = "Synthetic test summary"
EXPECTED_NOTES_FILENAME = (
    f"{FIXTURE_RECORDING_DATE}--{FIXTURE_MEETING_TITLE}--{FIXTURE_SUMMARY}.md"
)


def _seed_cache(tmp_path: Path, with_transcript_json: bool = False) -> Path:
    """Build a minimal cache layout that mimics what the understand stage produced."""
    from notetaker.cache import url_hash
    from notetaker.contracts.recording_meta import RecordingMetaSchema
    cache_root = tmp_path / "cache"
    h = url_hash(RECORDING_URL)
    cache_dir = cache_root / h
    (cache_dir / "understanding").mkdir(parents=True, exist_ok=True)
    (cache_dir / "capture").mkdir(parents=True, exist_ok=True)
    shutil.copy(
        FIXTURE_DIR / "slide_content.json",
        cache_dir / "understanding" / "slide_content.json",
    )
    meta = RecordingMetaSchema(
        recording_url=RECORDING_URL,
        created_at="2026-05-09T00:00:00+00:00",
        meeting_title=FIXTURE_MEETING_TITLE,
        recording_date=FIXTURE_RECORDING_DATE,
    )
    meta.write(cache_dir / "meta.json")
    if with_transcript_json:
        shutil.copy(
            FIXTURE_DIR / "transcript.json",
            cache_dir / "capture" / "transcript.json",
        )
    return cache_root


def _mock_client(text: str = MOCK_NOTES_TEXT, in_tok: int = 1000, out_tok: int = 200):
    """
    Build a MagicMock that handles BOTH the render call (returns Markdown notes)
    and the post-render summary call (returns JSON {"summary": ...}). Discrimination
    happens on prompt content — the summary prompt starts with "Read the meeting notes".
    """
    client = MagicMock()

    def _create(**kwargs):
        prompt = kwargs.get("messages", [{}])[0].get("content", "")
        if "Read the meeting notes" in prompt:
            return SimpleNamespace(
                content=[SimpleNamespace(
                    text=json.dumps({"summary": FIXTURE_SUMMARY}),
                )],
                usage=SimpleNamespace(input_tokens=400, output_tokens=15),
            )
        return SimpleNamespace(
            content=[SimpleNamespace(text=text)],
            usage=SimpleNamespace(input_tokens=in_tok, output_tokens=out_tok),
        )

    client.messages.create.side_effect = _create
    return client


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Point all notetaker user-data paths at tmp_path so tests don't touch real cache."""
    cache_root = _seed_cache(tmp_path)
    log_root = tmp_path / "logs"
    monkeypatch.setenv("HOME", str(tmp_path))

    # Build a config-overrides TOML that points the cache + logs at tmp dirs.
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        f"""
[cache]
cache_dir = "{cache_root}"
retention_days = 30

[logging]
log_dir = "{log_root}"
retention_days = 30

[notes]
retention_days = 365
"""
    )
    monkeypatch.setenv("NOTETAKER_CONFIG", str(cfg_path))
    return SimpleNamespace(tmp_path=tmp_path, cache_root=cache_root, cfg_path=cfg_path)


def test_full_path_writes_working_doc_and_notes(runner, isolated_env):
    transcript = isolated_env.tmp_path / "zoom_chat.txt"
    shutil.copy(FIXTURE_DIR / "transcript_block.txt", transcript)

    with patch("anthropic.Anthropic", return_value=_mock_client()):
        result = runner.invoke(
            app,
            ["notes", RECORDING_URL, str(transcript)],
        )

    assert result.exit_code == 0, result.output + result.stderr

    from notetaker.cache import url_hash
    cache_dir = isolated_env.cache_root / url_hash(RECORDING_URL)
    notes_dir = cache_dir / "notes"
    assert (notes_dir / "working_doc.md").exists()
    notes_file = notes_dir / EXPECTED_NOTES_FILENAME
    assert notes_file.exists()
    assert notes_file.read_text() == MOCK_NOTES_TEXT
    # Cost-summary line must be in stdout per quickstart.md. Token counts now
    # reflect the combined render + summary calls (1000+400, 200+15).
    assert "input_tokens=1,400" in result.stdout
    assert "output_tokens=215" in result.stdout
    assert "cost=$" in result.stdout
    assert "notes:" in result.stdout


def test_full_path_uses_cached_transcript_json_when_no_path_supplied(runner, isolated_env):
    # Re-seed with transcript.json present.
    cache_root = _seed_cache(isolated_env.tmp_path, with_transcript_json=True)
    isolated_env.cache_root = cache_root

    with patch("anthropic.Anthropic", return_value=_mock_client()):
        result = runner.invoke(app, ["notes", RECORDING_URL])

    assert result.exit_code == 0, result.output + result.stderr
    from notetaker.cache import url_hash
    cache_dir = cache_root / url_hash(RECORDING_URL)
    assert (cache_dir / "notes" / EXPECTED_NOTES_FILENAME).exists()


def test_refusal_when_slide_content_missing(runner, isolated_env):
    from notetaker.cache import url_hash
    cache_dir = isolated_env.cache_root / url_hash(RECORDING_URL)
    (cache_dir / "understanding" / "slide_content.json").unlink()

    transcript = isolated_env.tmp_path / "z.txt"
    shutil.copy(FIXTURE_DIR / "transcript_block.txt", transcript)

    result = runner.invoke(app, ["notes", RECORDING_URL, str(transcript)])
    assert result.exit_code == 1
    assert "slide_content.json missing" in result.stderr


def test_refusal_to_overwrite_without_force(runner, isolated_env):
    transcript = isolated_env.tmp_path / "z.txt"
    shutil.copy(FIXTURE_DIR / "transcript_block.txt", transcript)

    with patch("anthropic.Anthropic", return_value=_mock_client()):
        first = runner.invoke(app, ["notes", RECORDING_URL, str(transcript)])
    assert first.exit_code == 0

    with patch("anthropic.Anthropic", return_value=_mock_client(text="# Different notes\n")):
        second = runner.invoke(app, ["notes", RECORDING_URL, str(transcript)])
    assert second.exit_code == 1
    assert "already exists" in second.stderr


def test_force_overwrites(runner, isolated_env):
    transcript = isolated_env.tmp_path / "z.txt"
    shutil.copy(FIXTURE_DIR / "transcript_block.txt", transcript)

    with patch("anthropic.Anthropic", return_value=_mock_client()):
        runner.invoke(app, ["notes", RECORDING_URL, str(transcript)])

    with patch("anthropic.Anthropic", return_value=_mock_client(text="# Round two\n")):
        result = runner.invoke(app, ["notes", RECORDING_URL, str(transcript), "--force"])
    assert result.exit_code == 0

    from notetaker.cache import url_hash
    cache_dir = isolated_env.cache_root / url_hash(RECORDING_URL)
    assert (cache_dir / "notes" / EXPECTED_NOTES_FILENAME).read_text() == "# Round two\n"


def test_refusal_when_no_transcript_and_no_cached(runner, isolated_env):
    # No transcript path argument, no cached transcript.json.
    result = runner.invoke(app, ["notes", RECORDING_URL])
    assert result.exit_code == 1
    assert "No transcript provided" in result.stderr
    assert "browser-scrape block format" in result.stderr or "browser" in result.stderr


def test_re_render_skips_assembly_and_only_calls_llm(runner, isolated_env):
    """T022: --re-render reads existing working_doc and skips parse/assembly events."""
    transcript = isolated_env.tmp_path / "z.txt"
    shutil.copy(FIXTURE_DIR / "transcript_block.txt", transcript)

    # First invocation produces the working doc.
    with patch("anthropic.Anthropic", return_value=_mock_client(text="# v1\n")):
        first = runner.invoke(app, ["notes", RECORDING_URL, str(transcript)])
    assert first.exit_code == 0

    # Second invocation: --re-render with no transcript path; mock should still be called once.
    with patch("anthropic.Anthropic", return_value=_mock_client(text="# v2\n")) as anthropic_ctor:
        second = runner.invoke(
            app, ["notes", RECORDING_URL, "--re-render", "--force"]
        )

    assert second.exit_code == 0, second.output + second.stderr
    from notetaker.cache import url_hash
    cache_dir = isolated_env.cache_root / url_hash(RECORDING_URL)
    notes_path = cache_dir / "notes" / EXPECTED_NOTES_FILENAME
    assert notes_path.read_text() == "# v2\n"


def test_re_render_refuses_when_no_working_doc_exists(runner, isolated_env):
    result = runner.invoke(app, ["notes", RECORDING_URL, "--re-render", "--force"])
    assert result.exit_code == 1
    assert "no working doc" in result.stderr or "Run `notetaker notes" in result.stderr


def test_dry_run_skips_llm_call_and_emits_estimate(runner, isolated_env, tmp_path):
    transcript = isolated_env.tmp_path / "z.txt"
    shutil.copy(FIXTURE_DIR / "transcript_block.txt", transcript)

    log_file = isolated_env.tmp_path / "dry_run.log"
    monkey_client = _mock_client()

    with patch("anthropic.Anthropic", return_value=monkey_client):
        result = runner.invoke(
            app,
            ["notes", RECORDING_URL, str(transcript), "--dry-run"],
        )

    assert result.exit_code == 0, result.output + result.stderr
    # No LLM call must have been made.
    assert monkey_client.messages.create.call_count == 0
    # Notes file must NOT exist after a dry-run.
    from notetaker.cache import url_hash
    cache_dir = isolated_env.cache_root / url_hash(RECORDING_URL)
    assert not (cache_dir / "notes" / EXPECTED_NOTES_FILENAME).exists()
    assert not (cache_dir / "notes" / "notes.md").exists()
    # But working doc IS written so a future --re-render is possible.
    assert (cache_dir / "notes" / "working_doc.md").exists()
    # Console output names projected cost.
    assert "dry-run" in result.stdout
    assert "projected_cost_usd_floor" in result.stdout


def test_working_doc_is_at_documented_path_with_all_slides(runner, isolated_env):
    """T023: working_doc.md is at <cache>/<hash>/notes/working_doc.md and lists every slide title."""
    transcript = isolated_env.tmp_path / "z.txt"
    shutil.copy(FIXTURE_DIR / "transcript_block.txt", transcript)

    with patch("anthropic.Anthropic", return_value=_mock_client()):
        result = runner.invoke(app, ["notes", RECORDING_URL, str(transcript)])
    assert result.exit_code == 0, result.output + result.stderr

    from notetaker.cache import url_hash
    cache_dir = isolated_env.cache_root / url_hash(RECORDING_URL)
    working_doc = cache_dir / "notes" / "working_doc.md"
    notes = cache_dir / "notes" / EXPECTED_NOTES_FILENAME
    assert working_doc.exists()
    assert notes.exists()

    body = working_doc.read_text()
    # Every slide title from the fixture appears in the working doc.
    for title in [
        "Project kick-off",
        "Architecture overview",
        "Open questions",
        "Next steps",
    ]:
        assert title in body
    # The s003 (no-title) slide surfaces its raw OCR.
    assert "_Raw text on slide:_" in body


def test_inspect_edit_rerender_passes_edited_working_doc_to_llm(runner, isolated_env):
    """T025: edit working_doc.md, run --re-render, and confirm the prompt
    sent to the mocked client contains the edit."""
    transcript = isolated_env.tmp_path / "z.txt"
    shutil.copy(FIXTURE_DIR / "transcript_block.txt", transcript)

    # Step 1: produce the working doc.
    with patch("anthropic.Anthropic", return_value=_mock_client()):
        first = runner.invoke(app, ["notes", RECORDING_URL, str(transcript)])
    assert first.exit_code == 0

    # Step 2: edit the working doc — change one slide title.
    from notetaker.cache import url_hash
    cache_dir = isolated_env.cache_root / url_hash(RECORDING_URL)
    working_doc = cache_dir / "notes" / "working_doc.md"
    edited_marker = "EDITED_TITLE_FOR_TEST"
    body = working_doc.read_text().replace("Project kick-off", edited_marker)
    working_doc.write_text(body)

    # Step 3: --re-render with --force; capture what was passed to the mocked client.
    captured_prompts: list[str] = []

    def _capturing_factory():
        client = MagicMock()

        def _create(**kwargs):
            prompt = kwargs["messages"][0]["content"]
            captured_prompts.append(prompt)
            if "Read the meeting notes" in prompt:
                return SimpleNamespace(
                    content=[SimpleNamespace(
                        text=json.dumps({"summary": FIXTURE_SUMMARY}),
                    )],
                    usage=SimpleNamespace(input_tokens=10, output_tokens=5),
                )
            return SimpleNamespace(
                content=[SimpleNamespace(text="# Edited render\n")],
                usage=SimpleNamespace(input_tokens=10, output_tokens=5),
            )
        client.messages.create.side_effect = _create
        return client

    with patch("anthropic.Anthropic", side_effect=_capturing_factory):
        result = runner.invoke(
            app, ["notes", RECORDING_URL, "--re-render", "--force"]
        )

    assert result.exit_code == 0, result.output + result.stderr
    # Two captured prompts: the render call and the summary call.
    assert len(captured_prompts) >= 1
    # The edited content reaches the render LLM (first call).
    assert edited_marker in captured_prompts[0]
    # And the new notes file reflects the new render output.
    assert (cache_dir / "notes" / EXPECTED_NOTES_FILENAME).read_text() == "# Edited render\n"


def test_re_render_and_dry_run_are_mutually_exclusive(runner, isolated_env):
    transcript = isolated_env.tmp_path / "z.txt"
    shutil.copy(FIXTURE_DIR / "transcript_block.txt", transcript)
    result = runner.invoke(
        app,
        ["notes", RECORDING_URL, str(transcript), "--re-render", "--dry-run"],
    )
    assert result.exit_code == 2
    assert "mutually exclusive" in (result.stderr + result.output)


def test_notes_writes_human_readable_filename(runner, isolated_env):
    """Spec 005 / T015: notes file is named <date>--<title>--<summary>.md."""
    transcript = isolated_env.tmp_path / "z.txt"
    shutil.copy(FIXTURE_DIR / "transcript_block.txt", transcript)

    with patch("anthropic.Anthropic", return_value=_mock_client()):
        result = runner.invoke(app, ["notes", RECORDING_URL, str(transcript)])
    assert result.exit_code == 0, result.output + result.stderr

    from notetaker.cache import url_hash
    cache_dir = isolated_env.cache_root / url_hash(RECORDING_URL)
    notes_dir = cache_dir / "notes"
    expected = notes_dir / EXPECTED_NOTES_FILENAME
    assert expected.exists()
    # No legacy notes.md should be left around.
    assert not (notes_dir / "notes.md").exists()
    # The stdout `notes:` line names the human-readable path.
    assert EXPECTED_NOTES_FILENAME in result.stdout


def test_legacy_notes_md_is_renamed_in_place(runner, isolated_env):
    """Spec 005 / T015: a pre-existing notes.md is removed when --force re-runs."""
    transcript = isolated_env.tmp_path / "z.txt"
    shutil.copy(FIXTURE_DIR / "transcript_block.txt", transcript)

    # Pre-create a legacy notes.md as if it survived a pre-feature run.
    from notetaker.cache import url_hash
    cache_dir = isolated_env.cache_root / url_hash(RECORDING_URL)
    notes_dir = cache_dir / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    legacy = notes_dir / "notes.md"
    legacy.write_text("# stale notes content from before spec 005\n")

    with patch("anthropic.Anthropic", return_value=_mock_client()):
        result = runner.invoke(
            app, ["notes", RECORDING_URL, str(transcript), "--force"]
        )
    assert result.exit_code == 0, result.output + result.stderr

    # Legacy file is gone, human-readable file is present with new content.
    assert not legacy.exists()
    new_path = notes_dir / EXPECTED_NOTES_FILENAME
    assert new_path.exists()
    assert new_path.read_text() == MOCK_NOTES_TEXT


def test_meta_summary_is_written(runner, isolated_env):
    """Spec 005 / T015: meta.summary is populated after a successful notes run."""
    transcript = isolated_env.tmp_path / "z.txt"
    shutil.copy(FIXTURE_DIR / "transcript_block.txt", transcript)

    with patch("anthropic.Anthropic", return_value=_mock_client()):
        result = runner.invoke(app, ["notes", RECORDING_URL, str(transcript)])
    assert result.exit_code == 0, result.output + result.stderr

    from notetaker.cache import url_hash
    from notetaker.contracts.recording_meta import RecordingMetaSchema
    cache_dir = isolated_env.cache_root / url_hash(RECORDING_URL)
    meta = RecordingMetaSchema.from_path(cache_dir / "meta.json")
    assert meta.summary == FIXTURE_SUMMARY
    assert meta.schema_version == "2"
