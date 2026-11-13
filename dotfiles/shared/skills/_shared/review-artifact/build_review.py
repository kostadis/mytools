#!/usr/bin/env python3
"""Build a batch-review artifact page from a JSON item list.

The page is a direct port of the "Chapter 63 Rulings" artifact
(claude.ai/code/artifact/e7370038-fb48-4755-bc47-129d18b0dd23, 2026-08-19),
which is the proven shape: one card per judgement call, Approve / Reject /
Discuss per card (plus any extraVerdicts the caller declares), an optional per-card note, a "Discuss all N" bulk button,
a progress counter, and one Save button.

Saving calls window.claude.use('artifact').publish(...) — the page rewrites
ITSELF with the decisions embedded in <script type="application/json"
id="state">. Claude then reads that block back with read_decisions.py.

Usage:
    build_review.py --in items.json --out page.html [--save artifact|local]

--save artifact (default) writes the page above: Save republishes the page.
--save local writes a standalone page for a runtime with no artifact store
(Codex): Copy output, Save output (a download named by the spec's optional
"outputName", default decisions.json) and, when a server injects
<meta name="codex-review-save" content="enabled">, Save to VM via
PUT ./decisions. The card standard is identical in both modes.

Input schema: see CONTRACT.md. Required keys: title, items[].
Each item requires id, t, y, n; ev is optional but strongly encouraged.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from review_ids import REVIEW_ID_RE, derive_review_id, slug_review_id  # noqa: E402,F401  (derive_review_id: for callers)

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
  --x:#5A5C8F; --x-bg:#E4E4F0;
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
    --x:#A9ABE0; --x-bg:#23243A;
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
  --x:#A9ABE0; --x-bg:#23243A;
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
.chip.x{background:var(--x-bg);color:var(--x)}
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
.item[data-x="1"]{border-left-color:var(--x)}

.item-head{display:flex;gap:12px;align-items:baseline}
.num{font-family:var(--mono);font-size:12px;color:var(--ink-3);flex:none;padding-top:4px;font-variant-numeric:tabular-nums}
.item h2{font-family:var(--serif);font-size:1.24rem;font-weight:600;line-height:1.28;margin:0;text-wrap:balance}
.edit{flex:1 1 auto;min-width:0;font-size:1.06rem;font-weight:700;line-height:1.5;color:var(--ink);overflow-wrap:anywhere}
.edit .lbl,.why .lbl,.guess .lbl{display:block;font-family:var(--mono);font-size:11px;font-weight:500;letter-spacing:.09em;
  text-transform:uppercase;color:var(--accent);margin-bottom:4px}
.edit i{font-style:normal}
.edit i:nth-of-type(odd){font-weight:500;color:var(--ink-2)}
.edit code{font-family:var(--mono);font-size:.95rem}
.why{font-size:15px;line-height:1.55;color:var(--ink-2)}
.why .lbl{color:var(--ink-3)}
.guess{background:var(--talk-bg);border-radius:3px;padding:10px 13px;font-size:15px;line-height:1.5;color:var(--ink)}
.guess .lbl{color:var(--talk)}
.ch .mine{display:block;font-size:10px;letter-spacing:.06em;margin-top:2px;color:var(--talk)}

.outcomes{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px}
.outcome{background:var(--surface-2);border-radius:3px;padding:11px 13px;font-size:15px;line-height:1.55;color:var(--ink-2)}
.outcome b{display:block;font-family:var(--mono);font-size:10.5px;letter-spacing:.09em;
  text-transform:uppercase;margin-bottom:4px}
.outcome.y b{color:var(--ok)}
.outcome.n b{color:var(--no)}
.outcome.x b{color:var(--x)}
.outcome code{font-family:var(--mono);font-size:13.5px;overflow-wrap:anywhere;color:var(--ink)}

.ev{font-size:15px;color:var(--ink-2);line-height:1.6;margin:0;padding-left:12px;border-left:2px solid var(--rule-soft)}
.ev code{font-family:var(--mono);font-size:13.5px;overflow-wrap:anywhere}
.ev em{color:var(--ink-2);font-style:italic}

.choices{display:flex;gap:8px;flex-wrap:wrap}
.ch{flex:1 1 auto;min-width:104px;background:transparent;border:1px solid var(--rule);color:var(--ink-2);
  border-radius:3px;padding:10px 14px;font-family:var(--mono);font-size:12px;letter-spacing:.07em;
  text-transform:uppercase;font-weight:500;transition:background .12s,border-color .12s,color .12s}
.ch:hover{border-color:var(--ink-3);color:var(--ink)}
.ch[aria-pressed="true"][data-choice="approve"]{background:var(--ok-bg);border-color:var(--ok);color:var(--ok)}
.ch[aria-pressed="true"][data-choice="reject"]{background:var(--no-bg);border-color:var(--no);color:var(--no)}
.ch[aria-pressed="true"][data-choice="discuss"]{background:var(--talk-bg);border-color:var(--talk);color:var(--talk)}
.ch[aria-pressed="true"][data-x="1"]{background:var(--x-bg);border-color:var(--x);color:var(--x)}

.picks{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.picks .lbl{font-family:var(--mono);font-size:11px;font-weight:500;letter-spacing:.09em;text-transform:uppercase;color:var(--ink-3);margin-right:4px}
.pk{background:transparent;border:1px solid var(--rule);color:var(--ink);border-radius:3px;padding:9px 14px;
  font-family:var(--sans);font-size:17px;font-weight:500;transition:background .12s,border-color .12s,color .12s}
.pk:hover{border-color:var(--ink-3)}
.pk[aria-pressed="true"]{background:var(--ok-bg);border-color:var(--ok);color:var(--ok)}
.pk .mine{display:block;font-family:var(--mono);font-size:10px;letter-spacing:.06em;margin-top:2px;color:var(--talk)}
.note{width:100%;background:var(--ground);border:1px solid var(--rule);border-radius:3px;color:var(--ink);
  font-family:var(--sans);font-size:15px;padding:9px 12px}
.note::placeholder{color:var(--ink-3)}
.note:focus-visible{outline:2px solid var(--accent);outline-offset:-1px}
.note[hidden]{display:none}

.foot{margin-top:56px;padding-top:26px;border-top:2px solid var(--ink);font-size:15px;color:var(--ink-2);line-height:1.6}
.foot code{font-family:var(--mono);font-size:12px;overflow-wrap:anywhere}
.foot .applied{margin:0 0 14px}

.search{width:min(260px,100%);height:37px;padding:0 10px;border:1px solid var(--rule);border-radius:3px;
  background:var(--surface);color:var(--ink);font-family:var(--sans);font-size:13px}
.search:focus-visible{outline:2px solid var(--accent);outline-offset:-1px}
.filters{display:flex;gap:5px;flex-wrap:wrap}
.filter{height:37px;padding:0 10px;border:1px solid var(--rule);border-radius:3px;background:transparent;
  color:var(--ink-2);font-family:var(--mono);font-size:11px;text-transform:uppercase}
.filter[aria-pressed="true"]{background:var(--surface-2);border-color:var(--ink-3);color:var(--ink)}
.none{color:var(--ink-3);font-size:14px;padding:20px 0}
@media (max-width:600px){.wrap{padding:0 16px 80px}.item-head{flex-direction:column;gap:4px}
  .search{width:100%}.filters{width:100%}.filter{flex:1 1 30%;min-width:0}}
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
var EXTRA = __EXTRA__;

var LABEL = {approve:"Approve", reject:"Reject", discuss:"Discuss"};
var KEYS = ['approve','reject','discuss'];
var ISX = {};
EXTRA.forEach(function(e){ LABEL[e.key] = e.label; KEYS.push(e.key); ISX[e.key] = true; });

function esc(s){return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}

function readState(){
  try { return JSON.parse(document.getElementById("state").textContent); }
  catch(e){ return {decisions:{},notes:{},savedAt:null}; }
}

var state = readState();
if(!state.decisions) state.decisions = {};
if(!state.notes) state.notes = {};
if(!state.picks) state.picks = {};
var HASPICKS = ITEMS.some(function(it){ return it.picks && it.picks.length; });

var dirty = false;
var readOnly = false;
// View-only controls. Kept out of `state`, so they are never saved with the rulings.
var ui = {filter: 'all', search: ''};

function counts(){
  var c = {};
  KEYS.forEach(function(k){ c[k] = 0; });
  c.pick = 0;
  ITEMS.forEach(function(it){ var d = state.decisions[it.id]; if(d && d in c) c[d]++; });
  return c;
}

function render(){
  var c = counts(), done = 0;
  KEYS.forEach(function(k){ done += c[k]; });
  done += c.pick;
  var query = ui.search.toLowerCase();
  var visible = ITEMS.filter(function(it){
    var choice = state.decisions[it.id] || '';
    var filterMatch = ui.filter === 'all' || (ui.filter === 'unmarked' ? !choice : choice === ui.filter);
    var searchMatch = !query || [it.id, it.edit || '', it.t, it.y, it.n, it.ev || ''].join(' ').toLowerCase().indexOf(query) !== -1;
    return filterMatch && searchMatch;
  });
  var h = '';

  h += '<div class="wrap">';
  h += '<div class="top">';
  h += '<div class="eyebrow">' + EYEBROW + '</div>';
  h += '<h1>' + esc(TITLE) + '</h1>';
  h += '<p class="lede">' + LEDE + '</p>';
  h += '</div>';

  h += '<div class="bar">';
  h += '<span class="prog"><b>' + done + '</b> of ' + ITEMS.length + ' decided</span>';
  h += '<span class="chips">';
  if(c.approve) h += '<span class="chip a">' + c.approve + ' approve</span>';
  if(c.reject)  h += '<span class="chip r">' + c.reject + ' reject</span>';
  if(c.discuss) h += '<span class="chip d">' + c.discuss + ' discuss</span>';
  if(c.pick) h += '<span class="chip a">' + c.pick + ' word picked</span>';
  EXTRA.forEach(function(e){ if(c[e.key]) h += '<span class="chip x">' + c[e.key] + ' ' + esc(e.label.toLowerCase()) + '</span>'; });
  h += '</span>';
  h += '<span class="spacer"></span>';
  h += '<input class="search" id="search" type="search" placeholder="Search" value="' + esc(ui.search) + '">';
  h += '<span class="filters">';
  [['all','All'],['unmarked','Unmarked'],['approve','Approved'],['reject','Rejected'],['discuss','Discuss']].concat(HASPICKS ? [['pick','Picked']] : [], 
    EXTRA.map(function(e){ return [e.key, esc(e.label)]; })).forEach(function(pair){
    h += '<button class="filter" data-filter="' + pair[0] + '" aria-pressed="' + (ui.filter === pair[0]) + '">' + pair[1] + '</button>';
  });
  h += '</span>';
  h += '<button class="bulk" id="allDiscuss">Discuss all ' + ITEMS.length + '</button>';
  h += '<button class="save" id="save"' + (dirty && !readOnly ? '' : ' disabled') + '>' +
       (readOnly ? 'Read only' : 'Save decisions') + '</button>';
  h += '</div>';

  h += '<div class="msg" id="msg" hidden></div>';

  h += '<div class="items">';
  if(!visible.length) h += '<p class="none">No items match this search or filter.</p>';
  visible.forEach(function(it){
    var i = ITEMS.indexOf(it);
    var d = state.decisions[it.id] || '';
    h += '<div class="item"' + (d ? ' data-choice="' + d + '"' + (ISX[d] ? ' data-x="1"' : '') : '') + '>';
    h += '<div class="item-head"><span class="num">' + (i+1 < 10 ? '0' : '') + (i+1) + '</span>';
    if(it.edit){
      h += '<div class="edit"><span class="lbl">Proposed edit</span>' + it.edit + '</div></div>';
      h += '<div class="why"><span class="lbl">Why</span>' + it.t + '</div>';
    } else {
      h += '<h2>' + it.t + '</h2></div>';
    }
    if(it.guess) h += '<div class="guess"><span class="lbl">My guess: ' + esc(LABEL[it.guess] || it.guess) + '</span>' + (it.guessWhy || '') + '</div>';
    h += '<div class="outcomes">';
    h += '<div class="outcome y"><b>If approved</b>' + it.y + '</div>';
    h += '<div class="outcome n"><b>If rejected</b>' + it.n + '</div>';
    EXTRA.forEach(function(e){
      h += '<div class="outcome x"><b>If ' + esc(e.label.toLowerCase()) + '</b>' + ((it.x && it.x[e.key]) || e.outcome) + '</div>';
    });
    h += '</div>';
    if(it.ev) h += '<p class="ev">' + it.ev + '</p>';
    if(it.picks && it.picks.length){
      h += '<div class="picks"><span class="lbl">' + esc(it.picksLabel || 'Or change to') + '</span>';
      it.picks.forEach(function(w){
        var on = d === 'pick' && state.picks[it.id] === w;
        h += '<button class="pk" data-item="' + it.id + '" data-pick="' + esc(w) + '" aria-pressed="' + (on ? 'true' : 'false') + '">' +
             esc(w) + (it.guessPick === w ? '<span class="mine">my guess</span>' : '') + '</button>';
      });
      h += '</div>';
    }
    h += '<div class="choices">';
    KEYS.forEach(function(k){
      h += '<button class="ch" data-item="' + it.id + '" data-choice="' + k + '"' + (ISX[k] ? ' data-x="1"' : '') + ' aria-pressed="' +
           (d === k ? 'true' : 'false') + '">' + LABEL[k] + (it.guess === k ? '<span class="mine">my guess</span>' : '') + '</button>';
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
  var search = document.getElementById('search');
  if(search) search.addEventListener('input', function(){
    ui.search = search.value;
    render();
    var next = document.getElementById('search');
    if(next){ next.focus(); next.setSelectionRange(next.value.length, next.value.length); }
  });
  Array.prototype.forEach.call(document.querySelectorAll('[data-filter]'), function(b){
    b.addEventListener('click', function(){ ui.filter = b.getAttribute('data-filter'); render(); });
  });
  Array.prototype.forEach.call(document.querySelectorAll('.ch'), function(b){
    b.addEventListener('click', function(){
      var id = b.getAttribute('data-item'), k = b.getAttribute('data-choice');
      state.decisions[id] = (state.decisions[id] === k) ? undefined : k;
      if(!state.decisions[id]) delete state.decisions[id];
      delete state.picks[id];
      dirty = true;
      render();
    });
  });

  Array.prototype.forEach.call(document.querySelectorAll('.pk'), function(b){
    b.addEventListener('click', function(){
      var id = b.getAttribute('data-item'), w = b.getAttribute('data-pick');
      if(state.decisions[id] === 'pick' && state.picks[id] === w){ delete state.decisions[id]; delete state.picks[id]; }
      else { state.decisions[id] = 'pick'; state.picks[id] = w; }
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
    ITEMS.forEach(function(it){ state.decisions[it.id] = 'discuss'; delete state.picks[it.id]; });
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
    '<title>' + esc(TITLE) + '<\/title>' +
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


# --save local: the artifact page's source with its save surface swapped for
# the standalone one. Each anchor must match exactly once, so an edit to SRC
# that would silently leave a page half-localised fails the build instead.
LOCAL_SAVE_JS = r"""
function output(){
  var c = counts(), decisions = {}, notes = {}, picks = {}, unmarked = [], tally = {}, decided = 0;
  KEYS.forEach(function(k){ tally[k] = c[k]; decided += c[k]; });
  if(HASPICKS){ tally.pick = c.pick; decided += c.pick; }
  ITEMS.forEach(function(it){
    var choice = state.decisions[it.id];
    if(choice) decisions[it.id] = choice; else unmarked.push(it.id);
    if(choice === 'pick' && state.picks[it.id]) picks[it.id] = state.picks[it.id];
    if(state.notes[it.id]) notes[it.id] = state.notes[it.id];
  });
  var out = {
    schemaVersion: 1,
    reviewId: state.reviewId,
    savedAt: new Date().toISOString().replace('T',' ').slice(0,16) + ' UTC',
    decided: decided,
    tally: tally,
    decisions: decisions,
    notes: notes,
    discuss: ITEMS.filter(function(it){ return decisions[it.id] === 'discuss'; }).map(function(it){ return it.id; }),
    unmarked: unmarked
  };
  if(HASPICKS) out.picks = picks;
  if(EXTRA.length) out.extraVerdicts = EXTRA.map(function(e){ return e.key; });
  return out;
}

function outputText(){ return JSON.stringify(output(), null, 2); }

function copyOutput(){
  var value = outputText();
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(value).then(function(){ flash('Decision output copied.'); }).catch(function(){ fallbackCopy(value); });
  } else fallbackCopy(value);
}

function fallbackCopy(value){
  var area = document.createElement('textarea');
  area.value = value; area.style.position = 'fixed'; area.style.opacity = '0';
  document.body.appendChild(area); area.select();
  try {
    if(document.execCommand('copy')) flash('Decision output copied.');
    else window.prompt('Copy the decision output:', value);
  } catch(e) { window.prompt('Copy the decision output:', value); }
  area.remove();
}

async function doSave(){
  if(HOSTED){
    var button = document.getElementById('save');
    if(button) button.disabled = true;
    try {
      var response = await fetch(new URL('decisions', window.location.href), {
        method:'PUT', headers:{'Content-Type':'application/json'}, body:outputText()
      });
      var result = await response.json().catch(function(){ return {}; });
      if(!response.ok) throw new Error(result.error || ('save failed (' + response.status + ')'));
      flash('Saved on VM: ' + result.saved + '.');
    } catch(e) {
      flash('Could not save on VM: ' + e.message, true);
    } finally {
      if(button) button.disabled = false;
    }
    return;
  }
  var blob = new Blob([outputText()], {type:'application/json'});
  var url = URL.createObjectURL(blob);
  var link = document.createElement('a');
  link.href = url; link.download = OUTPUT_NAME;
  document.body.appendChild(link); link.click(); link.remove();
  URL.revokeObjectURL(url);
  flash('Saved ' + OUTPUT_NAME + '.');
}

render();
"""

LOCAL_EDITS = [
    ("var EXTRA = __EXTRA__;\n",
     "var EXTRA = __EXTRA__;\nvar OUTPUT_NAME = __OUTPUT_NAME__;\n"
     "var HOSTED = document.querySelector('meta[name=\"codex-review-save\"]') !== null;\n"),
    ("""  h += '<button class="save" id="save"' + (dirty && !readOnly ? '' : ' disabled') + '>' +
       (readOnly ? 'Read only' : 'Save decisions') + '</button>';
""",
     """  // Nothing to export until the GM has marked or noted something, so an
  // all-unmarked file can never pass for a review.
  var any = Object.keys(state.decisions).length || Object.keys(state.notes).length;
  h += '<button class="bulk" id="copy"' + (any ? '' : ' disabled') + '>Copy output</button>';
  h += '<button class="save" id="save"' + (any ? '' : ' disabled') + '>' +
       (HOSTED ? 'Save to VM' : 'Save output') + '</button>';
"""),
    ("""      var s = document.getElementById('save');
      if(s && !readOnly) s.disabled = false;
""",
     """      var any = Object.keys(state.decisions).length || Object.keys(state.notes).length;
      ['copy', 'save'].forEach(function(bid){ var b = document.getElementById(bid); if(b) b.disabled = !any; });
"""),
    ("""  h += 'Saving writes your decisions into this page as a new version, so they reach me without anything to copy across. ' +
       (state.savedAt ? 'Last saved <code>' + esc(state.savedAt) + '</code>.' : 'Nothing saved yet.');
""",
     """  h += (HOSTED
       ? 'Save to VM writes <code>' + esc(OUTPUT_NAME) + '</code> in the active Codex workspace. '
       : 'Use Copy output to paste the rulings into chat, or Save output to download <code>' + esc(OUTPUT_NAME) + '</code>. ') +
       'Unmarked findings remain unresolved; they are never treated as rejected.';
"""),
    ("""  var save = document.getElementById('save');
  if(save) save.addEventListener('click', doSave);
""",
     """  var copy = document.getElementById('copy');
  if(copy) copy.addEventListener('click', copyOutput);
  var save = document.getElementById('save');
  if(save) save.addEventListener('click', doSave);
"""),
]

# The standalone page loads no web fonts: it opens from file:// or a private VM.
LOCAL_PAGE_STRIP = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="__FONTS_TEXT__">'
)


# An item that stands for several review items says so. Spliced in only for a page that has such an
# item, so every other page stays byte-identical to what it was before.
GROUP_CSS = (".group{font-family:var(--mono);font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;"
             "color:var(--talk);background:var(--talk-bg);border-radius:2px;padding:4px 9px;align-self:flex-start}\n")
GROUP_ANCHOR = """    h += '<div class="outcomes">';
"""
GROUP_JS = """    var gm = [];
    if(it.group) gm.push(esc(it.group));
    if(it.members && it.members.length > 1) gm.push('Applies to ' + it.members.length + ' items');
    if(gm.length) h += '<div class="group">' + gm.join(' &middot; ') + '</div>';
"""


def has_group(items: list[dict]) -> bool:
    return any(it.get("group") or len(it.get("members") or []) > 1 for it in items)


def localize_src(src: str) -> str:
    """Swap the artifact save surface in `src` for the standalone one."""
    for old, new in LOCAL_EDITS:
        if src.count(old) != 1:
            raise SystemExit(f"internal error: --save local anchor not found exactly once: {old[:60]!r}")
        src = src.replace(old, new)
    cut_from, cut_to = src.find("function renderDoc(){"), src.rfind("render();")
    if cut_from < 0 or cut_to < cut_from:
        raise SystemExit("internal error: --save local cannot find renderDoc()..render()")
    return src[:cut_from].rstrip("\n") + "\n" + LOCAL_SAVE_JS.lstrip("\n")


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
    for i, it in enumerate(items):
        if not isinstance(it, dict) or "picks" not in it:
            continue
        pk = it["picks"]
        if (not isinstance(pk, list) or not 1 <= len(pk) <= 12
                or not all(isinstance(w, str) and w.strip() for w in pk) or len(set(pk)) != len(pk)):
            errs.append(f"items[{i}] ({it.get('id', '?')}) 'picks' must be 1-12 distinct non-empty strings")
        elif it.get("guessPick") and it["guessPick"] not in pk:
            errs.append(f"items[{i}] ({it.get('id', '?')}) guessPick {it['guessPick']!r} is not one of its picks")
    keys = {"approve", "reject", "discuss"} | {e.get("key") for e in (spec.get("extraVerdicts") or []) if isinstance(e, dict)}
    for i, it in enumerate(items):
        if isinstance(it, dict) and it.get("guess") and it["guess"] not in keys:
            errs.append(f"items[{i}] ({it.get('id', '?')}) guess {it['guess']!r} is not a verdict on this page")
    extra = spec.get("extraVerdicts") or []
    if not isinstance(extra, list):
        errs.append("'extraVerdicts' must be a list")
        extra = []
    for j, e in enumerate(extra):
        key = e.get("key") if isinstance(e, dict) else None
        if not key or not re.fullmatch(r"[a-z_]{1,24}", str(key)) or key in ("approve", "reject", "discuss"):
            errs.append(f"extraVerdicts[{j}] needs a 'key' of 1-24 chars [a-z_], not approve/reject/discuss")
        elif not e.get("label") or not e.get("outcome"):
            errs.append(f"extraVerdicts[{j}] ({key}) needs 'label' and 'outcome' - the outcome says what the verdict does")
    if len({e.get("key") for e in extra if isinstance(e, dict)}) != len(extra):
        errs.append("extraVerdicts keys must be unique")
    if spec.get("reviewId") and not REVIEW_ID_RE.fullmatch(str(spec["reviewId"])):
        errs.append("'reviewId' must be 1-128 chars of [A-Za-z0-9_.:@-]")
    if "outputName" in spec and not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", str(spec["outputName"])):
        errs.append("'outputName' must be 1-128 chars of [A-Za-z0-9_.-]")
    pre = spec.get("state") or {}
    if pre.get("decisions") or pre.get("notes") or pre.get("picks") or pre.get("savedAt"):
        errs.append("'state' must not pre-fill decisions, notes or savedAt - a page always "
                    "starts unmarked and unsaved; put a recommendation in the card's guess/guessWhy")
    return errs


EXACT = re.compile(r"(?:<br>\s*)*<b>Exact edits:</b>(?:\s*<br>)*", re.I)


def lift_edits(items: list[dict]) -> list[dict]:
    """Give each card a top-line `edit`. A card that sets none gets the
    'Exact edits:' tail of its `y`, so the before -> after text is what the
    GM reads first, in full size, and `y` keeps only the where/what prose."""
    out = []
    for it in items:
        it = dict(it)
        if not it.get("edit"):
            parts = EXACT.split(it.get("y", ""), maxsplit=1)
            if len(parts) == 2 and parts[1].strip():
                it["edit"] = parts[1].strip()
                it["y"] = parts[0].strip() or "Apply the proposed edit."
        out.append(it)
    return out


_TOKEN = re.compile(r"__([A-Z_]+)__")


def fill(template: str, values: dict[str, str]) -> str:
    """Substitute __NAME__ tokens in one pass. Only names in `values` are touched, and a value is
    inserted verbatim, never re-scanned, so user text that happens to contain a token stays as written."""
    return _TOKEN.sub(lambda m: values[m.group(1)] if m.group(1) in values else m.group(0), template)


def build(spec: dict, save: str = "artifact") -> str:
    if save not in ("artifact", "local"):
        raise ValueError(f"save must be 'artifact' or 'local', not {save!r}")
    spec = dict(spec, items=lift_edits(spec["items"]))
    page, base = PAGE, SRC
    if save == "local":
        base = localize_src(SRC)
        page = PAGE.replace(LOCAL_PAGE_STRIP, "")
        assert page != PAGE, "LOCAL_PAGE_STRIP no longer matches PAGE"
    # The page inserts eyebrow/lede/footer as HTML. The artifact page has always done so; the retired Codex
    # builder escaped them as text (esc() in its page script), so --save local keeps that and no Codex caller
    # changes behaviour.
    chrome = {k: spec.get(k, "") for k in ("eyebrow", "lede", "footer")}
    if save == "local":
        chrome = {k: html.escape(v) for k, v in chrome.items()}
    css = CSS
    if has_group(spec["items"]):
        if base.count(GROUP_ANCHOR) != 1:
            raise SystemExit("internal error: group marker anchor not found exactly once")
        base = base.replace(GROUP_ANCHOR, GROUP_JS + GROUP_ANCHOR)
        css = CSS + GROUP_CSS
    # One pass over each template: a token inside a value (an item's text, a title) is never re-scanned.
    src = fill(base, {
        "FONTS": js(FONTS),
        "TITLE": js(spec["title"]),
        "EYEBROW": js(chrome["eyebrow"]),
        "LEDE": js(chrome["lede"]),
        "FOOTER": js(chrome["footer"]),
        "ITEMS": js(spec["items"]),
        "EXTRA": js(spec.get("extraVerdicts") or []),
        "OUTPUT_NAME": js(spec.get("outputName", "decisions.json")),
    })

    if re.search(r"</script", src, re.I):
        raise SystemExit(
            "refusing to emit: an unescaped '</script' reached the page source. "
            "Check the item text for a literal closing script tag."
        )

    slug = slug_review_id(spec["title"])
    if save == "local":
        # read_decisions --in --items derives the expected id from the title, so
        # the default must be reproducible (no timestamp) for the check to hold.
        review_id = spec.get("reviewId") or slug
    else:
        review_id = spec.get("reviewId") or "{}@{}".format(
            slug[:80], datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    state = {"decisions": {}, "notes": {}, "picks": {}, "savedAt": None, "reviewId": review_id}
    return fill(page, {
        "TITLE_TEXT": html.escape(spec["title"]),
        "FONTS_TEXT": FONTS,
        "CSS": css,
        "STATE": json.dumps(state, ensure_ascii=False).replace("<", "\\u003c"),
        "SRC": src,
    })


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="items JSON (see CONTRACT.md)")
    ap.add_argument("--out", required=True, type=Path, help="HTML page to write")
    ap.add_argument("--save", choices=("artifact", "local"), default="artifact",
                    help="save surface: artifact republishes the page (default); local is the "
                         "standalone Copy output / Save output / Save to VM page")
    args = ap.parse_args()

    spec = json.loads(args.inp.read_text(encoding="utf-8"))
    errs = validate(spec)
    if errs:
        for e in errs:
            print(f"error: {e}", file=sys.stderr)
        return 1

    html = build(spec, args.save)
    args.out.write_text(html, encoding="utf-8")
    kb = len(html.encode("utf-8")) / 1024
    print(f"wrote {args.out}  ({len(spec['items'])} items, {kb:.1f} KB)")
    if kb > 15000:
        print("warning: page is near the 16MB artifact limit - split the review", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
