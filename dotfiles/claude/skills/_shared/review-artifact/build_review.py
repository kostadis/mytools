#!/usr/bin/env python3
"""Build a batch-review artifact page from a JSON item list.

The page is a direct port of the "Chapter 63 Rulings" artifact
(claude.ai/code/artifact/e7370038-fb48-4755-bc47-129d18b0dd23, 2026-08-19),
which is the proven shape: one card per judgement call, Approve / Reject /
Discuss per card, an optional per-card note, a "Discuss all N" bulk button,
a progress counter, and one Save button.

Saving calls window.claude.use('artifact').publish(...) — the page rewrites
ITSELF with the decisions embedded in <script type="application/json"
id="state">. Claude then reads that block back with read_decisions.py.

Usage:
    build_review.py --in items.json --out page.html

Input schema: see CONTRACT.md. Required keys: title, items[].
Each item requires id, t, y, n; ev is optional but strongly encouraged.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

FONTS = ("https://fonts.googleapis.com/css2?family=Spectral:ital,wght@0,400;0,600;0,800;1,400"
         "&family=Archivo:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap")

CSS = r"""
:root {
  --ground:#F1F3F1; --surface:#FAFBFA; --surface-2:#E6EAE7;
  --rule:#CBD3CD; --rule-soft:#DDE3DE;
  --ink:#171B19; --ink-2:#4A544E; --ink-3:#6E7A73;
  --accent:#2F6F62; --accent-soft:#DCE9E5;
  --ok:#2F6F62; --ok-bg:#DCE9E5;
  --no:#A63446; --no-bg:#F5E2E5;
  --talk:#A26A1F; --talk-bg:#F6EBDA;
  --shadow:0 1px 2px rgba(23,27,25,.05),0 8px 24px -16px rgba(23,27,25,.18);
  --serif:"Spectral",Georgia,serif;
  --sans:"Archivo","Helvetica Neue",Arial,sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;
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
.eyebrow{font-family:var(--mono);font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);margin-bottom:14px}
h1{font-family:var(--serif);font-weight:800;font-size:clamp(2.2rem,5.5vw,3.4rem);line-height:1.04;letter-spacing:-.02em;margin:0 0 14px;text-wrap:balance}
.lede{font-family:var(--serif);font-size:clamp(1rem,2vw,1.16rem);color:var(--ink-2);max-width:60ch;margin:0;line-height:1.5}

.bar{position:sticky;top:0;z-index:20;background:var(--ground);border-bottom:1px solid var(--rule);
  padding:12px 0;margin-bottom:6px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.prog{font-family:var(--mono);font-size:13px;color:var(--ink-2);font-variant-numeric:tabular-nums}
.prog b{color:var(--ink);font-size:15px}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip{font-family:var(--mono);font-size:11px;letter-spacing:.06em;text-transform:uppercase;padding:3px 8px;border-radius:2px;font-weight:500}
.chip.a{background:var(--ok-bg);color:var(--ok)}
.chip.r{background:var(--no-bg);color:var(--no)}
.chip.d{background:var(--talk-bg);color:var(--talk)}
.spacer{flex:1 1 auto}

button{font-family:inherit;font-size:inherit;cursor:pointer}
button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

.save{background:var(--accent);color:var(--ground);border:1px solid var(--accent);
  border-radius:3px;padding:9px 20px;font-family:var(--mono);font-size:12.5px;letter-spacing:.06em;
  text-transform:uppercase;font-weight:500;transition:opacity .15s}
.save[disabled]{opacity:.35;cursor:not-allowed}
:root[data-theme="dark"] .save,:root:not([data-theme="light"]) .save{color:#0D1211}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]) .save{color:#FAFBFA}}

.bulk{background:transparent;border:1px solid var(--rule);color:var(--ink-2);border-radius:3px;
  padding:8px 13px;font-family:var(--mono);font-size:11.5px;letter-spacing:.05em;text-transform:uppercase}
.bulk:hover{border-color:var(--talk);color:var(--talk)}

.msg{font-family:var(--mono);font-size:12px;padding:10px 14px;border-radius:3px;margin:10px 0 0;
  background:var(--surface-2);color:var(--ink-2);border-left:2px solid var(--accent)}
.msg.warn{border-left-color:var(--talk);color:var(--talk)}
.msg[hidden]{display:none}

.items{display:flex;flex-direction:column;gap:14px;margin-top:22px}

.item{background:var(--surface);border:1px solid var(--rule);border-left:3px solid var(--rule);
  border-radius:3px;padding:20px 22px 18px;display:flex;flex-direction:column;gap:12px;box-shadow:var(--shadow)}
.item[data-choice="approve"]{border-left-color:var(--ok)}
.item[data-choice="reject"]{border-left-color:var(--no)}
.item[data-choice="discuss"]{border-left-color:var(--talk)}

.item-head{display:flex;gap:12px;align-items:baseline}
.num{font-family:var(--mono);font-size:12px;color:var(--ink-3);flex:none;padding-top:4px;font-variant-numeric:tabular-nums}
.item h2{font-family:var(--serif);font-size:1.24rem;font-weight:600;line-height:1.28;margin:0;text-wrap:balance}

.outcomes{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px}
.outcome{background:var(--surface-2);border-radius:3px;padding:11px 13px;font-size:13.4px;line-height:1.5;color:var(--ink-2)}
.outcome b{display:block;font-family:var(--mono);font-size:10.5px;letter-spacing:.09em;
  text-transform:uppercase;margin-bottom:4px}
.outcome.y b{color:var(--ok)}
.outcome.n b{color:var(--no)}
.outcome code{font-family:var(--mono);font-size:12px;overflow-wrap:anywhere;color:var(--ink)}

.ev{font-size:13px;color:var(--ink-3);line-height:1.55;margin:0;padding-left:12px;border-left:2px solid var(--rule-soft)}
.ev code{font-family:var(--mono);font-size:12px;overflow-wrap:anywhere}
.ev em{color:var(--ink-2);font-style:italic}

.choices{display:flex;gap:8px;flex-wrap:wrap}
.ch{flex:1 1 auto;min-width:104px;background:transparent;border:1px solid var(--rule);color:var(--ink-2);
  border-radius:3px;padding:10px 14px;font-family:var(--mono);font-size:12px;letter-spacing:.07em;
  text-transform:uppercase;font-weight:500;transition:background .12s,border-color .12s,color .12s}
.ch:hover{border-color:var(--ink-3);color:var(--ink)}
.ch[aria-pressed="true"][data-choice="approve"]{background:var(--ok-bg);border-color:var(--ok);color:var(--ok)}
.ch[aria-pressed="true"][data-choice="reject"]{background:var(--no-bg);border-color:var(--no);color:var(--no)}
.ch[aria-pressed="true"][data-choice="discuss"]{background:var(--talk-bg);border-color:var(--talk);color:var(--talk)}

.note{width:100%;background:var(--ground);border:1px solid var(--rule);border-radius:3px;color:var(--ink);
  font-family:var(--sans);font-size:13.5px;padding:9px 12px}
.note::placeholder{color:var(--ink-3)}
.note:focus-visible{outline:2px solid var(--accent);outline-offset:-1px}
.note[hidden]{display:none}

.foot{margin-top:56px;padding-top:26px;border-top:2px solid var(--ink);font-size:13.4px;color:var(--ink-2);line-height:1.6}
.foot code{font-family:var(--mono);font-size:12px;overflow-wrap:anywhere}
.foot .applied{margin:0 0 14px}

@media (max-width:600px){.wrap{padding:0 16px 80px}.item-head{flex-direction:column;gap:4px}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""

# The page's own source. Everything the page needs to re-render itself lives
# here, because renderDoc() rebuilds the whole document from #css + #src +
# the current state. Placeholders are replaced with JSON literals.
SRC = r"""
var FONTS = __FONTS__;
var TITLE = __TITLE__;
var EYEBROW = __EYEBROW__;
var LEDE = __LEDE__;
var FOOTER = __FOOTER__;
var ITEMS = __ITEMS__;

var LABEL = {approve:"Approve", reject:"Reject", discuss:"Discuss"};

function esc(s){return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}

function readState(){
  try { return JSON.parse(document.getElementById("state").textContent); }
  catch(e){ return {decisions:{},notes:{},savedAt:null}; }
}

var state = readState();
if(!state.decisions) state.decisions = {};
if(!state.notes) state.notes = {};

var dirty = false;
var readOnly = false;

function counts(){
  var c = {approve:0,reject:0,discuss:0};
  ITEMS.forEach(function(it){ var d = state.decisions[it.id]; if(d) c[d]++; });
  return c;
}

function render(){
  var c = counts(), done = c.approve + c.reject + c.discuss;
  var h = '';

  h += '<div class="wrap">';
  h += '<div class="top">';
  h += '<div class="eyebrow">' + EYEBROW + '</div>';
  h += '<h1>' + TITLE + '</h1>';
  h += '<p class="lede">' + LEDE + '</p>';
  h += '</div>';

  h += '<div class="bar">';
  h += '<span class="prog"><b>' + done + '</b> of ' + ITEMS.length + ' decided</span>';
  h += '<span class="chips">';
  if(c.approve) h += '<span class="chip a">' + c.approve + ' approve</span>';
  if(c.reject)  h += '<span class="chip r">' + c.reject + ' reject</span>';
  if(c.discuss) h += '<span class="chip d">' + c.discuss + ' discuss</span>';
  h += '</span>';
  h += '<span class="spacer"></span>';
  h += '<button class="bulk" id="allDiscuss">Discuss all ' + ITEMS.length + '</button>';
  h += '<button class="save" id="save"' + (dirty && !readOnly ? '' : ' disabled') + '>' +
       (readOnly ? 'Read only' : 'Save decisions') + '</button>';
  h += '</div>';

  h += '<div class="msg" id="msg" hidden></div>';

  h += '<div class="items">';
  ITEMS.forEach(function(it, i){
    var d = state.decisions[it.id] || '';
    h += '<div class="item"' + (d ? ' data-choice="' + d + '"' : '') + '>';
    h += '<div class="item-head"><span class="num">' + (i+1 < 10 ? '0' : '') + (i+1) + '</span>';
    h += '<h2>' + it.t + '</h2></div>';
    h += '<div class="outcomes">';
    h += '<div class="outcome y"><b>If approved</b>' + it.y + '</div>';
    h += '<div class="outcome n"><b>If rejected</b>' + it.n + '</div>';
    h += '</div>';
    if(it.ev) h += '<p class="ev">' + it.ev + '</p>';
    h += '<div class="choices">';
    ['approve','reject','discuss'].forEach(function(k){
      h += '<button class="ch" data-item="' + it.id + '" data-choice="' + k + '" aria-pressed="' +
           (d === k ? 'true' : 'false') + '">' + LABEL[k] + '</button>';
    });
    h += '</div>';
    h += '<input class="note" data-note="' + it.id + '" placeholder="Add a note for this one (optional)" value="' +
         esc(state.notes[it.id] || '') + '"' + (d === 'discuss' || state.notes[it.id] ? '' : ' hidden') + '>';
    h += '</div>';
  });
  h += '</div>';

  h += '<div class="foot">';
  if(FOOTER) h += '<p class="applied">' + FOOTER + '</p>';
  h += 'Saving writes your decisions into this page as a new version, so they reach me without anything to copy across. ' +
       (state.savedAt ? 'Last saved <code>' + esc(state.savedAt) + '</code>.' : 'Nothing saved yet.');
  h += '</div>';
  h += '</div>';

  document.getElementById('app').innerHTML = h;
  wire();
}

function flash(text, warn){
  var m = document.getElementById('msg');
  if(!m) return;
  m.textContent = text;
  m.className = warn ? 'msg warn' : 'msg';
  m.hidden = false;
}

function wire(){
  Array.prototype.forEach.call(document.querySelectorAll('.ch'), function(b){
    b.addEventListener('click', function(){
      var id = b.getAttribute('data-item'), k = b.getAttribute('data-choice');
      state.decisions[id] = (state.decisions[id] === k) ? undefined : k;
      if(!state.decisions[id]) delete state.decisions[id];
      dirty = true;
      render();
    });
  });

  Array.prototype.forEach.call(document.querySelectorAll('.note'), function(n){
    n.addEventListener('input', function(){
      var id = n.getAttribute('data-note');
      if(n.value) state.notes[id] = n.value; else delete state.notes[id];
      dirty = true;
      var s = document.getElementById('save');
      if(s && !readOnly) s.disabled = false;
    });
  });

  var all = document.getElementById('allDiscuss');
  if(all) all.addEventListener('click', function(){
    ITEMS.forEach(function(it){ state.decisions[it.id] = 'discuss'; });
    dirty = true;
    render();
  });

  var save = document.getElementById('save');
  if(save) save.addEventListener('click', doSave);
}

function renderDoc(){
  var css = document.getElementById('css').textContent;
  var src = document.getElementById('src').textContent;
  var json = JSON.stringify(state).replace(/</g, '\\u003c');
  return '<!doctype html><html lang="en"><head><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width, initial-scale=1">' +
    '<title>' + TITLE + '<\/title>' +
    '<link rel="preconnect" href="https://fonts.googleapis.com">' +
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>' +
    '<link rel="stylesheet" href="' + FONTS + '">' +
    '<style id="css">' + css + '<\/style><\/head><body>' +
    '<div id="app"><\/div>' +
    '<script type="application/json" id="state">' + json + '<\/script>' +
    '<script type="text/plain" id="src">' + src + '<\/script>' +
    '<script>new Function(document.getElementById("src").textContent)();<\/script>' +
    '<\/body><\/html>';
}

function doSave(){
  var btn = document.getElementById('save');
  if(btn) btn.disabled = true;
  flash('Saving...');

  window.claude.use('artifact').then(function(api){
    if(!api){
      readOnly = true;
      flash('This view can\'t write to the page - your marks are still on screen, but they won\'t reach me. Tell me your picks in chat instead.', true);
      render();
      return;
    }
    state.savedAt = new Date().toISOString().replace('T',' ').slice(0,16) + ' UTC';
    return api.publish(renderDoc()).then(function(){
      flash('Saved. Your decisions are with me - tell me you\'re done and I\'ll pick them up.');
    });
  }).catch(function(err){
    var code = (err && err.code) || 'upstream_error';
    if(code === 'conflict'){
      flash('Another version was published first - this view is reloading to it.');
      return;
    }
    if(code === 'not_writer' || code === 'not_granted' || code === 'not_declared' || code === 'capability_disabled' || code === 'capability_removed' || code === 'consent_required'){
      readOnly = true;
      flash('This view is read-only - your marks show on screen but can\'t be saved. Tell me your picks in chat instead.', true);
      render();
      return;
    }
    if(code === 'rate_limited'){
      flash('Saving too often - give it a few seconds and press save again.', true);
      if(btn) btn.disabled = false;
      return;
    }
    if(code === 'too_large'){
      flash('This page is too large to save. Tell me your picks in chat and I\'ll split the review.', true);
      return;
    }
    flash('Save failed (' + code + '). Your marks are still on screen - try again, or tell me your picks in chat.', true);
    if(btn) btn.disabled = false;
  });
}

render();
"""

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">\
<meta name="viewport" content="width=device-width, initial-scale=1">\
<title>__TITLE_TEXT__</title>\
<link rel="preconnect" href="https://fonts.googleapis.com">\
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\
<link rel="stylesheet" href="__FONTS_TEXT__">\
<style id="css">__CSS__</style></head><body>\
<div id="app"></div>\
<script type="application/json" id="state">__STATE__</script>\
<script type="text/plain" id="src">__SRC__</script>\
<script>new Function(document.getElementById("src").textContent)();</script>\
</body></html>"""

REQUIRED_ITEM_KEYS = ("id", "t", "y", "n")


def js(value) -> str:
    """JSON literal safe to embed in a <script> block."""
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")


def validate(spec: dict) -> list[str]:
    errs: list[str] = []
    if not spec.get("title"):
        errs.append("top-level 'title' is required")
    items = spec.get("items")
    if not isinstance(items, list) or not items:
        errs.append("'items' must be a non-empty list")
        return errs
    seen: set[str] = set()
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            errs.append(f"items[{i}] is not an object")
            continue
        for k in REQUIRED_ITEM_KEYS:
            if not it.get(k):
                errs.append(f"items[{i}] ({it.get('id', '?')}) is missing required key '{k}'")
        iid = it.get("id")
        if iid:
            if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", str(iid)):
                errs.append(f"items[{i}] id {iid!r} must be 1-64 chars of [A-Za-z0-9_.:-]")
            if iid in seen:
                errs.append(f"duplicate item id {iid!r} - decisions are keyed by id, so ids must be unique")
            seen.add(iid)
    return errs


def build(spec: dict) -> str:
    src = (SRC
           .replace("__FONTS__", js(FONTS))
           .replace("__TITLE__", js(spec["title"]))
           .replace("__EYEBROW__", js(spec.get("eyebrow", "")))
           .replace("__LEDE__", js(spec.get("lede", "")))
           .replace("__FOOTER__", js(spec.get("footer", "")))
           .replace("__ITEMS__", js(spec["items"])))

    if re.search(r"</script", src, re.I):
        raise SystemExit(
            "refusing to emit: an unescaped '</script' reached the page source. "
            "Check the item text for a literal closing script tag."
        )

    state = spec.get("state") or {"decisions": {}, "notes": {}, "savedAt": None}
    return (PAGE
            .replace("__TITLE_TEXT__", spec["title"])
            .replace("__FONTS_TEXT__", FONTS)
            .replace("__CSS__", CSS)
            .replace("__STATE__", json.dumps(state, ensure_ascii=False).replace("<", "\\u003c"))
            .replace("__SRC__", src))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="items JSON (see CONTRACT.md)")
    ap.add_argument("--out", required=True, type=Path, help="HTML page to write")
    args = ap.parse_args()

    spec = json.loads(args.inp.read_text(encoding="utf-8"))
    errs = validate(spec)
    if errs:
        for e in errs:
            print(f"error: {e}", file=sys.stderr)
        return 1

    html = build(spec)
    args.out.write_text(html, encoding="utf-8")
    kb = len(html.encode("utf-8")) / 1024
    print(f"wrote {args.out}  ({len(spec['items'])} items, {kb:.1f} KB)")
    if kb > 15000:
        print("warning: page is near the 16MB artifact limit - split the review", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
