#!/usr/bin/env python3
"""
adventure_editor.py — Visual block editor for 5etools adventure/book JSON files.

Two-panel layout: block tree editor (left) + CSS-approximated preview (right).
Supports editing sections, entries, insets, read-aloud boxes, lists, tables,
images, quotes, and horizontal rules.

Usage:
    python3 adventure_editor.py                        # http://localhost:5104
    python3 adventure_editor.py adventure-foo.json     # pre-load a specific file
    python3 adventure_editor.py --port 8080
"""

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

from flask import Flask, jsonify, request

from toc_editor import list_json_files
import fix_adventure_json as _fix

app = Flask(__name__)

_preload_file: str = ""
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


def save_adventure(sess: dict, new_data: list) -> None:
    """Rebuild IDs and TOC, then write the adventure JSON with .bak backup."""
    raw = sess["raw"]
    index_key = sess["index_key"]
    data_key = sess["data_key"]

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

@app.route("/")
def index():
    return HTML.replace('"__PRELOAD__"', json.dumps(_preload_file))


@app.route("/api/files")
def api_files():
    return jsonify(list_json_files())


@app.route("/api/load", methods=["POST"])
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


@app.route("/api/save", methods=["POST"])
def api_save():
    path = request.json.get("path", "")
    new_data = request.json.get("data", [])
    sess = _sessions.get(path)
    if not sess:
        return jsonify({"error": "File not loaded"}), 400

    try:
        save_adventure(sess, new_data)

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
            "toc_entries": len(sess["meta"].get("contents", [])),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/undolog/push", methods=["POST"])
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


@app.route("/api/undolog/undo", methods=["POST"])
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


@app.route("/api/undolog/redo", methods=["POST"])
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


@app.route("/api/undolog", methods=["GET"])
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


@app.route("/api/undolog/jump", methods=["POST"])
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


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Adventure Editor</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
* { box-sizing: border-box; }
body { font-size: 14px; margin: 0; overflow: hidden; height: 100vh; }

/* Toolbar */
.toolbar { padding: 6px 12px; background: #f8f9fa; border-bottom: 1px solid #dee2e6; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.toolbar .form-select, .toolbar .form-control { max-width: 300px; }

/* Main panels */
.main-wrap { display: flex; height: calc(100vh - 42px); }
.panel-editor { width: 50%; display: flex; flex-direction: column; border-right: 1px solid #dee2e6; }
.panel-preview { width: 50%; overflow-y: auto; padding: 16px 24px; background: #fff; }

/* Tree area */
.tree-area { flex: 1; overflow-y: auto; padding: 8px; }

/* Tag toolbar */
.tag-bar { padding: 4px 8px; background: #f0f0f0; border-top: 1px solid #dee2e6; display: flex; gap: 4px; flex-wrap: wrap; align-items: center; }
.tag-bar .btn { font-size: 11px; padding: 1px 6px; }
.tag-bar-label { font-size: 11px; color: #666; margin-right: 4px; }

/* Tree nodes */
.tree-node { margin-left: 16px; }
.tree-node.depth-0 { margin-left: 0; }
.tree-root > .tree-node { margin-left: 0; }

.node-header { display: flex; align-items: center; gap: 4px; padding: 2px 4px; border-radius: 3px; cursor: pointer; min-height: 28px; }
.node-header:hover { background: #e9ecef; }
.node-header.selected { background: #cfe2ff; }

.node-toggle { width: 16px; text-align: center; font-size: 10px; cursor: pointer; color: #666; flex-shrink: 0; user-select: none; }
.node-badge { font-size: 10px; padding: 1px 5px; border-radius: 3px; color: #fff; flex-shrink: 0; font-weight: 600; }
.badge-section { background: #0d6efd; }
.badge-entries { background: #198754; }
.badge-inset { background: #e67e22; }
.badge-readaloud { background: #b8860b; }
.badge-list { background: #6f42c1; }
.badge-table { background: #dc3545; }
.badge-image { background: #20c997; }
.badge-quote { background: #6c757d; }
.badge-hr { background: #adb5bd; }
.badge-string { background: #495057; }

.node-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.node-label.text-preview { color: #666; font-style: italic; }

.node-actions { display: none; gap: 2px; flex-shrink: 0; }
.node-header:hover .node-actions,
.node-header.selected .node-actions { display: flex; }
.node-actions .btn { font-size: 10px; padding: 0 4px; line-height: 1.6; }
.node-actions .btn-move { color: #0d6efd; border-color: #0d6efd; }
.node-actions .btn-nest { color: #198754; border-color: #198754; }

/* Inline edit form */
.node-edit { margin-left: 20px; padding: 6px 8px; background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; margin-top: 2px; margin-bottom: 4px; }
.node-edit label { font-size: 11px; font-weight: 600; color: #555; }
.node-edit .form-control { font-size: 13px; }
.node-edit textarea { font-family: monospace; font-size: 12px; resize: vertical; }
.node-edit .edit-actions { display: flex; gap: 4px; margin-top: 6px; }
.node-edit .edit-actions .btn { font-size: 11px; }

.node-children { }

/* Add section button */
.add-section-bar { padding: 8px; text-align: center; }

/* Preview styles */
.pv-section { margin-bottom: 1.5em; }
.pv-section > h2 { border-bottom: 2px solid #822000; color: #822000; font-variant: small-caps; font-size: 1.5em; margin-bottom: 0.5em; }
.pv-entries { margin-bottom: 0.5em; }
.pv-entries > h3 { color: #822000; font-size: 1.2em; margin-bottom: 0.3em; }
.pv-entries > h4 { color: #822000; font-size: 1.05em; margin-bottom: 0.2em; }
.pv-entries > h5 { color: #822000; font-size: 0.95em; font-style: italic; margin-bottom: 0.2em; }
.pv-inset { border: 2px solid #e0c8a0; background: #fdf5e6; padding: 0.8em; margin: 0.5em 0; border-radius: 4px; }
.pv-inset > .pv-inset-title { font-weight: 700; font-variant: small-caps; color: #822000; margin-bottom: 0.3em; }
.pv-readaloud { border-left: 4px solid #b8860b; background: #fef9ef; padding: 0.8em; margin: 0.5em 0; font-style: italic; }
.pv-list { padding-left: 1.5em; margin: 0.3em 0; }
.pv-list li { margin-bottom: 0.2em; }
.pv-table { border-collapse: collapse; width: 100%; margin: 0.5em 0; font-size: 13px; }
.pv-table th { background: #822000; color: #fff; padding: 4px 8px; text-align: left; }
.pv-table td { border: 1px solid #ddd; padding: 4px 8px; }
.pv-table tr:nth-child(even) td { background: #f9f3ee; }
.pv-table caption { caption-side: top; font-weight: 700; color: #822000; font-variant: small-caps; margin-bottom: 4px; }
.pv-quote { border-left: 3px solid #999; padding-left: 1em; color: #555; font-style: italic; margin: 0.5em 0; }
.pv-quote-by { text-align: right; font-style: normal; font-size: 0.9em; color: #888; }
.pv-hr { border: none; border-top: 1px solid #822000; margin: 1em 0; }
.pv-image { margin: 0.5em 0; padding: 0.5em; background: #f0f0f0; border-radius: 4px; text-align: center; color: #666; font-style: italic; }
.pv-para { margin: 0.3em 0; line-height: 1.5; }

/* Tag rendering in preview */
.tag-spell { color: #4a148c; }
.tag-creature { color: #1b5e20; font-weight: 600; }
.tag-item { color: #0d47a1; }
.tag-condition { color: #b71c1c; font-weight: 600; }
.tag-dc { font-weight: 700; }
.tag-damage { color: #c62828; }
.tag-hit { font-weight: 700; }
.tag-skill { color: #4a148c; }

/* Selected block highlight in preview */
.pv-highlight { outline: 2px solid #0d6efd; outline-offset: 2px; border-radius: 3px; }

/* Dirty indicator */
.dirty-dot { width: 8px; height: 8px; border-radius: 50%; background: #dc3545; display: inline-block; margin-left: 4px; }

/* List item editor */
.list-item-row { display: flex; gap: 4px; margin-bottom: 3px; align-items: center; }
.list-item-row input { flex: 1; }

/* Table editor */
.table-editor { font-size: 12px; }
.table-editor input { font-size: 12px; padding: 2px 4px; }
.table-editor td, .table-editor th { padding: 2px; }
</style>
</head>
<body>

<!-- Toolbar -->
<div class="toolbar">
  <select id="fileSel" class="form-select form-select-sm" style="max-width:300px">
    <option value="">Select a file...</option>
  </select>
  <button class="btn btn-sm btn-primary" onclick="doLoad()">Load</button>
  <button class="btn btn-sm btn-success" onclick="doSave()" id="saveBtn" disabled>Save</button>
  <span id="dirtyDot" style="display:none" class="dirty-dot" title="Unsaved changes"></span>
  <span style="border-left:1px solid #ccc; height:20px; margin:0 4px"></span>
  <button class="btn btn-sm btn-outline-secondary" onclick="doUndo()" id="undoBtn" disabled title="Undo (Ctrl+Z)">Undo</button>
  <button class="btn btn-sm btn-outline-secondary" onclick="doRedo()" id="redoBtn" disabled title="Redo (Ctrl+Shift+Z)">Redo</button>
  <div class="dropdown d-inline-block">
    <button class="btn btn-sm btn-outline-secondary dropdown-toggle" id="historyBtn" data-bs-toggle="dropdown" disabled title="Change history">History</button>
    <ul class="dropdown-menu dropdown-menu-end" id="historyMenu" style="max-height:400px; overflow-y:auto; font-size:12px; min-width:350px;"></ul>
  </div>
  <span style="border-left:1px solid #ccc; height:20px; margin:0 4px"></span>
  <button class="btn btn-sm btn-outline-secondary" onclick="collapseAll()" title="Collapse all">Collapse</button>
  <button class="btn btn-sm btn-outline-secondary" onclick="expandAll()" title="Expand all">Expand</button>
  <div class="dropdown d-inline-block">
    <button class="btn btn-sm btn-outline-secondary dropdown-toggle" data-bs-toggle="dropdown" title="Expand to level...">Level</button>
    <ul class="dropdown-menu" style="font-size:12px; min-width:120px">
      <li><a class="dropdown-item" href="#" onclick="event.preventDefault(); expandToLevel(0)">Sections only</a></li>
      <li><a class="dropdown-item" href="#" onclick="event.preventDefault(); expandToLevel(1)">Level 1</a></li>
      <li><a class="dropdown-item" href="#" onclick="event.preventDefault(); expandToLevel(2)">Level 2</a></li>
      <li><a class="dropdown-item" href="#" onclick="event.preventDefault(); expandToLevel(3)">Level 3</a></li>
    </ul>
  </div>
  <span class="flex-grow-1"></span>
  <span id="statusMsg" class="text-muted" style="font-size:12px">Ready</span>
</div>

<!-- Main panels -->
<div class="main-wrap">
  <!-- Left: editor -->
  <div class="panel-editor">
    <div class="tree-area" id="treeArea">
      <div class="text-muted text-center mt-5">Load a file to begin editing</div>
    </div>

    <!-- Tag toolbar -->
    <div class="tag-bar" id="tagBar">
      <span class="tag-bar-label">Tags:</span>
      <button class="btn btn-outline-secondary" onclick="insertTag('b')" title="{@b bold}"><b>B</b></button>
      <button class="btn btn-outline-secondary" onclick="insertTag('i')" title="{@i italic}"><i>I</i></button>
      <button class="btn btn-outline-secondary" onclick="insertTag('spell')" title="{@spell name}">Spell</button>
      <button class="btn btn-outline-secondary" onclick="insertTag('creature')" title="{@creature name}">Creature</button>
      <button class="btn btn-outline-secondary" onclick="insertTag('condition')" title="{@condition name}">Condition</button>
      <button class="btn btn-outline-secondary" onclick="insertTag('dc')" title="{@dc N}">DC</button>
      <button class="btn btn-outline-secondary" onclick="insertTag('damage')" title="{@damage XdY+Z}">Damage</button>
      <button class="btn btn-outline-secondary" onclick="insertTag('hit')" title="{@hit N}">Hit</button>
      <button class="btn btn-outline-secondary" onclick="insertTag('item')" title="{@item name}">Item</button>
      <button class="btn btn-outline-secondary" onclick="insertTag('skill')" title="{@skill name}">Skill</button>
      <button class="btn btn-outline-secondary" onclick="insertTag('atk')" title="{@atk mw}">Atk</button>
      <button class="btn btn-outline-secondary" onclick="insertTag('h')" title="{@h} (Hit:)">@h</button>
      <button class="btn btn-outline-secondary" onclick="insertTag('recharge')" title="{@recharge N}">Recharge</button>
    </div>
  </div>

  <!-- Right: preview -->
  <div class="panel-preview" id="previewArea">
    <div class="text-muted text-center mt-5">Preview will appear here</div>
  </div>
</div>

<!-- Add Block Modal -->
<div class="modal fade" id="addBlockModal" tabindex="-1">
  <div class="modal-dialog">
    <div class="modal-content">
      <div class="modal-header py-2">
        <h6 class="modal-title">Add Block</h6>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body">
        <div class="mb-2">
          <label class="form-label fw-bold" style="font-size:12px">Block Type</label>
          <select class="form-select form-select-sm" id="addBlockType" onchange="onAddBlockTypeChange()">
            <option value="section">Section (top-level chapter)</option>
            <option value="entries" selected>Entries (subsection with heading)</option>
            <option value="text">Text (paragraph)</option>
            <option value="inset">Inset (sidebar box)</option>
            <option value="insetReadaloud">Read-Aloud Box</option>
            <option value="table">Table (paste tab/pipe-separated)</option>
            <option value="statblock">Stat Block (paste text)</option>
            <option value="list">List</option>
            <option value="quote">Quote</option>
            <option value="image">Image</option>
            <option value="hr">Horizontal Rule</option>
          </select>
        </div>
        <div class="mb-2" id="addBlockNameRow">
          <label class="form-label fw-bold" style="font-size:12px">Name</label>
          <input class="form-control form-control-sm" id="addBlockName" placeholder="Section or entry name...">
        </div>
        <div class="mb-2" id="addBlockPasteRow" style="display:none">
          <label class="form-label fw-bold" style="font-size:12px">Content (paste text)</label>
          <textarea class="form-control form-control-sm" id="addBlockPaste" rows="8"
            style="font-family:monospace; font-size:12px"
            placeholder="Paste content here..."
            oninput="onAddBlockPasteInput()"></textarea>
          <div id="addBlockParseResult"></div>
        </div>
      </div>
      <div class="modal-footer py-1">
        <button type="button" class="btn btn-sm btn-secondary" data-bs-dismiss="modal">Cancel</button>
        <button type="button" class="btn btn-sm btn-primary" onclick="confirmAddBlock()">Add</button>
      </div>
    </div>
  </div>
</div>

<script>
// =========================================================================
// State
// =========================================================================
let state = {
  path: "",
  data: [],
  selectedPath: null,  // JSON-encoded path array, e.g. "[0,\"entries\",2]"
  dirty: false,
  collapsed: {},  // pathKey -> true if collapsed
  undoPosition: -1,
  undoTotal: 0,
};

let lastActiveTextarea = null;

// =========================================================================
// Utilities
// =========================================================================
function escHtml(s) {
  const d = document.createElement("div");
  d.textContent = s || "";
  return d.innerHTML;
}

function pathKey(pathArr) { return JSON.stringify(pathArr); }
function parsePath(key) { return JSON.parse(key); }

function getByPath(data, pathArr) {
  let obj = data;
  for (const seg of pathArr) {
    if (obj == null) return undefined;
    obj = obj[seg];
  }
  return obj;
}

function setByPath(data, pathArr, value) {
  let obj = data;
  for (let i = 0; i < pathArr.length - 1; i++) {
    obj = obj[pathArr[i]];
  }
  obj[pathArr[pathArr.length - 1]] = value;
}

function deleteByPath(data, pathArr) {
  let obj = data;
  for (let i = 0; i < pathArr.length - 1; i++) {
    obj = obj[pathArr[i]];
  }
  const last = pathArr[pathArr.length - 1];
  if (Array.isArray(obj)) {
    obj.splice(last, 1);
  } else {
    delete obj[last];
  }
}

function insertAfterPath(data, pathArr, value) {
  const parentPath = pathArr.slice(0, -1);
  const idx = pathArr[pathArr.length - 1];
  const parent = getByPath(data, parentPath);
  if (Array.isArray(parent)) {
    parent.splice(idx + 1, 0, value);
  }
}

function getNodeType(node) {
  if (typeof node === "string") return "string";
  if (node && node.type) return node.type;
  return "unknown";
}

function getNodeName(node) {
  if (typeof node === "string") {
    return node.length > 60 ? node.substring(0, 60) + "..." : node;
  }
  return node.name || "";
}

function getChildrenKey(node) {
  const t = getNodeType(node);
  if (t === "list") return "items";
  return "entries";
}

function getChildren(node) {
  if (typeof node === "string") return [];
  if (node.type === "list") return node.items || [];
  if (node.type === "table" || node.type === "hr" || node.type === "image") return [];
  return node.entries || [];
}

function badgeClass(t) {
  const map = {
    section: "badge-section", entries: "badge-entries",
    inset: "badge-inset", insetReadaloud: "badge-readaloud",
    list: "badge-list", table: "badge-table",
    image: "badge-image", quote: "badge-quote",
    hr: "badge-hr", string: "badge-string",
  };
  return map[t] || "badge-string";
}

function badgeLabel(t) {
  const map = {
    section: "SEC", entries: "ENT", inset: "INS",
    insetReadaloud: "READ", list: "LIST", table: "TBL",
    image: "IMG", quote: "QUO", hr: "HR", string: "TXT",
  };
  return map[t] || t.toUpperCase().substring(0, 4);
}

function markDirty() {
  state.dirty = true;
  document.getElementById("dirtyDot").style.display = "inline-block";
  document.getElementById("saveBtn").disabled = false;
}

function setStatus(msg, cls) {
  const el = document.getElementById("statusMsg");
  el.textContent = msg;
  el.className = cls || "text-muted";
}

// =========================================================================
// Tag insertion
// =========================================================================
function insertTag(tag) {
  const ta = lastActiveTextarea;
  if (!ta) return;
  ta.focus();
  const start = ta.selectionStart;
  const end = ta.selectionEnd;
  const sel = ta.value.substring(start, end);
  let replacement;
  if (tag === "h") {
    replacement = "{@h}";
  } else if (sel) {
    replacement = `{@${tag} ${sel}}`;
  } else {
    replacement = `{@${tag} }`;
  }
  ta.setRangeText(replacement, start, end, "end");
  // Move cursor inside closing brace if no selection
  if (!sel && tag !== "h") {
    ta.selectionStart = ta.selectionEnd = start + replacement.length - 1;
  }
  ta.dispatchEvent(new Event("input", { bubbles: true }));
}

// =========================================================================
// Load / Save
// =========================================================================
async function loadFileList() {
  const resp = await fetch("/api/files");
  const files = await resp.json();
  const sel = document.getElementById("fileSel");
  sel.innerHTML = '<option value="">Select a file...</option>';
  for (const f of files) {
    const o = document.createElement("option");
    o.value = f; o.textContent = f;
    sel.appendChild(o);
  }
}

async function doLoad() {
  const path = document.getElementById("fileSel").value;
  if (!path) return;
  setStatus("Loading...", "text-primary");
  try {
    const resp = await fetch("/api/load", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ path }),
    });
    const result = await resp.json();
    if (result.error) { setStatus(result.error, "text-danger"); return; }
    state.path = path;
    state.data = result.data;
    state.selectedPath = null;
    state.dirty = false;
    state.collapsed = {};
    state.undoPosition = (result.undolog && result.undolog.position != null) ? result.undolog.position : -1;
    state.undoTotal = (result.undolog && result.undolog.entries) ? result.undolog.entries.length : 0;
    document.getElementById("dirtyDot").style.display = "none";
    document.getElementById("saveBtn").disabled = true;
    renderTree();
    renderPreview();
    updateUndoUI();
    const logMsg = state.undoTotal > 0 ? ` (${state.undoTotal} undo entries loaded)` : "";
    setStatus(`Loaded: ${result.meta.name || path} (${state.data.length} sections)${logMsg}`, "text-success");
  } catch (e) {
    setStatus("Load failed: " + e.message, "text-danger");
  }
}

async function doSave() {
  if (!state.path) return;
  setStatus("Saving...", "text-primary");
  try {
    const resp = await fetch("/api/save", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ path: state.path, data: state.data }),
    });
    const result = await resp.json();
    if (result.error) { setStatus("Save failed: " + result.error, "text-danger"); return; }
    state.dirty = false;
    document.getElementById("dirtyDot").style.display = "none";
    document.getElementById("saveBtn").disabled = true;
    setStatus(`Saved: ${result.sections} sections, ${result.toc_entries} TOC entries`, "text-success");
  } catch (e) {
    setStatus("Save failed: " + e.message, "text-danger");
  }
}

// =========================================================================
// Tree rendering
// =========================================================================
function renderTree() {
  const area = document.getElementById("treeArea");
  area.innerHTML = "";
  const root = document.createElement("div");
  root.className = "tree-root";

  for (let i = 0; i < state.data.length; i++) {
    root.appendChild(buildTreeNode(state.data[i], [i], 0));
  }

  // Add section button
  const addBar = document.createElement("div");
  addBar.className = "add-section-bar";
  addBar.innerHTML = `<button class="btn btn-sm btn-outline-primary" onclick="addTopLevelSection()">+ Add Section</button>`;
  root.appendChild(addBar);

  area.appendChild(root);
}

function buildTreeNode(node, path, depth) {
  const pk = pathKey(path);
  const type = getNodeType(node);
  const children = getChildren(node);
  const hasChildren = children.length > 0;
  const isCollapsed = !!state.collapsed[pk];
  const isSelected = state.selectedPath === pk;

  const wrap = document.createElement("div");
  wrap.className = `tree-node depth-${depth}`;
  wrap.dataset.path = pk;

  // Header row
  const header = document.createElement("div");
  header.className = "node-header" + (isSelected ? " selected" : "");

  // Toggle
  const toggle = document.createElement("span");
  toggle.className = "node-toggle";
  if (hasChildren) {
    toggle.textContent = isCollapsed ? "\u25B6" : "\u25BC";
    toggle.onclick = (e) => { e.stopPropagation(); toggleCollapse(pk); };
  }
  header.appendChild(toggle);

  // Badge
  const badge = document.createElement("span");
  badge.className = `node-badge ${badgeClass(type)}`;
  badge.textContent = badgeLabel(type);
  header.appendChild(badge);

  // Label
  const label = document.createElement("span");
  label.className = "node-label" + (type === "string" ? " text-preview" : "");
  if (type === "string") {
    label.textContent = getNodeName(node);
  } else if (type === "hr") {
    label.textContent = "--- horizontal rule ---";
    label.classList.add("text-preview");
  } else if (type === "table") {
    const cap = node.caption || (node.colLabels || []).join(", ") || "table";
    label.textContent = cap;
  } else if (type === "image") {
    label.textContent = node.title || (node.href && node.href.path) || "image";
  } else {
    label.textContent = getNodeName(node) || "(unnamed)";
  }
  header.appendChild(label);

  // Action buttons — use addEventListener to avoid HTML-escaping issues with JSON path keys
  const actions = document.createElement("span");
  actions.className = "node-actions";
  const btnDefs = [
    { label: "\u2191", title: "Move up", cls: "btn-move", fn: () => moveNode(pk, -1) },
    { label: "\u2193", title: "Move down", cls: "btn-move", fn: () => moveNode(pk, 1) },
    { label: "\u2190", title: "Promote (move out of parent)", cls: "btn-nest", fn: () => promoteNode(pk) },
    { label: "\u2192", title: "Demote (nest into sibling above)", cls: "btn-nest", fn: () => demoteNode(pk) },
    { label: "+", title: "Add sibling after", cls: "", fn: () => addSibling(pk) },
    { label: "\u00D7", title: "Delete", cls: "btn-del", fn: () => deleteNode(pk) },
  ];
  for (const bd of btnDefs) {
    const btn = document.createElement("button");
    btn.className = `btn btn-outline-${bd.cls === "btn-del" ? "danger" : "secondary"} ${bd.cls}`;
    btn.title = bd.title;
    btn.textContent = bd.label;
    btn.addEventListener("click", (e) => { e.stopPropagation(); bd.fn(); });
    actions.appendChild(btn);
  }
  header.appendChild(actions);

  header.onclick = () => selectNode(pk);
  wrap.appendChild(header);

  // Inline edit form (if selected)
  if (isSelected) {
    const editForm = buildEditForm(node, path, type);
    // Stop all keyboard events from bubbling out of the edit form
    editForm.addEventListener("keydown", (e) => e.stopPropagation());
    editForm.addEventListener("click", (e) => e.stopPropagation());
    wrap.appendChild(editForm);
  }

  // Children
  if (hasChildren && !isCollapsed) {
    const childWrap = document.createElement("div");
    childWrap.className = "node-children";
    const childKey = getChildrenKey(node);
    for (let i = 0; i < children.length; i++) {
      childWrap.appendChild(buildTreeNode(children[i], [...path, childKey, i], depth + 1));
    }
    wrap.appendChild(childWrap);
  }

  return wrap;
}

// =========================================================================
// Inline edit forms
// =========================================================================
function buildEditForm(node, path, type) {
  const form = document.createElement("div");
  form.className = "node-edit";
  const pk = pathKey(path);

  if (type === "string") {
    form.innerHTML = `
      <label>Text</label>
      <textarea class="form-control edit-field" data-field="__string__" rows="4"
        onfocus="lastActiveTextarea=this">${escHtml(node)}</textarea>
      <div class="edit-actions">
        <button class="btn btn-sm btn-primary" onclick="commitEdit('${pk}')">Done</button>
        <button class="btn btn-sm btn-outline-secondary" onclick="cancelEdit()">Cancel</button>
      </div>`;
  } else if (type === "hr") {
    form.innerHTML = `<span class="text-muted">Horizontal rule (no editable fields)</span>
      <div class="edit-actions">
        <button class="btn btn-sm btn-outline-secondary" onclick="cancelEdit()">Close</button>
      </div>`;
  } else if (type === "table") {
    form.appendChild(buildTableEditor(node, path));
  } else if (type === "list") {
    form.appendChild(buildListEditor(node, path));
  } else if (type === "image") {
    form.innerHTML = `
      <label>Title</label>
      <input class="form-control mb-1 edit-field" data-field="title" value="${escHtml(node.title || "")}">
      <label>Path (href.path)</label>
      <input class="form-control mb-1 edit-field" data-field="href.path" value="${escHtml((node.href && node.href.path) || "")}">
      <div class="edit-actions">
        <button class="btn btn-sm btn-primary" onclick="commitEdit('${pk}')">Done</button>
        <button class="btn btn-sm btn-outline-secondary" onclick="cancelEdit()">Cancel</button>
      </div>`;
  } else if (type === "quote") {
    const entriesText = (node.entries || []).filter(e => typeof e === "string").join("\n");
    form.innerHTML = `
      <label>Quote text (one paragraph per line)</label>
      <textarea class="form-control mb-1 edit-field" data-field="__quote_entries__" rows="3"
        onfocus="lastActiveTextarea=this">${escHtml(entriesText)}</textarea>
      <label>By</label>
      <input class="form-control mb-1 edit-field" data-field="by" value="${escHtml(node.by || "")}">
      <label>From</label>
      <input class="form-control mb-1 edit-field" data-field="from" value="${escHtml(node.from || "")}">
      <div class="edit-actions">
        <button class="btn btn-sm btn-primary" onclick="commitEdit('${pk}')">Done</button>
        <button class="btn btn-sm btn-outline-secondary" onclick="cancelEdit()">Cancel</button>
      </div>`;
  } else {
    // section, entries, inset, insetReadaloud — all have optional name + entries
    const showName = (type !== "insetReadaloud");
    let html = "";
    if (showName) {
      html += `<label>Name</label>
        <input class="form-control mb-1 edit-field" data-field="name" value="${escHtml(node.name || "")}">`;
    }
    // Type selector
    html += `<label>Type</label>
      <select class="form-select form-select-sm mb-1 edit-field" data-field="type">
        <option value="section" ${type === "section" ? "selected" : ""}>section</option>
        <option value="entries" ${type === "entries" ? "selected" : ""}>entries</option>
        <option value="inset" ${type === "inset" ? "selected" : ""}>inset</option>
        <option value="insetReadaloud" ${type === "insetReadaloud" ? "selected" : ""}>insetReadaloud</option>
      </select>`;
    html += `<div class="edit-actions">
      <button class="btn btn-sm btn-primary" onclick="commitEdit('${pk}')">Done</button>
      <button class="btn btn-sm btn-outline-secondary" onclick="cancelEdit()">Cancel</button>
      <button class="btn btn-sm btn-outline-primary ms-auto" onclick="addChild('${pk}')">+ Add child</button>
    </div>`;
    form.innerHTML = html;
  }

  return form;
}

function buildTableEditor(node, path) {
  const div = document.createElement("div");
  div.className = "table-editor";
  const pk = pathKey(path);
  const cols = node.colLabels || [];
  const rows = node.rows || [];

  let html = `<label>Caption</label>
    <input class="form-control mb-1 tbl-caption" value="${escHtml(node.caption || "")}">`;

  html += `<table class="table table-sm table-bordered mb-1"><thead><tr>`;
  for (let c = 0; c < cols.length; c++) {
    html += `<th><input class="form-control form-control-sm tbl-col" data-col="${c}" value="${escHtml(cols[c])}"></th>`;
  }
  html += `<th style="width:30px"><button class="btn btn-sm btn-outline-primary" onclick="addTableCol('${pk}')" title="Add column">+</button></th>`;
  html += `</tr></thead><tbody>`;
  for (let r = 0; r < rows.length; r++) {
    html += `<tr>`;
    for (let c = 0; c < cols.length; c++) {
      const val = (rows[r] && rows[r][c] != null) ? rows[r][c] : "";
      html += `<td><input class="form-control form-control-sm tbl-cell" data-row="${r}" data-col="${c}"
        onfocus="lastActiveTextarea=this" value="${escHtml(String(val))}"></td>`;
    }
    html += `<td><button class="btn btn-sm btn-outline-danger" onclick="deleteTableRow('${pk}', ${r})">&times;</button></td>`;
    html += `</tr>`;
  }
  html += `</tbody></table>`;
  html += `<div class="edit-actions">
    <button class="btn btn-sm btn-outline-primary" onclick="addTableRow('${pk}')">+ Row</button>
    <button class="btn btn-sm btn-primary ms-auto" onclick="commitTableEdit('${pk}')">Done</button>
    <button class="btn btn-sm btn-outline-secondary" onclick="cancelEdit()">Cancel</button>
  </div>`;

  div.innerHTML = html;
  return div;
}

function buildListEditor(node, path) {
  const div = document.createElement("div");
  const pk = pathKey(path);
  const items = node.items || [];

  let html = `<label>List items</label>`;
  for (let i = 0; i < items.length; i++) {
    const val = typeof items[i] === "string" ? items[i] : JSON.stringify(items[i]);
    html += `<div class="list-item-row">
      <input class="form-control form-control-sm list-item" data-idx="${i}"
        onfocus="lastActiveTextarea=this" value="${escHtml(val)}">
      <button class="btn btn-sm btn-outline-danger" onclick="deleteListItem('${pk}', ${i})">&times;</button>
    </div>`;
  }
  html += `<div class="edit-actions">
    <button class="btn btn-sm btn-outline-primary" onclick="addListItem('${pk}')">+ Item</button>
    <button class="btn btn-sm btn-primary ms-auto" onclick="commitListEdit('${pk}')">Done</button>
    <button class="btn btn-sm btn-outline-secondary" onclick="cancelEdit()">Cancel</button>
  </div>`;

  div.innerHTML = html;
  return div;
}

// =========================================================================
// Edit operations — commit on "Done", not on every keystroke
// =========================================================================

function findNodeEdit(pk) {
  for (const el of document.querySelectorAll(".tree-node")) {
    if (el.dataset.path === pk) {
      return el.querySelector(".node-edit");
    }
  }
  return null;
}

function commitEdit(pk) {
  // Read all edit-field values from the form and apply to the data model
  const path = parsePath(pk);
  const node = getByPath(state.data, path);
  const type = getNodeType(node);
  const formEl = findNodeEdit(pk);
  if (!formEl) { cancelEdit(); return; }

  pushUndo("Edit " + (type === "string" ? "text" : (node.name || type)));

  if (type === "string") {
    const ta = formEl.querySelector('[data-field="__string__"]');
    if (ta) setByPath(state.data, path, ta.value);
  } else {
    // Read all .edit-field inputs
    formEl.querySelectorAll(".edit-field").forEach(el => {
      const field = el.dataset.field;
      const val = el.value;
      if (field === "__quote_entries__") {
        node.entries = val.split("\n").filter(l => l.length > 0);
      } else if (field === "href.path") {
        if (!node.href) node.href = { type: "internal" };
        node.href.path = val;
      } else if (field === "type") {
        node.type = val;
      } else {
        if (val === "" && field !== "name") {
          delete node[field];
        } else {
          node[field] = val;
        }
      }
    });
  }

  markDirty();
  state.selectedPath = null;
  renderTree();
  renderPreview();
}

function commitTableEdit(pk) {
  const path = parsePath(pk);
  const node = getByPath(state.data, path);
  const formEl = findNodeEdit(pk);
  if (!formEl || !node) { cancelEdit(); return; }

  pushUndo("Edit table");

  // Read caption
  const capInput = formEl.querySelector(".tbl-caption");
  if (capInput) {
    if (capInput.value.trim()) node.caption = capInput.value.trim();
    else delete node.caption;
  }

  // Read column labels
  formEl.querySelectorAll(".tbl-col").forEach(el => {
    const c = parseInt(el.dataset.col);
    if (node.colLabels && c < node.colLabels.length) node.colLabels[c] = el.value;
  });

  // Read cells
  formEl.querySelectorAll(".tbl-cell").forEach(el => {
    const r = parseInt(el.dataset.row);
    const c = parseInt(el.dataset.col);
    if (node.rows && node.rows[r]) node.rows[r][c] = el.value;
  });

  markDirty();
  state.selectedPath = null;
  renderTree();
  renderPreview();
}

function commitListEdit(pk) {
  const path = parsePath(pk);
  const node = getByPath(state.data, path);
  const formEl = findNodeEdit(pk);
  if (!formEl || !node) { cancelEdit(); return; }

  pushUndo("Edit list");

  // Read all list item inputs
  const newItems = [];
  formEl.querySelectorAll(".list-item").forEach(el => {
    newItems.push(el.value);
  });
  node.items = newItems;

  markDirty();
  state.selectedPath = null;
  renderTree();
  renderPreview();
}

function cancelEdit() {
  state.selectedPath = null;
  renderTree();
  renderPreview();
}

// Table structural operations (these re-render the form immediately)
function addTableRow(pk) {
  pushUndo("Add table row");
  const node = getByPath(state.data, parsePath(pk));
  if (node) {
    if (!node.rows) node.rows = [];
    const cols = (node.colLabels || []).length || 2;
    node.rows.push(new Array(cols).fill(""));
    markDirty(); renderTree(); state.selectedPath = pk; highlightSelected(); renderPreview();
  }
}
function deleteTableRow(pk, rowIdx) {
  pushUndo("Delete table row");
  const node = getByPath(state.data, parsePath(pk));
  if (node && node.rows) { node.rows.splice(rowIdx, 1); markDirty(); renderTree(); state.selectedPath = pk; highlightSelected(); renderPreview(); }
}
function addTableCol(pk) {
  pushUndo("Add table column");
  const node = getByPath(state.data, parsePath(pk));
  if (node) {
    if (!node.colLabels) node.colLabels = [];
    node.colLabels.push("New Column");
    for (const row of (node.rows || [])) { row.push(""); }
    markDirty(); renderTree(); state.selectedPath = pk; highlightSelected(); renderPreview();
  }
}

// List structural operations
function deleteListItem(pk, idx) {
  pushUndo("Delete list item");
  const node = getByPath(state.data, parsePath(pk));
  if (node && node.items) { node.items.splice(idx, 1); markDirty(); renderTree(); state.selectedPath = pk; highlightSelected(); renderPreview(); }
}
function addListItem(pk) {
  pushUndo("Add list item");
  const node = getByPath(state.data, parsePath(pk));
  if (node) {
    if (!node.items) node.items = [];
    node.items.push("");
    markDirty(); renderTree(); state.selectedPath = pk; highlightSelected(); renderPreview();
  }
}

// =========================================================================
// Node operations (add, delete, move)
// =========================================================================
function selectNode(pk) {
  state.selectedPath = (state.selectedPath === pk) ? null : pk;
  renderTree();
  highlightSelected();
  scrollPreviewToSelected();
}

function findByPvPath(pk) {
  // Use querySelectorAll and match manually to avoid CSS escaping issues with JSON paths
  for (const el of document.querySelectorAll("[data-pv-path]")) {
    if (el.dataset.pvPath === pk) return el;
  }
  return null;
}

function highlightSelected() {
  // Highlight in tree
  document.querySelectorAll(".node-header").forEach(h => h.classList.remove("selected"));
  if (state.selectedPath) {
    const treeNode = document.querySelector(`.tree-node[data-path]`);
    for (const el of document.querySelectorAll(".tree-node")) {
      if (el.dataset.path === state.selectedPath) {
        const hdr = el.querySelector(":scope > .node-header");
        if (hdr) hdr.classList.add("selected");
        break;
      }
    }
  }
  // Highlight in preview
  document.querySelectorAll(".pv-highlight").forEach(el => el.classList.remove("pv-highlight"));
  if (state.selectedPath) {
    const pvEl = findByPvPath(state.selectedPath);
    if (pvEl) pvEl.classList.add("pv-highlight");
  }
}

function scrollPreviewToSelected() {
  if (!state.selectedPath) return;
  setTimeout(() => {
    const pvEl = findByPvPath(state.selectedPath);
    if (pvEl) {
      pvEl.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, 50);
}

function toggleCollapse(pk) {
  state.collapsed[pk] = !state.collapsed[pk];
  renderTree();
  state.selectedPath = state.selectedPath; // preserve
  highlightSelected();
}

function collapseAll() {
  // Walk the entire tree and collapse every node that has children
  function walkCollapse(node, path) {
    if (typeof node === "string") return;
    const children = getChildren(node);
    if (children.length > 0) {
      state.collapsed[pathKey(path)] = true;
      const childKey = getChildrenKey(node);
      for (let i = 0; i < children.length; i++) {
        walkCollapse(children[i], [...path, childKey, i]);
      }
    }
  }
  for (let i = 0; i < state.data.length; i++) {
    walkCollapse(state.data[i], [i]);
  }
  renderTree();
  highlightSelected();
}

function expandAll() {
  state.collapsed = {};
  renderTree();
  highlightSelected();
}

function expandToLevel(maxDepth) {
  // First collapse everything, then expand nodes up to maxDepth
  state.collapsed = {};
  function walkLevel(node, path, depth) {
    if (typeof node === "string") return;
    const children = getChildren(node);
    if (children.length > 0) {
      if (depth >= maxDepth) {
        state.collapsed[pathKey(path)] = true;
      }
      const childKey = getChildrenKey(node);
      for (let i = 0; i < children.length; i++) {
        walkLevel(children[i], [...path, childKey, i], depth + 1);
      }
    }
  }
  for (let i = 0; i < state.data.length; i++) {
    walkLevel(state.data[i], [i], 0);
  }
  renderTree();
  highlightSelected();
}

function getParentArray(path) {
  // For a path like [0, "entries", 2], the parent array is at [0, "entries"]
  // For a path like [3], the parent array is state.data itself
  if (path.length === 1) return state.data;
  const parentPath = path.slice(0, -1);
  return getByPath(state.data, parentPath);
}

function moveNode(pk, direction) {
  pushUndo(`Move ${direction < 0 ? "up" : "down"}`);
  const path = parsePath(pk);
  const idx = path[path.length - 1];
  const parent = getParentArray(path);
  if (!Array.isArray(parent)) return;
  const newIdx = idx + direction;
  if (newIdx < 0 || newIdx >= parent.length) return;
  // Swap
  [parent[idx], parent[newIdx]] = [parent[newIdx], parent[idx]];
  markDirty();
  // Update selected path
  const newPath = [...path.slice(0, -1), newIdx];
  state.selectedPath = pathKey(newPath);
  renderTree();
  highlightSelected();
  renderPreview();
}

function promoteNode(pk) {
  pushUndo("Promote (outdent)");
  // Move node out of its current parent, placing it after the parent in the grandparent array
  const path = parsePath(pk);
  if (path.length <= 1) return; // Already at top level, can't promote

  // path = [...grandparentPath, childrenKey, idx]
  // We need at least 3 segments: grandparent..., "entries"/"items", index
  if (path.length < 3) return;

  const idx = path[path.length - 1]; // index in parent's children array
  const childrenKey = path[path.length - 2]; // "entries" or "items"
  const parentObjPath = path.slice(0, -2); // path to the parent object

  const parentObj = parentObjPath.length === 0 ? null : getByPath(state.data, parentObjPath);
  const parentArray = getParentArray(path);
  if (!Array.isArray(parentArray)) return;

  // Remove node from current parent
  const node = parentArray.splice(idx, 1)[0];

  // Find grandparent array and insert after the parent object
  if (parentObjPath.length === 0) {
    // Parent is a top-level item in state.data — can't promote further
    parentArray.splice(idx, 0, node); // put it back
    return;
  }

  const grandparentArray = getParentArray(parentObjPath);
  if (!Array.isArray(grandparentArray)) {
    parentArray.splice(idx, 0, node); // put it back
    return;
  }

  const parentIdx = parentObjPath[parentObjPath.length - 1];
  grandparentArray.splice(parentIdx + 1, 0, node);

  // New path is in the grandparent's array, one after parent
  const newPath = [...parentObjPath.slice(0, -1), parentIdx + 1];
  state.selectedPath = pathKey(newPath);
  markDirty();
  renderTree();
  highlightSelected();
  renderPreview();
}

function demoteNode(pk) {
  pushUndo("Demote (indent)");
  // Nest this node into the preceding sibling's children (entries/items)
  const path = parsePath(pk);
  const idx = path[path.length - 1];
  if (idx === 0) return; // No preceding sibling

  const parent = getParentArray(path);
  if (!Array.isArray(parent)) return;

  const prevSibling = parent[idx - 1];
  if (typeof prevSibling === "string" || !prevSibling) return; // Can't nest into a string

  // Determine children key for the sibling
  const sibChildKey = (prevSibling.type === "list") ? "items" : "entries";
  if (!prevSibling[sibChildKey]) prevSibling[sibChildKey] = [];

  // Remove from current position and append to sibling's children
  const node = parent.splice(idx, 1)[0];
  prevSibling[sibChildKey].push(node);

  // Ensure sibling is expanded
  const sibPath = [...path.slice(0, -1), idx - 1];
  state.collapsed[pathKey(sibPath)] = false;

  // New path is inside the sibling
  const newChildIdx = prevSibling[sibChildKey].length - 1;
  const newPath = [...sibPath, sibChildKey, newChildIdx];
  state.selectedPath = pathKey(newPath);
  markDirty();
  renderTree();
  highlightSelected();
  renderPreview();
}

function deleteNode(pk) {
  if (!confirm("Delete this block?")) return;
  pushUndo("Delete block");
  const path = parsePath(pk);
  deleteByPath(state.data, path);
  state.selectedPath = null;
  markDirty();
  renderTree();
  renderPreview();
}

function addTopLevelSection() {
  pushUndo("Add section");
  state.data.push({
    type: "section",
    name: "New Section",
    entries: [],
  });
  const pk = pathKey([state.data.length - 1]);
  state.selectedPath = pk;
  markDirty();
  renderTree();
  highlightSelected();
  renderPreview();
}

// =========================================================================
// Add block — modal-based type picker with smart paste
// =========================================================================
let _addBlockCallback = null;

function addSibling(pk) {
  openAddBlockModal((newNode) => {
    const type = typeof newNode === "string" ? "text" : (newNode.type || "block");
    pushUndo(`Add ${type}`);
    const path = parsePath(pk);
    insertAfterPath(state.data, path, newNode);
    const newPath = [...path.slice(0, -1), path[path.length - 1] + 1];
    state.selectedPath = pathKey(newPath);
    markDirty();
    renderTree();
    highlightSelected();
    renderPreview();
  });
}

function addChild(pk) {
  openAddBlockModal((newNode) => {
    const type = typeof newNode === "string" ? "text" : (newNode.type || "block");
    pushUndo(`Add child ${type}`);
    const path = parsePath(pk);
    const node = getByPath(state.data, path);
    if (!node || typeof node === "string") return;
    const childKey = getChildrenKey(node);
    if (!node[childKey]) node[childKey] = [];
    node[childKey].push(newNode);
    state.collapsed[pk] = false;
    const newPath = [...path, childKey, node[childKey].length - 1];
    state.selectedPath = pathKey(newPath);
    markDirty();
    renderTree();
    highlightSelected();
    renderPreview();
  });
}

function openAddBlockModal(callback) {
  _addBlockCallback = callback;
  // Reset modal state
  document.getElementById("addBlockType").value = "entries";
  document.getElementById("addBlockName").value = "";
  document.getElementById("addBlockPaste").value = "";
  document.getElementById("addBlockParseResult").innerHTML = "";
  document.getElementById("addBlockNameRow").style.display = "";
  document.getElementById("addBlockPasteRow").style.display = "none";
  onAddBlockTypeChange();
  const modal = new bootstrap.Modal(document.getElementById("addBlockModal"));
  modal.show();
  // Focus the name field after modal opens
  document.getElementById("addBlockModal").addEventListener("shown.bs.modal", () => {
    const nameField = document.getElementById("addBlockName");
    if (nameField.offsetParent !== null) nameField.focus();
  }, { once: true });
}

function onAddBlockTypeChange() {
  const type = document.getElementById("addBlockType").value;
  const nameRow = document.getElementById("addBlockNameRow");
  const pasteRow = document.getElementById("addBlockPasteRow");
  const parseResult = document.getElementById("addBlockParseResult");
  parseResult.innerHTML = "";

  // Show/hide fields based on type
  if (type === "section" || type === "entries" || type === "inset") {
    nameRow.style.display = "";
    pasteRow.style.display = "none";
  } else if (type === "table" || type === "statblock") {
    nameRow.style.display = "";
    pasteRow.style.display = "";
  } else if (type === "insetReadaloud" || type === "text") {
    nameRow.style.display = "none";
    pasteRow.style.display = "";
    document.getElementById("addBlockPaste").placeholder =
      type === "text" ? "Enter paragraph text..." : "Enter read-aloud text...";
  } else {
    nameRow.style.display = "none";
    pasteRow.style.display = "none";
  }
}

function onAddBlockPasteInput() {
  const type = document.getElementById("addBlockType").value;
  const text = document.getElementById("addBlockPaste").value;
  const resultDiv = document.getElementById("addBlockParseResult");

  if (!text.trim()) { resultDiv.innerHTML = ""; return; }

  if (type === "table") {
    const parsed = parseTableText(text);
    if (parsed) {
      let html = '<div class="mt-2"><small class="text-success">Parsed table:</small>';
      html += '<table class="table table-sm table-bordered mt-1" style="font-size:12px"><thead><tr>';
      for (const col of parsed.colLabels) html += `<th>${escHtml(col)}</th>`;
      html += '</tr></thead><tbody>';
      for (const row of parsed.rows.slice(0, 5)) {
        html += '<tr>';
        for (const cell of row) html += `<td>${escHtml(cell)}</td>`;
        html += '</tr>';
      }
      if (parsed.rows.length > 5) html += `<tr><td colspan="${parsed.colLabels.length}" class="text-muted">...${parsed.rows.length - 5} more rows</td></tr>`;
      html += '</tbody></table></div>';
      resultDiv.innerHTML = html;
    } else {
      resultDiv.innerHTML = '<small class="text-warning">Could not parse as table. Try tab-separated or pipe-separated format.</small>';
    }
  } else if (type === "statblock") {
    const parsed = parseStatblockText(text);
    let html = '<div class="mt-2"><small class="text-success">Parsed stat block:</small>';
    html += '<table class="table table-sm table-bordered mt-1" style="font-size:12px"><tbody>';
    for (const row of parsed.rows.slice(0, 8)) {
      html += `<tr><td><b>${escHtml(row[0])}</b></td><td>${escHtml(row[1])}</td></tr>`;
    }
    if (parsed.rows.length > 8) html += `<tr><td colspan="2" class="text-muted">...${parsed.rows.length - 8} more rows</td></tr>`;
    if (parsed.traits.length > 0) {
      html += `<tr><td colspan="2" class="text-muted">${parsed.traits.length} trait(s)/action(s) found</td></tr>`;
    }
    html += '</tbody></table></div>';
    resultDiv.innerHTML = html;
  }
}

function parseTableText(text) {
  // Try tab-separated first, then pipe-separated, then multi-space
  const lines = text.trim().split("\n").filter(l => l.trim());
  if (lines.length < 2) return null;

  let separator = null;
  // Detect separator from first line
  if (lines[0].includes("\t")) separator = "\t";
  else if (lines[0].includes("|")) separator = "|";
  else if (lines[0].match(/  {2,}/)) separator = /  {2,}/;

  if (!separator) {
    // Try key:value or key=value format (2-column)
    const kvLines = lines.filter(l => l.match(/^[^:=]+[:=].+/));
    if (kvLines.length >= lines.length * 0.6) {
      const rows = [];
      for (const l of lines) {
        const m = l.match(/^([^:=]+)[:=]\s*(.*)/);
        if (m) rows.push([m[1].trim(), m[2].trim()]);
        else rows.push([l.trim(), ""]);
      }
      return { colLabels: ["Attribute", "Value"], rows };
    }
    return null;
  }

  const splitLine = (line) => {
    if (separator instanceof RegExp) return line.split(separator).map(s => s.trim());
    return line.split(separator).map(s => s.trim()).filter(s => s !== "");
  };

  const headerCells = splitLine(lines[0]);
  if (headerCells.length < 2) return null;

  // Skip separator lines (e.g., "---|---" or "====")
  let startRow = 1;
  if (lines[startRow] && lines[startRow].match(/^[\s|=\-:+]+$/)) startRow++;

  const rows = [];
  for (let i = startRow; i < lines.length; i++) {
    const cells = splitLine(lines[i]);
    // Pad or trim to match header count
    while (cells.length < headerCells.length) cells.push("");
    rows.push(cells.slice(0, headerCells.length));
  }

  return { colLabels: headerCells, rows };
}

function parseStatblockText(text) {
  // Parse stat block text into key-value rows + traits/actions
  const lines = text.trim().split("\n").filter(l => l.trim());
  const rows = [];
  const traits = [];
  const knownKeys = [
    "Type", "Armor Class", "Hit Points", "Speed", "STR", "DEX", "CON",
    "INT", "WIS", "CHA", "Saving Throws", "Skills", "Damage Resistances",
    "Damage Immunities", "Condition Immunities", "Senses", "Languages",
    "Challenge", "Proficiency Bonus", "Damage Vulnerabilities",
  ];

  let inTraits = false;
  let currentTrait = null;

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;

    // Check if it's a known key-value pair
    let matched = false;
    if (!inTraits) {
      for (const key of knownKeys) {
        if (trimmed.startsWith(key)) {
          let value = trimmed.substring(key.length).replace(/^[\s.:]+/, "").trim();
          // Handle "Armor Class 14 (natural armor)" format
          if (!value && trimmed.match(new RegExp(`^${key}\\s+(.+)`, "i"))) {
            value = trimmed.match(new RegExp(`^${key}\\s+(.+)`, "i"))[1];
          }
          rows.push([key, value]);
          matched = true;
          break;
        }
      }
      // Check for ability score line: "12 (+1) 14 (+2) ..."
      if (!matched && trimmed.match(/^\d+\s*\([+\-]\d+\)/)) {
        const scores = trimmed.match(/(\d+)\s*\([+\-]?\d+\)/g);
        if (scores && scores.length >= 6) {
          const abilities = ["STR", "DEX", "CON", "INT", "WIS", "CHA"];
          for (let i = 0; i < 6 && i < scores.length; i++) {
            const m = scores[i].match(/(\d+)/);
            if (m) rows.push([abilities[i], scores[i]]);
          }
          matched = true;
        }
      }
    }

    if (!matched) {
      inTraits = true;
      // Check if this looks like a trait/action header (bold text followed by period)
      const traitMatch = trimmed.match(/^([A-Z][^.]+)\.\s*(.*)/);
      if (traitMatch) {
        if (currentTrait) traits.push(currentTrait);
        currentTrait = { name: traitMatch[1].trim(), text: traitMatch[2] || "" };
      } else if (currentTrait) {
        currentTrait.text += (currentTrait.text ? " " : "") + trimmed;
      } else {
        // Fallback: treat as trait with no name
        if (currentTrait) traits.push(currentTrait);
        currentTrait = { name: "", text: trimmed };
      }
    }
  }
  if (currentTrait) traits.push(currentTrait);

  return { rows, traits };
}

function confirmAddBlock() {
  const type = document.getElementById("addBlockType").value;
  const name = document.getElementById("addBlockName").value.trim();
  const pasteText = document.getElementById("addBlockPaste").value.trim();

  let newNode;

  switch (type) {
    case "section":
      newNode = { type: "section", name: name || "New Section", entries: [] };
      break;
    case "entries":
      newNode = { type: "entries", name: name || "New Heading", entries: [] };
      break;
    case "inset":
      newNode = { type: "inset", name: name || "Sidebar", entries: [] };
      break;
    case "insetReadaloud":
      newNode = { type: "insetReadaloud", entries: pasteText ? pasteText.split("\n").filter(l => l.trim()) : ["Read-aloud text."] };
      break;
    case "text":
      newNode = pasteText || "New paragraph text";
      break;
    case "list":
      newNode = { type: "list", items: ["Item 1"] };
      break;
    case "hr":
      newNode = { type: "hr" };
      break;
    case "image":
      newNode = { type: "image", href: { type: "internal", path: "" }, title: name || "" };
      break;
    case "quote":
      newNode = { type: "quote", entries: pasteText ? pasteText.split("\n").filter(l => l.trim()) : ["Quote text."], by: "", from: "" };
      break;
    case "table": {
      const parsed = pasteText ? parseTableText(pasteText) : null;
      if (parsed) {
        newNode = {
          type: "table",
          colLabels: parsed.colLabels,
          colStyles: parsed.colLabels.map(() => ""),
          rows: parsed.rows,
        };
        if (name) newNode.caption = name;
      } else {
        newNode = {
          type: "table",
          colLabels: ["Column 1", "Column 2"],
          colStyles: ["", ""],
          rows: [["", ""]],
        };
        if (name) newNode.caption = name;
      }
      break;
    }
    case "statblock": {
      const parsed = pasteText ? parseStatblockText(pasteText) : { rows: [], traits: [] };
      // Build as an entries block with a stat-block table + trait entries
      const children = [];
      if (parsed.rows.length > 0) {
        children.push({
          type: "table",
          colLabels: ["Attribute", "Value"],
          colStyles: ["", ""],
          rows: parsed.rows,
        });
      }
      for (const trait of parsed.traits) {
        if (trait.name) {
          children.push({
            type: "entries",
            name: trait.name,
            entries: trait.text ? [trait.text] : [],
          });
        } else if (trait.text) {
          children.push(trait.text);
        }
      }
      newNode = {
        type: "entries",
        name: name || "Stat Block",
        entries: children.length > 0 ? children : [],
      };
      break;
    }
    default:
      newNode = "New paragraph text";
  }

  // Close modal
  bootstrap.Modal.getInstance(document.getElementById("addBlockModal")).hide();

  if (_addBlockCallback) {
    _addBlockCallback(newNode);
    _addBlockCallback = null;
  }
}

// =========================================================================
// Preview rendering
// =========================================================================
function renderPreview() {
  const area = document.getElementById("previewArea");
  if (!state.data.length) {
    area.innerHTML = '<div class="text-muted text-center mt-5">Preview will appear here</div>';
    return;
  }
  let html = "";
  for (let i = 0; i < state.data.length; i++) {
    html += renderPreviewNode(state.data[i], [i], 0);
  }
  area.innerHTML = html;
  highlightSelected();
}

function renderPreviewNode(node, path, depth) {
  const pk = pathKey(path);
  const type = getNodeType(node);

  if (type === "string") {
    return `<p class="pv-para" data-pv-path='${pk}'>${renderTags(escHtml(node))}</p>`;
  }

  if (type === "hr") {
    return `<hr class="pv-hr" data-pv-path='${pk}'>`;
  }

  if (type === "section") {
    let h = `<div class="pv-section" data-pv-path='${pk}'>`;
    h += `<h2>${renderTags(escHtml(node.name || ""))}</h2>`;
    h += renderPreviewChildren(node, path, depth);
    h += `</div>`;
    return h;
  }

  if (type === "entries") {
    const hLevel = Math.min(depth + 3, 5);
    let h = `<div class="pv-entries" data-pv-path='${pk}'>`;
    if (node.name) h += `<h${hLevel}>${renderTags(escHtml(node.name))}</h${hLevel}>`;
    h += renderPreviewChildren(node, path, depth + 1);
    h += `</div>`;
    return h;
  }

  if (type === "inset") {
    let h = `<div class="pv-inset" data-pv-path='${pk}'>`;
    if (node.name) h += `<div class="pv-inset-title">${renderTags(escHtml(node.name))}</div>`;
    h += renderPreviewChildren(node, path, depth);
    h += `</div>`;
    return h;
  }

  if (type === "insetReadaloud") {
    let h = `<div class="pv-readaloud" data-pv-path='${pk}'>`;
    h += renderPreviewChildren(node, path, depth);
    h += `</div>`;
    return h;
  }

  if (type === "list") {
    let h = `<ul class="pv-list" data-pv-path='${pk}'>`;
    for (const item of (node.items || [])) {
      if (typeof item === "string") {
        h += `<li>${renderTags(escHtml(item))}</li>`;
      } else if (item && item.type === "item") {
        h += `<li>`;
        if (item.name) h += `<b>${renderTags(escHtml(item.name))}</.</b> `;
        h += renderTags(escHtml(item.entry || ""));
        h += `</li>`;
      } else if (typeof item === "object") {
        h += `<li>${renderTags(escHtml(JSON.stringify(item)))}</li>`;
      }
    }
    h += `</ul>`;
    return h;
  }

  if (type === "table") {
    let h = `<table class="pv-table" data-pv-path='${pk}'>`;
    if (node.caption) h += `<caption>${renderTags(escHtml(node.caption))}</caption>`;
    if (node.colLabels && node.colLabels.length) {
      h += `<thead><tr>`;
      for (const col of node.colLabels) h += `<th>${renderTags(escHtml(col))}</th>`;
      h += `</tr></thead>`;
    }
    h += `<tbody>`;
    for (const row of (node.rows || [])) {
      if (Array.isArray(row)) {
        h += `<tr>`;
        for (const cell of row) h += `<td>${renderTags(escHtml(String(cell)))}</td>`;
        h += `</tr>`;
      }
    }
    h += `</tbody></table>`;
    return h;
  }

  if (type === "image") {
    const title = node.title || (node.href && node.href.path) || "Image";
    return `<div class="pv-image" data-pv-path='${pk}'>[Image: ${escHtml(title)}]</div>`;
  }

  if (type === "quote") {
    let h = `<div class="pv-quote" data-pv-path='${pk}'>`;
    for (const e of (node.entries || [])) {
      if (typeof e === "string") h += `<p>${renderTags(escHtml(e))}</p>`;
    }
    if (node.by || node.from) {
      h += `<div class="pv-quote-by">\u2014 `;
      if (node.by) h += escHtml(node.by);
      if (node.from) h += `, <i>${escHtml(node.from)}</i>`;
      h += `</div>`;
    }
    h += `</div>`;
    return h;
  }

  // Fallback: unknown type with entries
  if (node.entries) {
    let h = `<div data-pv-path='${pk}'>`;
    if (node.name) h += `<b>${renderTags(escHtml(node.name))}</b>`;
    h += renderPreviewChildren(node, path, depth);
    h += `</div>`;
    return h;
  }

  return `<p class="pv-para text-muted" data-pv-path='${pk}'>[${type}]</p>`;
}

function renderPreviewChildren(node, path, depth) {
  let h = "";
  const childKey = getChildrenKey(node);
  const children = node[childKey] || [];
  for (let i = 0; i < children.length; i++) {
    h += renderPreviewNode(children[i], [...path, childKey, i], depth);
  }
  return h;
}

// =========================================================================
// {@tag} rendering for preview
// =========================================================================
function renderTags(html) {
  // Process {@tag ...} patterns
  // Note: html is already escaped, so { and } are literal, @ is literal
  return html.replace(/\{@(\w+)\s*([^}]*)\}/g, (match, tag, content) => {
    content = content.trim();
    // Split on | for display text
    const parts = content.split("|");
    const name = parts[0];
    const display = parts.length > 1 ? parts[1] : name;

    switch (tag) {
      case "b": return `<b>${display}</b>`;
      case "i": return `<i>${display}</i>`;
      case "bold": return `<b>${display}</b>`;
      case "italic": return `<i>${display}</i>`;
      case "spell": return `<i class="tag-spell">${display}</i>`;
      case "creature": return `<span class="tag-creature">${display}</span>`;
      case "condition": return `<span class="tag-condition">${display}</span>`;
      case "dc": return `<span class="tag-dc">DC ${name}</span>`;
      case "damage": return `<span class="tag-damage">${name}</span>`;
      case "hit": return `<span class="tag-hit">+${name}</span>`;
      case "h": return `<i>Hit:</i> `;
      case "item": return `<span class="tag-item">${display}</span>`;
      case "skill": return `<span class="tag-skill">${display}</span>`;
      case "atk": return `<i>[${name}]</i>`;
      case "recharge": return `(Recharge ${name})`;
      case "dice": return `${name}`;
      case "note": return `<i>(${display})</i>`;
      case "area": return `<b>${display}</b>`;
      case "adventure": return `<i>${display}</i>`;
      case "book": return `<i>${display}</i>`;
      case "sense": return display;
      case "chance": return `${name}%`;
      case "scaledice": return display || name;
      case "scaledamage": return display || name;
      case "filter": return display;
      case "action": return `<span class="tag-condition">${display}</span>`;
      case "status": return `<span class="tag-condition">${display}</span>`;
      default: return `<span title="{@${tag}}">${display || name}</span>`;
    }
  });
}

// =========================================================================
// Undo / Redo
// =========================================================================

// Push current state as an undo checkpoint BEFORE the mutation happens.
// Call this at the start of every mutating operation.
function pushUndo(action) {
  const snapshot = JSON.parse(JSON.stringify(state.data));
  // Fire-and-forget persist to server
  fetch("/api/undolog/push", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ path: state.path, action, data: snapshot }),
  }).then(r => r.json()).then(res => {
    if (res.ok) {
      state.undoPosition = res.position;
      state.undoTotal = res.total;
      updateUndoUI();
    }
  }).catch(() => {});
}

// Debounced undo push for text edits — capture state on first keystroke,
// commit the checkpoint after 1s of inactivity
let _textUndoTimer = null;
let _textUndoCaptured = false;
function pushUndoDebounced(action) {
  if (!_textUndoCaptured) {
    // Capture snapshot before first keystroke in this burst
    _textUndoCaptured = true;
    pushUndo(action);
  }
  clearTimeout(_textUndoTimer);
  _textUndoTimer = setTimeout(() => { _textUndoCaptured = false; }, 1000);
}

async function doUndo() {
  if (!state.path) return;
  try {
    const resp = await fetch("/api/undolog/undo", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ path: state.path }),
    });
    const result = await resp.json();
    if (result.error) { setStatus("Undo: " + result.error, "text-warning"); return; }
    state.data = result.data;
    state.undoPosition = result.position;
    state.undoTotal = result.total;
    state.selectedPath = null;
    markDirty();
    renderTree();
    renderPreview();
    updateUndoUI();
    setStatus(`Undid: ${result.action}`, "text-info");
  } catch (e) {
    setStatus("Undo failed: " + e.message, "text-danger");
  }
}

async function doRedo() {
  if (!state.path) return;
  try {
    const resp = await fetch("/api/undolog/redo", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ path: state.path }),
    });
    const result = await resp.json();
    if (result.error) { setStatus("Redo: " + result.error, "text-warning"); return; }
    state.data = result.data;
    state.undoPosition = result.position;
    state.undoTotal = result.total;
    state.selectedPath = null;
    markDirty();
    renderTree();
    renderPreview();
    updateUndoUI();
    setStatus(`Redid: ${result.action}`, "text-info");
  } catch (e) {
    setStatus("Redo failed: " + e.message, "text-danger");
  }
}

async function jumpToUndo(idx) {
  if (!state.path) return;
  try {
    const resp = await fetch("/api/undolog/jump", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ path: state.path, idx }),
    });
    const result = await resp.json();
    if (result.error) { setStatus(result.error, "text-danger"); return; }
    state.data = result.data;
    state.undoPosition = result.position;
    state.undoTotal = result.total;
    state.selectedPath = null;
    markDirty();
    renderTree();
    renderPreview();
    updateUndoUI();
    setStatus(`Jumped to: ${result.action}`, "text-info");
  } catch (e) {
    setStatus("Jump failed: " + e.message, "text-danger");
  }
}

function updateUndoUI() {
  const pos = state.undoPosition ?? -1;
  const total = state.undoTotal ?? 0;
  document.getElementById("undoBtn").disabled = (pos < 0);
  document.getElementById("redoBtn").disabled = (pos + 1 >= total);
  document.getElementById("historyBtn").disabled = (total === 0);
  refreshHistoryMenu();
}

async function refreshHistoryMenu() {
  if (!state.path) return;
  try {
    const resp = await fetch(`/api/undolog?path=${encodeURIComponent(state.path)}`);
    const result = await resp.json();
    const menu = document.getElementById("historyMenu");
    const entries = result.entries || [];
    const pos = result.position ?? -1;
    if (entries.length === 0) {
      menu.innerHTML = '<li class="px-3 py-1 text-muted">No history</li>';
      return;
    }
    let html = "";
    // Show newest first
    for (let i = entries.length - 1; i >= 0; i--) {
      const e = entries[i];
      const active = (i === pos) ? "active" : "";
      const ts = new Date(e.ts * 1000).toLocaleTimeString();
      html += `<li><a class="dropdown-item ${active}" href="#" onclick="event.preventDefault(); jumpToUndo(${i})">`;
      html += `<span class="text-muted me-2" style="font-size:10px">${ts}</span>`;
      html += `${escHtml(e.action)}`;
      html += `</a></li>`;
    }
    menu.innerHTML = html;
  } catch (e) { /* ignore */ }
}

// =========================================================================
// Keyboard shortcuts
// =========================================================================
document.addEventListener("keydown", (e) => {
  // Ctrl+S = save
  if ((e.ctrlKey || e.metaKey) && e.key === "s") {
    e.preventDefault();
    if (state.dirty) doSave();
  }
  // Ctrl+Z = undo
  if ((e.ctrlKey || e.metaKey) && e.key === "z" && !e.shiftKey) {
    e.preventDefault();
    doUndo();
  }
  // Ctrl+Shift+Z or Ctrl+Y = redo
  if ((e.ctrlKey || e.metaKey) && (e.key === "Z" || e.key === "y")) {
    e.preventDefault();
    doRedo();
  }
});

// =========================================================================
// Init
// =========================================================================
(async function init() {
  await loadFileList();
  const preload = "__PRELOAD__";
  if (preload) {
    document.getElementById("fileSel").value = preload;
    doLoad();
  }
})();
</script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    global _preload_file

    parser = argparse.ArgumentParser(description="Visual block editor for 5etools adventure JSON")
    parser.add_argument("file", nargs="?", default=None, help="JSON file to pre-load")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5104)))
    args = parser.parse_args()

    if args.file:
        _preload_file = args.file

    print(f"Adventure Editor: http://localhost:{args.port}")
    app.run(host="0.0.0.0", port=args.port, debug=True)


if __name__ == "__main__":
    main()
