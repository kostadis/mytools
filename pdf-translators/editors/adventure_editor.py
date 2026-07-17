#!/usr/bin/env python3
"""
adventure_editor.py — block-editor logic for 5etools adventure/book JSON files.

Blueprint for the unified Vue 3 + Vite SPA served by ``editor_server.py``
(routes mounted under ``/api/adv``). Backs a two-panel layout: virtualized
block tree editor (left) + document preview (right). Supports editing
sections, entries, insets, read-aloud boxes, lists, tables, images, quotes,
and horizontal rules, plus a persistent disk-backed undo log
(``<file>.undolog.json``).

Run via ``editor_server.py`` — see that module's docstring for usage.
"""

import json
import shutil
import time
from pathlib import Path

from flask import Blueprint, jsonify, request

from editors.toc_editor import list_json_files
import lib.fix_adventure_json as _fix

bp = Blueprint("adventure", __name__, url_prefix="/api/adv")

_sessions: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_adventure(path: Path) -> dict:
    """Load a 5etools adventure/book JSON and return session data."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    if "adventure" in raw:
        index_key, data_key = "adventure", "adventureData"
    elif "book" in raw:
        index_key, data_key = "book", "bookData"
    else:
        raise ValueError("Not a valid 5etools adventure/book JSON")

    meta = raw[index_key][0]
    data = raw[data_key][0].get("data", [])

    return {
        "raw": raw,
        "index_key": index_key,
        "data_key": data_key,
        "meta": meta,
        "data": data,
    }


def save_adventure(sess: dict, new_data: list) -> list[str]:
    """Rebuild IDs and TOC, then update the session. Returns list of warnings."""
    raw = sess["raw"]
    index_key = sess["index_key"]
    data_key = sess["data_key"]
    warnings = []

    # Guard: promote non-section top-level entries to sections
    for i, entry in enumerate(new_data):
        if isinstance(entry, dict) and entry.get("type") != "section":
            old_type = entry.get("type", "?")
            entry["type"] = "section"
            warnings.append(f"data[{i}] was type '{old_type}', promoted to 'section' "
                            f"(non-section top-level breaks TOC alignment)")
        elif isinstance(entry, str):
            # Bare string at top level — wrap in a section
            new_data[i] = {"type": "section", "name": "Untitled", "entries": [entry]}
            warnings.append(f"data[{i}] was a bare string, wrapped in a section")

    # Replace data
    raw[data_key][0]["data"] = new_data

    # Rebuild IDs
    _fix.reset_ids()
    _fix.assign_ids(new_data)

    # Rebuild TOC
    toc = _fix.build_toc(new_data)
    raw[index_key][0]["contents"] = toc

    # Update session
    sess["data"] = new_data
    sess["meta"] = raw[index_key][0]
    return warnings


# ---------------------------------------------------------------------------
# Undo log helpers
# ---------------------------------------------------------------------------

def _undolog_path(adventure_path: str) -> Path:
    """Return the undo log file path for a given adventure file."""
    p = Path(adventure_path)
    return p.with_suffix(".undolog.json")


def _load_undolog(adventure_path: str) -> dict:
    """Load undo log from disk, or return empty log."""
    p = _undolog_path(adventure_path)
    if p.is_file():
        try:
            with open(p, encoding="utf-8") as f:
                log = json.load(f)
            if isinstance(log, dict) and "entries" in log:
                return log
        except (json.JSONDecodeError, OSError):
            pass
    return {"entries": [], "position": -1}


def _save_undolog(adventure_path: str, undolog: dict) -> None:
    """Persist undo log to disk."""
    p = _undolog_path(adventure_path)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(undolog, f, indent="\t", ensure_ascii=False)
        f.write("\n")


def _undolog_summary(undolog: dict) -> list[dict]:
    """Return entry list without snapshot data (for the UI)."""
    return [
        {"idx": i, "ts": e.get("ts", 0), "action": e.get("action", "")}
        for i, e in enumerate(undolog.get("entries", []))
    ]


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------

@bp.route("/files")
def api_files():
    return jsonify(list_json_files())


@bp.route("/load", methods=["POST"])
def api_load():
    path = request.json.get("path", "")
    if not path or not Path(path).is_file():
        return jsonify({"error": "File not found"}), 400
    try:
        sess = load_adventure(Path(path))
        # Load existing undo log if available
        sess["undolog"] = _load_undolog(path)
        _sessions[path] = sess
        undolog = sess["undolog"]
        return jsonify({
            "meta": {
                "name": sess["meta"].get("name", ""),
                "source": sess["meta"].get("id", ""),
            },
            "data": sess["data"],
            "undolog": {
                "entries": _undolog_summary(undolog),
                "position": undolog.get("position", -1),
            },
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/save", methods=["POST"])
def api_save():
    path = request.json.get("path", "")
    new_data = request.json.get("data", [])
    sess = _sessions.get(path)
    if not sess:
        return jsonify({"error": "File not loaded"}), 400

    try:
        save_warnings = save_adventure(sess, new_data)

        # Write .bak backup
        p = Path(path)
        bak = p.with_suffix(".bak")
        if p.exists():
            shutil.copy2(p, bak)

        # Write JSON
        with open(p, "w", encoding="utf-8") as f:
            json.dump(sess["raw"], f, indent="\t", ensure_ascii=False)
            f.write("\n")

        return jsonify({
            "ok": True,
            "sections": len(new_data),
            "warnings": save_warnings,
            "toc_entries": len(sess["meta"].get("contents", [])),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/undolog/push", methods=["POST"])
def api_undolog_push():
    """Append a snapshot to the undo log and persist to disk."""
    path = request.json.get("path", "")
    action = request.json.get("action", "")
    data = request.json.get("data")
    sess = _sessions.get(path)
    if not sess:
        return jsonify({"error": "File not loaded"}), 400

    undolog = sess.setdefault("undolog", {"entries": [], "position": -1})

    # Truncate any entries after current position (discard redo history on new action)
    undolog["entries"] = undolog["entries"][:undolog["position"] + 1]

    # Append new entry
    undolog["entries"].append({
        "ts": time.time(),
        "action": action,
        "data": data,
    })
    undolog["position"] = len(undolog["entries"]) - 1

    # Limit to 200 entries max
    if len(undolog["entries"]) > 200:
        trim = len(undolog["entries"]) - 200
        undolog["entries"] = undolog["entries"][trim:]
        undolog["position"] = max(0, undolog["position"] - trim)

    _save_undolog(path, undolog)
    return jsonify({
        "ok": True,
        "position": undolog["position"],
        "total": len(undolog["entries"]),
    })


@bp.route("/undolog/undo", methods=["POST"])
def api_undolog_undo():
    """Move back one step. Returns the snapshot to restore."""
    path = request.json.get("path", "")
    sess = _sessions.get(path)
    if not sess:
        return jsonify({"error": "File not loaded"}), 400

    undolog = sess.get("undolog", {"entries": [], "position": -1})
    pos = undolog["position"]
    if pos < 0 or not undolog["entries"]:
        return jsonify({"error": "Nothing to undo"}), 400

    # Current position has the state BEFORE the last action was applied.
    # Return that snapshot and decrement position.
    entry = undolog["entries"][pos]
    undolog["position"] = pos - 1
    _save_undolog(path, undolog)

    return jsonify({
        "ok": True,
        "action": entry["action"],
        "data": entry["data"],
        "position": undolog["position"],
        "total": len(undolog["entries"]),
    })


@bp.route("/undolog/redo", methods=["POST"])
def api_undolog_redo():
    """Move forward one step. Returns the snapshot to restore."""
    path = request.json.get("path", "")
    sess = _sessions.get(path)
    if not sess:
        return jsonify({"error": "File not loaded"}), 400

    undolog = sess.get("undolog", {"entries": [], "position": -1})
    pos = undolog["position"]
    if pos + 1 >= len(undolog["entries"]):
        return jsonify({"error": "Nothing to redo"}), 400

    undolog["position"] = pos + 1
    entry = undolog["entries"][undolog["position"]]
    _save_undolog(path, undolog)

    return jsonify({
        "ok": True,
        "action": entry["action"],
        "data": entry["data"],
        "position": undolog["position"],
        "total": len(undolog["entries"]),
    })


@bp.route("/undolog", methods=["GET"])
def api_undolog_list():
    """Return the undo log entry list (descriptions only, no snapshots)."""
    path = request.args.get("path", "")
    sess = _sessions.get(path)
    if not sess:
        return jsonify({"error": "File not loaded"}), 400

    undolog = sess.get("undolog", {"entries": [], "position": -1})
    return jsonify({
        "entries": _undolog_summary(undolog),
        "position": undolog["position"],
    })


@bp.route("/undolog/jump", methods=["POST"])
def api_undolog_jump():
    """Jump to a specific position in the undo log. Returns the snapshot."""
    path = request.json.get("path", "")
    idx = request.json.get("idx", -1)
    sess = _sessions.get(path)
    if not sess:
        return jsonify({"error": "File not loaded"}), 400

    undolog = sess.get("undolog", {"entries": [], "position": -1})
    if idx < 0 or idx >= len(undolog["entries"]):
        return jsonify({"error": "Invalid position"}), 400

    undolog["position"] = idx
    entry = undolog["entries"][idx]
    _save_undolog(path, undolog)

    return jsonify({
        "ok": True,
        "action": entry["action"],
        "data": entry["data"],
        "position": undolog["position"],
        "total": len(undolog["entries"]),
    })

