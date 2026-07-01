"""stdio MCP server exposing the Drive-tagging tools to a Cursor SDK agent.

The agent autonomously calls these tools to process the Drive worklist:

    next_file -> find_similar / search_categories / list_categories
              -> create_category -> assign_categories -> link_files

All durable state lives in turbovecdb (documents + categories) and the graph
SQLite, so the agent's conversation can be reset/resumed without losing work.

Behavior is controlled by env vars set by the runner:
    DT_EXECUTE=1   also write tags to Drive appProperties (default: dry-run)
    DT_RUN_ID      stamp written to appProperties as dt_run
    DT_FOLDER_ID   restrict the worklist to direct children of this folder id
"""

from __future__ import annotations

import json
import os
from typing import Optional

from mcp.server.fastmcp import FastMCP

from . import extract, gdrive
from .config import CONFIG
from .graph import Graph
from .store import Store

mcp = FastMCP("drive-tagger")


class _State:
    """Holds the worklist and durable stores for the lifetime of the server."""

    def __init__(self) -> None:
        self.store = Store()
        self.graph = Graph()
        self.records: list[dict] = self._load_worklist()
        self.processed: set[str] = {
            d["id"] for d in self.store.all_documents() if d.get("processed")
        }
        self.skipped: set[str] = set()
        self.current: Optional[str] = None
        self.returned_this_run = 0
        self.execute = os.environ.get("DT_EXECUTE", "0") == "1"
        self.run_id = os.environ.get("DT_RUN_ID", "")

    def _load_worklist(self) -> list[dict]:
        path = CONFIG.scan_path
        if not path.exists():
            return []
        folder_id = os.environ.get("DT_FOLDER_ID", "").strip()
        descendants = extract.folder_descendants(folder_id, path) if folder_id else None
        records = []
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not extract.is_processable(rec):
                    continue
                if descendants is not None:
                    parents = rec.get("parents") or []
                    if not any(p in descendants for p in parents):
                        continue
                records.append(rec)
        return records


_STATE: Optional[_State] = None


def _state() -> _State:
    global _STATE
    if _STATE is None:
        _STATE = _State()
    return _STATE


def _next_unprocessed(st: _State) -> Optional[dict]:
    for rec in st.records:
        fid = rec["id"]
        if fid in st.processed or fid in st.skipped or fid == st.current:
            continue
        return rec
    return None


@mcp.tool()
def next_file() -> dict:
    """Advance the worklist. Marks the previously returned file as done, then
    embeds and stores the next unprocessed file and returns it with a content
    snippet. Returns {"done": true} when the worklist (or per-run budget) is
    exhausted. This is the entry point for each iteration of the loop."""
    st = _state()

    # Mark the previously handed-out file as processed.
    if st.current is not None:
        st.store.mark_processed(st.current)
        st.processed.add(st.current)
        st.current = None

    if st.returned_this_run >= CONFIG.max_files_per_run:
        return {"done": True, "reason": "per-run file budget reached", "remaining": _remaining(st)}

    while True:
        rec = _next_unprocessed(st)
        if rec is None:
            return {"done": True, "remaining": 0}
        fid = rec["id"]
        # Skip if unchanged from a previous run.
        if st.store.has_unchanged(fid, rec.get("md5_checksum"), rec.get("modified_time")):
            st.processed.add(fid)
            continue
        try:
            text = extract.extract_text(rec)
        except Exception as exc:  # noqa: BLE001 - surface extraction issues, keep going
            st.skipped.add(fid)
            continue
        if not text:
            st.skipped.add(fid)
            continue
        st.store.add_document(rec, text)
        st.current = fid
        st.returned_this_run += 1
        snippet = text[:1500]
        return {
            "file_id": fid,
            "name": rec.get("name", ""),
            "mime_type": rec.get("mime_type", ""),
            "web_view_link": rec.get("web_view_link", ""),
            "snippet": snippet,
            "remaining": _remaining(st),
        }


def _remaining(st: _State) -> int:
    return sum(
        1
        for r in st.records
        if r["id"] not in st.processed and r["id"] not in st.skipped
    )


@mcp.tool()
def find_similar(file_id: str, k: int = 0) -> list[dict]:
    """Return the files most similar to the given file (excluding itself), each
    with its currently assigned categories. Use this to see what neighbors exist
    and how they were categorized before deciding."""
    st = _state()
    return st.store.find_similar(file_id, k or CONFIG.similar_k)


@mcp.tool()
def search_categories(file_id: str, k: int = 0) -> list[dict]:
    """Return existing categories most semantically relevant to a file's content,
    ranked by distance. Use this to find reusable categories before creating new
    ones."""
    st = _state()
    return st.store.search_categories(file_id, k or CONFIG.similar_k)


@mcp.tool()
def list_categories() -> list[dict]:
    """List every existing category with its description and member count."""
    st = _state()
    return st.store.list_categories()


@mcp.tool()
def create_category(name: str, description: str = "") -> dict:
    """Create a new category (or update its description if it already exists).
    Provide a concise, reusable name and a one-sentence description of the theme."""
    st = _state()
    try:
        return st.store.create_category(name, description)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@mcp.tool()
def assign_categories(file_id: str, categories: list[str]) -> dict:
    """Attach one or more categories to a file (unioned with any existing). Aim
    for the richest fitting set, not a single tag. Unknown names are auto-created.
    When running with --execute, this also writes the tags to Drive appProperties."""
    st = _state()
    try:
        merged = st.store.assign_categories(file_id, categories)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    wrote_drive = False
    if st.execute and merged:
        props = {"dt_categories": ",".join(merged)}
        if st.run_id:
            props["dt_run"] = st.run_id
        try:
            gdrive.tag(file_id, props, execute=True)
            wrote_drive = True
        except Exception as exc:  # noqa: BLE001
            return {"file_id": file_id, "categories": merged, "drive_error": str(exc)}
    return {"file_id": file_id, "categories": merged, "wrote_drive": wrote_drive}


@mcp.tool()
def link_files(src_id: str, dst_id: str, relation: str = "related-to", note: str = "") -> dict:
    """Record a typed connection between two files (e.g. relation = "supersedes",
    "part-of", "duplicate-of", "related-to"). Use this to capture relationships
    beyond shared categories."""
    st = _state()
    try:
        added = st.graph.add_link(src_id, dst_id, relation, note)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    return {"added": added, "src_id": src_id, "dst_id": dst_id, "relation": relation}


@mcp.tool()
def stats() -> dict:
    """Return current counts: documents stored, categories, links, and files
    remaining in the worklist."""
    st = _state()
    return {
        "documents": st.store.count_documents(),
        "categories": len(st.store.list_categories()),
        "links": st.graph.count(),
        "remaining": _remaining(st),
        "execute": st.execute,
    }


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
