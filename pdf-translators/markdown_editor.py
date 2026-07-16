#!/usr/bin/env python3
"""markdown_editor.py — heading-tree editor for Markdown files.

Backend for the Vue 3 + Vite SPA in ``frontend/``. Serves the built bundle
(``frontend/dist``) plus a small JSON API for listing, loading and saving
Markdown files. The UI is a collapsible, *virtualized* heading tree (left) +
markdown heading preview (right) — designed for cleaning up OCR output from
extract_markdown.py before running ``pdf_to_5etools_v2.py --from-markdown``.

Operations per heading row (in the browser):
  ▶/▼  expand/collapse        ↑ ↓  move section up/down (whole subtree)
  ◀ ▶  promote/demote level   ✕    delete heading + its content (undo recovers)

Keyboard (when not editing): u/d move · [ ] promote/demote · Del delete ·
Ctrl+Z / Ctrl+Shift+Z undo/redo · Ctrl+S save.

Usage:
    # one-time / after UI changes — build the SPA:
    cd frontend && npm install && npm run build

    # run the editor:
    python3 markdown_editor.py [file.md] [--port N]   # http://127.0.0.1:5107

    # UI development with hot reload (Vite proxies /api to this backend):
    python3 markdown_editor.py [file.md] &            # backend on 5107
    cd frontend && npm run dev                        # UI on 5173
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__)
_preload_file: str = ""
DEFAULT_PORT = 5107
DIST = Path(__file__).with_name("frontend") / "dist"

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

@app.route("/api/config")
def api_config():
    """Startup config for the SPA — currently just the CLI-preloaded file."""
    return jsonify({"preload": _preload_file})


@app.route("/api/files")
def api_files():
    d = Path(request.args.get("dir", "."))
    try:
        files = sorted(str(p) for p in d.glob("*.md"))
    except Exception:
        files = []
    return jsonify(files)


@app.route("/api/load")
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


@app.route("/api/save", methods=["POST"])
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


# ── SPA serving (built Vue bundle) ───────────────────────────────────────────

@app.route("/assets/<path:filename>")
def spa_assets(filename: str):
    """Hashed Vite assets — safe to cache aggressively (content-addressed)."""
    return send_from_directory(DIST / "assets", filename)


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def spa(path: str):
    """Catch-all: serve a real file from dist/ if it exists, else index.html.
    index.html is never cached so a rebuilt bundle is always picked up."""
    if not DIST.exists():
        return (
            "<h1>Frontend not built</h1>"
            "<p>Run: <code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code></p>",
            503,
        )
    if path and (DIST / path).is_file():
        return send_from_directory(DIST, path)
    index = DIST / "index.html"
    return (index.read_text(encoding="utf-8"), 200,
            {"Content-Type": "text/html", "Cache-Control": "no-store, must-revalidate"})


# ── Entry point ───────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    global _preload_file
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", nargs="?", type=Path, default=None,
                   help="Markdown file to open immediately.")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = p.parse_args(argv)
    if args.file:
        _preload_file = str(args.file.expanduser().resolve())
    if not DIST.exists():
        print("⚠  frontend/dist not found — build it first: "
              "cd frontend && npm install && npm run build")
    print(f"Markdown editor → http://127.0.0.1:{args.port}")
    app.run(host="0.0.0.0", port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
