"""Flask web UI for FlexAI Social Encounter resolution.

    python3 app.py                      # loads workbooks from the default dir
    python3 app.py --data-dir ~/foo     # override the workbook directory
    FLEXAI_DATA_DIR=... python3 app.py  # same via env var

The server binds to :5105 by default; pick a different port with --port.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, render_template_string, request

import flexai_social as fs


# ---------------------------------------------------------------------------
# Data dir resolution
# ---------------------------------------------------------------------------


def resolve_data_dir(cli_value: Optional[str] = None) -> Path:
    """Pick a data directory in precedence order: CLI > env > default."""
    if cli_value:
        return Path(cli_value).expanduser()
    env_value = os.environ.get("FLEXAI_DATA_DIR")
    if env_value:
        return Path(env_value).expanduser()
    return fs.default_data_dir()


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(table=None, data_dir: Optional[Path] = None) -> Flask:
    """Build a Flask app. Pass `table` directly for tests.

    If `table` is None the factory loads the workbooks from `data_dir`.
    """
    if table is None:
        if data_dir is None:
            data_dir = resolve_data_dir()
        table = fs.load_tables(data_dir)

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


def _cell_to_json(cell, system: str):
    if cell is None:
        return None
    dcs_key = "dcs_5e" if system == "5e" else "dcs_pf2e"
    return {
        "npc_turn": {k: _range_to_list(v) for k, v in cell.get("npc_turn", {}).items()},
        "success_results": {k: _range_to_list(v) for k, v in cell.get("success_results", {}).items()},
        "failure_results": {k: _range_to_list(v) for k, v in cell.get("failure_results", {}).items()},
        "dcs": dict(cell.get(dcs_key, {}) or {}),
        "dcs_5e": dict(cell.get("dcs_5e", {}) or {}),
        "dcs_pf2e": dict(cell.get("dcs_pf2e", {}) or {}),
    }


def _vocab_for_ui():
    return {
        "roles": [{"key": k, "label": fs.display(k)} for k in fs.list_roles()],
        "sizes": [{"key": k, "label": fs.display(k)} for k in fs.list_sizes()],
        "contexts": [{"key": k, "label": fs.display(k)} for k in fs.list_contexts()],
        "ranks": fs.list_ranks(),
        "choices": [{"key": k, "label": fs.display(k)} for k in fs.list_choices()],
        "results": [{"key": k, "label": fs.display(k)} for k in fs.list_results()],
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
        role = request.args.get("role", "ally")
        size = request.args.get("size", "normal")
        context = request.args.get("context", "passing_by")
        rank = request.args.get("rank", "A")
        system = request.args.get("system", "5e")
        cell = fs.get_cell(app.config["TABLE"], role, size, context, rank)
        return jsonify({
            "role": role,
            "size": size,
            "context": context,
            "rank": rank,
            "system": system,
            "cell": _cell_to_json(cell, system),
            "available": [
                {"choice": c, "label": fs.display(c), "dc": dc}
                for c, dc in fs.available_choices(cell, system=system)
            ],
            # Always list every choice so the UI can grey out unavailable rows:
            "all_choices": [
                {
                    "choice": c,
                    "label": fs.display(c),
                    "dc": (cell.get("dcs_5e" if system == "5e" else "dcs_pf2e", {}) or {}).get(c)
                           if cell else None,
                }
                for c in fs.list_choices()
            ],
            "dcs": dict((cell.get("dcs_5e" if system == "5e" else "dcs_pf2e", {}) or {}) if cell else {}),
            "npc_turn": _cell_to_json(cell, system)["npc_turn"] if cell else {},
            "success_results": _cell_to_json(cell, system)["success_results"] if cell else {},
            "failure_results": _cell_to_json(cell, system)["failure_results"] if cell else {},
        })

    @app.route("/api/roll/npc-turn", methods=["POST"])
    def api_roll_npc_turn():
        body = request.get_json(silent=True) or {}
        cell = fs.get_cell(
            app.config["TABLE"],
            body.get("role", "ally"),
            body.get("size", "normal"),
            body.get("context", "passing_by"),
            body.get("rank", "A"),
        )
        roll, choice = fs.roll_npc_turn(cell)
        return jsonify({
            "roll": roll,
            "choice": choice,
            "choice_label": fs.display(choice) if choice else None,
        })

    @app.route("/api/roll/result", methods=["POST"])
    def api_roll_result():
        body = request.get_json(silent=True) or {}
        cell = fs.get_cell(
            app.config["TABLE"],
            body.get("role", "ally"),
            body.get("size", "normal"),
            body.get("context", "passing_by"),
            body.get("rank", "A"),
        )
        success = bool(body.get("success", True))
        roll, result = fs.roll_result(cell, success=success)
        return jsonify({
            "roll": roll,
            "success": success,
            "result": result,
            "result_label": fs.display(result) if result else None,
        })

    @app.route("/api/attempt", methods=["POST"])
    def api_attempt():
        body = request.get_json(silent=True) or {}
        cell = fs.get_cell(
            app.config["TABLE"],
            body.get("role", "ally"),
            body.get("size", "normal"),
            body.get("context", "passing_by"),
            body.get("rank", "A"),
        )
        out = fs.attempt(
            cell,
            choice=body.get("choice", "diplomacy"),
            pc_total=int(body.get("pc_total", 0)),
            system=body.get("system", "5e"),
        )
        out["choice_label"] = fs.display(out["choice"]) if out.get("choice") else None
        out["result_label"] = fs.display(out["result"]) if out.get("result") else None
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
  <title>FlexAI Social Encounter</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { padding: 1rem 1.25rem 2rem; background: #f6f7f9; }
    .nav-link.active { font-weight: 600; }
    .card { box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
    .dc-cell { font-variant-numeric: tabular-nums; }
    .unavailable { color: #999; font-style: italic; }
    .result-banner { font-size: 1.1rem; }
    .result-success { color: #0a6f3c; }
    .result-failure { color: #a02020; }
    .scratch { font-size: 0.85rem; color: #666; }
    .choice-row td { vertical-align: middle; }
    .npc-turn-roll { font-size: 1.5rem; font-weight: 600; }
    .small-caps { font-variant-caps: small-caps; letter-spacing: 0.03em; }
  </style>
</head>
<body>
  <div class="container-fluid" style="max-width: 1100px;">
    <div class="d-flex align-items-center mb-3">
      <h1 class="h3 m-0 me-3">FlexAI Social Encounter</h1>
      <a class="btn btn-sm btn-outline-secondary" href="/rules" target="_blank">View rules (pp. 260-265)</a>
    </div>

    <!-- Selector row -->
    <div class="card mb-3">
      <div class="card-body row g-3">
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
          <label class="form-label small-caps">Context</label>
          <select id="context" class="form-select">
            {% for c in vocab.contexts %}<option value="{{c.key}}">{{c.label}}</option>{% endfor %}
          </select>
        </div>
        <div class="col-md-2">
          <label class="form-label small-caps">Challenge Rank</label>
          <select id="rank" class="form-select">
            {% for rk in vocab.ranks %}<option value="{{rk}}">{{rk}}</option>{% endfor %}
          </select>
        </div>
        <div class="col-md-3">
          <label class="form-label small-caps">System</label>
          <select id="system" class="form-select">
            <option value="5e">5E / Fifth Edition</option>
            <option value="pf2e">Pathfinder 2E</option>
          </select>
        </div>
      </div>
    </div>

    <!-- NPC turn -->
    <div class="card mb-3">
      <div class="card-body">
        <div class="d-flex align-items-center justify-content-between">
          <div>
            <div class="text-muted small-caps">NPC Turn (Conversational Volley)</div>
            <div id="npc-turn-display" class="npc-turn-roll text-muted">—</div>
          </div>
          <div>
            <button id="btn-roll-npc-turn" class="btn btn-primary">Roll d100 for NPC</button>
          </div>
        </div>
      </div>
    </div>

    <!-- PC Choices -->
    <div class="card mb-3">
      <div class="card-header d-flex justify-content-between align-items-center">
        <span class="small-caps">PC Choices &mdash; DC (auto-fail if unlisted)</span>
        <div class="d-flex align-items-center gap-2">
          <label class="form-label m-0 small-caps">PC total</label>
          <input id="pc-total" type="number" class="form-control form-control-sm" style="width: 6rem;" value="15">
        </div>
      </div>
      <table class="table table-sm m-0">
        <thead class="table-light">
          <tr>
            <th>Choice</th>
            <th class="dc-cell">DC</th>
            <th></th>
          </tr>
        </thead>
        <tbody id="choices-body"></tbody>
      </table>
    </div>

    <!-- Last result -->
    <div class="card mb-3">
      <div class="card-body">
        <div class="small-caps text-muted mb-2">Last resolution</div>
        <div id="result-banner" class="result-banner text-muted">Nothing rolled yet.</div>
        <div id="result-detail" class="scratch mt-2"></div>
      </div>
    </div>
  </div>

<script>
const state = {
  role: 'ally', size: 'normal', context: 'passing_by', rank: 'A', system: '5e',
  cell: null,
};

function qs(id) { return document.getElementById(id); }

function setDropdownsFromState() {
  qs('role').value = state.role;
  qs('size').value = state.size;
  qs('context').value = state.context;
  qs('rank').value = state.rank;
  qs('system').value = state.system;
}

async function refreshCell() {
  const params = new URLSearchParams(state);
  const resp = await fetch('/api/cell?' + params.toString());
  const data = await resp.json();
  state.cell = data;
  renderChoices(data);
}

function renderChoices(data) {
  const tbody = qs('choices-body');
  tbody.innerHTML = '';
  const rows = data.all_choices || [];
  for (const row of rows) {
    const tr = document.createElement('tr');
    tr.className = 'choice-row';
    const tdName = document.createElement('td');
    tdName.textContent = row.label;
    const tdDc = document.createElement('td');
    tdDc.className = 'dc-cell';
    if (row.dc === null || row.dc === undefined) {
      tdDc.innerHTML = '<span class="unavailable">—</span>';
    } else {
      tdDc.textContent = row.dc;
    }
    const tdBtn = document.createElement('td');
    tdBtn.className = 'text-end';
    if (row.dc === null || row.dc === undefined) {
      const span = document.createElement('span');
      span.className = 'unavailable';
      span.textContent = 'auto-fail';
      tdBtn.appendChild(span);
    } else {
      const btn = document.createElement('button');
      btn.className = 'btn btn-sm btn-outline-primary';
      btn.textContent = 'Attempt';
      btn.addEventListener('click', () => attemptChoice(row.choice));
      tdBtn.appendChild(btn);
    }
    tr.appendChild(tdName);
    tr.appendChild(tdDc);
    tr.appendChild(tdBtn);
    tbody.appendChild(tr);
  }
}

async function rollNpcTurn() {
  const resp = await fetch('/api/roll/npc-turn', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      role: state.role, size: state.size,
      context: state.context, rank: state.rank,
    }),
  });
  const data = await resp.json();
  const label = data.choice_label || '(no bucket)';
  qs('npc-turn-display').innerHTML =
    `<span class="text-body">d100 = ${data.roll}</span> &rarr; <strong>${label}</strong>`;
  qs('npc-turn-display').classList.remove('text-muted');
}

async function attemptChoice(choice) {
  const pc_total = parseInt(qs('pc-total').value || '0', 10);
  const resp = await fetch('/api/attempt', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      role: state.role, size: state.size,
      context: state.context, rank: state.rank,
      system: state.system,
      choice, pc_total,
    }),
  });
  const data = await resp.json();
  showResult(data);
}

function showResult(data) {
  const banner = qs('result-banner');
  const detail = qs('result-detail');
  banner.classList.remove('text-muted', 'result-success', 'result-failure');

  if (data.dc === null || data.dc === undefined) {
    banner.classList.add('result-failure');
    banner.innerHTML = `<strong>${data.choice_label}</strong> — automatic failure (no DC)`;
    detail.textContent = data.notes || '';
    return;
  }

  const verdict = data.success ? 'SUCCESS' : 'FAILURE';
  banner.classList.add(data.success ? 'result-success' : 'result-failure');
  const resultLabel = data.result_label || '(no result bucket)';
  banner.innerHTML =
    `<strong>${data.choice_label}</strong> ` +
    `&mdash; PC ${data.pc_total} vs DC ${data.dc} &mdash; ` +
    `<span>${verdict}</span> &mdash; ` +
    `d100 = ${data.roll} &rarr; <strong>${resultLabel}</strong>`;

  let note = '';
  if (!data.success) {
    note = 'Lenient: give the party a recovery beat. Immediate (on critical failure): snap the consequence shut.';
  } else {
    note = 'Success: apply the result above. "Feels wrong"? Reroll per the rulebook (p. 261).';
  }
  detail.textContent = note;
}

for (const id of ['role', 'size', 'context', 'rank', 'system']) {
  qs(id).addEventListener('change', () => {
    state[id] = qs(id).value;
    refreshCell();
  });
}
qs('btn-roll-npc-turn').addEventListener('click', rollNpcTurn);

setDropdownsFromState();
refreshCell();
</script>
</body>
</html>
"""


_RULES_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>FlexAI Social Encounter Rules</title>
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
    parser = argparse.ArgumentParser(description="FlexAI Social Encounter web UI")
    parser.add_argument(
        "--data-dir",
        help="Directory containing the two FlexAI_Social_*.xlsx workbooks. "
             "Defaults to $FLEXAI_DATA_DIR or the hard-coded DriveThru path.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5105)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    data_dir = resolve_data_dir(args.data_dir)
    print(f"[flexai-social] data_dir = {data_dir}")
    print(f"[flexai-social] main     = {fs.MAIN_WORKBOOK_NAME}")
    print(f"[flexai-social] dcs      = {fs.DCS_WORKBOOK_NAME}")

    app = create_app(data_dir=data_dir)
    print(f"[flexai-social] listening on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    _cli()
