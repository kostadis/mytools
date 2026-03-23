#!/usr/bin/env python3
"""
toc_editor.py — Interactive TOC editor for 5etools adventure/book JSON files.

Displays the contents[] (sidebar TOC) alongside the corresponding data[] section
at each array index so mismatches are immediately visible.  Supports inline
rename, drag-and-drop reorder, add/delete rows.  Every save appends a
before/after pair to toc_corrections.jsonl for use as training examples.

Usage:
    python3 toc_editor.py                      # http://localhost:5101
    python3 toc_editor.py adventure-foo.json   # pre-load a specific file
    PORT=5200 python3 toc_editor.py
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request

app = Flask(__name__)
CORRECTIONS_FILE = Path("toc_corrections.jsonl")

_preload_file: str = ""


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def list_json_files(root: Path = Path(".")) -> list[str]:
    results = []
    for p in sorted(root.rglob("*.json")):
        if any(part.startswith(".") or part in ("node_modules", "__pycache__")
               for part in p.parts):
            continue
        results.append(str(p))
    return results


def _snippet(entry: dict) -> str:
    """Return the first ~120 chars of readable text from an entry dict."""
    for e in entry.get("entries", []):
        if isinstance(e, str):
            return e[:120]
        if isinstance(e, dict):
            for ss in e.get("entries", []):
                if isinstance(ss, str):
                    return ss[:120]
    return ""


def load_adventure(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    if "adventure" in raw:
        index_key, data_key = "adventure", "adventureData"
    elif "book" in raw:
        index_key, data_key = "book", "bookData"
    else:
        raise ValueError("Not a valid 5etools adventure/book JSON")

    toc = raw[index_key][0].get("contents", [])
    data_items = raw[data_key][0].get("data", [])

    data_sections = []
    for i, s in enumerate(data_items):
        if isinstance(s, dict):
            data_sections.append({
                "index": i,
                "type": s.get("type", "?"),
                "name": s.get("name", ""),
                "is_section": s.get("type") == "section",
                "snippet": _snippet(s),
            })
        else:
            data_sections.append({
                "index": i,
                "type": "string",
                "name": str(s)[:80],
                "is_section": False,
                "snippet": "",
            })

    return {"toc": toc, "data_sections": data_sections}


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return HTML.replace('"__PRELOAD__"', json.dumps(_preload_file))


@app.route("/api/files")
def api_files():
    return jsonify(list_json_files())


@app.route("/api/load")
def api_load():
    path_str = request.args.get("path", "").strip()
    if not path_str:
        return jsonify({"error": "No path provided"}), 400
    try:
        return jsonify(load_adventure(Path(path_str)))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def _demote_one(data: list, contents: list, idx: int) -> None:
    """Demote data[idx] into data[idx-1] in-place. Updates contents in sync."""
    entry = data.pop(idx)
    entry["type"] = "entries"
    data[idx - 1].setdefault("entries", []).append(entry)

    if idx < len(contents):
        moved = contents.pop(idx)
        prev  = contents[idx - 1]
        prev.setdefault("headers", [])
        prev["headers"].append(moved["name"])
        if moved.get("headers"):
            prev["headers"].extend(moved["headers"])


@app.route("/api/demote", methods=["POST"])
def api_demote():
    """Move one or more data[] entries down one level into the section above.

    Body: { "path": "...", "indices": [3, 5, 7] }
    Indices are processed highest-first so earlier positions stay stable.
    """
    body    = request.json or {}
    path    = Path(body.get("path", ""))
    indices = body.get("indices", [])

    if not indices:
        return jsonify({"error": "indices list is empty"}), 400
    if any(i < 1 for i in indices):
        return jsonify({"error": "all indices must be >= 1"}), 400

    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    index_key = "adventure" if "adventure" in raw else "book"
    data_key  = "adventureData" if "adventure" in raw else "bookData"
    contents  = raw[index_key][0].get("contents", [])
    data      = raw[data_key][0].get("data", [])

    for idx in sorted(set(indices), reverse=True):
        if idx >= len(data):
            return jsonify({"error": f"index {idx} out of range"}), 400
        _demote_one(data, contents, idx)

    raw[index_key][0]["contents"] = contents
    raw[data_key][0]["data"]      = data

    bak = path.with_suffix(".bak")
    bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent="\t", ensure_ascii=False)

    return jsonify({"ok": True, "new_length": len(data)})


@app.route("/api/save", methods=["POST"])
def api_save():
    body = request.json or {}
    path = Path(body.get("path", ""))
    new_toc = body.get("toc", [])

    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    index_key = "adventure" if "adventure" in raw else "book"
    old_toc = raw[index_key][0].get("contents", [])
    raw[index_key][0]["contents"] = new_toc

    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent="\t", ensure_ascii=False)

    pair = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_file": str(path),
        "toc_before": old_toc,
        "toc_after": new_toc,
    }
    with open(CORRECTIONS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TOC Editor</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
<style>
  body { font-size: 14px; }
  .drag-handle { cursor: grab; color: #aaa; user-select: none; padding: 0 6px; }
  .drag-handle:active { cursor: grabbing; }
  .sortable-ghost { opacity: 0.4; background: #cfe2ff !important; }
  tr.mismatch td { background: #fff3cd; }
  tr.orphan td   { background: #f8d7da; }
  .data-name { color: #444; }
  .snippet   { color: #888; font-size: 0.78em; white-space: nowrap;
               overflow: hidden; text-overflow: ellipsis; max-width: 340px; }
  .hdr-input { font-size: 0.78em; color: #666; border: none; background: transparent;
               width: 100%; outline: none; padding: 1px 2px; }
  .hdr-input:focus { background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 3px; }
  #tocTable td, #tocTable th { vertical-align: middle; }
  .col-idx  { width: 2.5em; text-align: center; color: #999; font-size: 0.8em; }
  .col-drag { width: 1.5em; }
  .col-match{ width: 1.8em; text-align: center; }
  .col-type { width: 5.5em; text-align: center; }
  .col-del    { width: 2em;   text-align: center; }
  .col-demote { width: 2em;   text-align: center; }
  .col-chk    { width: 2em;   text-align: center; }
  .match-ok   { color: #198754; }
  .match-fail { color: #dc3545; font-weight: bold; }
</style>
</head>
<body class="bg-light">
<div class="container-fluid py-3" style="max-width:1200px">

  <!-- Toolbar -->
  <div class="d-flex flex-wrap align-items-center gap-2 mb-3">
    <h5 class="mb-0 me-2">TOC Editor</h5>
    <select id="fileSelect" class="form-select form-select-sm" style="max-width:420px">
      <option value="">— select a file —</option>
    </select>
    <button id="btnLoad"         class="btn btn-sm btn-primary">Load</button>
    <button id="btnSave"         class="btn btn-sm btn-success"          disabled>Save</button>
    <button id="btnRevert"       class="btn btn-sm btn-outline-secondary" disabled>Revert</button>
    <button id="btnDemoteSelect" class="btn btn-sm btn-outline-warning"   disabled>↓ Demote selected (<span id="selCount">0</span>)</button>
    <span id="statusMsg" class="ms-2 small text-muted"></span>
  </div>

  <!-- Summary bar -->
  <div id="summaryBar" class="d-none mb-2 small d-flex gap-3 align-items-center flex-wrap">
    <span>TOC entries: <strong id="sToc">0</strong></span>
    <span>Data items: <strong id="sData">0</strong></span>
    <span>Name mismatches: <strong id="sMismatch">0</strong></span>
    <span>Non-section data items: <strong id="sOrphan">0</strong></span>
    <span class="ms-auto text-muted">
      <span class="badge bg-warning text-dark">yellow</span> name mismatch &nbsp;
      <span class="badge bg-danger">red</span> data item is not a section
    </span>
  </div>

  <!-- Table -->
  <div class="card shadow-sm">
    <div class="card-body p-0">
      <table class="table table-sm table-bordered mb-0" id="tocTable">
        <thead class="table-dark">
          <tr>
            <th class="col-chk"><input type="checkbox" id="chkAll" title="Select all"></th>
            <th class="col-idx">#</th>
            <th class="col-drag"></th>
            <th>TOC Entry Name <span class="text-muted fw-normal">(editable · headers below)</span></th>
            <th class="col-match" title="Name matches data section at same index">≈</th>
            <th>Data section at this index <span class="text-muted fw-normal">(read-only)</span></th>
            <th class="col-type">Type</th>
            <th class="col-demote" title="Move this section inside the one above it">↓</th>
            <th class="col-del"></th>
          </tr>
        </thead>
        <tbody id="tocBody"></tbody>
      </table>
    </div>
  </div>

  <div class="mt-2 d-none" id="addArea">
    <button class="btn btn-sm btn-outline-primary" id="btnAdd">+ Add row</button>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.2/Sortable.min.js"></script>
<script>
const PRELOAD = "__PRELOAD__";

let currentFile  = null;
let originalToc  = null;
let dataSections = [];
let sortable     = null;

// ── Bootstrap ─────────────────────────────────────────────────────────────

fetch("/api/files").then(r => r.json()).then(files => {
  const sel = document.getElementById("fileSelect");
  files.forEach(f => {
    const o = document.createElement("option");
    o.value = o.textContent = f;
    sel.appendChild(o);
  });
  if (PRELOAD) { sel.value = PRELOAD; loadFile(PRELOAD); }
});

document.getElementById("btnLoad").onclick = () => {
  const f = document.getElementById("fileSelect").value;
  if (f) loadFile(f);
};

// ── Load ──────────────────────────────────────────────────────────────────

function loadFile(path) {
  setStatus("Loading…");
  fetch("/api/load?path=" + encodeURIComponent(path))
    .then(r => r.json())
    .then(d => {
      if (d.error) { setStatus("Error: " + d.error, true); return; }
      currentFile  = path;
      dataSections = d.data_sections;
      originalToc  = JSON.parse(JSON.stringify(d.toc));
      renderTable(d.toc);
      document.getElementById("btnSave").disabled   = false;
      document.getElementById("btnRevert").disabled = false;
      document.getElementById("addArea").classList.remove("d-none");
      setStatus("Loaded: " + path);
      refresh();
    })
    .catch(e => setStatus("Error: " + e, true));
}

// ── Render ────────────────────────────────────────────────────────────────

function renderTable(toc) {
  const tbody = document.getElementById("tocBody");
  tbody.innerHTML = "";
  toc.forEach((entry, i) => tbody.appendChild(makeRow(entry, i)));
  if (sortable) sortable.destroy();
  sortable = new Sortable(tbody, {
    handle: ".drag-handle",
    animation: 150,
    ghostClass: "sortable-ghost",
    onEnd: refresh,
  });
}

function makeRow(entry, i) {
  const ds = dataSections[i] || null;
  const tr = document.createElement("tr");
  // Store full original entry so extra fields (ordinal, etc.) are preserved on save
  tr.dataset.entry = JSON.stringify(entry);

  const nameMatch = ds && entry.name === ds.name;
  const isSection = ds ? ds.is_section : true;
  tr.className = rowCls(ds, nameMatch, isSection);

  const hdrText = (entry.headers || []).join(", ");
  const dsName  = ds ? esc(ds.name) : "<em class='text-muted'>—</em>";
  const snippet = ds && ds.snippet
    ? `<div class="snippet" title="${esc(ds.snippet)}">${esc(ds.snippet)}</div>` : "";
  const typeBadge = ds
    ? `<span class="badge ${isSection ? "bg-success" : "bg-danger"}">${esc(ds.type)}</span>` : "";
  const matchIcon = !ds ? "" : (nameMatch
    ? `<span class="match-ok">✓</span>`
    : `<span class="match-fail">✗</span>`);

  const chkCell   = i === 0
    ? `<td class="col-chk"></td>`
    : `<td class="col-chk"><input type="checkbox" class="row-chk"></td>`;
  const demoteBtn = i === 0
    ? `<td class="col-demote"></td>`
    : `<td class="col-demote">
         <button class="btn btn-sm btn-link text-secondary p-0 btn-demote"
                 title="Nest inside section above">↓</button>
       </td>`;

  tr.innerHTML = `
    ${chkCell}
    <td class="col-idx row-idx">${i}</td>
    <td class="col-drag drag-handle">≡</td>
    <td>
      <input type="text" class="form-control form-control-sm toc-name" value="${esc(entry.name)}">
      <input type="text" class="hdr-input mt-1 px-1" placeholder="headers (comma-separated)"
             value="${esc(hdrText)}" title="Sub-headers shown in sidebar">
    </td>
    <td class="col-match match-icon">${matchIcon}</td>
    <td>
      <div class="data-name">${dsName}</div>
      ${snippet}
    </td>
    <td class="col-type">${typeBadge}</td>
    ${demoteBtn}
    <td class="col-del">
      <button class="btn btn-sm btn-link text-danger p-0 btn-del" title="Remove row">×</button>
    </td>`;

  tr.querySelector(".btn-del").onclick = () => { tr.remove(); refresh(); };
  tr.querySelector(".toc-name").oninput = refresh;
  if (i > 0) {
    tr.querySelector(".btn-demote").onclick = () => demoteRows([tr]);
    tr.querySelector(".row-chk").onchange   = updateSelCount;
  }
  return tr;
}

function rowCls(ds, nameMatch, isSection) {
  if (!ds) return "";
  if (!isSection) return "orphan";
  if (!nameMatch) return "mismatch";
  return "";
}

// ── Refresh stats + row colouring ─────────────────────────────────────────

function refresh() {
  const rows = [...document.querySelectorAll("#tocBody tr")];
  let mismatches = 0, orphans = 0;

  rows.forEach((tr, i) => {
    const ds        = dataSections[i] || null;
    const nameVal   = tr.querySelector(".toc-name").value;
    const nameMatch = ds && nameVal === ds.name;
    const isSection = ds ? ds.is_section : true;

    tr.querySelector(".row-idx").textContent = i;
    tr.querySelector(".match-icon").innerHTML = !ds ? ""
      : nameMatch ? `<span class="match-ok">✓</span>`
                  : `<span class="match-fail">✗</span>`;
    tr.className = rowCls(ds, nameMatch, isSection);

    if (ds && !nameMatch) mismatches++;
    if (ds && !isSection) orphans++;
  });

  document.getElementById("sToc").textContent      = rows.length;
  document.getElementById("sData").textContent     = dataSections.length;
  document.getElementById("sMismatch").textContent = mismatches;
  document.getElementById("sMismatch").className   =
    mismatches ? "text-danger fw-bold" : "text-success fw-bold";
  document.getElementById("sOrphan").textContent   = orphans;
  document.getElementById("summaryBar").classList.remove("d-none");
  updateSelCount();
}

// ── Add row ───────────────────────────────────────────────────────────────

document.getElementById("btnAdd").onclick = () => {
  const tbody = document.getElementById("tocBody");
  const i = tbody.children.length;
  tbody.appendChild(makeRow({ name: "New Section", headers: [] }, i));
  refresh();
};

// ── Save ──────────────────────────────────────────────────────────────────

document.getElementById("btnSave").onclick = () => {
  if (!currentFile) return;
  const rows = [...document.querySelectorAll("#tocBody tr")];
  const toc = rows.map(tr => {
    // Preserve any extra fields (ordinal, etc.) from the original entry
    const base    = JSON.parse(tr.dataset.entry || "{}");
    const name    = tr.querySelector(".toc-name").value.trim();
    const hdrRaw  = tr.querySelector(".hdr-input").value.trim();
    const headers = hdrRaw
      ? hdrRaw.split(",").map(h => h.trim()).filter(Boolean) : [];
    return { ...base, name, headers };
  });

  setStatus("Saving…");
  fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: currentFile, toc }),
  })
  .then(r => r.json())
  .then(d => {
    if (d.error) { setStatus("Save error: " + d.error, true); return; }
    // Update stored entries so row colours reflect the saved state
    document.querySelectorAll("#tocBody tr").forEach((tr, i) => {
      tr.dataset.entry = JSON.stringify(toc[i]);
    });
    originalToc = JSON.parse(JSON.stringify(toc));
    setStatus("Saved ✓  Training pair appended to toc_corrections.jsonl");
  })
  .catch(e => setStatus("Save error: " + e, true));
};

// ── Revert ────────────────────────────────────────────────────────────────

document.getElementById("btnRevert").onclick = () => {
  if (!originalToc) return;
  renderTable(originalToc);
  refresh();
  setStatus("Reverted to last loaded state.");
};

// ── Selection ─────────────────────────────────────────────────────────────

document.getElementById("chkAll").onchange = function () {
  document.querySelectorAll(".row-chk").forEach(c => { c.checked = this.checked; });
  updateSelCount();
};

function updateSelCount() {
  const n = document.querySelectorAll(".row-chk:checked").length;
  document.getElementById("selCount").textContent = n;
  document.getElementById("btnDemoteSelect").disabled = n === 0 || !currentFile;
}

document.getElementById("btnDemoteSelect").onclick = () => {
  const checked = [...document.querySelectorAll(".row-chk:checked")]
    .map(c => c.closest("tr"));
  if (checked.length) demoteRows(checked);
};

// ── Demote ────────────────────────────────────────────────────────────────

function demoteRows(trs) {
  const items = trs.map(tr => ({
    idx:  parseInt(tr.querySelector(".row-idx").textContent, 10),
    name: tr.querySelector(".toc-name").value.trim() || "?",
  }));
  const names = items.map(it => `  • [${it.idx}] ${it.name}`).join("\n");

  if (!confirm(`Demote ${items.length} section(s) — each will be nested inside the section above it:\n\n${names}\n\nA .bak backup will be written first.`)) return;

  setStatus("Demoting…");
  fetch("/api/demote", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: currentFile, indices: items.map(it => it.idx) }),
  })
  .then(r => r.json())
  .then(d => {
    if (d.error) { setStatus("Demote error: " + d.error, true); return; }
    setStatus(`Demoted ${items.length} section(s). Reloading…`);
    loadFile(currentFile);
  })
  .catch(e => setStatus("Demote error: " + e, true));
}

// ── Helpers ───────────────────────────────────────────────────────────────

function setStatus(msg, isErr) {
  const el = document.getElementById("statusMsg");
  el.textContent = msg;
  el.className = "ms-2 small " + (isErr ? "text-danger" : "text-muted");
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
</script>
</body>
</html>
"""


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="TOC editor for 5etools adventure JSON")
    parser.add_argument("file", nargs="?", default="", help="JSON file to pre-load")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5101)))
    args = parser.parse_args()

    _preload_file = args.file
    print(f"TOC Editor running at http://localhost:{args.port}")
    app.run(port=args.port, debug=False)
