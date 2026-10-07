#!/usr/bin/env python3
"""Digest a large corpus of dossier files with tagged per-chapter notes.

Proven on 174 npc_*.md files (7.3 MB) -> 10k-word cited digest in seconds.
Expected input format per file:
  frontmatter: name:, n_facts:, chapters:
  body fields: **Current Status:** / **Allegiance/Faction:** / **Current Location:**
               (capitalization VARIES -- always match case-insensitively)
  notes:      '## Per-Chapter Notes' with lines '- [chNN] (EVENT) text — subject: ...'

Adjust SRC/OUT/labels for the corpus at hand.
"""
import re, os, glob, json, subprocess

SRC = '/home/kostadis/oota-augment/npc_*.md'
OUT = '/tmp/digest.md'
MIN_FACTS = 6          # roster significance threshold
PER_CH = 4             # event bullets per chapter
CLIP_W = 38            # max words per event line

def clean(s): return re.sub(r'\s+', ' ', s).strip().rstrip('\\').strip()

def clip(t, n=CLIP_W):
    ws = t.split()
    if len(ws) <= n: return t
    s = ' '.join(ws[:n]); cut = max(s.rfind('. '), s.rfind('; '))
    return s[:cut+1] if cut > n*0.7 else s + '…'

def toks(t): return set(re.findall(r'[a-z]{3,}', t.lower()))

def field(body, label):
    m = re.search(r'\*\*' + label + r':?\*\*:?\s*(.+)', body, re.I)
    return clean(m.group(1)) if m else ''

npcs, events, seen = {}, {}, set()
for f in sorted(glob.glob(SRC)):
    txt = open(f).read()
    m = re.search(r'name:\s*(.+)', txt)
    name = m.group(1).strip() if m else os.path.basename(f)
    nf = int((re.search(r'n_facts:\s*(\d+)', txt) or [0, 0])[1] or 0) if re.search(r'n_facts:\s*(\d+)', txt) else 0
    ch = re.search(r'chapters:\s*(.+)', txt)
    body = txt.split('## Per-Chapter Notes')[0]
    npcs[name] = {'n_facts': nf, 'chapters': ch.group(1).strip() if ch else '', 'body': body}
    for ln in txt.splitlines():
        mm = re.match(r'- \[ch(\d+)\] \(EVENT\) (.+?)(?:\s+—\s+subject:.*)?$', ln.strip())
        if mm:
            c, t = int(mm.group(1)), mm.group(2).strip()
            k = (c, re.sub(r'\W+', '', t.lower())[:90])   # exact dedupe
            if k in seen: continue
            seen.add(k); events.setdefault(c, []).append(t)

# fuzzy dedupe within chapter
for c in events:
    out = []
    for t in events[c]:
        tt = toks(t)
        if not any(len(tt & toks(u)) / max(1, min(len(tt), len(toks(u)))) > 0.75 for u in out):
            out.append(t)
    events[c] = out

# rank: named-entity mentions + length bonus
names = [k.split()[0] for k, v in npcs.items() if v['n_facts'] >= 15]
def score(t):
    return sum(1 for n in names if n in t) + min(len(t), 260)/260 - (1 if len(t) < 45 else 0)
sel = {c: [clip(t) for t in sorted(events[c], key=score, reverse=True)[:PER_CH]] for c in events}

def chtag(ch):
    m = re.findall(r'\d+', ch)
    if not m: return ''
    return f"[ch{int(m[0]):02d}]" if len(m) == 1 else f"[ch{int(m[0]):02d}–ch{int(m[-1]):02d}]"

def firstbullets(body, n):
    m = re.search(r'\*\*Definin[^\n]*\n((?:- .*\n?)+)', body, re.I)
    return [clip(clean(b[2:]), 40) for b in (m.group(1).splitlines() if m else []) if b.strip().startswith('- ')][:n]

roster = []
for nf, k in sorted(((v['n_facts'], k) for k, v in npcs.items() if v['n_facts'] >= MIN_FACTS), reverse=True):
    v = npcs[k]; b = v['body']
    parts = []
    st = field(b, 'Current [Ss]tatus'); al = field(b, 'Allegiance/[Ff]action'); lo = field(b, 'Current [Ll]ocation')
    if st: parts.append(clip(st, 25))
    if al: parts.append('Allegiance: ' + clip(al, 22))
    if lo: parts.append('Last seen: ' + clip(lo, 25))
    parts += firstbullets(b, 2 if nf >= 30 else 1)
    if not parts: parts = [clip(clean(re.sub(r'[#*]', '', b.split('---')[-1])), 35)]
    roster.append(f"**{k}** {chtag(v['chapters'])} — " + ' '.join(p.rstrip('.;') + '.' for p in parts if p))

with open(OUT, 'w') as o:
    o.write('# Digest\n\n## Part 1 — Chronological Event List\n\n')
    for c in sorted(sel):
        o.write(f'### Chapter {c}\n\n')
        for t in sel[c]: o.write(f'- [ch{c:02d}] {t}\n')
        o.write('\n')
    o.write('## Part 2 — Roster\n\n')
    for l in roster: o.write(f'- {l}\n')

print(subprocess.run(['wc', '-w', OUT], capture_output=True, text=True).stdout)
# empty-entry sanity check (catches case-sensitive field misses)
print('empty roster entries:', sum(1 for l in roster if l.endswith('— ')))
