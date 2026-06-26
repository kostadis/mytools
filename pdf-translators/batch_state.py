#!/usr/bin/env python3
"""batch_state.py — SQLite state store for batch_convert.py.

Replaces the old flat ``dmsguild-manifest.json``. batch_convert is the single
writer (it pulls canonical/dedup flags from the rpg-lib API at startup, records
the conversion plan here, and updates each doc's progress as it converts);
``batch_status.py`` is a read-only reader. WAL mode lets the status tool read a
consistent committed snapshot while a conversion is in flight, with no writer
blocking and no torn rows.

One ``docs`` row per PDF mirrors the in-memory doc dict batch_convert has always
used, so the Dispatcher and dedup code keep operating on plain dicts — this class
is just the load/save boundary around that dict. The only field beyond the old
JSON shape is ``is_pf`` (rpg-lib's printer-friendly flag, the dedup tiebreak).
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS docs (
    rel            TEXT PRIMARY KEY,
    status         TEXT NOT NULL,
    reason         TEXT DEFAULT '',
    size           INTEGER DEFAULT 0,
    mtime          INTEGER DEFAULT 0,
    pages          INTEGER DEFAULT 0,
    text_chars     INTEGER DEFAULT 0,
    is_pf          INTEGER DEFAULT 0,
    eligible_small INTEGER DEFAULT 0,
    endpoint       TEXT DEFAULT '',
    attempts       INTEGER DEFAULT 0,
    exit           INTEGER,
    duration_s     REAL DEFAULT 0,
    log            TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_docs_status ON docs(status);
"""

# Doc-dict columns persisted to the docs table (rel is the PK / dict key).
_DOC_COLS = ("status", "reason", "size", "mtime", "pages", "text_chars",
             "is_pf", "eligible_small", "endpoint", "attempts", "exit",
             "duration_s", "log")
_INT_COLS = {"size", "mtime", "pages", "text_chars", "is_pf",
             "eligible_small", "attempts"}


class StateDB:
    """Writer-side handle to the batch state DB (batch_convert owns this)."""

    def __init__(self, path: str):
        self.path = str(path)
        # check_same_thread=False: Dispatcher worker threads write, but every
        # write goes through the Dispatcher lock, so access is already serial.
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    # ---- existence / load --------------------------------------------------
    def exists_with_docs(self) -> bool:
        return self.conn.execute("SELECT 1 FROM docs LIMIT 1").fetchone() is not None

    def load_docs(self) -> dict[str, dict]:
        """Return ``{rel: doc-dict}`` mirroring the old manifest ``docs`` shape."""
        out: dict[str, dict] = {}
        for row in self.conn.execute("SELECT * FROM docs"):
            d = {k: row[k] for k in row.keys() if k != "rel"}
            out[row["rel"]] = d
        return out

    # ---- meta --------------------------------------------------------------
    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, *, root: str, source: str, api_base: str) -> None:
        now = str(int(time.time()))
        rows = {"root": root, "source": source, "api_base": api_base,
                "saved_at": now, "schema_version": str(SCHEMA_VERSION)}
        with self.conn:
            self.conn.executemany(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                list(rows.items()),
            )

    def _touch_saved_at(self) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES('saved_at', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(int(time.time())),),
        )

    # ---- writes ------------------------------------------------------------
    def save_docs(self, docs: dict[str, dict]) -> None:
        """Bulk INSERT OR REPLACE every doc (one transaction). Used after the
        scan/build and after dedup/enqueue mutate the in-memory dict."""
        cols = ("rel",) + _DOC_COLS
        placeholders = ",".join("?" * len(cols))
        rows = []
        for rel, ent in docs.items():
            rows.append((rel,) + tuple(self._coerce(c, ent.get(c)) for c in _DOC_COLS))
        with self.conn:
            self.conn.executemany(
                f"INSERT OR REPLACE INTO docs({','.join(cols)}) VALUES({placeholders})",
                rows,
            )
            self._touch_saved_at()

    def update_progress(self, rel: str, *, status: str, reason: str = "",
                        endpoint: str, attempts: int, exit: int | None,
                        duration_s: float, log: str) -> None:
        """Single-row UPDATE of a doc's progress after a conversion attempt.

        ``reason`` is the machine-readable failure cause (e.g.
        ``chunk_too_big:cap=20000``, ``timeout``, ``partial``) so a later run can
        tell a deterministic, won't-improve-on-rerun failure from a transient one.
        Empty on success."""
        with self.conn:
            self.conn.execute(
                "UPDATE docs SET status=?, reason=?, endpoint=?, attempts=?, "
                "exit=?, duration_s=?, log=? WHERE rel=?",
                (status, reason, endpoint, attempts, exit, duration_s, log, rel),
            )
            self._touch_saved_at()

    def mark_running(self, rel: str, endpoint: str) -> None:
        """Mark a doc as in-flight on ``endpoint``. The encode phase runs the
        converter in-process (worker threads), so there is no longer a converter
        subprocess for ``batch_status.py`` to pgrep — it reads ``status='running'``
        from here instead to show which docs are currently converting. Overwritten
        by :meth:`update_progress` when the attempt finishes."""
        with self.conn:
            self.conn.execute(
                "UPDATE docs SET status='running', endpoint=? WHERE rel=?",
                (endpoint, rel))
            self._touch_saved_at()

    @staticmethod
    def _coerce(col: str, val):
        if val is None:
            return 0 if col in _INT_COLS else (0.0 if col == "duration_s" else
                                               (None if col == "exit" else ""))
        if col in _INT_COLS:
            return int(val)
        if col == "duration_s":
            return float(val)
        return val

    def close(self) -> None:
        self.conn.close()


def open_readonly(path: str) -> sqlite3.Connection:
    """Read-only connection for batch_status (consistent WAL snapshot)."""
    conn = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn
