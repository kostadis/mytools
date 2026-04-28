#!/usr/bin/env python3
"""
toc_editor.py — Interactive TOC editor for 5etools adventure/book JSON files.

Displays the contents[] (sidebar TOC) alongside the corresponding data[] section
at each array index so mismatches are immediately visible.  Supports inline
rename, ↑↓ reorder (sections and headers), add/delete rows.  Every save appends a
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

    # Annotate each toc entry with its original data[] index so save can
    # reorder data[] when the user reorders sections.
    annotated_toc = []
    for i, entry in enumerate(toc):
        e = dict(entry)
        e["_dataIdx"] = i
        annotated_toc.append(e)

    return {"toc": annotated_toc, "data_sections": data_sections}


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
    body    = request.json or {}
    path    = Path(body.get("path", ""))
    new_toc = body.get("toc", [])

    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    index_key = "adventure" if "adventure" in raw else "book"
    data_key  = "adventureData" if "adventure" in raw else "bookData"
    old_toc   = raw[index_key][0].get("contents", [])
    data      = raw[data_key][0].get("data", [])

    # Reorder data[] to match the new section order, using the _dataIdx
    # field that was injected by load_adventure().
    orig_indices = [e.get("_dataIdx") for e in new_toc if isinstance(e, dict)]
    if (orig_indices
            and all(isinstance(i, int) for i in orig_indices)
            and len(orig_indices) == len(data)):
        valid = [i for i in orig_indices if 0 <= i < len(data)]
        if len(valid) == len(data):
            raw[data_key][0]["data"] = [data[i] for i in valid]

    # Strip _dataIdx before persisting (it's a UI-only field)
    clean_toc = [
        {k: v for k, v in e.items() if k != "_dataIdx"}
        for e in new_toc
    ]
    raw[index_key][0]["contents"] = clean_toc

    bak = path.with_suffix(".bak")
    bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent="\t", ensure_ascii=False)

    pair = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_file": str(path),
        "toc_before": old_toc,
        "toc_after": clean_toc,
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
  tr.mismatch td { background: #fff3cd; }
  tr.orphan td   { background: #f8d7da; }
  tr.hdr-row td  { background: #f8f9fa; }
  .data-name { color: #444; }
  .snippet   { color: #888; font-size: 0.78em; white-space: nowrap;
               overflow: hidden; text-overflow: ellipsis; max-width: 340px; }
  #tocTable td, #tocTable th { vertical-align: middle; }
  .col-chk  { width: 2em;   text-align: center; }
  .col-move { width: 3.2em; white-space: nowrap; text-align: center; }
  .col-idx  { width: 2.5em; text-align: center; color: #999; font-size: 0.8em; }
  .col-match{ width: 1.8em; text-align: center; }
  .col-type { width: 5.5em; text-align: center; }
  .col-del  { width: 2em;   text-align: center; }
  .match-ok   { color: #198754; }
  .match-fail { color: #dc3545; font-weight: bold; }
  .btn-mv {
    background: none; border: 1px solid #dee2e6; border-radius: 3px;
    padding: 0 3px; font-size: 0.75em; cursor: pointer; color: #666;
    line-height: 1.4;
  }
  .btn-mv:hover { background: #e9ecef; color: #000; }
  .btn-mv:disabled { opacity: 0.25; cursor: default; }
  .hdr-indent    { padding-left: 2.5em !important; color: #555; font-style: italic; }
  .subhdr-indent { padding-left: 5em  !important; color: #777; font-style: italic; font-size:0.82em; }
  tr.subhdr-row td { background: #f0f0f0; }
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
    <button id="btnLoad"   class="btn btn-sm btn-primary">Load</button>
    <button id="btnSave"   class="btn btn-sm btn-success"          disabled>Save</button>
    <button id="btnRevert" class="btn btn-sm btn-outline-secondary" disabled>Revert</button>
    <span class="ms-1 text-muted small">Add:</span>
    <button id="btnAddSection"    class="btn btn-sm btn-outline-primary"   disabled>+ Section</button>
    <button id="btnAddHeader"     class="btn btn-sm btn-outline-secondary" disabled>+ Header</button>
    <button id="btnAddSubheader"  class="btn btn-sm btn-outline-secondary" disabled>+ Sub-header</button>
    <button id="btnDemoteSelect"  class="btn btn-sm btn-outline-warning"   disabled>↳ Demote selected (<span id="selCount">0</span>)</button>
    <span id="statusMsg" class="ms-2 small text-muted"></span>
  </div>

  <!-- Summary bar -->
  <div id="summaryBar" class="d-none mb-2 small d-flex gap-3 align-items-center flex-wrap">
    <span>TOC sections: <strong id="sToc">0</strong></span>
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
            <th class="col-chk"><input type="checkbox" id="chkAll" title="Select all sections"></th>
            <th class="col-move">Move</th>
            <th class="col-idx">#</th>
            <th>TOC Entry / Header <span class="text-muted fw-normal">(editable)</span></th>
            <th class="col-match" title="Name matches data section at same index">≈</th>
            <th>Data section at this index <span class="text-muted fw-normal">(read-only)</span></th>
            <th class="col-type">Type</th>
            <th class="col-del"></th>
          </tr>
        </thead>
        <tbody id="tocBody"></tbody>
      </table>
    </div>
  </div>
</div>

<script>
const PRELOAD = "__PRELOAD__";

let currentFile  = null;
let originalToc  = null;
let dataSections = [];

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
      document.getElementById("btnSave").disabled      = false;
      document.getElementById("btnRevert").disabled    = false;
      document.getElementById("btnAddSection").disabled   = false;
      document.getElementById("btnAddHeader").disabled    = false;
      document.getElementById("btnAddSubheader").disabled = false;
      setStatus("Loaded: " + path);
      refresh();
    })
    .catch(e => setStatus("Error: " + e, true));
}

// ── Render ────────────────────────────────────────────────────────────────

function renderTable(toc) {
  const tbody = document.getElementById("tocBody");
  tbody.innerHTML = "";
  let si = 0;
  toc.forEach(entry => {
    tbody.appendChild(makeSectionRow(entry, si));
    (entry.headers || []).forEach(h => {
      if (h && typeof h === "object" && h.depth) {
        tbody.appendChild(makeSubheaderRow(h.header ?? ""));
      } else {
        tbody.appendChild(makeHeaderRow(typeof h === "string" ? h : (h.header ?? "")));
      }
    });
    si++;
  });
}

function makeSectionRow(entry, si) {
  const ds = dataSections[si] || null;
  const tr = document.createElement("tr");
  tr.dataset.kind    = "section";
  tr.dataset.dataIdx = entry._dataIdx ?? si;
  // Preserve extra fields (ordinal, etc.) not shown in the UI
  const extra = {};
  for (const [k, v] of Object.entries(entry)) {
    if (!["name", "headers", "_dataIdx"].includes(k)) extra[k] = v;
  }
  tr.dataset.extra = JSON.stringify(extra);

  const nameMatch = ds && entry.name === ds.name;
  const isSection = ds ? ds.is_section : true;
  tr.className = rowCls(ds, nameMatch, isSection);

  const dsName    = ds ? esc(ds.name) : "<em class='text-muted'>—</em>";
  const snippet   = ds && ds.snippet
    ? `<div class="snippet" title="${esc(ds.snippet)}">${esc(ds.snippet)}</div>` : "";
  const typeBadge = ds
    ? `<span class="badge ${isSection ? "bg-success" : "bg-danger"}">${esc(ds.type)}</span>` : "";
  const matchIcon = !ds ? "" : nameMatch
    ? `<span class="match-ok">✓</span>` : `<span class="match-fail">✗</span>`;

  const chkCell = si === 0
    ? `<td class="col-chk"></td>`
    : `<td class="col-chk"><input type="checkbox" class="row-chk"></td>`;

  tr.innerHTML = `
    ${chkCell}
    <td class="col-move">
      <button class="btn-mv btn-mv-up"  title="Move section up">↑</button>
      <button class="btn-mv btn-mv-dn"  title="Move section down">↓</button>
      <button class="btn-mv btn-mv-dem" title="Demote: nest inside section above" style="font-size:0.65em">↳</button>
    </td>
    <td class="col-idx row-idx">${si}</td>
    <td>
      <input type="text" class="form-control form-control-sm toc-name" value="${esc(entry.name)}">
    </td>
    <td class="col-match match-icon">${matchIcon}</td>
    <td>
      <div class="data-name">${dsName}</div>
      ${snippet}
    </td>
    <td class="col-type">${typeBadge}</td>
    <td class="col-del">
      <button class="btn btn-sm btn-link text-danger p-0 btn-del" title="Remove section and its headers">×</button>
    </td>`;

  tr.querySelector(".btn-mv-up").onclick  = () => { moveSectionUp(tr);   refresh(); };
  tr.querySelector(".btn-mv-dn").onclick  = () => { moveSectionDown(tr); refresh(); };
  tr.querySelector(".btn-mv-dem").onclick = () => demoteRows([tr]);
  tr.querySelector(".toc-name").oninput   = refresh;
  tr.querySelector(".btn-del").onclick    = () => { removeSectionBlock(tr); refresh(); };
  if (si > 0) tr.querySelector(".row-chk").onchange = updateSelCount;
  return tr;
}

function makeHeaderRow(name) {
  const tr = document.createElement("tr");
  tr.dataset.kind = "header";
  tr.className = "hdr-row";

  tr.innerHTML = `
    <td class="col-chk"></td>
    <td class="col-move">
      <button class="btn-mv btn-mv-up"  title="Move header block up within section">↑</button>
      <button class="btn-mv btn-mv-dn"  title="Move header block down within section">↓</button>
      <button class="btn-mv btn-mv-dem" title="Demote to sub-header under previous header" style="font-size:0.65em">↳</button>
    </td>
    <td class="col-idx" style="color:#bbb">·</td>
    <td class="hdr-indent" colspan="4">
      <input type="text" class="form-control form-control-sm toc-name"
             style="font-size:0.85em; font-style:italic" value="${esc(name)}">
    </td>
    <td class="col-del">
      <button class="btn btn-sm btn-link text-danger p-0 btn-del" title="Remove header and its sub-headers">×</button>
    </td>`;

  tr.querySelector(".btn-mv-up").onclick  = () => { moveHeaderUp(tr);   };
  tr.querySelector(".btn-mv-dn").onclick  = () => { moveHeaderDown(tr); };
  tr.querySelector(".btn-mv-dem").onclick = () => demoteHeader(tr);
  tr.querySelector(".btn-del").onclick    = () => { getHeaderBlock(tr).forEach(r => r.remove()); };
  return tr;
}

function makeSubheaderRow(name) {
  const tr = document.createElement("tr");
  tr.dataset.kind = "subheader";
  tr.className = "subhdr-row";

  tr.innerHTML = `
    <td class="col-chk"></td>
    <td class="col-move">
      <button class="btn-mv btn-mv-up" title="Move sub-header up within header">↑</button>
      <button class="btn-mv btn-mv-dn" title="Move sub-header down within header">↓</button>
    </td>
    <td class="col-idx" style="color:#ccc">·</td>
    <td class="subhdr-indent" colspan="4">
      <input type="text" class="form-control form-control-sm toc-name" value="${esc(name)}">
    </td>
    <td class="col-del">
      <button class="btn btn-sm btn-link text-danger p-0 btn-del" title="Remove sub-header">×</button>
    </td>`;

  tr.querySelector(".btn-mv-up").onclick = () => moveSubheaderUp(tr);
  tr.querySelector(".btn-mv-dn").onclick = () => moveSubheaderDown(tr);
  tr.querySelector(".btn-del").onclick   = () => tr.remove();
  return tr;
}

// ── Block helpers ──────────────────────────────────────────────────────────

/** Collect section row + all following header/subheader rows until next section. */
function getSectionBlock(sectionTr) {
  const rows = [sectionTr];
  let next = sectionTr.nextElementSibling;
  while (next && next.dataset.kind !== "section") {
    rows.push(next);
    next = next.nextElementSibling;
  }
  return rows;
}

/** Collect header row + all immediately-following subheader rows. */
function getHeaderBlock(headerTr) {
  const rows = [headerTr];
  let next = headerTr.nextElementSibling;
  while (next && next.dataset.kind === "subheader") {
    rows.push(next);
    next = next.nextElementSibling;
  }
  return rows;
}

function prevSectionRow(tr) {
  let el = tr.previousElementSibling;
  while (el) {
    if (el.dataset.kind === "section") return el;
    el = el.previousElementSibling;
  }
  return null;
}

/** Find the previous header row (not subheader) before tr, stopping at section boundary. */
function prevHeaderRow(tr) {
  let el = tr.previousElementSibling;
  while (el && el.dataset.kind !== "section") {
    if (el.dataset.kind === "header") return el;
    el = el.previousElementSibling;
  }
  return null;
}

/** Find the next header row (not subheader) after a block, stopping at section boundary. */
function nextHeaderRowAfterBlock(block) {
  let el = block[block.length - 1].nextElementSibling;
  while (el && el.dataset.kind !== "section") {
    if (el.dataset.kind === "header") return el;
    el = el.nextElementSibling;
  }
  return null;
}

function nextSectionRowAfterBlock(block) {
  let el = block[block.length - 1].nextElementSibling;
  while (el) {
    if (el.dataset.kind === "section") return el;
    el = el.nextElementSibling;
  }
  return null;
}

// ── Move operations ────────────────────────────────────────────────────────

function moveSectionUp(tr) {
  const block = getSectionBlock(tr);
  const prevSec = prevSectionRow(tr);
  if (!prevSec) return;
  const prevBlock = getSectionBlock(prevSec);
  const tbody = tr.parentElement;
  block.forEach(row => tbody.insertBefore(row, prevBlock[0]));
}

function moveSectionDown(tr) {
  const block = getSectionBlock(tr);
  const nextSec = nextSectionRowAfterBlock(block);
  if (!nextSec) return;
  const nextBlock = getSectionBlock(nextSec);
  const tbody = tr.parentElement;
  nextBlock.forEach(row => tbody.insertBefore(row, block[0]));
}

/** Move header block (header + its subheaders) up past the previous header block. */
function moveHeaderUp(tr) {
  const block = getHeaderBlock(tr);
  const prev = prevHeaderRow(tr);
  if (!prev) return;
  const prevBlock = getHeaderBlock(prev);
  const tbody = tr.parentElement;
  block.forEach(row => tbody.insertBefore(row, prevBlock[0]));
}

/** Move header block down past the next header block. */
function moveHeaderDown(tr) {
  const block = getHeaderBlock(tr);
  const next = nextHeaderRowAfterBlock(block);
  if (!next) return;
  const nextBlock = getHeaderBlock(next);
  const tbody = tr.parentElement;
  nextBlock.forEach(row => tbody.insertBefore(row, block[0]));
}

function moveSubheaderUp(tr) {
  const prev = tr.previousElementSibling;
  if (!prev || prev.dataset.kind !== "subheader") return;
  tr.parentElement.insertBefore(tr, prev);
}

function moveSubheaderDown(tr) {
  const next = tr.nextElementSibling;
  if (!next || next.dataset.kind !== "subheader") return;
  tr.parentElement.insertBefore(next, tr);
}

/** Demote a header row to a sub-header under the previous header's block. */
function demoteHeader(tr) {
  const prev = prevHeaderRow(tr);
  if (!prev) { setStatus("No header above to demote into.", true); return; }
  const block = getHeaderBlock(tr);
  const prevBlock = getHeaderBlock(prev);
  const anchor = prevBlock[prevBlock.length - 1].nextElementSibling;
  const tbody = tr.parentElement;
  // Convert each row in block to subheader rows
  block.forEach(row => {
    const name = row.querySelector(".toc-name").value.trim();
    const subRow = makeSubheaderRow(name);
    tbody.insertBefore(subRow, anchor);
    row.remove();
  });
}

function removeSectionBlock(sectionTr) {
  getSectionBlock(sectionTr).forEach(row => row.remove());
}

// ── Refresh stats + row colouring ─────────────────────────────────────────

function rowCls(ds, nameMatch, isSection) {
  if (!ds) return "";
  if (!isSection) return "orphan";
  if (!nameMatch) return "mismatch";
  return "";
}

function refresh() {
  const rows = [...document.querySelectorAll("#tocBody tr")];
  let si = 0, mismatches = 0, orphans = 0;

  rows.forEach(tr => {
    if (tr.dataset.kind !== "section") return;

    const ds        = dataSections[si] || null;
    const nameVal   = tr.querySelector(".toc-name").value;
    const nameMatch = ds && nameVal === ds.name;
    const isSection = ds ? ds.is_section : true;

    tr.querySelector(".row-idx").textContent    = si;
    tr.querySelector(".match-icon").innerHTML   = !ds ? ""
      : nameMatch ? `<span class="match-ok">✓</span>`
                  : `<span class="match-fail">✗</span>`;
    tr.className = rowCls(ds, nameMatch, isSection);

    if (ds && !nameMatch) mismatches++;
    if (ds && !isSection) orphans++;
    si++;
  });

  document.getElementById("sToc").textContent      = si;
  document.getElementById("sData").textContent     = dataSections.length;
  document.getElementById("sMismatch").textContent = mismatches;
  document.getElementById("sMismatch").className   =
    mismatches ? "text-danger fw-bold" : "text-success fw-bold";
  document.getElementById("sOrphan").textContent   = orphans;
  document.getElementById("summaryBar").classList.remove("d-none");
  document.getElementById("chkAll").checked = false;
  updateSelCount();
}

// ── Build TOC from DOM ─────────────────────────────────────────────────────

function buildToc() {
  const rows = [...document.querySelectorAll("#tocBody tr")];
  const toc  = [];
  let current = null;

  rows.forEach(tr => {
    if (tr.dataset.kind === "section") {
      if (current) toc.push(current);
      const extra = JSON.parse(tr.dataset.extra || "{}");
      current = {
        ...extra,
        name: tr.querySelector(".toc-name").value.trim(),
        headers: [],
        _dataIdx: parseInt(tr.dataset.dataIdx, 10),
      };
    } else if (tr.dataset.kind === "header" && current) {
      const name = tr.querySelector(".toc-name").value.trim();
      if (name) current.headers.push(name);
    } else if (tr.dataset.kind === "subheader" && current) {
      const name = tr.querySelector(".toc-name").value.trim();
      if (name) current.headers.push({ header: name, depth: 1 });
    }
  });
  if (current) toc.push(current);
  return toc;
}

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
  const trs = [...document.querySelectorAll(".row-chk:checked")].map(c => c.closest("tr"));
  if (trs.length) demoteRows(trs);
};

// ── Add rows ──────────────────────────────────────────────────────────────

document.getElementById("btnAddSection").onclick = () => {
  const tbody = document.getElementById("tocBody");
  const si    = [...tbody.querySelectorAll("tr[data-kind='section']")].length;
  tbody.appendChild(makeSectionRow({ name: "New Section", headers: [] }, si));
  refresh();
};

document.getElementById("btnAddHeader").onclick = () => {
  const tbody = document.getElementById("tocBody");
  if (!tbody.querySelector("tr[data-kind='section']")) {
    setStatus("Add a section first before adding a header.", true);
    return;
  }
  tbody.appendChild(makeHeaderRow("New Header"));
};

document.getElementById("btnAddSubheader").onclick = () => {
  const tbody = document.getElementById("tocBody");
  if (!tbody.querySelector("tr[data-kind='header']")) {
    setStatus("Add a header first before adding a sub-header.", true);
    return;
  }
  tbody.appendChild(makeSubheaderRow("New Sub-header"));
};

// ── Save ──────────────────────────────────────────────────────────────────

document.getElementById("btnSave").onclick = () => {
  if (!currentFile) return;
  const toc = buildToc();

  setStatus("Saving…");
  fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: currentFile, toc }),
  })
  .then(r => r.json())
  .then(d => {
    if (d.error) { setStatus("Save error: " + d.error, true); return; }
    setStatus("Saved ✓  Training pair appended to toc_corrections.jsonl — reloading…");
    // Reload so data[] order is reflected in the alignment columns
    loadFile(currentFile);
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

// ── Demote (server-side) ──────────────────────────────────────────────────

function demoteRows(trs) {
  // Collect current visual indices (section rows only)
  const sectionRows = [...document.querySelectorAll("#tocBody tr[data-kind='section']")];
  const items = trs.map(tr => {
    const idx  = sectionRows.indexOf(tr);
    const name = tr.querySelector(".toc-name").value.trim() || "?";
    return { idx, name };
  }).filter(it => it.idx >= 1);  // can't demote index 0

  if (!items.length) {
    setStatus("First section cannot be demoted.", true);
    return;
  }

  const names = items.map(it => `  • [${it.idx}] ${it.name}`).join("\n");
  if (!confirm(
    `Demote ${items.length} section(s) — each will be nested inside the section above it:\n\n${names}\n\nA .bak backup will be written first.`
  )) return;

  // Save first so indices in file match current visual order
  const toc = buildToc();
  fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: currentFile, toc }),
  })
  .then(r => r.json())
  .then(d => {
    if (d.error) { setStatus("Save error before demote: " + d.error, true); return; }
    setStatus("Demoting…");
    return fetch("/api/demote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: currentFile, indices: items.map(it => it.idx) }),
    });
  })
  .then(r => r && r.json())
  .then(d => {
    if (!d) return;
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
