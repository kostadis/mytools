from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from notetaker.contracts.recording_meta import RecordingMetaSchema
from notetaker.utils.logging import get_logger

logger = get_logger(__name__)

_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "_ga",
})

STAGE_SUBDIRS = {
    "capture": "capture",
    "extraction": "extraction",
    "understanding": "understanding",
}

# Reserved subdirectory under a cache root for the post-capture notes feature.
# Subject to its own retention (`[notes] retention_days`), exempt from the standard
# cache retention purge (FR-018).
NOTES_SUBDIR = "notes"


def normalise_url(url: str) -> str:
    """Strip tracking query parameters and normalise the URL for stable cache keying."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    filtered = {k: v for k, v in qs.items() if k not in _TRACKING_PARAMS}
    clean_query = urlencode(filtered, doseq=True)
    normalised = urlunparse(parsed._replace(query=clean_query, fragment=""))
    return normalised


def url_hash(url: str) -> str:
    """Return a 16-character hex prefix of the SHA-256 of the normalised URL."""
    clean = normalise_url(url)
    return hashlib.sha256(clean.encode()).hexdigest()[:16]


class Cache:
    """
    URL-keyed artifact cache.

    Layout under cache_root:
        <url_hash>/
            meta.json          — {recording_url, created_at}
            capture/           — frames + transcript
            extraction/        — slide_timeline.json
            understanding/     — slide_content.json
            notes/             — working_doc.md, notes.md (separate retention knob)
    """

    def __init__(self, cache_root: Path, recording_url: str, force: bool = False):
        self.recording_url = recording_url
        self._hash = url_hash(recording_url)
        self.root = cache_root / self._hash
        self.force = force

    def stage_dir(self, stage: str) -> Path:
        path = self.root / STAGE_SUBDIRS[stage]
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def notes_dir(self) -> Path:
        """Return the notes subdirectory; create it if missing."""
        path = self.root / NOTES_SUBDIR
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def notes_dir_path(self) -> Path:
        """Return the notes subdirectory path *without* creating it."""
        return self.root / NOTES_SUBDIR

    def artifact_path(self, stage: str, filename: str) -> Path:
        return self.stage_dir(stage) / filename

    def is_hit(self, stage: str, filename: str, schema_version: str = "1.0") -> bool:
        """Return True if the artifact exists, is not force-bypassed, and has matching schema_version."""
        if self.force:
            return False
        path = self.artifact_path(stage, filename)
        if not path.exists():
            return False
        try:
            with open(path) as fh:
                data = json.load(fh)
            return data.get("schema_version") == schema_version
        except Exception:
            return False

    def initialise(
        self,
        *,
        meeting_title: str | None = None,
        recording_date: str | None = None,
    ) -> None:
        """Create the cache directory and write meta.json if not already present.

        ``meeting_title`` and ``recording_date`` are optional capture-side
        annotations that the Zoom adapter populates when it can scrape them
        (spec 005). The notes stage later writes ``summary`` into the same
        file via ``RecordingMetaSchema.write``.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        meta_path = self.root / "meta.json"
        if not meta_path.exists():
            meta = RecordingMetaSchema(
                recording_url=self.recording_url,
                created_at=datetime.now(timezone.utc).isoformat(),
                meeting_title=meeting_title,
                recording_date=recording_date,
            )
            meta.write(meta_path)
            logger.debug("cache.initialised", path=str(self.root))

    def read_meta(self) -> RecordingMetaSchema | None:
        """Load this cache entry's meta.json. Returns None if missing or malformed."""
        meta_path = self.root / "meta.json"
        if not meta_path.exists():
            return None
        try:
            return RecordingMetaSchema.from_path(meta_path)
        except Exception as exc:  # pragma: no cover - logged for diagnosis
            logger.debug(
                "cache.meta_read_failed",
                path=str(meta_path),
                error=str(exc),
            )
            return None

    def notes_file_path(
        self,
        *,
        filename_max_chars: int,
        summary_max_chars: int,
    ) -> Path | None:
        """
        Resolve the human-readable notes file path inside this cache entry.

        Returns the derived path even when the file does not yet exist
        (callers create it). Returns None if meta.json is missing or
        unreadable — those entries cannot be addressed by the human-readable
        scheme until a notes run repopulates the metadata.
        """
        from notetaker.notes.naming import derive_notes_filename

        meta = self.read_meta()
        if meta is None:
            return None
        name = derive_notes_filename(
            meta,
            max_chars=filename_max_chars,
            summary_max_chars=summary_max_chars,
        )
        return self.notes_dir_path / name

    @classmethod
    def iter_entries(
        cls, cache_root: Path
    ) -> Iterator[tuple[str, RecordingMetaSchema]]:
        """
        Walk ``cache_root`` and yield (url_hash, meta) for every directory
        whose meta.json loads cleanly. Directories without a meta.json or
        with a malformed one are skipped silently (debug-logged).
        """
        if not cache_root.exists():
            return
        for entry in sorted(cache_root.iterdir()):
            if not entry.is_dir():
                continue
            meta_path = entry / "meta.json"
            if not meta_path.exists():
                continue
            try:
                meta = RecordingMetaSchema.from_path(meta_path)
            except Exception as exc:
                logger.debug(
                    "cache.iter_skipped_malformed",
                    path=str(meta_path),
                    error=str(exc),
                )
                continue
            yield entry.name, meta

    @staticmethod
    def purge_stale(
        cache_root: Path,
        retention_days: int,
        notes_retention_days: int = 0,
    ) -> int:
        """
        Delete cache directories whose meta.json is older than retention_days.

        FR-018: the `notes/` subdirectory is exempt from the standard purge.
        When a cache entry is otherwise stale, its `notes/` subdirectory and
        `meta.json` are preserved (other subdirs and stray files are removed),
        unless `notes/` is itself older than `notes_retention_days` (and that
        knob is non-zero), in which case `notes/` is also removed and the cache
        entry is fully purged.

        Separately, when a cache entry is *not* stale but its `notes/` exceeds
        `notes_retention_days`, only `notes/` is deleted.

        Returns the count of fully-removed cache directories (for backwards
        compatibility with existing callers / tests). Partial preservations and
        notes-only purges are reported via structured log records but not
        counted in the return value.
        """
        if not cache_root.exists():
            return 0
        cache_cutoff = time.time() - retention_days * 86400 if retention_days > 0 else None
        notes_cutoff = (
            time.time() - notes_retention_days * 86400 if notes_retention_days > 0 else None
        )
        if cache_cutoff is None and notes_cutoff is None:
            return 0

        deleted = 0
        partial = 0
        notes_only = 0
        for entry in cache_root.iterdir():
            if not entry.is_dir():
                continue
            meta_path = entry / "meta.json"
            if not meta_path.exists():
                continue
            notes_path = entry / NOTES_SUBDIR
            cache_stale = cache_cutoff is not None and meta_path.stat().st_mtime < cache_cutoff
            notes_stale = (
                notes_cutoff is not None
                and notes_path.exists()
                and notes_path.stat().st_mtime < notes_cutoff
            )

            if cache_stale:
                if notes_path.exists() and not notes_stale:
                    for child in entry.iterdir():
                        if child == notes_path or child == meta_path:
                            continue
                        if child.is_dir():
                            shutil.rmtree(child, ignore_errors=True)
                        else:
                            child.unlink(missing_ok=True)
                    partial += 1
                    logger.info("cache.purged_partial", path=str(entry))
                else:
                    shutil.rmtree(entry, ignore_errors=True)
                    deleted += 1
                    logger.info("cache.purged", path=str(entry))
            elif notes_stale:
                shutil.rmtree(notes_path, ignore_errors=True)
                notes_only += 1
                logger.info("cache.notes_purged", path=str(notes_path))

        if deleted or partial or notes_only:
            logger.info(
                "cache.retention_cleanup",
                deleted=deleted,
                partial=partial,
                notes_only=notes_only,
                retention_days=retention_days,
                notes_retention_days=notes_retention_days,
            )
        return deleted
