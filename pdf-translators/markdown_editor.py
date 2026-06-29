#!/usr/bin/env python3
"""markdown_editor.py — heading-tree editor for Markdown files.

Collapsible heading tree (left) + raw markdown preview (right).
Designed for cleaning up OCR output from extract_markdown.py before
running pdf_to_5etools_v2.py --from-markdown.

Operations per heading row:
  ▶/▼  expand/collapse (only shown when heading has children)
  ↑ ↓  move section up/down within siblings (moves entire subtree)
  ◀ ▶  promote/demote heading level (change # count)
  ✕    delete heading + its content (undo recovers it)

Keyboard shortcuts (when not editing):
  u / d  move focused section up/down
  [  ]   promote / demote
  Del    delete section
  Ctrl+Z / Ctrl+Shift+Z  undo / redo
  Ctrl+S  save

Usage:
    python3 markdown_editor.py [file.md] [--port N]
    # http://localhost:5107
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from flask import Flask, jsonify, request

app = Flask(__name__)
_preload_file: str = ""
DEFAULT_PORT = 5107


# ── Flask routes ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return _HTML.replace("__PRELOAD__", _preload_file)


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
    path = Path(request.args.get("file", ""))
    if not path.exists():
        return jsonify({"error": f"Not found: {path}"}), 404
    return jsonify({"content": path.read_text(encoding="utf-8"),
                    "path": str(path.resolve())})


@app.route("/api/save", methods=["POST"])
def api_save():
    data = request.json
    path = Path(data["path"])
    content = data["content"]
    if path.exists():
        path.with_suffix(path.suffix + ".bak").write_text(
            path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(content, encoding="utf-8")
    return jsonify({"ok": True})


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
        _preload_file = str(args.file.resolve())
    print(f"Markdown editor → http://localhost:{args.port}")
    app.run(host="0.0.0.0", port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())


# ── HTML / CSS / JS (single-file inline template) ────────────────────────────

_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Markdown Editor</title>
<link rel="stylesheet"
  href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
<style>
  body { overflow: hidden; height: 100vh; display: flex; flex-direction: column; }
  #toolbar { flex: 0 0 auto; background: #212529; padding: 6px 12px;
             display: flex; align-items: center; gap: 8px; }
  #toolbar select, #toolbar input { max-width: 340px; font-size: .85rem; }
  #main  { flex: 1 1 0; display: flex; overflow: hidden; }
  #tree-panel  { width: 38%; overflow-y: auto; border-right: 2px solid #dee2e6;
                 padding: 6px 0; background: #f8f9fa; }
  #prev-panel  { flex: 1; overflow-y: auto; padding: 12px 16px;
                 background: #fff; font-family: monospace; font-size: .82rem;
                 white-space: pre-wrap; word-break: break-word; }

  /* heading rows */
  .hrow { display: flex; align-items: center; padding: 2px 6px 2px 4px;
          cursor: pointer; user-select: none; gap: 4px; }
  .hrow:hover { background: #e9ecef; }
  .hrow.selected { background: #cfe2ff; }
  .hrow.editing  { background: #fff3cd; }

  .hrow-toggle { width: 16px; text-align: center; flex-shrink: 0;
                 color: #6c757d; font-size: .75rem; }
  .hrow-badge  { flex-shrink: 0; width: 22px; text-align: center;
                 font-size: .7rem; font-weight: 700; border-radius: 3px;
                 padding: 1px 0; color: #fff; }
  .lvl-0 { background:#adb5bd; }
  .lvl-1 { background:#0d6efd; }
  .lvl-2 { background:#198754; }
  .lvl-3 { background:#fd7e14; }
  .lvl-4 { background:#6f42c1; }
  .lvl-5 { background:#dc3545; }
  .lvl-6 { background:#6c757d; }

  .hrow-text { flex: 1; overflow: hidden; text-overflow: ellipsis;
               white-space: nowrap; font-size: .85rem; }
  .hrow-text input { width: 100%; border: none; background: transparent;
                     font-size: .85rem; padding: 0; outline: 1px solid #0d6efd; }

  .hrow-acts { display: none; gap: 2px; flex-shrink: 0; }
  .hrow:hover .hrow-acts { display: flex; }
  .hrow.selected .hrow-acts { display: flex; }
  .hrow-acts button { padding: 0 5px; font-size: .75rem; line-height: 1.4;
                      border: 1px solid #dee2e6; border-radius: 3px;
                      background: #fff; cursor: pointer; }
  .hrow-acts button:hover { background: #e9ecef; }
  .hrow-acts .btn-del { color: #dc3545; border-color: #dc3545; }
  .hrow-acts button:disabled { opacity: .35; cursor: default; }

  /* preview highlight */
  .ph   { background: #fff3cd; }
  .ph-h { font-weight: bold; color: #0d6efd; }

  /* status bar */
  #status { flex: 0 0 auto; background: #343a40; color: #adb5bd;
            font-size: .75rem; padding: 2px 12px; }
</style>
</head>
<body>

<div id="toolbar">
  <span class="text-light fw-bold me-1" style="font-size:.9rem">MD</span>
  <input id="file-input" class="form-control form-control-sm" type="text"
         placeholder="path/to/file.md" style="max-width:380px">
  <button class="btn btn-sm btn-outline-light" id="btn-load">Load</button>
  <div class="vr" style="background:#6c757d;margin:0 4px"></div>
  <button class="btn btn-sm btn-outline-secondary" id="btn-undo" title="Undo (Ctrl+Z)">↩</button>
  <button class="btn btn-sm btn-outline-secondary" id="btn-redo" title="Redo (Ctrl+Shift+Z)">↪</button>
  <div class="vr" style="background:#6c757d;margin:0 4px"></div>
  <button class="btn btn-sm btn-success" id="btn-save" title="Save (Ctrl+S)">💾 Save</button>
  <span id="dirty-flag" class="text-warning ms-1" style="display:none">●</span>
</div>

<div id="main">
  <div id="tree-panel"></div>
  <div id="prev-panel"></div>
</div>

<div id="status">No file loaded.</div>

<script>
// ── State ──────────────────────────────────────────────────────────────────
let blocks   = [];          // [{id,level,text,body}]
let collapsed = new Set();  // indices of collapsed headings
let selected  = -1;         // focused row index
let currentFile = "";
let dirty = false;

// Undo / redo stacks — each entry is {blocks, collapsed, selected}
let undoStack = [];
let redoStack = [];

// ── Parse / serialize ──────────────────────────────────────────────────────

function parseMarkdown(md) {
  const lines = md.split('\n');
  const result = [];
  let cur = null;
  let pre = null;      // preamble accumulator

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const m = line.match(/^(#{1,6})\s+(.*)/);
    if (m) {
      if (cur) result.push(cur);
      else if (pre !== null) {
        if (pre.trim()) result.push({id: result.length, level: 0, text: '', body: pre});
        pre = null;
      }
      cur = {id: result.length, level: m[1].length, text: m[2], body: ''};
    } else {
      if (cur) {
        cur.body += line + (i < lines.length - 1 ? '\n' : '');
      } else {
        if (pre === null) pre = '';
        pre += line + (i < lines.length - 1 ? '\n' : '');
      }
    }
  }
  if (cur) result.push(cur);
  else if (pre !== null && pre.trim())
    result.push({id: result.length, level: 0, text: '', body: pre});

  // Assign stable ids
  result.forEach((b, i) => { b.id = i; });
  return result;
}

function blocksToMarkdown(blks) {
  return blks.map(b => {
    if (b.level === 0) return b.body;
    const hdr = '#'.repeat(b.level) + ' ' + b.text;
    return b.body ? hdr + '\n' + b.body : hdr;
  }).join('\n');
}

// ── Tree helpers ───────────────────────────────────────────────────────────

function hasChildren(blks, i) {
  return i + 1 < blks.length && blks[i + 1].level > blks[i].level;
}

// Returns exclusive end index of the section starting at i
function sectionEnd(blks, i) {
  const lvl = blks[i].level;
  let j = i + 1;
  while (j < blks.length && blks[j].level > lvl) j++;
  return j;
}

// Returns visible block indices given the current collapsed set
function visibleIndices(blks, col) {
  const vis = [];
  const hideStack = []; // stack of levels currently hiding children
  for (let i = 0; i < blks.length; i++) {
    const lvl = blks[i].level;
    while (hideStack.length && lvl <= hideStack[hideStack.length - 1]) hideStack.pop();
    if (!hideStack.length) {
      vis.push(i);
      if (col.has(i) && hasChildren(blks, i)) hideStack.push(lvl);
    }
  }
  return vis;
}

// Previous sibling index at same level (or -1)
function prevSibling(blks, i) {
  const lvl = blks[i].level;
  let j = i - 1;
  while (j >= 0 && blks[j].level > lvl) j--;
  return (j >= 0 && blks[j].level === lvl) ? j : -1;
}

// Next sibling index at same level (or -1)
function nextSibling(blks, i) {
  const end = sectionEnd(blks, i);
  return (end < blks.length && blks[end].level === blks[i].level) ? end : -1;
}

// ── Mutations (return new arrays; do not mutate) ───────────────────────────

function moveSectionUp(blks, i) {
  const prev = prevSibling(blks, i);
  if (prev < 0) return blks;
  const end = sectionEnd(blks, i);
  return [
    ...blks.slice(0, prev),
    ...blks.slice(i, end),
    ...blks.slice(prev, i),
    ...blks.slice(end),
  ];
}

function moveSectionDown(blks, i) {
  const next = nextSibling(blks, i);
  if (next < 0) return blks;
  const myEnd  = next;          // my group ends where next sibling starts
  const nxtEnd = sectionEnd(blks, next);
  return [
    ...blks.slice(0, i),
    ...blks.slice(next, nxtEnd),
    ...blks.slice(i, myEnd),
    ...blks.slice(nxtEnd),
  ];
}

function changeLevel(blks, i, delta) {
  const b = blks[i];
  const newLvl = Math.max(1, Math.min(6, b.level + delta));
  if (newLvl === b.level) return blks;
  const copy = blks.map((x, j) => j === i ? {...x, level: newLvl} : x);
  return copy;
}

function deleteSection(blks, i) {
  const end = sectionEnd(blks, i);
  return [...blks.slice(0, i), ...blks.slice(end)];
}

// ── History ────────────────────────────────────────────────────────────────

function snapshot() {
  return {blocks: blocks.map(b => ({...b})),
          collapsed: new Set(collapsed),
          selected};
}

function pushHistory() {
  undoStack.push(snapshot());
  redoStack = [];
  if (undoStack.length > 100) undoStack.shift();
}

function applySnapshot(s) {
  blocks   = s.blocks;
  collapsed = s.collapsed;
  selected  = s.selected;
}

function undo() {
  if (!undoStack.length) return;
  redoStack.push(snapshot());
  applySnapshot(undoStack.pop());
  render();
  setDirty(true);
}

function redo() {
  if (!redoStack.length) return;
  undoStack.push(snapshot());
  applySnapshot(redoStack.pop());
  render();
  setDirty(true);
}

// ── Dirty / save ──────────────────────────────────────────────────────────

function setDirty(v) {
  dirty = v;
  document.getElementById('dirty-flag').style.display = v ? '' : 'none';
  document.title = (v ? '● ' : '') + (currentFile.split('/').pop() || 'Markdown Editor');
}

async function save() {
  if (!currentFile) { status('No file loaded.'); return; }
  const md = blocksToMarkdown(blocks);
  const r = await fetch('/api/save', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({path: currentFile, content: md})});
  if (r.ok) { setDirty(false); status('Saved ✓'); }
  else      { status('Save failed!'); }
}

// ── Load ──────────────────────────────────────────────────────────────────

async function loadFile(path) {
  const r = await fetch('/api/load?file=' + encodeURIComponent(path));
  if (!r.ok) { status('Load failed: ' + path); return; }
  const {content, path: resolved} = await r.json();
  currentFile = resolved;
  blocks = parseMarkdown(content);
  collapsed = new Set();
  selected = -1;
  undoStack = []; redoStack = [];
  document.getElementById('file-input').value = resolved;
  setDirty(false);
  render();
  status(`Loaded: ${resolved.split('/').pop()}  (${blocks.length} blocks)`);
}

// ── Render tree ────────────────────────────────────────────────────────────

function render() {
  renderTree();
  renderPreview();
}

function renderTree() {
  const vis = visibleIndices(blocks, collapsed);
  const panel = document.getElementById('tree-panel');
  panel.innerHTML = '';

  for (const i of vis) {
    const b = blocks[i];
    const row = document.createElement('div');
    row.className = 'hrow' + (i === selected ? ' selected' : '');
    row.dataset.idx = i;

    // indent
    const indent = (b.level > 0 ? (b.level - 1) : 0) * 14;
    row.style.paddingLeft = (4 + indent) + 'px';

    // collapse toggle
    const tog = document.createElement('span');
    tog.className = 'hrow-toggle';
    if (b.level > 0 && hasChildren(blocks, i)) {
      tog.textContent = collapsed.has(i) ? '▶' : '▼';
      tog.addEventListener('click', e => { e.stopPropagation(); toggleCollapse(i); });
    }
    row.appendChild(tog);

    // level badge
    const badge = document.createElement('span');
    badge.className = 'hrow-badge lvl-' + Math.min(b.level, 6);
    badge.textContent = b.level === 0 ? 'P' : 'L' + b.level;
    row.appendChild(badge);

    // text
    const textWrap = document.createElement('span');
    textWrap.className = 'hrow-text';
    textWrap.textContent = b.level === 0 ? '(preamble)' : (b.text || '(empty)');
    textWrap.title = b.text;
    textWrap.addEventListener('dblclick', e => { e.stopPropagation(); startEdit(i, textWrap); });
    row.appendChild(textWrap);

    // action buttons
    if (b.level > 0) {
      const acts = document.createElement('span');
      acts.className = 'hrow-acts';

      const canUp   = prevSibling(blocks, i) >= 0;
      const canDown = nextSibling(blocks, i) >= 0;

      acts.appendChild(mkBtn('◀', 'Promote (reduce #)', () => { pushHistory(); blocks = changeLevel(blocks, i, -1); setDirty(true); render(); }, b.level <= 1));
      acts.appendChild(mkBtn('▶', 'Demote (add #)',    () => { pushHistory(); blocks = changeLevel(blocks, i, +1); setDirty(true); render(); }, b.level >= 6));
      acts.appendChild(mkBtn('↑', 'Move up',   () => { pushHistory(); const ni = prevSibling(blocks, i); blocks = moveSectionUp(blocks, i);   selected = ni >= 0 ? ni : i; setDirty(true); render(); }, !canUp));
      acts.appendChild(mkBtn('↓', 'Move down', () => { pushHistory(); const ni = nextSibling(blocks, i); blocks = moveSectionDown(blocks, i); selected = ni >= 0 ? ni : i; setDirty(true); render(); }, !canDown));

      const del = mkBtn('✕', 'Delete section', () => {
        pushHistory();
        blocks = deleteSection(blocks, i);
        if (selected >= blocks.length) selected = blocks.length - 1;
        setDirty(true); render();
      });
      del.classList.add('btn-del');
      acts.appendChild(del);

      row.appendChild(acts);
    }

    // row click = select + scroll preview
    row.addEventListener('click', () => { selected = i; renderTree(); scrollPreviewTo(i); });

    panel.appendChild(row);
  }
}

function mkBtn(label, title, handler, disabled) {
  const b = document.createElement('button');
  b.textContent = label; b.title = title;
  if (disabled) b.disabled = true;
  else b.addEventListener('click', e => { e.stopPropagation(); handler(); });
  return b;
}

function toggleCollapse(i) {
  if (collapsed.has(i)) collapsed.delete(i); else collapsed.add(i);
  renderTree();
}

// ── Inline edit ───────────────────────────────────────────────────────────

function startEdit(i, textWrap) {
  const b = blocks[i];
  const inp = document.createElement('input');
  inp.value = b.text;
  textWrap.innerHTML = '';
  textWrap.appendChild(inp);
  textWrap.closest('.hrow').classList.add('editing');
  inp.focus(); inp.select();

  function commit() {
    pushHistory();
    blocks[i] = {...b, text: inp.value.trim() || b.text};
    setDirty(true);
    render();
  }
  inp.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); commit(); }
    if (e.key === 'Escape') render(); // cancel
  });
  inp.addEventListener('blur', commit);
}

// ── Preview pane ──────────────────────────────────────────────────────────

function renderPreview() {
  const md = blocksToMarkdown(blocks);
  const panel = document.getElementById('prev-panel');

  // Build preview by scanning lines and tagging heading lines
  const lines = md.split('\n');
  let html = '';
  let lineToBlock = {};  // line index → block index
  let lineIdx = 0;

  for (let bi = 0; bi < blocks.length; bi++) {
    const b = blocks[bi];
    if (b.level === 0) {
      const bodyLines = b.body.split('\n');
      for (const l of bodyLines) {
        html += `<span>${esc(l)}\n</span>`;
        lineIdx++;
      }
    } else {
      const hline = '#'.repeat(b.level) + ' ' + b.text;
      html += `<span class="ph-h" id="ph-${bi}">${esc(hline)}\n</span>`;
      lineToBlock[lineIdx] = bi;
      lineIdx++;
      const bodyLines = b.body.split('\n');
      for (const l of bodyLines) {
        html += `<span>${esc(l)}\n</span>`;
        lineIdx++;
      }
    }
  }
  panel.innerHTML = html;

  // Highlight selected block
  if (selected >= 0) {
    const el = document.getElementById('ph-' + selected);
    if (el) el.classList.add('ph');
  }
}

function esc(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function scrollPreviewTo(i) {
  const el = document.getElementById('ph-' + i);
  if (el) el.scrollIntoView({block: 'center', behavior: 'smooth'});
  renderPreview(); // re-render to update highlight
}

// ── Status bar ────────────────────────────────────────────────────────────

function status(msg) {
  document.getElementById('status').textContent = msg;
}

// ── Keyboard shortcuts ────────────────────────────────────────────────────

document.addEventListener('keydown', e => {
  // Don't steal keys while editing an input
  if (e.target.tagName === 'INPUT') return;

  if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) { e.preventDefault(); undo(); return; }
  if ((e.ctrlKey || e.metaKey) && (e.key === 'Z' || (e.key === 'z' && e.shiftKey))) { e.preventDefault(); redo(); return; }
  if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); save(); return; }

  if (selected < 0) return;
  const b = blocks[selected];
  if (!b || b.level === 0) return;

  if (e.key === 'u') { pushHistory(); const ni = prevSibling(blocks, selected); blocks = moveSectionUp(blocks, selected);   if (ni >= 0) selected = ni; setDirty(true); render(); }
  if (e.key === 'd') { pushHistory(); const ni = nextSibling(blocks, selected); blocks = moveSectionDown(blocks, selected); if (ni >= 0) selected = ni; setDirty(true); render(); }
  if (e.key === '[') { pushHistory(); blocks = changeLevel(blocks, selected, -1); setDirty(true); render(); }
  if (e.key === ']') { pushHistory(); blocks = changeLevel(blocks, selected, +1); setDirty(true); render(); }
  if (e.key === 'Delete') {
    pushHistory();
    blocks = deleteSection(blocks, selected);
    if (selected >= blocks.length) selected = blocks.length - 1;
    setDirty(true); render();
  }
});

// ── Toolbar wiring ────────────────────────────────────────────────────────

document.getElementById('btn-load').addEventListener('click', () => {
  const v = document.getElementById('file-input').value.trim();
  if (v) loadFile(v);
});
document.getElementById('file-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') loadFile(e.target.value.trim());
});
document.getElementById('btn-undo').addEventListener('click', undo);
document.getElementById('btn-redo').addEventListener('click', redo);
document.getElementById('btn-save').addEventListener('click', save);

// ── Auto-load if a file was passed on the CLI ──────────────────────────────

const _preload = "__PRELOAD__";
if (_preload) {
  document.getElementById('file-input').value = _preload;
  loadFile(_preload);
}
</script>
</body>
</html>
"""
