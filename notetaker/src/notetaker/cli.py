from __future__ import annotations

import sys

import typer

from notetaker.cache import Cache
from notetaker.config import load_config
from notetaker.utils.heartbeat import HeartbeatTracker
from notetaker.utils.log_store import LogStore
from notetaker.utils.logging import configure_logging

app = typer.Typer(
    name="notetaker",
    help="Extract slides and transcripts from streamed meeting recordings.",
    no_args_is_help=True,
)


def _setup(debug: bool, force: bool, config_path: str | None):
    cfg = load_config()
    if debug:
        cfg.logging.level = "DEBUG"

    store = LogStore(cfg.log_dir_path, cfg.logging.retention_days)
    run_log_path = store.start_run(recording_url_hash=None)

    log_file_path = None if str(run_log_path) == "/dev/null" else run_log_path
    configure_logging(
        level=cfg.logging.level,
        fmt=cfg.logging.format,
        file_path=log_file_path,
    )

    if log_file_path is not None:
        print(f"[notetaker] Logging to {log_file_path}", file=sys.stderr)

    store.purge_stale()

    cfg._log_store = store  # type: ignore[attr-defined]
    cfg._heartbeat_tracker = HeartbeatTracker(  # type: ignore[attr-defined]
        cfg.logging.heartbeat_interval_seconds
    )

    Cache.purge_stale(
        cfg.cache_dir_path,
        cfg.cache.retention_days,
        notes_retention_days=cfg.notes.retention_days,
    )
    return cfg


@app.command()
def capture(
    url: str = typer.Argument(..., help="Zoom viewer URL"),
    debug: bool = typer.Option(False, "--debug", help="Preserve intermediates, verbose logging"),
    force: bool = typer.Option(False, "--force", help="Re-run even if cached output exists"),
):
    """Stage 1: Screen-record frames and scrape transcript during browser playback."""
    import asyncio
    from notetaker.stages.capture.adapters.zoom import ZoomAdapter

    cfg = _setup(debug, force, None)
    adapter = ZoomAdapter(cfg, debug=debug, force=force)
    frames_path, transcript_path = asyncio.run(adapter.capture(url))
    typer.echo(f"Capture complete.\n  frames_manifest : {frames_path}\n  transcript      : {transcript_path}")


@app.command()
def extract(
    url: str = typer.Argument(..., help="Zoom viewer URL (used to locate cached frames)"),
    debug: bool = typer.Option(False, "--debug"),
    force: bool = typer.Option(False, "--force"),
):
    """Stage 2: Detect slide transitions from captured frames and produce a slide timeline."""
    import asyncio
    from notetaker.stages.extraction import run as run_extraction

    cfg = _setup(debug, force, None)
    result = asyncio.run(run_extraction(url, cfg, force=force))
    typer.echo(
        f"Extraction complete.\n"
        f"  slides          : {result.total_slides}\n"
        f"  unique slides   : {result.unique_slides}\n"
        f"  output          : {result.output_path}"
    )


@app.command()
def understand(
    url: str = typer.Argument(..., help="Zoom viewer URL (used to locate cached slide timeline)"),
    debug: bool = typer.Option(False, "--debug"),
    force: bool = typer.Option(False, "--force"),
):
    """Stage 3: Extract content from each unique slide via vision LLM (with OCR fallback)."""
    import asyncio
    from notetaker.stages.understanding import run as run_understanding

    cfg = _setup(debug, force, None)
    result = asyncio.run(run_understanding(url, cfg, force=force, debug=debug))
    typer.echo(
        f"Understanding complete.\n"
        f"  vision          : {result.vision_count}\n"
        f"  OCR fallback    : {result.ocr_count}\n"
        f"  total cost      : ${result.total_cost_usd:.4f}\n"
        f"  output          : {result.output_path}"
    )
    if result.ocr_count > 0:
        typer.echo(
            typer.style(
                f"  WARNING: {result.ocr_count} slide(s) used OCR fallback (budget ceiling reached).",
                fg=typer.colors.YELLOW,
            )
        )


@app.command()
def notes(
    recording: str = typer.Argument(
        ...,
        help="Recording URL or 16-character cache id (notetaker resolves it the same way as elsewhere).",
    ),
    transcript_path: str = typer.Argument(
        None,
        help="Path to a transcript file (browser-scrape block format, .vtt, or notetaker transcript.json). "
             "Omit to use the cached transcript.json from a successful live capture.",
    ),
    output: str = typer.Option(
        None,
        "--output",
        "-o",
        help="Override the default notes path inside the cache.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite an existing notes file.",
    ),
    re_render: bool = typer.Option(
        False,
        "--re-render",
        help="Skip parse + assembly; reuse the existing working_doc.md and only re-run the LLM call.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Assemble the working doc and report projected cost; do not call the LLM.",
    ),
    debug: bool = typer.Option(False, "--debug"),
):
    """Combine extracted slides with a transcript and render polished Markdown notes via one LLM call."""
    from pathlib import Path
    from notetaker.notes import NotesError, NotesMode, run_notes

    cfg = _setup(debug, force=False, config_path=None)

    if re_render and dry_run:
        typer.echo("--re-render and --dry-run are mutually exclusive.", err=True)
        raise typer.Exit(2)

    mode = (
        NotesMode.RE_RENDER if re_render
        else NotesMode.DRY_RUN if dry_run
        else NotesMode.FULL
    )
    transcript = Path(transcript_path).expanduser() if transcript_path else None
    output_p = Path(output).expanduser() if output else None

    try:
        result = run_notes(
            recording_arg=recording,
            transcript_path=transcript,
            mode=mode,
            config=cfg,
            force=force,
            output_path=output_p,
        )
    except NotesError as exc:
        typer.echo(f"[notetaker notes] {exc}", err=True)
        raise typer.Exit(1)

    typer.echo(f"working_doc: {result.working_doc_path}  ({result.working_doc_path.stat().st_size:,} bytes)")
    if result.mode == NotesMode.DRY_RUN:
        typer.echo(
            f"dry-run: model={cfg.resolved_notes_model()}  "
            f"projected_cost_usd_floor=${result.cost_usd:.4f}"
        )
        return

    r = result.render
    typer.echo(
        f"input_tokens={r.total_input_tokens:,}  "
        f"output_tokens={r.total_output_tokens:,}  "
        f"cost=${r.total_cost_usd:.4f}"
    )
    typer.echo(f"notes: {result.notes_path}")


@app.command()
def export(
    directory: str = typer.Argument(
        ...,
        help="Target directory. Created (with parents) if missing.",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Replace existing files in the target directory. "
             "Default behaviour preserves existing files and reports collisions.",
    ),
    debug: bool = typer.Option(False, "--debug"),
):
    """Copy every cached notes file into <directory> under its human-readable name."""
    from pathlib import Path
    from notetaker.cache_ops import export_notes

    cfg = _setup(debug, force=False, config_path=None)
    target = Path(directory).expanduser().resolve()

    summary = export_notes(cfg.cache_dir_path, target, cfg, overwrite=overwrite)

    typer.echo(f"exported to: {summary.target_dir}")
    typer.echo(
        f"copied={summary.copied}  skipped_no_notes={summary.skipped_no_notes}"
        f"  skipped_collision={summary.skipped_collision}"
        f"  legacy_resolved={summary.legacy_resolved}"
    )


@app.command()
def purge(
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Skip the interactive confirmation prompt. Required for non-interactive use.",
    ),
    debug: bool = typer.Option(False, "--debug"),
):
    """Delete the entire notetaker cache. Requires confirmation; pass --yes for scripts."""
    import sys as _sys
    from notetaker.cache import Cache
    from notetaker.cache_ops import purge_cache

    cfg = _setup(debug, force=False, config_path=None)
    cache_root = cfg.cache_dir_path

    # Pre-flight summary so the user sees scope before confirming.
    entries = list(Cache.iter_entries(cache_root))
    total_bytes = 0
    for url_hash, _meta in entries:
        for p in (cache_root / url_hash).rglob("*"):
            if p.is_file():
                try:
                    total_bytes += p.stat().st_size
                except OSError:
                    pass
    typer.echo(
        f"Cache: {cache_root}  ;  entries={len(entries)}  ;  total_size={total_bytes} bytes"
    )

    if not entries:
        result = purge_cache(cache_root, confirmed=False)  # short-circuit no-op
        typer.echo(f"purged: {cache_root}")
        typer.echo("entries_removed=0  bytes_reclaimed=0")
        return

    if yes:
        confirmed = True
    else:
        try:
            confirmed = typer.confirm("Proceed?", default=False)
        except (EOFError, typer.Abort):
            typer.echo(
                "[notetaker purge] Refusing to purge non-interactively without --yes",
                err=True,
            )
            raise typer.Exit(1)

    if not confirmed:
        typer.echo("purge cancelled")
        return

    summary = purge_cache(cache_root, confirmed=True)
    typer.echo(f"purged: {summary.cache_root}")
    typer.echo(
        f"entries_removed={summary.entries_removed}  "
        f"bytes_reclaimed={summary.bytes_reclaimed}"
    )


@app.command()
def run(
    url: str = typer.Argument(..., help="Zoom viewer URL"),
    debug: bool = typer.Option(False, "--debug"),
    force: bool = typer.Option(False, "--force"),
):
    """Chain the unattended stages in order: capture → extract → understand."""
    import asyncio

    cfg = _setup(debug, force, None)

    from notetaker.cache import Cache
    from notetaker.stages.capture.adapters.zoom import ZoomAdapter
    from notetaker.stages.extraction import run as run_extraction
    from notetaker.stages.understanding import run as run_understanding

    adapter = ZoomAdapter(cfg, debug=debug, force=force)
    asyncio.run(adapter.capture(url))

    asyncio.run(run_extraction(url, cfg, force=force))
    asyncio.run(run_understanding(url, cfg, force=force, debug=debug))

    cache_root = Cache(cfg.cache_dir_path, recording_url=url).root
    typer.echo(
        f"\nPipeline complete (capture + extract + understand). Cache: {cache_root}\n"
        f"Next: notetaker notes \"{url}\" <transcript-file>\n"
        f"       (or omit <transcript-file> to use the cached transcript.json from a successful live capture)"
    )


def _invoke_with_crash_capture(invoke):
    """Run `invoke` (a zero-arg callable) with top-level exception capture.

    Any non-SystemExit / non-ClickException exception raised inside `invoke`
    is recorded to the run log as an `unhandled_exception` record before
    being re-raised, satisfying SC-003 / FR-008. Click's own user-error
    exceptions are passed through to its own renderer unchanged so the
    terminal output is unaffected (FR-011).
    """
    import traceback
    import click
    from notetaker.utils.logging import get_logger

    try:
        return invoke()
    except SystemExit:
        raise
    except click.exceptions.ClickException as exc:
        exc.show()
        sys.exit(exc.exit_code)
    except (click.exceptions.Abort, KeyboardInterrupt) as exc:
        get_logger(__name__).error(
            "cli.unhandled_exception",
            event_category="unhandled_exception",
            exc_type=type(exc).__name__,
            traceback=traceback.format_exc(),
            message=str(exc),
        )
        sys.exit(1)
    except BaseException as exc:
        get_logger(__name__).error(
            "cli.unhandled_exception",
            event_category="unhandled_exception",
            exc_type=type(exc).__name__,
            traceback=traceback.format_exc(),
            message=str(exc),
        )
        raise


def main():
    """Entry point. See `_invoke_with_crash_capture` for the rationale.

    We invoke the underlying click command with `standalone_mode=False` so
    non-Click exceptions raised inside subcommand bodies (e.g. FileNotFoundError
    when the user runs `extract` before `capture`) propagate to our catch
    instead of being swallowed by click's own error handler.
    """
    from typer.main import get_command
    command = get_command(app)
    return _invoke_with_crash_capture(lambda: command(standalone_mode=False))
