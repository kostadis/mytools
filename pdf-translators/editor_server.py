#!/usr/bin/env python3
"""editor_server.py — unified server for the Markdown and Adventure editors.

Single Flask app / single Vue 3 + Vite SPA (``frontend/``) with a left
sidebar that switches the central pane between:

  - Markdown Editor   — heading-tree editor for .md files (``markdown_editor.py``,
                         routes under /api/md)
  - Adventure Editor   — block editor for 5etools adventure/book .json files
                         (``adventure_editor.py``, routes under /api/adv)

Switching editors is a client-side view swap, not a page reload — a file
loaded in one editor stays loaded when you switch away and back.

Usage:
    # one-time / after UI changes — build the SPA:
    cd frontend && npm install && npm run build

    # run the server:
    python3 editor_server.py [file] [--port N]   # http://127.0.0.1:5107
        # file ending in .md/.markdown preloads the Markdown Editor
        # file ending in .json preloads the Adventure Editor

    # UI development with hot reload (Vite proxies /api to this backend):
    python3 editor_server.py [file] &            # backend on 5107
    cd frontend && npm run dev                    # UI on 5173
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

import adventure_editor
import markdown_editor

app = Flask(__name__)
app.register_blueprint(markdown_editor.bp)
app.register_blueprint(adventure_editor.bp)

_preload_editor: str | None = None
_preload_path: str = ""
DEFAULT_PORT = 5107
DIST = Path(__file__).with_name("frontend") / "dist"

_MARKDOWN_SUFFIXES = {".md", ".markdown"}
_ADVENTURE_SUFFIXES = {".json"}


# ── JSON API ─────────────────────────────────────────────────────────────────

@app.route("/api/config")
def api_config():
    """Startup config for the SPA: which editor (if any) to preload, and with
    which file — inferred from the CLI file argument's suffix."""
    return jsonify({"editor": _preload_editor, "path": _preload_path})


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
    global _preload_editor, _preload_path
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", nargs="?", type=Path, default=None,
                   help="Markdown (.md) or adventure (.json) file to open immediately.")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = p.parse_args(argv)
    if args.file:
        suffix = args.file.suffix.lower()
        if suffix in _MARKDOWN_SUFFIXES:
            _preload_editor = "markdown"
        elif suffix in _ADVENTURE_SUFFIXES:
            _preload_editor = "adventure"
        else:
            print(f"⚠  Unrecognized file type '{suffix}' — expected .md or .json. "
                  "Not preloading.")
        if _preload_editor:
            _preload_path = str(args.file.expanduser().resolve())
    if not DIST.exists():
        print("⚠  frontend/dist not found — build it first: "
              "cd frontend && npm install && npm run build")
    print(f"Editor server → http://127.0.0.1:{args.port}")
    app.run(host="0.0.0.0", port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
