#!/usr/bin/env python3
"""markdown_editor.py — heading-tree editor logic for Markdown files.

Blueprint for the unified Vue 3 + Vite SPA served by ``editor_server.py``
(routes mounted under ``/api/md``). Backs a collapsible, *virtualized*
heading tree (left) + markdown heading preview (right) — designed for
cleaning up OCR output from extract_markdown.py before running
``pdf_to_5etools_v2.py --from-markdown``.

Operations per heading row (in the browser):
  ▶/▼  expand/collapse        ↑ ↓  move section up/down (whole subtree)
  ◀ ▶  promote/demote level   ✕    delete heading + its content (undo recovers)

Keyboard (when not editing): u/d move · [ ] promote/demote · Del delete ·
Ctrl+Z / Ctrl+Shift+Z undo/redo · Ctrl+S save.

Run via ``editor_server.py`` — see that module's docstring for usage.
"""
from __future__ import annotations

import re
from pathlib import Path

from flask import Blueprint, jsonify, request

bp = Blueprint("markdown", __name__, url_prefix="/api/md")

_WINDOWS_PATH_RE = re.compile(r"^([A-Za-z]):[\\/]")


def _windows_path_hint(raw: str) -> str:
    """If `raw` looks like a Windows path (drive letter, or backslashes),
    suggest the WSL mount equivalent — the most common reason a path that's
    valid in the browser (Windows/WSLg) doesn't resolve in this process
    (WSL Linux filesystem)."""
    m = _WINDOWS_PATH_RE.match(raw)
    if m:
        drive = m.group(1).lower()
        rest = raw[m.end():].replace("\\", "/")
        return f" This looks like a Windows path — did you mean /mnt/{drive}/{rest}?"
    if "\\" in raw:
        return " This looks like a Windows path, but this server runs under WSL — use the /mnt/<drive>/... form."
    return ""


# ── JSON API ─────────────────────────────────────────────────────────────────

@bp.route("/files")
def api_files():
    d = Path(request.args.get("dir", "."))
    try:
        files = sorted(str(p) for p in d.glob("*.md"))
    except Exception:
        files = []
    return jsonify(files)


@bp.route("/load")
def api_load():
    raw = request.args.get("file", "")
    path = Path(raw).expanduser()
    if not path.exists():
        return jsonify({"error": f"Not found: {path}." + _windows_path_hint(raw)}), 404
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        return jsonify({"error": f"Could not read {path}: {e}"}), 400
    return jsonify({"content": content, "path": str(path.resolve())})


@bp.route("/save", methods=["POST"])
def api_save():
    data = request.json
    raw = data["path"]
    path = Path(raw).expanduser()
    content = data["content"]
    try:
        if path.exists():
            path.with_suffix(path.suffix + ".bak").write_text(
                path.read_text(encoding="utf-8"), encoding="utf-8")
        path.write_text(content, encoding="utf-8")
    except OSError as e:
        return jsonify({"error": f"Could not write {path}: {e}." + _windows_path_hint(raw)}), 400
    return jsonify({"ok": True})
