#!/usr/bin/env python3
"""Render an offline-review HTML artifact for an entity-triage queue.

Format follows the claude staged-consistency review page: one self-contained
HTML file, no network, decisions persisted to localStorage, Save/Copy exports
a decisions JSON the agent then applies through registry.py verbs.

Usage:
    python3 render_triage_review.py \
        --queue <campaign>/docs/.triage_queue.json \
        --plan  <campaign>/docs/.triage_review_plan.json \
        --out   <campaign>/docs/entity_triage_review.html

--plan is the agent-authored review plan (schema in SKILL.md "Offline review
artifact"). The queue is the raw triage-candidates output; sources/near_miss/
count are merged into each card by surface match. Deterministic, stdlib only,
writes nothing except the HTML file.
"""
import argparse, html, json, sys
from datetime import datetime, timezone


def norm(s):
    return "".join(c for c in s.lower() if c.isalnum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    queue = json.load(open(args.queue, encoding="utf-8"))
    plan = json.load(open(args.plan, encoding="utf-8"))

    by_norm = {}
    for c in queue.get("candidates", []):
        by_norm[c.get("norm") or norm(c.get("surface", ""))] = c
        by_norm.setdefault(norm(c.get("surface", "")), c)

    campaign = plan.get("campaign") or queue.get("campaign", "campaign")
    now = datetime.now(timezone.utc).strftime("%Y%m%d")
    review_id = plan.get("review_id") or f"entity-triage:{campaign}:{now}"
    items = []
    for i, it in enumerate(plan.get("items", []), 1):
        surf = it.get("surface", "")
        q = by_norm.get(it.get("norm") or norm(surf), {})
        if not q:  # tolerate plan-only items
            q = {"surface": surf}
        nm = q.get("near_miss")
        card = {
            "id": f"t-{i:02d}",
            "surface": surf,
            "count": q.get("count", 0),
            "sources": q.get("sources", []),
            "lane": it.get("lane", "batch"),
            "generic": it.get("generic", "unknown"),
            "near_miss": (f'{nm["name"]} (ratio {nm["ratio"]})' if nm else None),
            "ev": it.get("ev", ""),
            "rec": it.get("rec", "defer"),
            "rec_conf": it.get("rec_conf", ""),
            "rec_meta": it.get("rec_meta", {}),
            "choices": it.get("choices") or default_choices(nm, surf),
        }
        # the recommended ruling must always be clickable, even when the
        # default option set lacked it (e.g. curated alias rec without a
        # near-miss hint) — never strand a recommendation without a button
        rec = it.get("rec", "defer")
        if rec not in {c["k"] for c in card["choices"]}:
            tgt = it.get("rec_meta", {}).get("target")
            label = f"Alias of \"{tgt}\"" if rec == "alias" and tgt else (
                    f'Distinct (not "{tgt}")' if rec == "distinct" and tgt else
                    {"add": "New entity", "ignore": "Not an entity",
                     "defer": "Defer", "discuss": "Discuss"}.get(rec, rec.capitalize()))
            card["choices"].insert(0, {"k": rec, "label": label,
                                       "meta": it.get("rec_meta", {})})
        items.append(card)

    title = plan.get("title") or f"{campaign} — entity triage review"
    eyebrow = plan.get("eyebrow") or f"{campaign} / entity registry triage"
    lede = plan.get("lede") or (
        f"{len(items)} candidates awaiting ruling. Accept applies the "
        "recommended ruling; other buttons override it. Unmarked candidates "
        "are never treated as rejected.")
    footer = plan.get("footer") or ""
    payload = {
        "TITLE": title, "EYEBROW": eyebrow, "LEDE": lede, "FOOTER": footer,
        "REVIEW_ID": review_id,
        "OUTPUT_NAME": f"entity_triage_decisions_{now}.json",
        "ITEMS": items,
    }
    out = PAGE.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False))
    out = out.replace("__TITLE_JSON__", html.escape(title, quote=True))
    open(args.out, "w", encoding="utf-8").write(out)
    print(f"wrote {args.out} ({len(items)} cards, review {review_id})")


def default_choices(nm, surf):
    ch = []
    if nm:
        ch.append({"k": "alias", "label": f'Alias of "{nm["name"]}"',
                   "meta": {"target": nm["name"]}})
        ch.append({"k": "distinct", "label": "Distinct entity (looks like it, isn't)",
                   "meta": {"target": nm["name"]}})
    ch.append({"k": "add", "label": "New entity", "meta": {"type": "npc"}})
    ch.append({"k": "ignore", "label": "Not an entity"})
    ch.append({"k": "defer", "label": "Defer"})
    ch.append({"k": "discuss", "label": "Discuss"})
    return ch


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>__TITLE_JSON__</title><style>
:root {
  --ground:#F1F3F1; --surface:#FAFBFA; --surface-2:#E6EAE7;
  --rule:#CBD3CD; --rule-soft:#DDE3DE;
  --ink:#171B19; --ink-2:#4A544E; --ink-3:#6E7A73;
  --accent:#2F6F62; --accent-soft:#DCE9E5;
  --ok:#2F6F62; --ok-bg:#DCE9E5;
  --no:#A63446; --no-bg:#F5E2E5;
  --talk:#A26A1F; --talk-bg:#F6EBDA;
  --shadow:0 1px 2px rgba(23,27,25,.05),0 8px 24px -16px rgba(23,27,25,.18);
  --serif:Georgia,"Times New Roman",serif;
  --sans:"Helvetica Neue",Arial,sans-serif;
  --mono:ui-monospace,Menlo,Consolas,monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ground:#101413; --surface:#171C1A; --surface-2:#1F2624;
    --rule:#2E3835; --rule-soft:#242C2A;
    --ink:#E0E6E2; --ink-2:#A9B4AE; --ink-3:#7C8882;
    --accent:#6BBBA7; --accent-soft:#1B2E2A;
    --ok:#6BBBA7; --ok-bg:#1B2E2A;
    --no:#E28794; --no-bg:#34191E;
    --talk:#DDAA5E; --talk-bg:#33280F;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 28px -18px rgba(0,0,0,.8);
  }
}
:root[data-theme="dark"] {
  --ground:#101413; --surface:#171C1A; --surface-2:#1F2624;
  --rule:#2E3835; --rule-soft:#242C2A;
  --ink:#E0E6E2; --ink-2:#A9B4AE; --ink-3:#7C8882;
  --accent:#6BBBA7; --accent-soft:#1B2E2A;
  --ok:#6BBBA7; --ok-bg:#1B2E2A;
  --no:#E28794; --no-bg:#34191E;
  --talk:#DDAA5E; --talk-bg:#33280F;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 28px -18px rgba(0,0,0,.8);
}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);font-size:16px;line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:940px;margin:0 auto;padding:0 24px 100px}
.top{padding:56px 0 26px}
.eyebrow{font-family:var(--mono);font-size:11.5px;text-transform:uppercase;color:var(--accent);margin-bottom:14px}
h1{font-family:var(--serif);font-weight:800;font-size:3rem;line-height:1.04;margin:0 0 14px;text-wrap:balance}
.lede{font-family:var(--serif);font-size:1.16rem;color:var(--ink-2);max-width:60ch;margin:0;line-height:1.5}
.bar{position:sticky;top:0;z-index:20;background:var(--ground);border-bottom:1px solid var(--rule);
  padding:12px 0;margin-bottom:6px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.prog{font-family:var(--mono);font-size:13px;color:var(--ink-2);font-variant-numeric:tabular-nums}
.prog b{color:var(--ink);font-size:15px}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip{font-family:var(--mono);font-size:11px;text-transform:uppercase;padding:3px 8px;border-radius:2px;font-weight:500}
.chip.a{background:var(--ok-bg);color:var(--ok)}
.chip.r{background:var(--no-bg);color:var(--no)}
.chip.d{background:var(--talk-bg);color:var(--talk)}
.chip.n{background:var(--surface-2);color:var(--ink-3)}
.spacer{flex:1 1 auto}
button{font-family:inherit;font-size:inherit;cursor:pointer}
button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.save{background:var(--accent);color:var(--ground);border:1px solid var(--accent);
  border-radius:3px;padding:9px 20px;font-family:var(--mono);font-size:12.5px;
  text-transform:uppercase;font-weight:500;transition:opacity .15s}
:root[data-theme="dark"] .save,:root:not([data-theme="light"]) .save{color:#0D1211}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]) .save{color:#FAFBFA}}
.bulk{background:transparent;border:1px solid var(--rule);color:var(--ink-2);border-radius:3px;
  padding:8px 13px;font-family:var(--mono);font-size:11.5px;text-transform:uppercase}
.bulk:hover{border-color:var(--talk);color:var(--talk)}
.msg{font-family:var(--mono);font-size:12px;padding:10px 14px;border-radius:3px;margin:10px 0 0;
  background:var(--surface-2);color:var(--ink-2);border-left:2px solid var(--accent)}
.msg.warn{border-left-color:var(--talk);color:var(--talk)}
.msg[hidden]{display:none}
.items{display:flex;flex-direction:column;gap:14px;margin-top:22px}
.item{background:var(--surface);border:1px solid var(--rule);border-left:3px solid var(--rule);
  border-radius:3px;padding:20px 22px 18px;display:flex;flex-direction:column;gap:12px;box-shadow:var(--shadow)}
.item[data-choice]:not([data-choice="defer"]):not([data-choice="discuss"]){border-left-color:var(--ok)}
.item[data-choice="defer"]{border-left-color:var(--ink-3)}
.item[data-choice="discuss"]{border-left-color:var(--talk)}
.item-head{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}
.num{font-family:var(--mono);font-size:12px;color:var(--ink-3);flex:none;padding-top:4px;font-variant-numeric:tabular-nums}
.item h2{font-family:var(--serif);font-size:1.24rem;font-weight:600;line-height:1.28;margin:0}
.meta{font-family:var(--mono);font-size:11.5px;color:var(--ink-3);display:flex;gap:10px;flex-wrap:wrap}
.rec{background:var(--surface-2);border-radius:3px;padding:11px 13px;font-size:13.4px;line-height:1.5;color:var(--ink-2)}
.rec b{display:block;font-family:var(--mono);font-size:10.5px;text-transform:uppercase;margin-bottom:4px;color:var(--accent)}
.ev{font-size:13px;color:var(--ink-3);line-height:1.55;margin:0;padding-left:12px;border-left:2px solid var(--rule-soft)}
.ev em{color:var(--ink-2);font-style:italic}
.choices{display:flex;gap:8px;flex-wrap:wrap}
.ch{flex:1 1 auto;min-width:104px;background:transparent;border:1px solid var(--rule);color:var(--ink-2);
  border-radius:3px;padding:10px 14px;font-family:var(--mono);font-size:12px;
  text-transform:uppercase;font-weight:500;transition:background .12s,border-color .12s,color .12s}
.ch:hover{border-color:var(--ink-3);color:var(--ink)}
.ch.rec-choice{border-color:var(--accent);color:var(--accent)}
.ch[aria-pressed="true"][data-choice="add"],.ch[aria-pressed="true"][data-choice="alias"],
.ch[aria-pressed="true"][data-choice="distinct"]{background:var(--ok-bg);border-color:var(--ok);color:var(--ok)}
.ch[aria-pressed="true"][data-choice="ignore"]{background:var(--no-bg);border-color:var(--no);color:var(--no)}
.ch[aria-pressed="true"][data-choice="discuss"]{background:var(--talk-bg);border-color:var(--talk);color:var(--talk)}
.ch[aria-pressed="true"][data-choice="defer"]{background:var(--surface-2);border-color:var(--ink-3);color:var(--ink)}
.note{width:100%;background:var(--ground);border:1px solid var(--rule);border-radius:3px;color:var(--ink);
  font-family:var(--sans);font-size:13.5px;padding:9px 12px}
.note::placeholder{color:var(--ink-3)}
.note:focus-visible{outline:2px solid var(--accent);outline-offset:-1px}
.note[hidden]{display:none}
.foot{margin-top:56px;padding-top:26px;border-top:2px solid var(--ink);font-size:13.4px;color:var(--ink-2);line-height:1.6}
.foot code{font-family:var(--mono);font-size:12px;overflow-wrap:anywhere}
.search{width:min(260px,100%);height:37px;padding:0 10px;border:1px solid var(--rule);border-radius:3px;
  background:var(--surface);color:var(--ink);font-family:var(--sans);font-size:13px}
.search:focus-visible{outline:2px solid var(--accent);outline-offset:-1px}
.filters{display:flex;gap:5px;flex-wrap:wrap}
.filter{height:37px;padding:0 10px;border:1px solid var(--rule);border-radius:3px;background:transparent;
  color:var(--ink-2);font-family:var(--mono);font-size:11px;text-transform:uppercase}
.filter[aria-pressed="true"]{background:var(--surface-2);border-color:var(--ink-3);color:var(--ink)}
@media (max-width:600px){
  .wrap{padding:0 16px 80px}
  h1{font-size:2.2rem}.lede{font-size:1rem}.search{width:100%}.filters{width:100%}
  .filter{flex:1 1 30%;min-width:0}.save,.bulk{flex:1 1 auto}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style></head><body><div id="app"></div><script type="application/json" id="state">{"decisions": {}, "notes": {}, "savedAt": null}</script><script type="text/plain" id="src">
var PAYLOAD = __PAYLOAD__;
var TITLE = PAYLOAD.TITLE, EYEBROW = PAYLOAD.EYEBROW, LEDE = PAYLOAD.LEDE, FOOTER = PAYLOAD.FOOTER;
var REVIEW_ID = PAYLOAD.REVIEW_ID, OUTPUT_NAME = PAYLOAD.OUTPUT_NAME, ITEMS = PAYLOAD.ITEMS;

function esc(s){return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}

function readState(){
  try { return JSON.parse(document.getElementById("state").textContent); }
  catch(e){ return {decisions:{},notes:{},savedAt:null}; }
}
var state = readState();
if(!state.decisions) state.decisions = {};
if(!state.notes) state.notes = {};
state.filter = 'all';
state.search = '';
try {
  var stored = JSON.parse(localStorage.getItem('triage-review:' + REVIEW_ID) || '{}');
  if(stored.decisions) state.decisions = stored.decisions;
  if(stored.notes) state.notes = stored.notes;
} catch(e) {}

function rulingOf(id){ var d = state.decisions[id]; return d ? d.k : ''; }
function counts(){
  var c = {};
  ITEMS.forEach(function(it){ var r = rulingOf(it.id); if(r) c[r] = (c[r]||0)+1; });
  return c;
}
function render(){
  var c = counts(), done = 0;
  Object.keys(c).forEach(function(k){ done += c[k]; });
  var query = state.search.toLowerCase();
  var visible = ITEMS.filter(function(it){
    var r = rulingOf(it.id);
    var filterMatch = state.filter === 'all'
      || (state.filter === 'unmarked' ? !r : state.filter === 'discuss' ? r === 'discuss' : !!r && r !== 'discuss' && r !== 'defer');
    var hay = [it.id,it.surface,(it.sources||[]).join(' '),it.ev,(it.near_miss||''),it.rec].join(' ').toLowerCase();
    return filterMatch && (!query || hay.indexOf(query) !== -1);
  });
  var h = '';
  h += '<div class="wrap"><div class="top">';
  h += '<div class="eyebrow">' + esc(EYEBROW) + '</div><h1>' + esc(TITLE) + '</h1>';
  h += '<p class="lede">' + esc(LEDE) + '</p></div>';

  h += '<div class="bar"><span class="prog"><b>' + done + '</b> of ' + ITEMS.length + ' decided</span><span class="chips">';
  ['add','alias','distinct','ignore','defer','discuss'].forEach(function(k){
    if(c[k]) h += '<span class="chip ' + (k==='add'||k==='alias'||k==='distinct'?'a':k==='ignore'?'r':k==='discuss'?'d':'n') + '">' + c[k] + ' ' + k + '</span>';
  });
  h += '</span><span class="spacer"></span>';
  h += '<input class="search" id="search" type="search" placeholder="Search candidates" value="' + esc(state.search) + '"><span class="filters">';
  [['all','All'],['unmarked','Unmarked'],['decided','Decided'],['discuss','Discuss']].forEach(function(p){
    h += '<button class="filter" data-filter="' + p[0] + '" aria-pressed="' + (state.filter===p[0]) + '">' + p[1] + '</button>';
  });
  h += '</span>';
  h += '<button class="bulk" id="allDefer">Defer all ' + ITEMS.length + '</button>';
  h += '<button class="bulk" id="allRec">Accept all recommended</button>';
  h += '<button class="bulk" id="copy">Copy output</button>';
  h += '<button class="save" id="save">Save output</button></div>';
  h += '<div class="msg" id="msg" hidden></div><div class="items">';

  visible.forEach(function(it){
    var i = ITEMS.indexOf(it);
    var r = rulingOf(it.id);
    h += '<div class="item"' + (r ? ' data-choice="' + r + '"' : '') + '>';
    h += '<div class="item-head"><span class="num">' + esc(it.id) + '</span><h2>' + esc(it.surface) + '</h2></div>';
    h += '<div class="meta"><span>count ' + it.count + '</span>';
    if(it.lane) h += '<span>' + esc(it.lane) + '</span>';
    if(it.generic) h += '<span>5etools: ' + esc(it.generic) + '</span>';
    if(it.near_miss) h += '<span>near-miss: ' + esc(it.near_miss) + '</span>';
    h += '</div>';
    if(it.sources && it.sources.length) h += '<div class="meta"><span>' + esc(it.sources.join(' · ')) + '</span></div>';
    h += '<div class="rec"><b>Recommended</b>' + esc(it.rec) + (it.rec_conf ? ' <em>(' + esc(it.rec_conf) + ')</em>' : '') + '</div>';
    if(it.ev) h += '<p class="ev">' + esc(it.ev) + '</p>';
    h += '<div class="choices">';
    it.choices.forEach(function(ch){
      h += '<button class="ch' + (ch.k === it.rec ? ' rec-choice' : '') + '" data-item="' + esc(it.id) +
           '" data-choice="' + esc(ch.k) + '" aria-pressed="' + (r===ch.k ? 'true':'false') + '">' +
           esc(ch.label) + '</button>';
    });
    h += '</div>';
    h += '<input class="note" data-note="' + esc(it.id) + '" placeholder="Note — needed for: type if not recommended, alias target, discuss question (optional)" value="' +
         esc(state.notes[it.id] || '') + '"' + (r === 'discuss' || state.notes[it.id] ? '' : ' hidden') + '>';
    h += '</div>';
  });
  if(!visible.length) h += '<div class="msg">No candidates match this view.</div>';
  h += '</div><div class="foot">';
  if(FOOTER) h += '<p>' + esc(FOOTER) + '</p>';
  h += 'Use Copy output to paste the rulings into chat, or Save output to download <code>' + esc(OUTPUT_NAME) +
       '</code>. Unmarked candidates remain unresolved; they are never treated as rejected. Nothing is written until the agent applies the exported file through the validated registry.py verbs.</div></div>';
  document.getElementById('app').innerHTML = h;
  wire();
}
function flash(text, warn){
  var m = document.getElementById('msg'); if(!m) return;
  m.textContent = text; m.className = warn ? 'msg warn' : 'msg'; m.hidden = false;
}
function persist(){
  try { localStorage.setItem('triage-review:' + REVIEW_ID, JSON.stringify({decisions:state.decisions,notes:state.notes})); }
  catch(e) {}
}
function itemById(id){ for(var i=0;i<ITEMS.length;i++) if(ITEMS[i].id===id) return ITEMS[i]; return null; }
function wire(){
  Array.prototype.forEach.call(document.querySelectorAll('.ch'), function(b){
    b.addEventListener('click', function(){
      var id = b.getAttribute('data-item'), k = b.getAttribute('data-choice');
      if(state.decisions[id] && state.decisions[id].k === k) delete state.decisions[id];
      else {
        var it = itemById(id), meta = {};
        (it ? it.choices : []).forEach(function(ch){ if(ch.k===k && ch.meta) meta = ch.meta; });
        if(k === it.rec && it.rec_meta) meta = it.rec_meta;
        state.decisions[id] = {k:k, meta:meta};
      }
      persist(); render();
    });
  });
  Array.prototype.forEach.call(document.querySelectorAll('.note'), function(n){
    n.addEventListener('input', function(){
      var id = n.getAttribute('data-note');
      if(n.value) state.notes[id] = n.value; else delete state.notes[id];
      persist();
    });
  });
  var d = document.getElementById('allDefer');
  if(d) d.addEventListener('click', function(){
    ITEMS.forEach(function(it){ state.decisions[it.id] = {k:'defer', meta:{}}; });
    persist(); render();
  });
  var rc = document.getElementById('allRec');
  if(rc) rc.addEventListener('click', function(){
    ITEMS.forEach(function(it){
      var meta = it.rec_meta || {};
      (it.choices||[]).forEach(function(ch){ if(ch.k===it.rec && ch.meta) meta = ch.meta; });
      state.decisions[it.id] = {k:it.rec, meta:meta};
    });
    persist(); render();
  });
  var s = document.getElementById('search');
  if(s) s.addEventListener('input', function(){
    state.search = s.value; render();
    var nx = document.getElementById('search');
    if(nx){ nx.focus(); nx.setSelectionRange(nx.value.length, nx.value.length); }
  });
  Array.prototype.forEach.call(document.querySelectorAll('[data-filter]'), function(b){
    b.addEventListener('click', function(){ state.filter = b.getAttribute('data-filter'); render(); });
  });
  var cp = document.getElementById('copy'); if(cp) cp.addEventListener('click', copyOutput);
  var sv = document.getElementById('save'); if(sv) sv.addEventListener('click', doSave);
}
function output(){
  var c = counts(), decisions = {}, notes = {}, unmarked = [];
  ITEMS.forEach(function(it){
    var d = state.decisions[it.id];
    if(d) decisions[it.id] = d; else unmarked.push(it.id);
    if(state.notes[it.id]) notes[it.id] = state.notes[it.id];
  });
  return {
    schemaVersion: 1,
    kind: "entity-triage-decisions",
    reviewId: REVIEW_ID,
    savedAt: new Date().toISOString().replace('T',' ').slice(0,16) + ' UTC',
    decided: Object.keys(decisions).length,
    tally: c,
    items: ITEMS.map(function(it){ return {id:it.id, surface:it.surface}; }),
    decisions: decisions,
    notes: notes,
    unmarked: unmarked
  };
}
function outputText(){ return JSON.stringify(output(), null, 2); }
function copyOutput(){
  var value = outputText();
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(value).then(function(){ flash('Decision output copied.'); }).catch(function(){ fallbackCopy(value); });
  } else fallbackCopy(value);
}
function fallbackCopy(value){
  var a = document.createElement('textarea'); a.value = value; a.style.position='fixed'; a.style.opacity='0';
  document.body.appendChild(a); a.select();
  try {
    if(document.execCommand('copy')) flash('Decision output copied.');
    else window.prompt('Copy the decision output:', value);
  } catch(e) { window.prompt('Copy the decision output:', value); }
  a.remove();
}
function doSave(){
  var blob = new Blob([outputText()], {type:'application/json'});
  var url = URL.createObjectURL(blob);
  var link = document.createElement('a'); link.href = url; link.download = OUTPUT_NAME;
  document.body.appendChild(link); link.click(); link.remove();
  URL.revokeObjectURL(url);
  flash('Saved ' + OUTPUT_NAME + '.');
}
render();
</script><script>new Function(document.getElementById("src").textContent)();</script></body></html>"""


if __name__ == "__main__":
    main()
