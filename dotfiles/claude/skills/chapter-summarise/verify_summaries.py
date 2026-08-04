#!/usr/bin/env python3
"""Verify generated session summaries against their source chapters.

Deterministic. No model calls. Never trust a generator's self-report — this is
the gate. Pairs each summary to its chapter by chapter index.

Checks, per chapter:
  gate    ## Scenes and ## NPCs present (campaignlib.lineage._summary_is_structured)
  MM      ## Memorable Moments absent (the fabrication magnet)
  ratio   summary words / chapter words; must be < 1.0
  FAB     attributed-dialogue quotes with no trace in the chapter
  novel   proper nouns in the summary absent from the chapter
  scn     ### scene count, and chunk count once the ## Scenes wrapper is stripped
  order   scene order monotonic against position in the chapter

Exit status is non-zero if any chapter fails a hard check (missing file, gate,
ratio >= 1.0, or a fabricated quote), so this can gate a loop.

Usage:
  verify_summaries.py --campaign-dir DIR [--summaries-dir summaries/haiku]
                      [--chapters-glob 'docs/chapters/chapter_*.md']
                      [--repo /home/kroussos/src/CampaignGenerator]
"""
import argparse
import difflib
import re
import sys
import unicodedata
from pathlib import Path

PAIR = re.compile(r'“([^“”\n]+)”|"([^"\n]+)"')


def base(s):
    s = unicodedata.normalize('NFKC', s)
    for a, b in (('’', "'"), ('‘', "'"), ('“', '"'), ('”', '"'),
                 ('—', ' '), ('–', ' '), ('…', '...')):
        s = s.replace(a, b)
    return re.sub(r'\s+', ' ', s).strip().lower()


def loose(s):
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', base(s))).strip()


def is_dialogue(q):
    return (' ' in q and len(q) >= 12
            and re.search(r'[.!?]["\']?$', q.strip())
            and q.strip()[0].isupper())


def scenes_section(t):
    m = re.search(r'(?ms)^##\s+Scenes\b.*?(?=^##\s+(?!#)|\Z)', t)
    return m.group(0) if m else ''


def name_tokens(t, midonly):
    """Capitalised tokens. midonly drops sentence-initial words, which are
    capitalised by grammar rather than because they are names."""
    t = re.sub(r'^#.*$', '', t, flags=re.M)
    out = set()
    for sent in re.split(r'(?<=[.!?:\n])\s+', t):
        ws = re.findall(r"\b[A-Z][a-zA-Z'’-]{2,}\b", sent)
        if midonly and ws:
            ws = ws[1:]
        for w in ws:
            out.add(re.sub(r"['’]s$", '', w).lower())
    return out


def anchor(scene_text, chap_loose):
    """Best character position in the chapter for this scene, via its longest
    traceable string. None when the scene is paraphrased past recognition —
    which makes its ordering UNVERIFIED, not verified."""
    qs = sorted((q for a, b in PAIR.findall(scene_text) for q in [a or b]),
                key=len, reverse=True)
    for q in qs[:6]:
        i = chap_loose.find(loose(q))
        if i >= 0:
            return i
    bullets = sorted((l.strip('- ').strip() for l in scene_text.splitlines()
                      if l.strip().startswith('- ')), key=len, reverse=True)
    for b in bullets[:4]:
        w = loose(b).split()
        for n in (14, 10, 7):
            if len(w) < n:
                continue
            i = chap_loose.find(' '.join(w[:n]))
            if i >= 0:
                return i
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--campaign-dir', required=True)
    ap.add_argument('--summaries-dir', default='summaries/haiku')
    ap.add_argument('--chapters-glob', default='docs/chapters/chapter_*.md')
    ap.add_argument('--repo', default='/home/kroussos/src/CampaignGenerator',
                    help='CampaignGenerator checkout, for campaignlib.textproc')
    args = ap.parse_args()

    sys.path.insert(0, args.repo)
    try:
        from campaignlib.textproc import chunk_by_scenes
    except ImportError:
        chunk_by_scenes = None
        print(f"warn: campaignlib not importable from {args.repo}; "
              f"skipping the h3-chunk check", file=sys.stderr)

    root = Path(args.campaign_dir)
    chapters = {}
    for f in sorted(root.glob(args.chapters_glob)):
        m = re.search(r'chapter_(\d+)', f.name)
        if m:
            chapters.setdefault(int(m.group(1)), f)

    summaries, dupes = {}, {}
    for d in sorted((root / args.summaries_dir).glob('*/')):
        m = re.match(r'0*(\d+)', d.name)
        p = d / 'session-summary.md'
        if m and p.exists():
            dupes.setdefault(int(m.group(1)), []).append(p)
            summaries[int(m.group(1))] = p

    if not summaries:
        print(f"no summaries under {root / args.summaries_dir}", file=sys.stderr)
        return 2

    # Two dirs for one chapter index means a stale leftover (usually a
    # pre-spelling-fix slug). Silently picking one would verify the wrong file
    # and report a clean run — refuse instead.
    collisions = {k: v for k, v in dupes.items() if len(v) > 1}
    if collisions:
        print("DUPLICATE SUMMARY DIRECTORIES — resolve before verifying:", file=sys.stderr)
        for k, v in sorted(collisions.items()):
            print(f"  chapter {k}:", file=sys.stderr)
            for p in v:
                print(f"    {p.parent.relative_to(root)}", file=sys.stderr)
        return 2

    rows, fabs, novels = [], [], []
    for ch in sorted(summaries):
        out = summaries[ch]
        if ch not in chapters:
            rows.append(dict(ch=ch, err=f'NO SOURCE CHAPTER for index {ch}'))
            continue
        ctext = chapters[ch].read_text(errors='replace')
        cl, cw = loose(ctext), len(ctext.split())
        t = out.read_text(errors='replace')
        sec = scenes_section(t)

        qs, seen = [], set()
        for a, b in PAIR.findall(sec):
            q = a or b
            if base(q) not in seen:
                seen.add(base(q))
                qs.append(q)
        dlg = [q for q in qs if is_dialogue(q)]
        bad = []
        for q in dlg:
            lq = loose(q)
            if lq in cl:
                continue
            best = max((difflib.SequenceMatcher(None, lq, cl[j:j + len(lq) + 20]).ratio()
                        for j in range(0, max(1, len(cl) - len(lq)), 60)), default=0)
            if best < 0.70:
                bad.append((q, round(best, 2)))
        fabs += [(ch, q, s) for q, s in bad]

        cset = (name_tokens(ctext, False)
                | {w.lower() for w in re.findall(r"\b[a-zA-Z'’-]{3,}\b", ctext)})
        nov = [n for n in sorted(name_tokens(t, True) - cset)
               if "'" not in n and len(n) > 3]
        novels += [(ch, n) for n in nov]

        titles = re.findall(r'(?m)^###\s+(.+)$', sec)
        nchunk, conv = 0, 'n/a'
        if chunk_by_scenes:
            body = re.sub(r'(?m)^##\s+Scenes\b.*\n', '', sec)
            r = chunk_by_scenes(body, 6000)
            nchunk, conv = (len(r[0]), r[1]) if r else (0, 'none')

        parts = re.split(r'(?m)^(?=###\s)', sec)[1:]
        pos = [anchor(p, cl) for p in parts]
        known = [p for p in pos if p is not None]

        rows.append(dict(
            ch=ch, w=len(t.split()), cw=cw, ratio=len(t.split()) / cw,
            gate=bool(re.search(r'(?m)^##\s+Scenes\b', t)) and bool(re.search(r'(?m)^##\s+NPCs\b', t)),
            mm=bool(re.search(r'(?m)^##\s+Memorable', t)),
            dlg=len(dlg), bad=len(bad), nov=len(nov),
            scenes=len(titles), chunks=nchunk, conv=conv,
            nanch=len(known), ntot=len(pos), mono=(known == sorted(known))))

    print(f"{'ch':>3} {'sum w':>6} {'ratio':>6} {'gate':>5} {'MM':>3} {'dlg':>4} "
          f"{'FAB':>4} {'novel':>5} {'scn':>4} {'chunks':>8} {'anchor':>7} {'order':>7}")
    hard_fail = []
    for r in rows:
        if r.get('err'):
            print(f"{r['ch']:>3}  {r['err']}")
            hard_fail.append(r['ch'])
            continue
        flags = ''
        if r['ratio'] >= 1.0:
            flags += '  NOT-SHORTER'
        if not r['gate']:
            flags += '  GATE-FAIL'
        if r['bad']:
            flags += '  FABRICATED'
        if flags:
            hard_fail.append(r['ch'])
        order = 'True' if r['mono'] else 'FALSE'
        if r['nanch'] == 0:
            order = 'unverif'
        print(f"{r['ch']:>3} {r['w']:>6} {r['ratio']:>6.2f} {str(r['gate']):>5} "
              f"{('YES' if r['mm'] else '-'):>3} {r['dlg']:>4} {r['bad']:>4} {r['nov']:>5} "
              f"{r['scenes']:>4} {r['chunks']:>3}/{r['conv']:<4} "
              f"{r['nanch']}/{r['ntot']:>5} {order:>7}{flags}")

    ok = [r for r in rows if not r.get('err')]
    n = len(ok)
    unver = [r['ch'] for r in ok if r['nanch'] == 0]
    print(f"\n{'=' * 88}")
    print(f"summaries found      : {n}")
    print(f"gate pass            : {sum(r['gate'] for r in ok)}/{n}")
    print(f"no Memorable Moments : {sum(not r['mm'] for r in ok)}/{n}")
    print(f"shorter than source  : {sum(r['ratio'] < 1.0 for r in ok)}/{n}")
    print(f"dialogue quotes      : {sum(r['dlg'] for r in ok)} total, "
          f"{sum(r['bad'] for r in ok)} with NO TRACE in chapter")
    print(f"novel proper nouns   : {sum(r['nov'] for r in ok)}")
    print(f"scenes               : {sum(r['scenes'] for r in ok)}; "
          f"h3-chunked: {sum(r['chunks'] for r in ok)}")
    print(f"order monotonic      : {sum(r['mono'] for r in ok)}/{n}"
          + (f"   (UNVERIFIED — no anchor — for ch {unver})" if unver else ""))
    if fabs:
        print("\n--- QUOTES WITH NO TRACE IN THE CHAPTER ---")
        print("    (check each by hand: a chapter typo the model silently fixed,")
        print("     or two real fragments stitched into one, both land here)")
        for ch, q, s in fabs:
            print(f"  ch{ch:<3} [{s}] \"{q[:92]}\"")
    if novels:
        print("\n--- NOVEL PROPER NOUNS (candidate misspellings / module bleed) ---")
        print("    (ordinary sentence-initial words leak in here; skim, don't trust)")
        for ch, nm in novels:
            print(f"  ch{ch:<3} {nm}")
    if hard_fail:
        print(f"\nHARD FAILURES in chapters: {sorted(set(hard_fail))}")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
