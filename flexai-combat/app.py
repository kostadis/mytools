"""Flask web UI for FlexAI Combat Encounter resolution.

    python3 app.py                      # loads workbook from the default dir
    python3 app.py --data-dir ~/foo     # override the workbook directory
    FLEXAI_COMBAT_DATA_DIR=... python3 app.py

Binds to :5106 by default so it can run alongside flexai-social (:5105).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, render_template_string, request

import flexai_combat as fc


# ---------------------------------------------------------------------------
# Data dir resolution
# ---------------------------------------------------------------------------


def resolve_data_dir(cli_value: Optional[str] = None) -> Path:
    if cli_value:
        return Path(cli_value).expanduser()
    env_value = os.environ.get("FLEXAI_COMBAT_DATA_DIR")
    if env_value:
        return Path(env_value).expanduser()
    return fc.default_data_dir()


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(table=None, data_dir: Optional[Path] = None) -> Flask:
    if table is None:
        if data_dir is None:
            data_dir = resolve_data_dir()
        table = fc.load_tables(data_dir)

    app = Flask(__name__)
    app.config["TABLE"] = table
    app.config["DATA_DIR"] = data_dir

    _register_routes(app)
    return app


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _range_to_list(rng):
    if rng is None:
        return None
    return [rng[0], rng[1]]


def _cell_to_json(cell):
    if cell is None:
        return {"outcomes": [], "targeting": {}}
    outcomes_list = []
    for (outcome, surge), rng in cell.get("outcomes", {}).items():
        outcomes_list.append({
            "outcome": outcome,
            "outcome_label": fc.display(outcome),
            "surge": surge,
            "surge_label": fc.display(surge) if surge else None,
            "range": _range_to_list(rng),
        })
    return {
        "outcomes": outcomes_list,
        "targeting": {k: _range_to_list(v) for k, v in cell.get("targeting", {}).items()},
    }


def _vocab_for_ui():
    return {
        "roles": [{"key": k, "label": fc.display(k)} for k in fc.list_roles()],
        "sizes": [{"key": k, "label": fc.display(k)} for k in fc.list_sizes()],
        "stances": [{"key": k, "label": fc.display(k)} for k in fc.list_stances()],
        "ranks": fc.list_ranks(),
        "outcomes": [{"key": k, "label": fc.display(k)} for k in fc.list_outcomes()],
        "targets": [{"key": k, "label": fc.display(k)} for k in fc.list_targets()],
        "tiers": list(fc.list_tiers()),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _register_routes(app: Flask) -> None:

    @app.route("/")
    def index():
        return render_template_string(_INDEX_HTML, vocab=_vocab_for_ui())

    @app.route("/api/cell")
    def api_cell():
        role = request.args.get("role", "brute")
        size = request.args.get("size", "normal")
        stance = request.args.get("stance", "fresh")
        rank = request.args.get("rank", "A")
        cell = fc.get_cell(app.config["TABLE"], role, size, stance, rank)
        data = _cell_to_json(cell)
        data.update({
            "role": role, "size": size, "stance": stance, "rank": rank,
            "found": cell is not None,
        })
        return jsonify(data)

    @app.route("/api/resolve", methods=["POST"])
    def api_resolve():
        body = request.get_json(silent=True) or {}
        out = fc.resolve_turn(
            app.config["TABLE"],
            body.get("role", "brute"),
            body.get("size", "normal"),
            body.get("stance", "fresh"),
            body.get("rank", "A"),
            tier=body.get("tier", "full"),
        )
        out["outcome_label"] = fc.display(out["outcome"]) if out.get("outcome") else None
        out["surge_label"] = fc.display(out["surge"]) if out.get("surge") else None
        out["target_label"] = fc.display(out["target"]) if out.get("target") else None
        return jsonify(out)

    @app.route("/rules")
    def rules_page():
        rules_path = Path(__file__).resolve().parent / "RULES.md"
        try:
            text = rules_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            text = "RULES.md not found."
        return render_template_string(_RULES_HTML, rules_text=text)


# ---------------------------------------------------------------------------
# HTML templates (inline)
# ---------------------------------------------------------------------------


_INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>FlexAI Combat Encounter</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { padding: 1rem 1.25rem 2rem; background: #f6f7f9; }
    .card { box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
    .small-caps { font-variant-caps: small-caps; letter-spacing: 0.03em; }
    .roll { font-size: 1.4rem; font-weight: 600; font-variant-numeric: tabular-nums; }
    .surge-tag { display: inline-block; padding: 0.1rem 0.5rem; border-radius: 0.3rem;
                 font-size: 0.85rem; font-weight: 500; margin-left: 0.4rem; }
    .surge-minor { background: #d8eaff; color: #144b80; }
    .surge-major { background: #a6d2ff; color: #07315a; }
    .lull-minor  { background: #fde4d3; color: #78411a; }
    .lull-major  { background: #f9c3a0; color: #4d2708; }
    .unavailable { color: #999; font-style: italic; }
    .bucket-table td, .bucket-table th { padding: 0.25rem 0.6rem; font-variant-numeric: tabular-nums; }
  </style>
</head>
<body>
  <div class="container-fluid" style="max-width: 1100px;">
    <div class="d-flex align-items-center mb-3">
      <h1 class="h3 m-0 me-3">FlexAI Combat Encounter</h1>
      <a class="btn btn-sm btn-outline-secondary" href="/rules" target="_blank">View rules (pp. 12-22)</a>
    </div>

    <div class="card mb-3">
      <div class="card-body row g-3 align-items-end">
        <div class="col-md-2">
          <label class="form-label small-caps">Tier</label>
          <select id="tier" class="form-select">
            {% for t in vocab.tiers %}<option value="{{t}}">{{t|capitalize}}</option>{% endfor %}
          </select>
        </div>
        <div class="col-md-2">
          <label class="form-label small-caps">Role</label>
          <select id="role" class="form-select">
            {% for r in vocab.roles %}<option value="{{r.key}}">{{r.label}}</option>{% endfor %}
          </select>
        </div>
        <div class="col-md-2">
          <label class="form-label small-caps">Role Size</label>
          <select id="size" class="form-select">
            {% for s in vocab.sizes %}<option value="{{s.key}}">{{s.label}}</option>{% endfor %}
          </select>
        </div>
        <div class="col-md-3">
          <label class="form-label small-caps">Stance</label>
          <select id="stance" class="form-select">
            {% for st in vocab.stances %}<option value="{{st.key}}">{{st.label}}</option>{% endfor %}
          </select>
        </div>
        <div class="col-md-1">
          <label class="form-label small-caps">Rank</label>
          <select id="rank" class="form-select">
            {% for rk in vocab.ranks %}<option value="{{rk}}">{{rk}}</option>{% endfor %}
          </select>
        </div>
        <div class="col-md-2 d-grid">
          <button id="btn-resolve" class="btn btn-primary">Resolve Turn</button>
        </div>
      </div>
      <div class="card-footer small text-muted" id="tier-hint">
        Simple: d20 on fixed tables (role/size/stance/rank ignored).
        Full: d100 on FlexTable, surge rows collapsed.
        Advanced: d100 on FlexTable, surge/lull tag retained.
      </div>
    </div>

    <div class="card mb-3">
      <div class="card-body">
        <div class="row">
          <div class="col-md-6">
            <div class="small-caps text-muted">Outcome</div>
            <div id="outcome-display" class="roll text-muted">&mdash;</div>
          </div>
          <div class="col-md-6">
            <div class="small-caps text-muted">Targeting</div>
            <div id="target-display" class="roll text-muted">&mdash;</div>
          </div>
        </div>
        <div id="resolve-notes" class="small text-muted mt-2"></div>
      </div>
    </div>

    <div class="row g-3">
      <div class="col-md-7">
        <div class="card h-100">
          <div class="card-header small-caps">Outcome buckets (d100)</div>
          <table class="table table-sm bucket-table m-0">
            <thead class="table-light"><tr><th>Outcome</th><th>Surge/Lull</th><th>Range</th></tr></thead>
            <tbody id="outcomes-body"></tbody>
          </table>
        </div>
      </div>
      <div class="col-md-5">
        <div class="card h-100">
          <div class="card-header small-caps">Targeting buckets (d100)</div>
          <table class="table table-sm bucket-table m-0">
            <thead class="table-light"><tr><th>Target</th><th>Range</th></tr></thead>
            <tbody id="targeting-body"></tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

<script>
const state = { tier: 'full', role: 'brute', size: 'normal', stance: 'fresh', rank: 'A' };

function qs(id) { return document.getElementById(id); }

function rangeText(r) {
  if (!r) return '<span class="unavailable">&mdash;</span>';
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(r[0])}-${r[1] === 100 ? '00' : pad(r[1])}`;
}

function surgeBadge(surge, label) {
  if (!surge) return '';
  const cls = surge.startsWith('minor_surge') || surge === 'minor_surge' ? 'surge-minor'
           : surge.startsWith('major_surge') || surge === 'major_surge' ? 'surge-major'
           : surge === 'minor_lull' ? 'lull-minor'
           : surge === 'major_lull' ? 'lull-major' : '';
  return `<span class="surge-tag ${cls}">${label}</span>`;
}

async function refreshCell() {
  const params = new URLSearchParams({
    role: state.role, size: state.size, stance: state.stance, rank: state.rank
  });
  const resp = await fetch('/api/cell?' + params.toString());
  const data = await resp.json();
  renderBuckets(data);
}

function renderBuckets(data) {
  const ob = qs('outcomes-body');
  ob.innerHTML = '';
  const outcomes = data.outcomes || [];
  outcomes.sort((a, b) => {
    const ra = a.range ? a.range[0] : 999;
    const rb = b.range ? b.range[0] : 999;
    return ra - rb;
  });
  for (const row of outcomes) {
    const tr = document.createElement('tr');
    tr.innerHTML =
      `<td>${row.outcome_label}</td>` +
      `<td>${row.surge ? surgeBadge(row.surge, row.surge_label) : ''}</td>` +
      `<td>${rangeText(row.range)}</td>`;
    if (!row.range) tr.classList.add('text-muted');
    ob.appendChild(tr);
  }

  const tb = qs('targeting-body');
  tb.innerHTML = '';
  const targets = data.targeting || {};
  // Keep canonical ordering from vocab
  const order = {{ vocab.targets | tojson }};
  for (const t of order) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${t.label}</td><td>${rangeText(targets[t.key])}</td>`;
    if (!targets[t.key]) tr.classList.add('text-muted');
    tb.appendChild(tr);
  }
}

async function resolveTurn() {
  const resp = await fetch('/api/resolve', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(state),
  });
  const data = await resp.json();
  const oDisp = qs('outcome-display');
  const tDisp = qs('target-display');
  oDisp.classList.remove('text-muted');
  tDisp.classList.remove('text-muted');

  const dieSize = state.tier === 'simple' ? 'd20' : 'd100';
  const oLabel = data.outcome_label || '(no bucket)';
  const tLabel = data.target_label || '(no bucket)';
  const surgeHtml = data.surge ? surgeBadge(data.surge, data.surge_label) : '';
  oDisp.innerHTML = `<span class="text-body">${dieSize}=${data.outcome_roll}</span> &rarr; <strong>${oLabel}</strong>${surgeHtml}`;
  tDisp.innerHTML = `<span class="text-body">${dieSize}=${data.target_roll}</span> &rarr; <strong>${tLabel}</strong>`;
  qs('resolve-notes').textContent = data.notes || '';
}

for (const id of ['tier', 'role', 'size', 'stance', 'rank']) {
  qs(id).addEventListener('change', () => {
    state[id] = qs(id).value;
    if (id !== 'tier') refreshCell();
  });
}
qs('btn-resolve').addEventListener('click', resolveTurn);

refreshCell();
</script>
</body>
</html>
"""


_RULES_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>FlexAI Combat Encounter Rules</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { padding: 2rem; max-width: 900px; margin: 0 auto; background: #f6f7f9; }
    #content { background: #fff; padding: 2rem 2.5rem; border-radius: 0.5rem;
               box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
    h1, h2, h3 { margin-top: 1.5rem; }
    table { border-collapse: collapse; margin: 1rem 0; }
    th, td { border: 1px solid #ccc; padding: 0.4rem 0.8rem; }
    th { background: #f0f0f0; }
  </style>
</head>
<body>
  <a href="/" class="btn btn-sm btn-outline-secondary mb-3">&larr; Back to resolver</a>
  <div id="content">Loading&hellip;</div>
  <script id="rules-md" type="text/plain">{{ rules_text }}</script>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <script>
    const md = document.getElementById('rules-md').textContent;
    document.getElementById('content').innerHTML = marked.parse(md);
  </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------


def _cli() -> None:
    parser = argparse.ArgumentParser(description="FlexAI Combat Encounter web UI")
    parser.add_argument(
        "--data-dir",
        help="Directory containing FlexAI_Combat_2021_01_04.xlsx. "
             "Defaults to $FLEXAI_COMBAT_DATA_DIR or the hard-coded default.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5106)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    data_dir = resolve_data_dir(args.data_dir)
    print(f"[flexai-combat] data_dir = {data_dir}")
    print(f"[flexai-combat] workbook = {fc.WORKBOOK_NAME}")

    app = create_app(data_dir=data_dir)
    print(f"[flexai-combat] listening on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    _cli()
