#!/usr/bin/env python3
"""
app.py
======
Standalone web interface for pdf_to_5etools.py, pdf_to_5etools_ocr.py,
and pdf_to_5etools_1e.py.

Requirements:
    pip install flask

Usage:
    cd pdf-translators
    python3 app.py
    # Open http://localhost:5100
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

try:
    from flask import Flask, Response, jsonify, request, send_file
except ImportError:
    sys.exit("Flask is required:  pip install flask")

app = Flask(__name__)
SCRIPT_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# Job store
# ---------------------------------------------------------------------------

class Job:
    def __init__(self, job_id: str, output_path: Path):
        self.job_id      = job_id
        self.output_path = output_path
        self._log: list[str] = []
        self._status     = "running"   # running | done | error
        self._lock       = threading.Lock()

    def append(self, line: str) -> None:
        with self._lock:
            self._log.append(line)

    def finish(self, ok: bool) -> None:
        with self._lock:
            self._status = "done" if ok else "error"

    def snapshot(self, from_idx: int) -> tuple[list[str], str]:
        with self._lock:
            return self._log[from_idx:], self._status


_jobs: dict[str, Job] = {}


# ---------------------------------------------------------------------------
# HTML (single-file frontend, no external build step)
# ---------------------------------------------------------------------------

HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PDF → 5etools Converter</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background: #f4f6f9; }
    .card { border: 1px solid #e0e4ea; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
    .card-title { font-size: .9rem; }
    #log {
      background: #1a1b26; color: #c0caf5;
      font-family: 'Cascadia Code', 'Fira Mono', 'Consolas', monospace;
      font-size: .8rem; height: 360px; overflow-y: auto;
      padding: 1rem; border-radius: .4rem;
      white-space: pre-wrap; word-break: break-all;
      line-height: 1.55;
    }
    .log-warn { color: #e0af68; }
    .log-err  { color: #f7768e; }
    .log-ok   { color: #9ece6a; }
    .log-sep  { color: #565f89; }
    #dropzone {
      border: 2px dashed #ced4da; border-radius: .5rem;
      padding: 2rem 1rem; text-align: center; cursor: pointer;
      transition: border-color .2s, background .2s;
    }
    #dropzone.over     { border-color: #0d6efd; background: #eef3ff; }
    #dropzone.has-file { border-color: #198754; background: #ecf8f2; }
    .badge-ocr { background: #7c3aed; }
    .form-label { font-size: .82rem; font-weight: 500; color: #495057; }
  </style>
</head>
<body>
<div class="container py-4" style="max-width:800px">

  <div class="mb-4">
    <h4 class="fw-bold mb-0">PDF → 5etools Converter</h4>
    <p class="text-muted mb-0" style="font-size:.9rem">
      Supports 5e sourcebooks, scanned PDFs, and 1st Edition AD&amp;D modules
    </p>
  </div>

  <form id="form" novalidate>

    <!-- ── PDF upload ─────────────────────────────────────────────────────── -->
    <div class="card mb-3">
      <div class="card-body">
        <div class="card-title fw-semibold mb-3">PDF File</div>
        <div id="dropzone" onclick="fileInput.click()">
          <div id="dropLabel">
            <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28"
                 fill="#adb5bd" class="d-block mx-auto mb-2" viewBox="0 0 16 16">
              <path d="M.5 9.9a.5.5 0 0 1 .5.5v2.5a1 1 0 0 0 1 1h12a1 1 0 0 0
                       1-1v-2.5a.5.5 0 0 1 1 0v2.5a2 2 0 0 1-2 2H2a2 2 0 0
                       1-2-2v-2.5a.5.5 0 0 1 .5-.5"/>
              <path d="M7.646 1.146a.5.5 0 0 1 .708 0l3 3a.5.5 0 0
                       1-.708.708L8.5 2.707V11.5a.5.5 0 0 1-1 0V2.707L5.354
                       4.854a.5.5 0 1 1-.708-.708z"/>
            </svg>
            <span class="text-muted">
              Drop a PDF here or <strong>click to browse</strong>
            </span>
          </div>
        </div>
        <input type="file" id="fileInput" name="pdf" accept=".pdf" class="d-none">
      </div>
    </div>

    <!-- ── Extraction mode ────────────────────────────────────────────────── -->
    <div class="card mb-3">
      <div class="card-body">
        <div class="card-title fw-semibold mb-3">Extraction Mode</div>
        <div class="d-flex flex-wrap gap-4 mb-2">
          <div class="form-check">
            <input class="form-check-input" type="radio" name="mode"
                   id="modeStd" value="standard" checked>
            <label class="form-check-label" for="modeStd">
              Standard &nbsp;<span class="badge bg-secondary fw-normal">PyMuPDF</span>
            </label>
          </div>
          <div class="form-check">
            <input class="form-check-input" type="radio" name="mode"
                   id="modeOcr" value="ocr">
            <label class="form-check-label" for="modeOcr">
              OCR-enhanced &nbsp;<span class="badge badge-ocr text-white fw-normal">Tesseract</span>
            </label>
          </div>
          <div class="form-check">
            <input class="form-check-input" type="radio" name="mode"
                   id="mode1e" value="1e">
            <label class="form-check-label" for="mode1e">
              1e Module &nbsp;<span class="badge fw-normal text-white" style="background:#b45309">AD&amp;D 1e</span>
            </label>
          </div>
        </div>
        <div class="text-muted" style="font-size:.82rem">
          Use <strong>OCR-enhanced</strong> for scanned/image PDFs.
          Use <strong>1e Module</strong> for classic TSR adventures
          (T1-4, B2, S1, etc.) — converts descending AC, THAC0, and HD to 5e.
        </div>

        <!-- OCR extras (hidden until OCR mode selected) -->
        <div id="ocrExtras" class="mt-3 pt-3 border-top d-none">
          <div class="row g-2">
            <div class="col-sm-3">
              <label class="form-label" for="dpiInput">Render DPI</label>
              <input type="number" class="form-control form-control-sm"
                     id="dpiInput" name="dpi" value="300" min="72" max="600">
            </div>
            <div class="col-sm-3">
              <label class="form-label" for="langInput">Language</label>
              <input type="text" class="form-control form-control-sm"
                     id="langInput" name="lang" value="eng"
                     placeholder="eng / eng+fra">
            </div>
            <div class="col-sm-6 d-flex align-items-end pb-1">
              <div class="form-check">
                <input class="form-check-input" type="checkbox"
                       id="forceOcr" name="force_ocr">
                <label class="form-check-label" for="forceOcr">
                  Force OCR every page
                  <span class="text-muted">(skip digital extraction)</span>
                </label>
              </div>
            </div>
          </div>
        </div>

        <!-- 1e extras (hidden until 1e mode selected) -->
        <div id="oneExtras" class="mt-3 pt-3 border-top d-none">
          <div class="row g-2">
            <div class="col-sm-3">
              <label class="form-label" for="moduleCode">Module Code</label>
              <input type="text" class="form-control form-control-sm"
                     id="moduleCode" name="module_code"
                     placeholder="T1-4 / B2 / S1">
            </div>
            <div class="col-sm-2">
              <label class="form-label" for="systemSelect">Edition</label>
              <select class="form-select form-select-sm" id="systemSelect" name="system">
                <option value="1e" selected>AD&amp;D 1e</option>
                <option value="2e">AD&amp;D 2e</option>
              </select>
            </div>
            <div class="col-sm-3">
              <label class="form-label" for="dpi1e">Render DPI</label>
              <input type="number" class="form-control form-control-sm"
                     id="dpi1e" name="dpi_1e" value="400" min="72" max="600">
            </div>
            <div class="col-sm-2">
              <label class="form-label" for="pageRange">Page range</label>
              <input type="text" class="form-control form-control-sm"
                     id="pageRange" name="page_range"
                     placeholder="e.g. 10-20">
              <div class="form-text">Leave blank for all pages.</div>
            </div>
            <div class="col-sm-3">
              <label class="form-label" for="skipPages">Skip Pages</label>
              <input type="text" class="form-control form-control-sm"
                     id="skipPages" name="skip_pages"
                     placeholder="e.g. 1-3,127-128">
            </div>
          </div>
          <div class="row g-2 mt-1">
            <div class="col-sm-4 d-flex align-items-end pb-1">
              <div class="form-check">
                <input class="form-check-input" type="checkbox"
                       id="forceOcr1e" name="force_ocr_1e" checked>
                <label class="form-check-label" for="forceOcr1e">
                  Force OCR every page
                </label>
              </div>
            </div>
            <div class="col-sm-5 d-flex align-items-end pb-1">
              <div class="form-check">
                <input class="form-check-input" type="checkbox"
                       id="noCrAdj" name="no_cr_adjustment">
                <label class="form-check-label" for="noCrAdj">
                  No CR adjustment
                  <span class="text-muted">(keep HD-only CR)</span>
                </label>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Output settings ────────────────────────────────────────────────── -->
    <div class="card mb-3">
      <div class="card-body">
        <div class="card-title fw-semibold mb-3">Output Settings</div>
        <div class="row g-3">
          <div class="col-sm-4">
            <label class="form-label" for="typeSelect">Content type</label>
            <select class="form-select form-select-sm" id="typeSelect" name="output_type">
              <option value="adventure" selected>Adventure</option>
              <option value="book">Book</option>
            </select>
          </div>
          <div class="col-sm-4">
            <label class="form-label" for="modeSelect">Output mode</label>
            <select class="form-select form-select-sm" id="modeSelect" name="output_mode">
              <option value="homebrew" selected>Homebrew (single file)</option>
              <option value="server">Server (two files)</option>
            </select>
            <div class="form-text">
              Homebrew = load via Manage Homebrew UI.
            </div>
          </div>
          <div class="col-sm-4">
            <label class="form-label" for="shortId">Short ID</label>
            <input type="text" class="form-control form-control-sm"
                   id="shortId" name="short_id"
                   placeholder="Auto-derived from filename"
                   style="text-transform:uppercase">
          </div>
          <div class="col-sm-6">
            <label class="form-label" for="authorInput">Author</label>
            <input type="text" class="form-control form-control-sm"
                   id="authorInput" name="author" value="Unknown">
          </div>
          <div class="col-sm-6">
            <label class="form-label" for="outName">Output filename</label>
            <input type="text" class="form-control form-control-sm"
                   id="outName" name="out_name"
                   placeholder="Auto (derived from PDF name)">
          </div>
        </div>
      </div>
    </div>

    <!-- ── Claude API ─────────────────────────────────────────────────────── -->
    <div class="card mb-3">
      <div class="card-body">
        <div class="card-title fw-semibold mb-3">Claude API</div>
        <div class="row g-3">
          <div class="col-sm-6">
            <label class="form-label" for="apiKey">API Key</label>
            <div class="input-group input-group-sm">
              <input type="password" class="form-control" id="apiKey"
                     name="api_key"
                     placeholder="sk-ant-… (or set ANTHROPIC_API_KEY env var)">
              <button class="btn btn-outline-secondary" type="button"
                      id="toggleKey" tabindex="-1">Show</button>
            </div>
          </div>
          <div class="col-sm-4">
            <label class="form-label" for="modelInput">Model</label>
            <input type="text" class="form-control form-control-sm"
                   id="modelInput" name="model"
                   value="claude-haiku-4-5-20251001">
          </div>
          <div class="col-sm-2">
            <label class="form-label" for="chunkInput">Pages / chunk</label>
            <input type="number" class="form-control form-control-sm"
                   id="chunkInput" name="pages_per_chunk"
                   value="6" min="1" max="30">
          </div>
        </div>
      </div>
    </div>

    <!-- ── Advanced ───────────────────────────────────────────────────────── -->
    <div class="card mb-4">
      <div class="card-body">
        <div class="card-title fw-semibold mb-3">Advanced</div>
        <div class="row g-2">
          <div class="col-sm-6">
            <div class="form-check">
              <input class="form-check-input" type="checkbox"
                     id="extractMonsters" name="extract_monsters">
              <label class="form-check-label" for="extractMonsters">
                Extract monsters
                <span class="text-muted">(second Claude pass for stat blocks)</span>
              </label>
            </div>
          </div>
          <div class="col-sm-6">
            <div class="form-check">
              <input class="form-check-input" type="checkbox"
                     id="monstersOnly" name="monsters_only">
              <label class="form-check-label" for="monstersOnly">
                Monsters only
                <span class="text-muted">(skip adventure text)</span>
              </label>
            </div>
          </div>
          <div class="col-sm-6" id="batchRow">
            <div class="form-check">
              <input class="form-check-input" type="checkbox"
                     id="useBatch" name="use_batch">
              <label class="form-check-label" for="useBatch">
                Batch API
                <span class="text-muted">(50% cheaper, async — takes minutes)</span>
              </label>
            </div>
          </div>
          <div class="col-sm-6">
            <div class="form-check">
              <input class="form-check-input" type="checkbox"
                     id="dryRun" name="dry_run">
              <label class="form-check-label" for="dryRun">
                Dry run
                <span class="text-muted">(count tokens only, no inference)</span>
              </label>
            </div>
          </div>
          <div class="col-sm-6">
            <div class="form-check">
              <input class="form-check-input" type="checkbox"
                     id="verbose" name="verbose">
              <label class="form-check-label" for="verbose">Verbose output</label>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Submit ─────────────────────────────────────────────────────────── -->
    <div class="d-flex align-items-center gap-3">
      <button type="submit" class="btn btn-primary px-4" id="submitBtn">
        <span class="spinner-border spinner-border-sm me-2 d-none"
              id="spinner"></span>
        Convert
      </button>
      <span id="statusBadge" class="badge fs-6 d-none"></span>
    </div>

  </form>

  <!-- ── Progress log ───────────────────────────────────────────────────── -->
  <div id="progressSection" class="mt-4 d-none">
    <div class="d-flex justify-content-between align-items-center mb-2">
      <span class="fw-semibold">Progress</span>
      <button class="btn btn-sm btn-outline-secondary" onclick="clearLog()">
        Clear
      </button>
    </div>
    <div id="log"></div>
    <div id="downloadRow" class="mt-3 d-none">
      <a id="downloadBtn" class="btn btn-success" href="#" download>
        ⬇ Download JSON
      </a>
    </div>
  </div>

</div><!-- /container -->

<script>
// ── File drop / select ──────────────────────────────────────────────────────
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('fileInput');
let selectedFile = null;

dropzone.addEventListener('dragover',  e => { e.preventDefault(); dropzone.classList.add('over'); });
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('over'));
dropzone.addEventListener('drop', e => {
  e.preventDefault();
  dropzone.classList.remove('over');
  const f = e.dataTransfer.files[0];
  if (f) setFile(f);
});
fileInput.addEventListener('change', () => { if (fileInput.files[0]) setFile(fileInput.files[0]); });

function setFile(f) {
  selectedFile = f;
  dropzone.classList.add('has-file');
  document.getElementById('dropLabel').innerHTML =
    `<strong>${esc(f.name)}</strong> &nbsp;<span class="text-muted">${(f.size/1048576).toFixed(1)} MB</span>`;

  // Auto-fill Short ID
  const idEl = document.getElementById('shortId');
  if (!idEl.value) {
    idEl.value = f.name.replace(/\.pdf$/i, '')
                        .replace(/[^A-Za-z0-9]/g, '_')
                        .toUpperCase().slice(0, 12);
  }
  // Auto-fill output filename
  const outEl = document.getElementById('outName');
  if (!outEl.value) {
    outEl.value = f.name.replace(/\.pdf$/i, '_5etools.json');
  }
}

function esc(s) {
  return s.replace(/[&<>"']/g, c =>
    ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
}

// ── Mode toggle ─────────────────────────────────────────────────────────────
document.querySelectorAll('input[name="mode"]').forEach(r =>
  r.addEventListener('change', () => {
    const ocr = document.getElementById('modeOcr').checked;
    const e1  = document.getElementById('mode1e').checked;
    document.getElementById('ocrExtras').classList.toggle('d-none', !ocr);
    document.getElementById('oneExtras').classList.toggle('d-none', !e1);
    document.getElementById('batchRow').classList.toggle('d-none', ocr || e1);
    // Adjust default pages/chunk for content density
    const chunkEl = document.getElementById('chunkInput');
    if (e1)       chunkEl.value = '3';
    else if (ocr) chunkEl.value = '4';
    else          chunkEl.value = '6';
  })
);

// ── API key show/hide ────────────────────────────────────────────────────────
document.getElementById('toggleKey').addEventListener('click', () => {
  const inp = document.getElementById('apiKey');
  const btn = document.getElementById('toggleKey');
  inp.type = inp.type === 'password' ? 'text' : 'password';
  btn.textContent = inp.type === 'password' ? 'Show' : 'Hide';
});

// ── Log helpers ──────────────────────────────────────────────────────────────
const logEl = document.getElementById('log');

function appendLog(line) {
  const div = document.createElement('div');
  if (/^={3,}/.test(line))                    div.className = 'log-sep';
  else if (/\[WARN\]|\[SKIP\]/.test(line))    div.className = 'log-warn';
  else if (/error|failed|FAIL/i.test(line) &&
           !/\[WARN\]/.test(line))             div.className = 'log-err';
  else if (/Done!|✓|complete/i.test(line))    div.className = 'log-ok';
  div.textContent = line;
  logEl.appendChild(div);
  logEl.scrollTop = logEl.scrollHeight;
}

function clearLog() { logEl.innerHTML = ''; }

// ── Submit ───────────────────────────────────────────────────────────────────
document.getElementById('form').addEventListener('submit', async e => {
  e.preventDefault();

  if (!selectedFile) {
    alert('Please select a PDF file first.');
    return;
  }

  const fd = new FormData(e.target);
  fd.set('pdf', selectedFile);

  // Reset UI
  setBusy(true);
  document.getElementById('progressSection').classList.remove('d-none');
  document.getElementById('downloadRow').classList.add('d-none');
  clearLog();
  setStatus('running', 'Running…');

  // Start job
  let jobId;
  try {
    const resp = await fetch('/convert', { method: 'POST', body: fd });
    const data = await resp.json();
    if (!resp.ok) {
      appendLog('Error: ' + (data.error || resp.statusText));
      setStatus('error', 'Error');
      setBusy(false);
      return;
    }
    jobId = data.job_id;
  } catch (err) {
    appendLog('Network error: ' + err);
    setStatus('error', 'Error');
    setBusy(false);
    return;
  }

  // Stream progress via Server-Sent Events
  const es = new EventSource(`/stream/${jobId}`);

  es.addEventListener('log', ev => appendLog(ev.data));

  es.addEventListener('done', ev => {
    es.close();
    const info = JSON.parse(ev.data);
    if (info.ok) {
      setStatus('done', 'Done');
      appendLog('✓ Conversion complete.');
      const dlRow = document.getElementById('downloadRow');
      dlRow.classList.remove('d-none');
      const dlBtn = document.getElementById('downloadBtn');
      dlBtn.href     = `/download/${jobId}`;
      dlBtn.download = info.filename;
    } else {
      setStatus('error', 'Failed');
      appendLog('✗ Conversion failed — see log above.');
    }
    setBusy(false);
  });

  es.onerror = () => {
    es.close();
    setStatus('error', 'Stream error');
    setBusy(false);
  };
});

function setBusy(busy) {
  document.getElementById('submitBtn').disabled = busy;
  document.getElementById('spinner').classList.toggle('d-none', !busy);
}

function setStatus(type, label) {
  const badge = document.getElementById('statusBadge');
  badge.className = 'badge fs-6 ' + {
    running: 'bg-primary',
    done:    'bg-success',
    error:   'bg-danger',
  }[type];
  badge.textContent = label;
  badge.classList.remove('d-none');
}
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return HTML


@app.route("/convert", methods=["POST"])
def convert():
    if "pdf" not in request.files or not request.files["pdf"].filename:
        return jsonify({"error": "No PDF uploaded"}), 400

    pdf_file        = request.files["pdf"]
    mode            = request.form.get("mode", "standard")
    output_type     = request.form.get("output_type", "adventure")
    short_id        = request.form.get("short_id", "").strip() or None
    author          = request.form.get("author", "Unknown")
    api_key         = request.form.get("api_key", "").strip() or None
    model           = request.form.get("model", "claude-haiku-4-5-20251001")
    pages_per_chunk = request.form.get("pages_per_chunk", "6")
    output_mode     = request.form.get("output_mode", "homebrew")
    out_name        = request.form.get("out_name", "").strip()

    extract_monsters = "extract_monsters" in request.form
    monsters_only    = "monsters_only"    in request.form
    use_batch        = "use_batch"        in request.form
    dry_run          = "dry_run"          in request.form
    verbose          = "verbose"          in request.form

    # OCR-specific
    dpi       = request.form.get("dpi", "300")
    lang      = request.form.get("lang", "eng")
    force_ocr = "force_ocr" in request.form

    # Save the uploaded PDF to a per-job temp directory
    tmpdir   = Path(tempfile.mkdtemp(prefix="5etools_"))
    pdf_path = tmpdir / pdf_file.filename
    pdf_file.save(str(pdf_path))

    # Derive short ID from filename if not provided
    if not short_id:
        short_id = re.sub(r"[^A-Z0-9]", "", pdf_path.stem.upper())[:8] or "HOMEBREW"

    # Output filename
    if not out_name:
        out_name = pdf_path.stem + "_5etools.json"
    out_path = tmpdir / out_name

    # Pick script
    if mode == "1e":
        script = "pdf_to_5etools_1e.py"
    elif mode == "ocr":
        script = "pdf_to_5etools_ocr.py"
    else:
        script = "pdf_to_5etools.py"

    cmd = [
        sys.executable, str(SCRIPT_DIR / script),
        str(pdf_path),
        "--type",            output_type,
        "--output-mode",     output_mode,
        "--id",              short_id,
        "--author",          author,
        "--out",             str(out_path),
        "--model",           model,
        "--pages-per-chunk", pages_per_chunk,
    ]

    if api_key:
        cmd += ["--api-key", api_key]
    if extract_monsters:
        cmd.append("--extract-monsters")
    if monsters_only:
        cmd.append("--monsters-only")
    if dry_run:
        cmd.append("--dry-run")
    if verbose:
        cmd.append("--verbose")

    if mode == "standard" and use_batch:
        cmd.append("--batch")

    if mode == "ocr":
        cmd += ["--dpi", dpi, "--lang", lang]
        if force_ocr:
            cmd.append("--force-ocr")

    if mode == "1e":
        module_code    = request.form.get("module_code", "").strip()
        system         = request.form.get("system", "1e")
        skip_pages     = request.form.get("skip_pages", "").strip()
        no_cr_adj      = "no_cr_adjustment" in request.form
        dpi_1e         = request.form.get("dpi_1e", "400")
        force_ocr_1e   = "force_ocr_1e" in request.form

        page_range   = request.form.get("page_range", "").strip()

        if module_code:
            cmd += ["--module-code", module_code]
        cmd += ["--system", system, "--dpi", dpi_1e]
        if force_ocr_1e:
            cmd.append("--force-ocr")
        if no_cr_adj:
            cmd.append("--no-cr-adjustment")
        if page_range:
            cmd += ["--pages", page_range]
        if skip_pages:
            cmd += ["--skip-pages", skip_pages]

    # Create job and launch background thread
    job_id = str(uuid.uuid4())
    job    = Job(job_id, out_path)
    _jobs[job_id] = job

    env = dict(os.environ)
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key

    def _run():
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
            )
            for line in iter(proc.stdout.readline, ""):
                job.append(line.rstrip())
            proc.wait()
            job.finish(proc.returncode == 0)
        except Exception as exc:
            job.append(f"[ERROR] Failed to start process: {exc}")
            job.finish(False)

    threading.Thread(target=_run, daemon=True).start()

    return jsonify({"job_id": job_id})


@app.route("/stream/<job_id>")
def stream(job_id: str):
    if job_id not in _jobs:
        return Response("Job not found", status=404)

    job = _jobs[job_id]

    def _generate():
        idx = 0
        while True:
            lines, status = job.snapshot(idx)
            for line in lines:
                # SSE data lines must not contain raw newlines
                safe = line.replace("\n", " ")
                yield f"event: log\ndata: {safe}\n\n"
            idx += len(lines)

            if status != "running":
                ok       = status == "done" and job.output_path.exists()
                filename = job.output_path.name
                payload  = json.dumps({"ok": ok, "filename": filename})
                yield f"event: done\ndata: {payload}\n\n"
                return

            time.sleep(0.25)

    return Response(
        _generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/download/<job_id>")
def download(job_id: str):
    if job_id not in _jobs:
        return Response("Job not found", status=404)
    job = _jobs[job_id]
    if not job.output_path.exists():
        return Response("Output file not ready", status=404)
    return send_file(
        str(job.output_path),
        as_attachment=True,
        download_name=job.output_path.name,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5100))
    print(f"\n  PDF → 5etools Web Interface")
    print(f"  Open http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, threaded=True, debug=False)
