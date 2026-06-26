"""SQLite store for typed file-to-file links (the connection graph).

This captures relationships beyond shared categories - e.g. ``supersedes``,
``part-of``, ``related-to``, ``duplicate-of`` - so the agent can record the
richest set of connections it discovers.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from .config import CONFIG


class Graph:
    def __init__(self, path: Path | None = None) -> None:
        CONFIG.ensure_dirs()
        self._path = str(path or CONFIG.graph_db)
        self._conn = sqlite3.connect(self._path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS links (
                src_id     TEXT NOT NULL,
                dst_id     TEXT NOT NULL,
                relation   TEXT NOT NULL,
                note       TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(src_id, dst_id, relation)
            )
            """
        )
        self._conn.commit()

    def add_link(self, src_id: str, dst_id: str, relation: str, note: str = "") -> bool:
        """Insert a typed edge. Returns True if newly added, False if it existed."""
        src_id = src_id.strip()
        dst_id = dst_id.strip()
        relation = relation.strip() or "related-to"
        if not src_id or not dst_id:
            raise ValueError("src_id and dst_id are required")
        if src_id == dst_id:
            raise ValueError("cannot link a file to itself")
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO links(src_id, dst_id, relation, note, created_at) "
            "VALUES(?, ?, ?, ?, ?)",
            (src_id, dst_id, relation, note, time.strftime("%Y-%m-%dT%H:%M:%S")),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def links_for(self, file_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT src_id, dst_id, relation, note FROM links WHERE src_id=? OR dst_id=?",
            (file_id, file_id),
        ).fetchall()
        return [
            {"src_id": r[0], "dst_id": r[1], "relation": r[2], "note": r[3]} for r in rows
        ]

    def all_links(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT src_id, dst_id, relation, note FROM links ORDER BY created_at"
        ).fetchall()
        return [
            {"src_id": r[0], "dst_id": r[1], "relation": r[2], "note": r[3]} for r in rows
        ]

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM links").fetchone()[0])

    def close(self) -> None:
        self._conn.commit()
        self._conn.close()
