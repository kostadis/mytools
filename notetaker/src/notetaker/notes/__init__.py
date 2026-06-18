"""
Orchestrator for the post-capture `notetaker notes` flow:
  parse_transcript_file -> build_working_doc -> render_notes
plus the re-render and dry-run modes that bypass parts of that pipeline.

The CLI surface in src/notetaker/cli.py delegates to `run_notes()` here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from notetaker.cache import Cache
from notetaker.config import Config
from notetaker.contracts.slide_content import SlideContentSchema
from notetaker.contracts.transcript import TranscriptSchema
from notetaker.notes.naming import derive_notes_filename
from notetaker.notes.render import RenderFailedError, RenderResult, render_notes
from notetaker.notes.summary import SummaryResult, generate_summary
from notetaker.notes.working_doc import build_working_doc
from notetaker.stages.capture.adapters.zoom_transcript_parsers import (
    parse_transcript_file,
)
from notetaker.utils.logging import get_logger

logger = get_logger(__name__)


class NotesMode(str, Enum):
    FULL = "full"
    RE_RENDER = "re_render"
    DRY_RUN = "dry_run"


@dataclass
class NotesRunResult:
    mode: NotesMode
    working_doc_path: Path
    notes_path: Path | None
    render: RenderResult | None
    cost_usd: float


class NotesError(RuntimeError):
    """Raised for user-facing notes-command errors that should produce a clean exit."""


def _resolve_cache(recording_arg: str, config: Config) -> Cache:
    """Resolve a recording URL or a 16-char cache id to a Cache instance."""
    cache_root = config.cache_dir_path
    arg = recording_arg.strip()
    if "/" not in arg and len(arg) == 16:
        # Looks like a cache id (URL hash). Locate the existing meta.json to
        # recover the recording_url, then construct the Cache around it.
        candidate = cache_root / arg
        meta = candidate / "meta.json"
        if not meta.exists():
            raise NotesError(
                f"No cache directory at {candidate} (no meta.json). "
                f"Pass the original recording URL instead, or run capture first."
            )
        url = json.loads(meta.read_text()).get("recording_url", arg)
        return Cache(cache_root, url)
    return Cache(cache_root, arg)


def _slide_content(cache: Cache) -> SlideContentSchema:
    path = cache.artifact_path("understanding", "slide_content.json")
    if not path.exists():
        raise NotesError(
            "slide_content.json missing at "
            f"{path} — run `notetaker understand <url>` first."
        )
    return SlideContentSchema.model_validate(json.loads(path.read_text()))


def _select_transcript(
    cache: Cache,
    transcript_path: Path | None,
) -> tuple[TranscriptSchema, str, Path]:
    """Return (transcript, format_label, source_path) following the FR-004 rules."""
    if transcript_path is not None:
        from notetaker.stages.capture.adapters.zoom_transcript_parsers import detect_format
        fmt = detect_format(transcript_path)
        ts = parse_transcript_file(transcript_path, recording_url=cache.recording_url)
        return ts, fmt, transcript_path

    cached = cache.artifact_path("capture", "transcript.json")
    if cached.exists():
        try:
            ts = TranscriptSchema.model_validate(json.loads(cached.read_text()))
        except Exception as exc:
            raise NotesError(
                f"Cached transcript.json at {cached} did not validate: {exc}. "
                f"Pass an explicit transcript file."
            ) from exc
        if ts.utterances:
            return ts, "transcript_json", cached

    raise NotesError(
        "No transcript provided and no usable cached transcript at "
        f"{cached}. See HOWTO.md \"Obtaining a transcript\" for the supported "
        "post-capture procedures (browser-scrape block format, WebVTT, or "
        "notetaker transcript.json)."
    )


def _resolve_human_readable_path(
    cache: Cache, config: Config, *, summary_override: str | None = None
) -> Path | None:
    """
    Compute the human-readable notes path for this cache entry. If ``summary_override``
    is provided, it replaces ``meta.summary`` in the derivation without writing meta
    (used post-render to compute the final write path).
    """
    meta = cache.read_meta()
    if meta is None:
        return None
    if summary_override is not None:
        meta = meta.model_copy(update={"summary": summary_override})
    name = derive_notes_filename(
        meta,
        max_chars=config.notes.filename_max_chars,
        summary_max_chars=config.notes.summary_max_chars,
    )
    return cache.notes_dir_path / name


def run_notes(
    recording_arg: str,
    transcript_path: Path | None,
    mode: NotesMode,
    config: Config,
    *,
    force: bool = False,
    output_path: Path | None = None,
    client=None,
) -> NotesRunResult:
    cache = _resolve_cache(recording_arg, config)
    notes_dir = cache.notes_dir
    working_doc_path = notes_dir / config.notes.working_doc_filename
    legacy_notes_path = notes_dir / config.notes.notes_filename  # "notes.md"

    # Pre-render existence check uses the human-readable path derived from the
    # cache entry's CURRENT meta (which may have summary=None on first run, or a
    # stale summary on re-run). Combined with the legacy notes.md fallback,
    # this covers every plausible target a prior run could have left behind.
    pre_render_target = _resolve_human_readable_path(cache, config)

    logger.info(
        "notes.command_start",
        event_category="command_start",
        recording_url_hash=cache._hash,
        mode=mode.value,
        model=config.resolved_notes_model(),
    )

    if mode == NotesMode.RE_RENDER:
        if not working_doc_path.exists():
            raise NotesError(
                f"Re-render requested but no working doc at {working_doc_path}. "
                f"Run `notetaker notes <url> <transcript>` (without --re-render) "
                f"first to produce one."
            )
        working_doc_text = working_doc_path.read_text()
    else:
        # Full or dry-run modes both go through assembly.
        slide_content = _slide_content(cache)
        transcript, fmt, src = _select_transcript(cache, transcript_path)
        logger.info(
            "notes.transcript_format_detected",
            format=fmt,
            path=str(src),
            utterance_count=len(transcript.utterances),
            speaker_count=len({u.speaker for u in transcript.utterances}),
        )
        working_doc_text = build_working_doc(slide_content, transcript)
        working_doc_path.write_text(working_doc_text)
        logger.info(
            "notes.working_doc_written",
            path=str(working_doc_path),
            slide_count=len(slide_content.slides),
            utterance_count=len(transcript.utterances),
            bytes=working_doc_path.stat().st_size,
        )

    if mode == NotesMode.DRY_RUN:
        wd_bytes = len(working_doc_text.encode("utf-8"))
        estimated_input_tokens = wd_bytes // 4
        # Floor projection: input tokens only, at the resolved model's input price.
        # Output is unknowable without making the call.
        from notetaker.notes.render import _SONNET_INPUT_PRICE_PER_MILLION
        projected = estimated_input_tokens / 1_000_000 * _SONNET_INPUT_PRICE_PER_MILLION
        logger.info(
            "notes.dry_run_estimate",
            working_doc_bytes=wd_bytes,
            estimated_input_tokens=estimated_input_tokens,
            model=config.resolved_notes_model(),
            projected_cost_usd_floor=projected,
        )
        return NotesRunResult(
            mode=mode,
            working_doc_path=working_doc_path,
            notes_path=None,
            render=None,
            cost_usd=projected,
        )

    # Existence guard. When --output is set we only protect that one explicit
    # path; otherwise we protect both the human-readable target derived from
    # current meta and any legacy notes.md left behind from before spec 005.
    if output_path is not None:
        candidates = [output_path] if output_path.exists() else []
    else:
        candidates = []
        if pre_render_target is not None and pre_render_target.exists():
            candidates.append(pre_render_target)
        if legacy_notes_path.exists() and legacy_notes_path not in candidates:
            candidates.append(legacy_notes_path)

    if candidates and not force:
        raise NotesError(
            f"Notes file already exists at {candidates[0]}. Pass --force to "
            f"overwrite or --output to choose a different path."
        )

    try:
        result = render_notes(working_doc_text, config, client=client)
    except RenderFailedError as exc:
        # FR-017: working doc is preserved; no notes file written.
        raise NotesError(str(exc)) from exc

    summary_result: SummaryResult = generate_summary(result.text, config, client=client)

    # Persist the summary into meta.json so the next run + the export command
    # both see it without re-calling Haiku. Lenient if meta is missing.
    meta = cache.read_meta()
    if meta is not None:
        meta = meta.model_copy(update={"summary": summary_result.text})
        meta.write(cache.root / "meta.json")

    # Compute the final write path now that the summary is known.
    if output_path is not None:
        final_path = output_path
    else:
        final_path = _resolve_human_readable_path(
            cache, config, summary_override=summary_result.text
        )
        if final_path is None:
            # meta.json is unreadable; fall back to the legacy filename so the
            # user still gets a notes file rather than a hard failure.
            final_path = legacy_notes_path

    logger.info(
        "notes.filename_derived",
        notes_filename=final_path.name,
        summary_outcome=summary_result.outcome,
        meeting_title=(meta.meeting_title if meta is not None else None),
    )

    # Pre-write cleanup: remove any stale or legacy file whose name differs
    # from `final_path`. A run with --force has already passed the consent gate.
    if output_path is None:
        if legacy_notes_path.exists() and legacy_notes_path != final_path:
            try:
                legacy_notes_path.unlink()
                logger.info(
                    "notes.legacy_renamed",
                    **{"from": str(legacy_notes_path), "to": str(final_path)},
                )
            except OSError:  # pragma: no cover
                pass
        if (
            pre_render_target is not None
            and pre_render_target != final_path
            and pre_render_target.exists()
        ):
            try:
                pre_render_target.unlink()
                logger.info(
                    "notes.filename_changed",
                    **{"from": str(pre_render_target), "to": str(final_path)},
                )
            except OSError:  # pragma: no cover
                pass

    final_path.write_text(result.text)

    total_cost = result.total_cost_usd + summary_result.total_cost_usd
    if (
        config.notes.cost_warn_threshold_usd > 0
        and total_cost > config.notes.cost_warn_threshold_usd
    ):
        logger.warning(
            "notes.cost_threshold_exceeded",
            cost_usd=total_cost,
            threshold_usd=config.notes.cost_warn_threshold_usd,
        )

    # Roll the summary call's cost into the returned RenderResult so the
    # CLI's existing `cost=$...` output reflects the full notes-stage spend.
    combined_result = RenderResult(
        text=result.text,
        model=result.model,
        total_attempts=result.total_attempts,
        total_input_tokens=result.total_input_tokens + summary_result.total_input_tokens,
        total_output_tokens=result.total_output_tokens + summary_result.total_output_tokens,
        total_cost_usd=total_cost,
        outcome=result.outcome,
    )

    return NotesRunResult(
        mode=mode,
        working_doc_path=working_doc_path,
        notes_path=final_path,
        render=combined_result,
        cost_usd=total_cost,
    )
