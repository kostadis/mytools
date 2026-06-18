"""
Cache-wide operations: export every rendered notes file out to a user-supplied
directory, and purge the entire cache root after explicit confirmation.

Both operations walk the cache via ``Cache.iter_entries`` so they share a
single source of truth about what counts as a legitimate cache entry.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from notetaker.cache import Cache
from notetaker.config import Config
from notetaker.notes.naming import derive_notes_filename
from notetaker.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ExportSummary:
    target_dir: Path
    copied: int
    skipped_no_notes: int
    skipped_collision: int
    legacy_resolved: int


@dataclass
class PurgeSummary:
    cache_root: Path
    entries_removed: int
    bytes_reclaimed: int
    cancelled: bool


def _entry_size(entry_dir: Path) -> int:
    total = 0
    for p in entry_dir.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def _resolve_source_notes_file(
    entry_dir: Path,
    meta,
    config: Config,
) -> tuple[Path | None, bool]:
    """
    Locate the notes file inside ``<entry_dir>/notes/`` and report whether it
    is a legacy ``notes.md`` (so the caller can count ``legacy_resolved``).

    Returns (path or None, is_legacy).
    """
    notes_dir = entry_dir / "notes"
    if not notes_dir.exists():
        return None, False

    derived_name = derive_notes_filename(
        meta,
        max_chars=config.notes.filename_max_chars,
        summary_max_chars=config.notes.summary_max_chars,
    )
    candidate = notes_dir / derived_name
    if candidate.exists():
        return candidate, False

    legacy = notes_dir / config.notes.notes_filename  # "notes.md"
    if legacy.exists():
        return legacy, True

    return None, False


def export_notes(
    cache_root: Path,
    target_dir: Path,
    config: Config,
    *,
    overwrite: bool = False,
) -> ExportSummary:
    """
    Copy every rendered notes file from ``cache_root`` into ``target_dir`` under
    its human-readable name. Cache copies are preserved (FR-011).

    Behaviour highlights:
      - Target directory is created (with parents) if missing (FR-012).
      - Entries with no notes file are skipped under ``skipped_no_notes``.
      - Destination collisions are skipped under ``skipped_collision`` unless
        ``overwrite=True``.
      - Legacy ``notes.md`` entries are mapped to a freshly-derived
        human-readable destination name (``legacy_resolved`` counts them).
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    target_dir = target_dir.resolve()

    summary = ExportSummary(
        target_dir=target_dir,
        copied=0,
        skipped_no_notes=0,
        skipped_collision=0,
        legacy_resolved=0,
    )

    for url_hash, meta in Cache.iter_entries(cache_root):
        entry_dir = cache_root / url_hash
        source, is_legacy = _resolve_source_notes_file(entry_dir, meta, config)

        if source is None:
            summary.skipped_no_notes += 1
            logger.info(
                "export.entry_skipped_no_notes",
                cache_id=url_hash,
            )
            continue

        dest_name = derive_notes_filename(
            meta,
            max_chars=config.notes.filename_max_chars,
            summary_max_chars=config.notes.summary_max_chars,
        )
        dest = target_dir / dest_name

        if dest.exists() and not overwrite:
            summary.skipped_collision += 1
            logger.info(
                "export.entry_skipped_collision",
                cache_id=url_hash,
                dest=str(dest),
                source=str(source),
            )
            continue

        shutil.copy2(source, dest)
        summary.copied += 1
        if is_legacy:
            summary.legacy_resolved += 1
        logger.info(
            "export.entry_copied",
            cache_id=url_hash,
            source=str(source),
            dest=str(dest),
            legacy=is_legacy,
        )

    logger.info(
        "export.summary",
        target_dir=str(target_dir),
        copied=summary.copied,
        skipped_no_notes=summary.skipped_no_notes,
        skipped_collision=summary.skipped_collision,
        legacy_resolved=summary.legacy_resolved,
    )
    return summary


def purge_cache(
    cache_root: Path,
    *,
    confirmed: bool,
) -> PurgeSummary:
    """
    Remove every per-recording entry under ``cache_root`` after explicit
    confirmation. The cache_root directory itself is preserved (so subsequent
    notetaker runs do not have to recreate it). Sibling directories of
    ``cache_root`` (for example ``logs/``) are NOT touched (FR-022).
    """
    summary = PurgeSummary(
        cache_root=cache_root,
        entries_removed=0,
        bytes_reclaimed=0,
        cancelled=False,
    )

    if not cache_root.exists():
        logger.info(
            "purge.summary",
            cache_root=str(cache_root),
            entries_removed=0,
            bytes_reclaimed=0,
            cancelled=False,
        )
        return summary

    if not confirmed:
        summary.cancelled = True
        logger.info(
            "purge.summary",
            cache_root=str(cache_root),
            entries_removed=0,
            bytes_reclaimed=0,
            cancelled=True,
        )
        return summary

    for url_hash, _meta in Cache.iter_entries(cache_root):
        entry_dir = cache_root / url_hash
        size = _entry_size(entry_dir)
        try:
            shutil.rmtree(entry_dir)
        except OSError as exc:
            logger.error(
                "purge.entry_remove_failed",
                cache_id=url_hash,
                error=str(exc),
            )
            continue
        summary.entries_removed += 1
        summary.bytes_reclaimed += size
        logger.info(
            "purge.entry_removed",
            cache_id=url_hash,
            bytes=size,
        )

    # Stray top-level files (no meta.json) — removed at debug level only.
    for child in cache_root.iterdir():
        if child.is_file():
            try:
                size = child.stat().st_size
                child.unlink()
                summary.bytes_reclaimed += size
                logger.debug("purge.stray_file_removed", path=str(child))
            except OSError:
                pass

    logger.info(
        "purge.summary",
        cache_root=str(cache_root),
        entries_removed=summary.entries_removed,
        bytes_reclaimed=summary.bytes_reclaimed,
        cancelled=False,
    )
    return summary
