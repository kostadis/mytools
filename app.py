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

  <div class="d-flex justify-content-between align-items-start mb-4">
    <div>
      <h4 class="fw-bold mb-0">PDF → 5etools Converter</h4>
      <p class="text-muted mb-0" style="font-size:.9rem">
        Supports 5e sourcebooks, scanned PDFs, and 1st Edition AD&amp;D modules
      </p>
    </div>
    <a href="/editor" class="btn btn-sm btn-outline-secondary">Manual Editor</a>
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
          <div class="col-sm-2">
            <label class="form-label" for="singlePage">Single page</label>
            <input type="number" class="form-control form-control-sm"
                   id="singlePage" name="single_page"
                   min="1" placeholder="e.g. 7">
            <div class="form-text">Leave blank for all.</div>
          </div>
        </div>
        <div class="row g-2 mt-1">
          <div class="col-sm-12">
            <div class="form-check">
              <input class="form-check-input" type="checkbox"
                     id="onePageAtATime" name="one_page_at_a_time">
              <label class="form-check-label" for="onePageAtATime">
                One page at a time
                <span class="text-muted">(sets pages/chunk to 1)</span>
              </label>
            </div>
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

// ── One page at a time ───────────────────────────────────────────────────────
document.getElementById('onePageAtATime').addEventListener('change', function() {
  const chunkEl = document.getElementById('chunkInput');
  if (this.checked) {
    chunkEl._savedValue = chunkEl.value;
    chunkEl.value = '1';
  } else {
    chunkEl.value = chunkEl._savedValue || '6';
  }
});

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
# Manual editor HTML
# ---------------------------------------------------------------------------

EDITOR_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>5etools Manual JSON Editor</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    html, body { height: 100%; overflow: hidden; background: #f4f6f9; }
    /* ── OCR panel ─────────────────────────────────────────────── */
    #ocr-panel {
      background: #1a1b26; border-radius: 6px; padding: 8px;
      font-family: 'Cascadia Code','Fira Mono',monospace; font-size: .77rem;
      overflow-y: auto; flex: 1 1 0; min-height: 0;
    }
    .ocr-line {
      padding: 2px 6px; border-radius: 3px; cursor: pointer;
      white-space: pre-wrap; word-break: break-word;
      line-height: 1.55; color: #c0caf5; user-select: none;
    }
    .ocr-line:hover            { background: rgba(255,255,255,.06); }
    .ocr-line.sel              { background: #1e3a5f !important; }
    .ocr-line.used             { opacity: .32; text-decoration: line-through; }
    .ocr-line.type-h1          { color: #7dcfff; font-weight: 700; }
    .ocr-line.type-h2          { color: #7aa2f7; font-weight: 600; }
    .ocr-line.type-h3          { color: #bb9af7; }
    .ocr-line.type-inset       { color: #e0af68; font-style: italic; }
    .ocr-line.type-stat        { color: #9ece6a; }
    .ocr-line.type-room        { color: #f7768e; font-weight: 600; }
    .ocr-line.type-sep         { color: #414868; border-top: 1px solid #414868; margin: 3px 0; }
    .ocr-line.type-ctx         { color: #414868; font-style: italic; }
    /* ── Entry cards ───────────────────────────────────────────── */
    #entry-panel { overflow-y: auto; flex: 1 1 0; min-height: 0; }
    .ecard {
      background: #fff; border: 1px solid #e0e4ea; border-radius: 6px;
      padding: 5px 8px; margin-bottom: 3px; font-size: .78rem;
    }
    .ecard .ename {
      font-weight: 600; outline: none; border-bottom: 1px dashed transparent;
      min-width: 40px; display: inline-block;
    }
    .ecard .ename:focus  { border-bottom-color: #6b7280; }
    .ecard .etext {
      color: #374151; outline: none; border-bottom: 1px dashed transparent;
      white-space: pre-wrap; word-break: break-word;
    }
    .ecard .etext:focus  { border-bottom-color: #6b7280; }
    .ecard .eprev       { color: #9ca3af; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 260px; }
    .tbadge { font-size: .6rem; padding: 1px 5px; border-radius: 3px; font-weight: 700; text-transform: uppercase; }
    .tb-section  { background:#dbeafe; color:#1e40af; }
    .tb-entries  { background:#ede9fe; color:#5b21b6; }
    .tb-room     { background:#fef3c7; color:#92400e; }
    .tb-inset    { background:#d1fae5; color:#065f46; }
    .tb-list     { background:#fce7f3; color:#9d174d; }
    .tb-table    { background:#fee2e2; color:#991b1b; }
    .tb-creature { background:#f3f4f6; color:#374151; }
    .tb-string   { background:#f0fdf4; color:#166534; }
    /* ── JSON preview ──────────────────────────────────────────── */
    #json-pre {
      background: #1a1b26; color: #c0caf5; font-family: monospace;
      font-size: .7rem; padding: 8px; border-radius: 6px;
      height: 160px; overflow-y: auto; white-space: pre;
    }
    /* ── Action bar ────────────────────────────────────────────── */
    #action-bar { background: #fff; border: 1px solid #e0e4ea; border-radius: 6px; padding: 8px 10px; }
    .abtn { font-size: .72rem; padding: 2px 7px; margin: 2px 1px; }
    /* ── Misc ──────────────────────────────────────────────────── */
    .bc-item { font-size: .78rem; }
  </style>
</head>
<body>
<div class="d-flex flex-column" style="height:100vh; padding:10px; gap:8px">

  <!-- ── Top bar ──────────────────────────────────────────────────────── -->
  <div class="d-flex flex-wrap gap-2 align-items-end">
    <a href="/" class="btn btn-sm btn-outline-secondary">← Converter</a>
    <div>
      <div style="font-size:.7rem;color:#6b7280">Debug dir</div>
      <div class="input-group input-group-sm">
        <input id="debugDir" type="text" class="form-control" style="width:240px" placeholder="/home/user/debug-1">
        <button class="btn btn-outline-secondary" onclick="listFiles()">Browse</button>
      </div>
    </div>
    <div>
      <div style="font-size:.7rem;color:#6b7280">File</div>
      <select id="fileSelect" class="form-select form-select-sm" style="width:230px" onchange="loadFile()">
        <option value="">— select —</option>
      </select>
    </div>
    <div>
      <div style="font-size:.7rem;color:#6b7280">ID</div>
      <input id="advId" type="text" class="form-control form-control-sm" style="width:80px" placeholder="T1-4">
    </div>
    <div>
      <div style="font-size:.7rem;color:#6b7280">Title</div>
      <input id="advTitle" type="text" class="form-control form-control-sm" style="width:200px" placeholder="Adventure title">
    </div>
    <div>
      <div style="font-size:.7rem;color:#6b7280">Author</div>
      <input id="advAuthor" type="text" class="form-control form-control-sm" style="width:130px" placeholder="Author">
    </div>
    <div class="ms-auto d-flex gap-1 align-items-end">
      <button class="btn btn-sm btn-outline-danger" onclick="clearAll()">Clear</button>
      <button class="btn btn-sm btn-success" onclick="downloadJson()">⬇ Download JSON</button>
    </div>
  </div>

  <!-- ── Main two-column area ─────────────────────────────────────────── -->
  <div class="d-flex gap-2 flex-grow-1 min-height-0" style="min-height:0">

    <!-- Left: OCR text -->
    <div class="d-flex flex-column" style="flex:0 0 50%; min-width:0">
      <div class="d-flex justify-content-between align-items-center mb-1">
        <span style="font-size:.75rem;font-weight:600">OCR Text</span>
        <span id="sel-count" style="font-size:.72rem;color:#6b7280">No selection</span>
      </div>
      <div id="ocr-panel" onclick="handleClick(event)">
        <div style="color:#414868;font-style:italic">Load a debug input file to begin.</div>
      </div>
    </div>

    <!-- Right: builder -->
    <div class="d-flex flex-column" style="flex:0 0 50%; min-width:0; gap:6px">

      <!-- Breadcrumb -->
      <div class="d-flex align-items-center gap-2">
        <button id="back-btn" class="btn btn-sm btn-outline-secondary py-0 px-2" onclick="goUp()" disabled>← Up</button>
        <ol class="breadcrumb mb-0" id="breadcrumb">
          <li class="breadcrumb-item active bc-item">root</li>
        </ol>
      </div>

      <!-- Entry list -->
      <div id="entry-panel">
        <div style="font-size:.8rem;color:#9ca3af">No entries yet.</div>
      </div>

      <!-- Action bar -->
      <div id="action-bar">
        <div style="font-size:.68rem;font-weight:700;color:#6b7280;margin-bottom:4px">ADD SELECTED LINES AS</div>
        <button class="btn btn-sm abtn" style="background:#dbeafe;color:#1e40af;border-color:#93c5fd" onclick="addAs('section')">H1 Section</button>
        <button class="btn btn-sm abtn" style="background:#ede9fe;color:#5b21b6;border-color:#c4b5fd" onclick="addAs('entries')">H2 Sub-section</button>
        <button class="btn btn-sm abtn" style="background:#fef3c7;color:#92400e;border-color:#fcd34d" onclick="addAs('room')">Room Key</button>
        <button class="btn btn-sm abtn" style="background:#d1fae5;color:#065f46;border-color:#6ee7b7" onclick="addAs('inset')">Inset</button>
        <button class="btn btn-sm abtn" style="background:#fce7f3;color:#9d174d;border-color:#f9a8d4" onclick="addAs('list')">List</button>
        <button class="btn btn-sm abtn" style="background:#fee2e2;color:#991b1b;border-color:#fca5a5" onclick="addAs('table')">Table</button>
        <button class="btn btn-sm abtn" style="background:#f3f4f6;color:#374151;border-color:#d1d5db" onclick="addAs('creature')">Stat Block</button>
        <button class="btn btn-sm abtn" style="background:#f0fdf4;color:#166534;border-color:#86efac" onclick="addAs('string')">Paragraph</button>
        <button class="btn btn-sm abtn btn-outline-secondary" onclick="skipLines()" title="Mark selected lines as used/ignored">Skip</button>
      </div>

      <!-- JSON preview -->
      <div style="font-size:.68rem;font-weight:700;color:#6b7280">JSON PREVIEW</div>
      <div id="json-pre">{}</div>

    </div>
  </div>
</div>

<script>
// ── State ────────────────────────────────────────────────────────────────────
let ocrLines = [];        // {raw, clean, ltype, idx, used}
let selected = new Set(); // selected line indices
let anchor   = null;      // shift-click anchor

let root = [];            // root entries array
let path = [];            // array of _eid values tracing cursor into tree
let _eid = 0;

// ── Tree helpers ─────────────────────────────────────────────────────────────
function newEid() { return ++_eid; }

function getArr(eid_path) {
  let arr = root;
  for (const id of eid_path) {
    const e = arr.find(x => x._eid === id);
    if (!e) return arr;
    arr = e.entries ?? e.items ?? arr;
  }
  return arr;
}

function target()  { return getArr(path); }
function canDive(e){ return Array.isArray(e.entries) || Array.isArray(e.items); }

// ── OCR parsing ───────────────────────────────────────────────────────────────
const STRIP_RE = /^\[H[123]\]\s*|^\[(?:INSET|STAT-BLOCK)-(?:START|END)\]\s*|^\[1E-STAT\]\s*|^\[OCR\]\s*|^\[2-COLUMN\]\s*|^\[ROOM-KEY-\d+\]\s*|^\[WANDERING-TABLE\]\s*|^---\s*(?:Page \d+|\(second column\))\s*---\s*|^\[CONTEXT:[^\]]*\]\s*/i;

function clean(raw) { return raw.replace(STRIP_RE, '').trim(); }

function ltype(raw) {
  if (/^\[CONTEXT:/i.test(raw))                   return 'ctx';
  if (/^---/.test(raw))                            return 'sep';
  if (/^\[H1\]/i.test(raw))                        return 'h1';
  if (/^\[H2\]/i.test(raw))                        return 'h2';
  if (/^\[H3\]/i.test(raw))                        return 'h3';
  if (/^\[INSET-(?:START|END)\]/i.test(raw))       return 'inset';
  if (/^\[(?:STAT-BLOCK-(?:START|END)|1E-STAT)\]/i.test(raw)) return 'stat';
  if (/^\[WANDERING-TABLE\]/i.test(raw))           return 'stat';
  if (/^\[ROOM-KEY-\d+\]/i.test(raw))             return 'room';
  return 'body';
}

// ── File loading ──────────────────────────────────────────────────────────────
async function listFiles() {
  const dir = document.getElementById('debugDir').value.trim();
  if (!dir) return;
  const r = await fetch('/api/list-debug-files?dir=' + encodeURIComponent(dir));
  const d = await r.json();
  if (d.error) { alert(d.error); return; }
  const sel = document.getElementById('fileSelect');
  sel.innerHTML = '<option value="">— select —</option>';
  (d.files || []).forEach(f => {
    const o = document.createElement('option');
    o.value = d.dir + '/' + f;
    o.textContent = f;
    sel.appendChild(o);
  });
}

async function loadFile() {
  const fp = document.getElementById('fileSelect').value;
  if (!fp) return;
  const r = await fetch('/api/read-debug-file?path=' + encodeURIComponent(fp));
  const d = await r.json();
  if (d.error) { alert(d.error); return; }
  ocrLines = d.content.split('\n').map((raw, idx) => ({raw, clean: clean(raw), ltype: ltype(raw), idx, used: false}));
  selected.clear(); anchor = null;
  renderOcr(); updateSelCount();
}

// ── OCR render ────────────────────────────────────────────────────────────────
function renderOcr() {
  const panel = document.getElementById('ocr-panel');
  panel.innerHTML = '';
  ocrLines.forEach(line => {
    const d = document.createElement('div');
    d.className = 'ocr-line type-' + line.ltype
                + (selected.has(line.idx) ? ' sel' : '')
                + (line.used ? ' used' : '');
    d.dataset.idx = line.idx;
    d.textContent = line.raw || '\u00a0';
    panel.appendChild(d);
  });
}

function handleClick(e) {
  const div = e.target.closest('.ocr-line');
  if (!div) return;
  const idx = +div.dataset.idx;
  if (e.shiftKey && anchor !== null) {
    const lo = Math.min(anchor, idx), hi = Math.max(anchor, idx);
    if (!e.ctrlKey && !e.metaKey) selected.clear();
    for (let i = lo; i <= hi; i++) selected.add(i);
  } else if (e.ctrlKey || e.metaKey) {
    selected.has(idx) ? selected.delete(idx) : selected.add(idx);
    anchor = idx;
  } else {
    selected.clear(); selected.add(idx); anchor = idx;
  }
  renderOcr(); updateSelCount();
}

function updateSelCount() {
  const n = selected.size;
  document.getElementById('sel-count').textContent = n ? `${n} line${n>1?'s':''} selected` : 'No selection';
}

// ── Entry creation ────────────────────────────────────────────────────────────
function selLines()  { return [...selected].sort((a,b)=>a-b).map(i => ocrLines[i]).filter(Boolean); }
function selText(sep){ return selLines().map(l=>l.clean).filter(Boolean).join(sep ?? '\n'); }

function addAs(type) {
  const lines = selLines().filter(l => l.clean);
  if (!lines.length) { alert('Select OCR lines first.'); return; }

  const arr = target();
  let entry;

  if (type === 'string') {
    entry = {_eid: newEid(), type: 'string', text: lines.map(l=>l.clean).join(' ')};

  } else if (type === 'section' || type === 'entries') {
    entry = {_eid: newEid(), type, name: lines[0].clean, entries: []};

  } else if (type === 'room') {
    const first = lines[0].clean;
    const m = first.match(/^(\d+)[.):\s]+(.+)/);
    const name = m ? `${m[1]}. ${m[2].trim()}` : first;
    entry = {_eid: newEid(), type: 'entries', name, entries: []};

  } else if (type === 'inset') {
    const name = lines[0].clean;
    const body = lines.slice(1).map(l=>l.clean).filter(Boolean);
    entry = {_eid: newEid(), type: 'inset', name, entries: body.length ? body : []};

  } else if (type === 'list') {
    entry = {_eid: newEid(), type: 'list', items: lines.map(l=>l.clean).filter(Boolean)};

  } else if (type === 'table') {
    const cols = lines[0].clean.split(/\t|\s{2,}/);
    const rows = lines.slice(1).map(l => l.clean.split(/\t|\s{2,}/));
    entry = {_eid: newEid(), type: 'table', caption: '', colLabels: cols, rows};

  } else if (type === 'creature') {
    const nameLine = lines.find(l => l.ltype !== 'stat') ?? lines[0];
    entry = {_eid: newEid(), type: 'creature', name: nameLine.clean,
             _1e_original: lines.map(l=>l.clean).join(' ')};
  }

  if (!entry) return;
  arr.push(entry);
  lines.forEach(l => { l.used = true; });
  selected.clear();
  renderOcr(); renderEntries(); updateJsonPreview(); updateSelCount();
}

function skipLines() {
  selLines().forEach(l => { l.used = true; });
  selected.clear();
  renderOcr(); updateSelCount();
}

// ── Tree navigation ───────────────────────────────────────────────────────────
function enterEntry(eid) {
  const e = target().find(x => x._eid === eid);
  if (e && canDive(e)) { path.push(eid); renderEntries(); updateBreadcrumb(); }
}

function goUp() {
  if (path.length) { path.pop(); renderEntries(); updateBreadcrumb(); }
}

function deleteEntry(eid) {
  const arr = target();
  const i = arr.findIndex(x => x._eid === eid);
  if (i !== -1) arr.splice(i, 1);
  renderEntries(); updateJsonPreview();
}

function moveEntry(eid, dir) {
  const arr = target();
  const i = arr.findIndex(x => x._eid === eid);
  const j = i + dir;
  if (i < 0 || j < 0 || j >= arr.length) return;
  [arr[i], arr[j]] = [arr[j], arr[i]];
  renderEntries(); updateJsonPreview();
}

// ── Entry rendering ───────────────────────────────────────────────────────────
const BADGE = {section:'tb-section', entries:'tb-entries', inset:'tb-inset',
               list:'tb-list', table:'tb-table', creature:'tb-creature', string:'tb-string'};
const LABEL = {section:'H1 Section', entries:'Section', inset:'Inset',
               list:'List', table:'Table', creature:'Stat Block', string:'Paragraph'};

function isRoom(e) { return e.type === 'entries' && /^\d+\./.test(e.name ?? ''); }

function preview(e) {
  if (e.type === 'string')   return e.text ?? '';
  if (e.type === 'list')     return (e.items ?? []).slice(0,3).join(' • ');
  if (e.type === 'table')    return `[Table ${(e.colLabels??[]).join(' | ')}]`;
  if (e.type === 'creature') return (e._1e_original ?? '').slice(0, 80);
  const n = (e.entries ?? e.items ?? []).length;
  return `${n} item${n===1?'':'s'} inside`;
}

function renderEntries() {
  const panel = document.getElementById('entry-panel');
  const arr   = target();
  if (!arr.length) {
    panel.innerHTML = '<div style="font-size:.8rem;color:#9ca3af">No entries here. Select OCR lines and click an action button.</div>';
    document.getElementById('back-btn').disabled = path.length === 0;
    return;
  }
  panel.innerHTML = '';
  arr.forEach(e => {
    const room  = isRoom(e);
    const badge = room ? 'tb-room' : (BADGE[e.type] ?? 'tb-string');
    const label = room ? 'Room Key' : (LABEL[e.type] ?? e.type);
    const dive  = canDive(e);
    const card  = document.createElement('div');
    card.className = 'ecard';
    card.innerHTML = `
      <div class="d-flex align-items-start gap-2">
        <span class="tbadge ${badge} mt-1 flex-shrink-0">${esc(label)}</span>
        <div class="flex-grow-1" style="min-width:0">
          ${e.name !== undefined ? `<div class="ename" contenteditable="true"
              onblur="saveName(${e._eid}, this.textContent)">${esc(e.name)}</div>` : ''}
          ${e.type === 'string' ? `<div class="etext" contenteditable="true"
              onblur="saveText(${e._eid}, this.textContent)">${esc(e.text)}</div>` : ''}
          ${e.type !== 'string' && e.name === undefined ? `<div class="eprev">${esc(preview(e))}</div>` : ''}
          ${e.name !== undefined && e.type !== 'string' ? `<div class="eprev" style="font-size:.7rem">${esc(preview(e))}</div>` : ''}
        </div>
        <div class="d-flex gap-1 flex-shrink-0 align-items-center">
          ${dive ? `<button class="btn btn-outline-primary py-0 px-1" style="font-size:.65rem"
                             onclick="enterEntry(${e._eid})">→</button>` : ''}
          <button class="btn btn-outline-secondary py-0 px-1" style="font-size:.65rem" onclick="moveEntry(${e._eid},-1)">↑</button>
          <button class="btn btn-outline-secondary py-0 px-1" style="font-size:.65rem" onclick="moveEntry(${e._eid},1)">↓</button>
          <button class="btn btn-outline-danger py-0 px-1"   style="font-size:.65rem" onclick="deleteEntry(${e._eid})">✕</button>
        </div>
      </div>`;
    panel.appendChild(card);
  });
  document.getElementById('back-btn').disabled = path.length === 0;
}

function saveName(eid, text) {
  const e = target().find(x => x._eid === eid);
  if (e) { e.name = text.trim(); updateJsonPreview(); }
}
function saveText(eid, text) {
  const e = target().find(x => x._eid === eid);
  if (e) { e.text = text.trim(); updateJsonPreview(); }
}

function updateBreadcrumb() {
  const bc = document.getElementById('breadcrumb');
  bc.innerHTML = '';
  const crumbs = ['root'];
  let arr = root;
  for (const id of path) {
    const e = arr.find(x => x._eid === id);
    crumbs.push(e?.name ?? `[${id}]`);
    arr = e?.entries ?? e?.items ?? [];
  }
  crumbs.forEach((c, i) => {
    const li = document.createElement('li');
    li.className = 'breadcrumb-item bc-item' + (i === crumbs.length-1 ? ' active' : '');
    li.textContent = c;
    bc.appendChild(li);
  });
}

// ── JSON build ────────────────────────────────────────────────────────────────
function buildEntries(arr) {
  return arr.map(e => {
    if (e.type === 'string') return e.text;
    const out = {};
    for (const [k,v] of Object.entries(e)) {
      if (k === '_eid') continue;
      if (k === 'entries') out.entries = buildEntries(v);
      else out[k] = v;
    }
    return out;
  });
}

function buildHomebrew() {
  const id     = document.getElementById('advId').value.trim()     || 'HOMEBREW';
  const title  = document.getElementById('advTitle').value.trim()  || 'My Adventure';
  const author = document.getElementById('advAuthor').value.trim() || 'Unknown';
  const entries = buildEntries(root);
  return {
    _meta: {sources: [{json: id, abbreviation: id.slice(0,6).toUpperCase(),
                        full: title, authors: [author], version: '1.0'}]},
    adventure:     [{name: title, id, source: id,
                     entries: [{type:'section', name: title, entries}]}],
    adventureData: [{id, entries: [{type:'section', name: title, entries}]}],
  };
}

function updateJsonPreview() {
  const s = JSON.stringify(buildHomebrew(), null, 2);
  document.getElementById('json-pre').textContent = s.length > 4000 ? s.slice(0,4000)+'\n… (truncated)' : s;
}

function downloadJson() {
  const json = JSON.stringify(buildHomebrew(), null, 2);
  const id   = document.getElementById('advId').value.trim() || 'homebrew';
  const a = Object.assign(document.createElement('a'), {
    href: URL.createObjectURL(new Blob([json], {type:'application/json'})),
    download: `adventure-${id.toLowerCase()}-manual.json`,
  });
  a.click();
}

function clearAll() {
  if (!confirm('Clear all entries?')) return;
  root = []; path = [];
  renderEntries(); updateJsonPreview(); updateBreadcrumb();
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
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

    extract_monsters    = "extract_monsters"    in request.form
    monsters_only       = "monsters_only"       in request.form
    use_batch           = "use_batch"           in request.form
    dry_run             = "dry_run"             in request.form
    verbose             = "verbose"             in request.form
    one_page_at_a_time  = "one_page_at_a_time"  in request.form
    single_page         = request.form.get("single_page", "").strip()

    if one_page_at_a_time:
        pages_per_chunk = "1"

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

    if single_page:
        cmd += ["--page", single_page]

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
# Manual editor routes
# ---------------------------------------------------------------------------

@app.route("/editor")
def editor():
    return EDITOR_HTML


@app.route("/api/list-debug-files")
def list_debug_files():
    dirpath = request.args.get("dir", "").strip()
    if not dirpath:
        return jsonify({"error": "No path provided"}), 400
    p = Path(dirpath).expanduser().resolve()
    if not p.is_dir():
        return jsonify({"error": f"Not a directory: {dirpath}"}), 400
    files = sorted(f.name for f in p.glob("*-input.txt"))
    return jsonify({"files": files, "dir": str(p)})


@app.route("/api/read-debug-file")
def read_debug_file():
    filepath = request.args.get("path", "").strip()
    if not filepath:
        return jsonify({"error": "No path provided"}), 400
    p = Path(filepath).expanduser().resolve()
    if not p.exists():
        return jsonify({"error": f"File not found: {filepath}"}), 404
    return jsonify({"content": p.read_text(encoding="utf-8", errors="replace")})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5100))
    print(f"\n  PDF → 5etools Web Interface")
    print(f"  Open http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, threaded=True, debug=False)
