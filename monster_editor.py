#!/usr/bin/env python3
"""
monster_editor.py — Interactive monster stat block discovery and extraction UI.

Scans a 5etools adventure JSON for embedded stat blocks, displays them in an
editable table with links back to the adventure viewer, and extracts selected
monsters into a 5etools bestiary JSON via the Claude API.

Usage:
    python3 monster_editor.py                          # http://localhost:5103
    python3 monster_editor.py adventure-toworlds.json  # pre-load a file
    python3 monster_editor.py --port 8080
"""

import json
import os
import re
import sys
import threading
import time
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file

# Sibling module imports
from extract_monsters import _has_ac_table, statblock_to_text, SYSTEM_PROMPT
from toc_editor import list_json_files
import claude_api as _api

app = Flask(__name__)

_preload_file: str = ""
_sessions: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------

def _make_slug(name: str) -> str:
    """Generate a 5etools-compatible URL slug from an entry name."""
    slug = re.sub(r"\s*\(\d+\)\s*$", "", name)  # strip count suffix like "(2)"
    slug = re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")
    return slug


def _parse_stat_summary(entry: dict) -> dict:
    """Extract AC, HP, and CR strings from a stat block entry's tables."""
    ac = hp = cr = ""
    for child in entry.get("entries", []):
        if not isinstance(child, dict) or child.get("type") != "table":
            continue
        # Format A: key-value rows [["Armor Class", "14"], ...]
        for row in child.get("rows", []):
            if not isinstance(row, list) or len(row) < 2:
                continue
            key = str(row[0]).strip()
            val = str(row[1]).strip()
            if key == "Armor Class":
                ac = val
            elif key == "Hit Points":
                hp = val
            elif key == "Challenge":
                cr = val.split("(")[0].strip()
        # Format B: colLabels ["Armor Class", "Hit Points", "Speed"]
        cols = child.get("colLabels", [])
        if "Armor Class" in cols and child.get("rows"):
            row = child["rows"][0]
            if isinstance(row, list):
                for i, label in enumerate(cols):
                    if i < len(row):
                        if label == "Armor Class":
                            ac = str(row[i]).strip()
                        elif label == "Hit Points":
                            hp = str(row[i]).strip()
        if "Challenge" in cols and child.get("rows"):
            row = child["rows"][0]
            if isinstance(row, list):
                for i, label in enumerate(cols):
                    if i < len(row) and label == "Challenge":
                        cr = str(row[i]).split("(")[0].strip()
    return {"ac": ac, "hp": hp, "cr": cr}


def discover_statblocks(data_array: list) -> list[dict]:
    """Walk the adventure data[] array, returning stat blocks with location metadata."""
    results: list[dict] = []

    def _walk(obj, data_index: int, parent_section: str, parent_name: str):
        if not isinstance(obj, dict):
            return
        cur_name = obj.get("name", "") or parent_name
        if obj.get("type") == "section" and obj.get("name"):
            parent_section = obj["name"]
        if obj.get("type") == "entries" and "entries" in obj:
            if _has_ac_table(obj):
                entry_name = obj.get("name", "") or parent_name
                results.append({
                    "index": len(results),
                    "data_index": data_index,
                    "name": entry_name,
                    "parent_section": parent_section,
                    "slug": _make_slug(entry_name),
                    "entry": obj,
                    **_parse_stat_summary(obj),
                })
                return
        for child in obj.get("entries", []):
            _walk(child, data_index, parent_section, cur_name)

    for i, section in enumerate(data_array):
        if not isinstance(section, dict):
            continue
        section_name = section.get("name", "")
        _walk(section, i, section_name, section_name)

    return results


# ---------------------------------------------------------------------------
# Extraction worker (runs in background thread)
# ---------------------------------------------------------------------------

def _extraction_worker(sess: dict, selected_indices: list[int],
                       name_overrides: dict, model: str,
                       output_filename: str, batch_size: int,
                       merge: bool = False):
    import anthropic

    progress = sess["extraction_progress"]
    try:
        statblocks = [sess["statblocks"][i] for i in selected_indices]

        # Apply name overrides from the UI
        for sb in statblocks:
            idx = sb["index"]
            if str(idx) in name_overrides:
                sb["entry"] = {**sb["entry"], "name": name_overrides[str(idx)]}

        texts = [statblock_to_text(sb["entry"]) for sb in statblocks]
        batches = [texts[i:i + batch_size]
                   for i in range(0, len(texts), batch_size)]

        progress["total"] = len(batches)
        client = anthropic.Anthropic()
        new_monsters: list = []

        for batch_idx, batch in enumerate(batches):
            combined = "\n\n---\n\n".join(batch)
            monsters = _api.call_claude(
                client, combined, model, SYSTEM_PROMPT,
                False, None, f"monsters-{batch_idx:04d}",
            )
            for m in monsters:
                if isinstance(m, dict):
                    m["source"] = sess["adventure_source_id"]
            new_monsters.extend(monsters)
            progress["current"] = batch_idx + 1
            progress["monster_count"] = len(new_monsters)

        # Merge into existing file or start fresh
        out_path = Path(output_filename)
        if merge and out_path.is_file():
            with open(out_path, encoding="utf-8") as f:
                existing = json.load(f)
            all_monsters = existing.get("monster", [])
        else:
            all_monsters = []

        all_monsters.extend(new_monsters)

        # Deduplicate by name (keep last — new overwrites old)
        seen: dict = {}
        for m in all_monsters:
            if isinstance(m, dict):
                seen[m.get("name", "")] = m
        all_monsters = list(seen.values())

        # Write output
        if merge and out_path.is_file():
            with open(out_path, encoding="utf-8") as f:
                homebrew_obj = json.load(f)
            homebrew_obj["monster"] = all_monsters
            homebrew_obj["_meta"]["dateLastModified"] = int(time.time())
        else:
            homebrew_obj = {
                "_meta": {
                    "sources": [sess["source_meta"]],
                    "dateAdded": int(time.time()),
                    "dateLastModified": int(time.time()),
                },
                "monster": all_monsters,
            }

        out_path.write_text(
            json.dumps(homebrew_obj, indent="\t", ensure_ascii=False),
            encoding="utf-8",
        )
        progress["status"] = "done"
        progress["output_file"] = output_filename
        progress["monster_count"] = len(all_monsters)

    except Exception as exc:
        progress["status"] = "error"
        progress["error"] = str(exc)


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return HTML.replace("__PRELOAD__", json.dumps(_preload_file))


@app.route("/api/files")
def api_files():
    return jsonify(list_json_files())


@app.route("/api/load", methods=["POST"])
def api_load():
    path = request.json.get("path", "")
    if not path or not Path(path).is_file():
        return jsonify({"error": f"File not found: {path}"}), 400

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    # Determine source info — bestiary gets its own source ID so it doesn't
    # conflict with the adventure file when both are loaded in 5etools.
    sources = data.get("_meta", {}).get("sources", [])
    adventure_source_id = sources[0]["json"] if sources else "HOMEBREW"
    source_id = adventure_source_id + "b"
    base = sources[0] if sources else {
        "json": adventure_source_id, "abbreviation": adventure_source_id[:8],
        "full": Path(path).stem, "version": "1.0.0",
        "authors": ["Unknown"], "convertedBy": ["monster_editor"],
    }
    source_meta = {
        **base,
        "json": source_id,
        "abbreviation": source_id[:8],
        "full": base.get("full", "") + " — Bestiary",
    }

    # Find the data array
    data_array = None
    for key in ("adventureData", "bookData"):
        if key in data and data[key]:
            data_array = data[key][0].get("data", [])
            break
    if data_array is None:
        return jsonify({"error": "No adventureData or bookData found"}), 400

    statblocks = discover_statblocks(data_array)

    sess = {
        "raw": data,
        "source_id": source_id,
        "adventure_source_id": adventure_source_id,
        "source_meta": source_meta,
        "statblocks": statblocks,
        "extraction_progress": {"status": "idle"},
    }
    _sessions[path] = sess

    # Return lightweight metadata (no raw entries)
    monsters = []
    for sb in statblocks:
        monsters.append({
            "index": sb["index"],
            "data_index": sb["data_index"],
            "name": sb["name"],
            "parent_section": sb["parent_section"],
            "slug": sb["slug"],
            "ac": sb["ac"],
            "hp": sb["hp"],
            "cr": sb["cr"],
        })

    return jsonify({
        "source_id": source_id,
        "monsters": monsters,
        "total": len(monsters),
    })


@app.route("/api/raw/<int:idx>")
def api_raw(idx: int):
    path = request.args.get("path", "")
    sess = _sessions.get(path)
    if not sess:
        return jsonify({"error": "Session not found — load file first"}), 400
    if idx < 0 or idx >= len(sess["statblocks"]):
        return jsonify({"error": f"Index {idx} out of range"}), 400
    entry = sess["statblocks"][idx]["entry"]
    return jsonify({"raw_json": json.dumps(entry, indent=2, ensure_ascii=False)})


@app.route("/api/extract", methods=["POST"])
def api_extract():
    body = request.json
    path = body.get("path", "")
    sess = _sessions.get(path)
    if not sess:
        return jsonify({"error": "Session not found — load file first"}), 400

    selected = body.get("selected", [])
    if not selected:
        return jsonify({"error": "No monsters selected"}), 400

    model = body.get("model", "claude-sonnet-4-6")
    output_filename = body.get("output_filename", "bestiary-output.json")
    batch_size = body.get("batch_size", 5)
    name_overrides = body.get("name_overrides", {})
    merge = body.get("merge", False)

    sess["extraction_progress"] = {
        "status": "running",
        "current": 0,
        "total": 0,
        "monster_count": 0,
        "error": None,
        "output_file": None,
    }

    t = threading.Thread(
        target=_extraction_worker,
        args=(sess, selected, name_overrides, model, output_filename, batch_size,
              merge),
        daemon=True,
    )
    t.start()
    return jsonify({"ok": True})


@app.route("/api/progress")
def api_progress():
    path = request.args.get("path", "")
    sess = _sessions.get(path)
    if not sess:
        return jsonify({"error": "Session not found"}), 400
    return jsonify(sess.get("extraction_progress", {"status": "idle"}))


@app.route("/api/download/<path:filename>")
def api_download(filename: str):
    p = Path(filename)
    if not p.is_file():
        return jsonify({"error": "File not found"}), 404
    return send_file(p, as_attachment=True, download_name=p.name)


# ---------------------------------------------------------------------------
# Embedded HTML / CSS / JS
# ---------------------------------------------------------------------------

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Monster Extractor</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
      rel="stylesheet">
<style>
  body { font-size: .875rem; }
  .table td, .table th { vertical-align: middle; white-space: nowrap; }
  .table td.wrap { white-space: normal; max-width: 260px; }
  .mon-name { min-width: 200px; }
  .detail-row td { white-space: pre-wrap; font-family: monospace; font-size: .75rem;
                   background: #f8f9fa; max-height: 400px; overflow-y: auto; }
  .detail-row pre { margin: 0; max-height: 400px; overflow-y: auto; }
  .badge-cr { min-width: 40px; }
  #progressArea { display: none; }
  #downloadArea { display: none; }
</style>
</head>
<body class="bg-light">
<div class="container-fluid py-3" style="max-width:1400px">

  <h5 class="mb-3">Monster Extractor</h5>

  <!-- Toolbar -->
  <div class="row g-2 mb-2 align-items-end">
    <div class="col-md-4">
      <label class="form-label mb-0 small">Adventure JSON</label>
      <select id="fileSel" class="form-select form-select-sm"></select>
    </div>
    <div class="col-auto">
      <button class="btn btn-sm btn-primary" onclick="doLoad()">Load</button>
    </div>
    <div class="col-md-2">
      <label class="form-label mb-0 small">Model</label>
      <select id="modelSel" class="form-select form-select-sm">
        <option value="claude-sonnet-4-6" selected>claude-sonnet-4-6</option>
        <option value="claude-haiku-4-5-20251001">claude-haiku-4-5</option>
        <option value="claude-opus-4-6">claude-opus-4-6</option>
      </select>
    </div>
    <div class="col-md-2">
      <label class="form-label mb-0 small">Output file</label>
      <input id="outFile" class="form-control form-control-sm" value="bestiary-output.json">
    </div>
    <div class="col-auto">
      <span id="status" class="text-muted small"></span>
    </div>
  </div>

  <!-- Summary bar -->
  <div class="d-flex align-items-center gap-2 mb-2">
    <span id="summary" class="small text-muted">No file loaded</span>
    <button class="btn btn-sm btn-outline-secondary" onclick="selectAll(true)" disabled id="btnSelAll">Select All</button>
    <button class="btn btn-sm btn-outline-secondary" onclick="selectAll(false)" disabled id="btnDesel">Deselect All</button>
    <div class="form-check form-check-inline ms-auto">
      <input class="form-check-input" type="checkbox" id="chkMerge">
      <label class="form-check-label small" for="chkMerge">Merge into existing file</label>
    </div>
    <button class="btn btn-sm btn-success" onclick="doExtract()" disabled id="btnExtract">Extract Selected</button>
  </div>

  <!-- Progress -->
  <div id="progressArea" class="mb-3">
    <div class="d-flex align-items-center gap-2 mb-1">
      <span id="progressText" class="small">Extracting...</span>
    </div>
    <div class="progress" style="height:20px">
      <div id="progressBar" class="progress-bar progress-bar-striped progress-bar-animated"
           role="progressbar" style="width:0%">0%</div>
    </div>
  </div>

  <!-- Download -->
  <div id="downloadArea" class="alert alert-success d-flex align-items-center gap-2 mb-3">
    <span id="downloadText"></span>
    <a id="downloadLink" class="btn btn-sm btn-primary" href="#" download>Download</a>
  </div>

  <!-- Monster table -->
  <div class="table-responsive">
    <table class="table table-sm table-bordered table-hover mb-0">
      <thead class="table-light">
        <tr>
          <th style="width:30px"><input type="checkbox" id="chkAll" checked onchange="selectAll(this.checked)"></th>
          <th>Name</th>
          <th>Section</th>
          <th style="width:50px">Idx</th>
          <th style="width:80px">AC</th>
          <th style="width:100px">HP</th>
          <th style="width:50px">CR</th>
          <th style="width:60px">View</th>
          <th style="width:30px"></th>
        </tr>
      </thead>
      <tbody id="monsterBody"></tbody>
    </table>
  </div>
</div>

<script>
const PRELOAD = __PRELOAD__;
let state = { path: "", sourceId: "", monsters: [] };
let pollTimer = null;

// ── Init ──────────────────────────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", async () => {
  const resp = await fetch("/api/files");
  const files = await resp.json();
  const sel = document.getElementById("fileSel");
  files.forEach(f => {
    const o = document.createElement("option");
    o.value = f; o.textContent = f;
    sel.appendChild(o);
  });
  if (PRELOAD) {
    sel.value = PRELOAD;
    doLoad();
  }
});

// ── Load ──────────────────────────────────────────────────────────────────
async function doLoad() {
  const path = document.getElementById("fileSel").value;
  if (!path) return;
  setStatus("Loading...", "text-muted");
  try {
    const resp = await fetch("/api/load", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({path}),
    });
    const data = await resp.json();
    if (data.error) { setStatus(data.error, "text-danger"); return; }
    state.path = path;
    state.sourceId = data.source_id;
    state.monsters = data.monsters;
    // Auto-set output filename
    const stem = path.replace(/\.json$/, "").replace(/^.*\//, "");
    document.getElementById("outFile").value = `bestiary-${stem}.json`;
    renderMonsters();
    setStatus(`Loaded ${data.total} stat blocks`, "text-success");
  } catch (e) {
    setStatus("Load error: " + e, "text-danger");
  }
}

// ── Render ────────────────────────────────────────────────────────────────
function renderMonsters() {
  const tbody = document.getElementById("monsterBody");
  tbody.innerHTML = "";
  state.monsters.forEach(m => {
    // Data row
    const tr = document.createElement("tr");
    tr.dataset.idx = m.index;
    const viewUrl = `http://localhost:5051/adventure.html#${state.sourceId},${m.data_index},${m.slug}`;
    tr.innerHTML = `
      <td><input type="checkbox" class="mon-chk" data-idx="${m.index}" checked onchange="updateSummary()"></td>
      <td><input type="text" class="form-control form-control-sm mon-name" value="${escHtml(m.name)}" data-idx="${m.index}"></td>
      <td class="wrap small text-muted">${escHtml(m.parent_section)}</td>
      <td class="text-center small">${m.data_index}</td>
      <td class="small">${escHtml(m.ac)}</td>
      <td class="small">${escHtml(m.hp)}</td>
      <td class="text-center"><span class="badge bg-secondary badge-cr">${escHtml(m.cr)}</span></td>
      <td><a href="${viewUrl}" target="_blank" class="btn btn-sm btn-outline-primary py-0 px-1">View</a></td>
      <td><button class="btn btn-sm btn-outline-secondary py-0 px-1" onclick="toggleDetail(${m.index})">+</button></td>
    `;
    tbody.appendChild(tr);

    // Detail row (hidden)
    const dr = document.createElement("tr");
    dr.id = `detail-${m.index}`;
    dr.className = "detail-row";
    dr.style.display = "none";
    dr.innerHTML = `<td colspan="9"><pre id="raw-${m.index}">Loading...</pre></td>`;
    tbody.appendChild(dr);
  });
  updateSummary();
  document.getElementById("btnSelAll").disabled = false;
  document.getElementById("btnDesel").disabled = false;
  document.getElementById("btnExtract").disabled = false;
}

// ── Detail expand/collapse ────────────────────────────────────────────────
async function toggleDetail(idx) {
  const dr = document.getElementById(`detail-${idx}`);
  if (dr.style.display === "none") {
    dr.style.display = "";
    const pre = document.getElementById(`raw-${idx}`);
    if (pre.textContent === "Loading...") {
      try {
        const resp = await fetch(`/api/raw/${idx}?path=${encodeURIComponent(state.path)}`);
        const data = await resp.json();
        pre.textContent = data.raw_json || "No data";
      } catch (e) {
        pre.textContent = "Error: " + e;
      }
    }
  } else {
    dr.style.display = "none";
  }
}

// ── Selection ─────────────────────────────────────────────────────────────
function selectAll(checked) {
  document.querySelectorAll(".mon-chk").forEach(c => c.checked = checked);
  document.getElementById("chkAll").checked = checked;
  updateSummary();
}

function updateSummary() {
  const total = state.monsters.length;
  const selected = document.querySelectorAll(".mon-chk:checked").length;
  document.getElementById("summary").textContent =
    `Found: ${total} | Selected: ${selected}`;
  document.getElementById("btnExtract").disabled = selected === 0;
}

// ── Extract ───────────────────────────────────────────────────────────────
async function doExtract() {
  const selected = [];
  const nameOverrides = {};
  document.querySelectorAll(".mon-chk:checked").forEach(c => {
    const idx = parseInt(c.dataset.idx);
    selected.push(idx);
  });
  // Collect name overrides
  document.querySelectorAll(".mon-name").forEach(input => {
    const idx = input.dataset.idx;
    const orig = state.monsters.find(m => m.index === parseInt(idx));
    if (orig && input.value !== orig.name) {
      nameOverrides[idx] = input.value;
    }
  });

  const model = document.getElementById("modelSel").value;
  const outputFilename = document.getElementById("outFile").value;
  const merge = document.getElementById("chkMerge").checked;

  document.getElementById("btnExtract").disabled = true;
  document.getElementById("progressArea").style.display = "";
  document.getElementById("downloadArea").style.display = "none";
  setStatus(merge ? "Extracting (merge)..." : "Extracting...", "text-muted");

  try {
    const resp = await fetch("/api/extract", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        path: state.path, selected, name_overrides: nameOverrides,
        model, output_filename: outputFilename, batch_size: 5, merge,
      }),
    });
    const data = await resp.json();
    if (data.error) {
      setStatus(data.error, "text-danger");
      document.getElementById("btnExtract").disabled = false;
      return;
    }
    startPolling();
  } catch (e) {
    setStatus("Extract error: " + e, "text-danger");
    document.getElementById("btnExtract").disabled = false;
  }
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(pollProgress, 2000);
}

async function pollProgress() {
  try {
    const resp = await fetch(`/api/progress?path=${encodeURIComponent(state.path)}`);
    const p = await resp.json();
    const bar = document.getElementById("progressBar");
    const text = document.getElementById("progressText");

    if (p.status === "running") {
      const pct = p.total > 0 ? Math.round((p.current / p.total) * 100) : 0;
      bar.style.width = pct + "%";
      bar.textContent = pct + "%";
      text.textContent = `Batch ${p.current}/${p.total} — ${p.monster_count} monsters so far`;
    } else if (p.status === "done") {
      clearInterval(pollTimer);
      bar.style.width = "100%";
      bar.textContent = "100%";
      bar.classList.remove("progress-bar-animated");
      bar.classList.add("bg-success");
      text.textContent = `Done! ${p.monster_count} monsters extracted.`;
      setStatus(`Extraction complete: ${p.monster_count} monsters`, "text-success");
      document.getElementById("downloadArea").style.display = "";
      document.getElementById("downloadText").textContent =
        `${p.output_file} (${p.monster_count} monsters)`;
      document.getElementById("downloadLink").href =
        `/api/download/${encodeURIComponent(p.output_file)}`;
      document.getElementById("btnExtract").disabled = false;
    } else if (p.status === "error") {
      clearInterval(pollTimer);
      bar.classList.add("bg-danger");
      bar.classList.remove("progress-bar-animated");
      text.textContent = "Error: " + (p.error || "unknown");
      setStatus("Extraction failed", "text-danger");
      document.getElementById("btnExtract").disabled = false;
    }
  } catch (e) {
    // Ignore transient fetch errors
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────
function setStatus(msg, cls) {
  const el = document.getElementById("status");
  el.textContent = msg;
  el.className = "small " + (cls || "text-muted");
}

function escHtml(s) {
  const d = document.createElement("div");
  d.textContent = s || "";
  return d.innerHTML;
}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Monster stat block extractor UI")
    parser.add_argument("file", nargs="?", default="", help="Pre-load this JSON file")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5103)))
    args = parser.parse_args()

    _preload_file = args.file
    print(f"Monster Editor: http://localhost:{args.port}")
    app.run(host="0.0.0.0", port=args.port, debug=True)
