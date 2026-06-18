"""Run log file storage: path resolution, latest-pointer, retention.

The `LogStore` is constructed by `cli._setup()` once per CLI invocation. It
owns the on-disk layout under `<log_dir>/`:

    <log_dir>/
        20260509T143022Z-3f7a91c8b2d0e1f4.log    # this run's log file
        20260508T091500Z-1a2b3c4d5e6f7890.log    # a prior run's log file
        latest.log                                # symlink to the most recent run

`start_run()` resolves the run log path, ensures the parent directory exists,
and atomically swings the `latest.log` symlink. `purge_stale()` mirrors
`Cache.purge_stale` semantics (mtime-based, `0 = keep forever`).

All filesystem operations are defensive — failure to create the directory or
the symlink falls back to an unwritable sentinel path so the caller can
proceed in degraded mode (FR-012).
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _utc_iso_basic() -> str:
    """UTC timestamp formatted as YYYYMMDDTHHMMSSZ — sortable, filename-safe."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class LogStore:
    """Owns the run-log directory layout for one CLI invocation."""

    def __init__(self, log_dir: Path, retention_days: int) -> None:
        self.log_dir = Path(log_dir)
        self.retention_days = retention_days
        self.degraded: bool = False
        self.degraded_reason: Optional[str] = None
        self._current_run_path: Optional[Path] = None

    def _try_make_dir(self) -> bool:
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            return True
        except OSError as exc:
            self.degraded = True
            self.degraded_reason = f"{type(exc).__name__}: {exc}"
            print(
                f"[notetaker] WARNING: cannot create log directory "
                f"{self.log_dir} ({self.degraded_reason}); continuing without file log",
                file=sys.stderr,
            )
            return False

    def start_run(self, recording_url_hash: Optional[str] = None) -> Path:
        """Resolve the run log path, ensure parent dir exists, swing `latest.log`.

        Returns a writable path on success, or `Path(os.devnull)` if the log
        directory could not be created. On the devnull path, no log file is
        ever written; downstream code must treat the path as opaque.
        """
        if not self._try_make_dir():
            self._current_run_path = Path(os.devnull)
            return self._current_run_path

        ts = _utc_iso_basic()
        if recording_url_hash:
            filename = f"{ts}-{recording_url_hash}.log"
        else:
            filename = f"{ts}.log"

        run_path = self.log_dir / filename
        # Touch the file so tail -f works even before the first record lands.
        try:
            run_path.touch()
        except OSError as exc:
            self.degraded = True
            self.degraded_reason = f"{type(exc).__name__}: {exc}"
            print(
                f"[notetaker] WARNING: cannot write run log at {run_path} "
                f"({self.degraded_reason}); continuing without file log",
                file=sys.stderr,
            )
            self._current_run_path = Path(os.devnull)
            return self._current_run_path

        self._current_run_path = run_path
        self.update_latest_pointer(run_path)
        return run_path

    def update_latest_pointer(self, target: Path) -> None:
        """Atomically point `<log_dir>/latest.log` at `target`.

        Uses the create-temp-symlink + os.replace dance to avoid a window
        where the symlink is missing or dangling. On filesystems / OSes
        without symlink support, emits one stderr warning and returns
        cleanly (FR-009 degraded).
        """
        latest = self.log_dir / "latest.log"
        tmp = self.log_dir / f".latest.log.tmp.{os.getpid()}"
        try:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
            os.symlink(target, tmp)
            os.replace(tmp, latest)
        except OSError as exc:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
            print(
                f"[notetaker] WARNING: cannot update latest.log symlink in "
                f"{self.log_dir} ({type(exc).__name__}: {exc}); "
                "you'll need to find the run log by timestamp instead",
                file=sys.stderr,
            )

    def purge_stale(self) -> tuple[int, int]:
        """Unlink run logs older than `retention_days` (mtime-based).

        Mirrors Cache.purge_stale semantics:
            retention_days == 0  → keep forever (no-op)
            retention_days > 0   → delete files whose mtime is older than the cutoff

        Emits exactly one structlog INFO record summarising the purge so the
        run log carries a record of which old files were removed (per data-model.md
        §RunLogFile lifecycle and tasks.md T006 + T022 verification).

        Returns (removed, kept).
        """
        # Imported lazily so this module has no startup dependency on logging
        # being configured; configure_logging() and start_run() typically run
        # in the same _setup() call but in either order.
        from notetaker.utils.logging import get_logger

        logger = get_logger(__name__)

        if self.retention_days <= 0:
            logger.info("log_store.purge_stale", removed=0, kept=0, reason="disabled")
            return (0, 0)
        if not self.log_dir.exists():
            logger.info("log_store.purge_stale", removed=0, kept=0, reason="no_log_dir")
            return (0, 0)

        cutoff = time.time() - self.retention_days * 86400
        removed = 0
        kept = 0
        for entry in self.log_dir.iterdir():
            if not entry.is_file():
                continue
            if entry.name == "latest.log" or entry.is_symlink():
                continue
            if not entry.name.endswith(".log"):
                continue
            try:
                if entry.stat().st_mtime < cutoff:
                    entry.unlink()
                    removed += 1
                else:
                    kept += 1
            except OSError:
                kept += 1

        logger.info("log_store.purge_stale", removed=removed, kept=kept,
                    retention_days=self.retention_days)
        return (removed, kept)
