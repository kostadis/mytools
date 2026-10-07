#!/usr/bin/env python3
"""Fold a chapter->date map into per-entity scan files as non-destructive anchors.
For every '## Chapter N:' header lacking a trailing '<!-- DATE: ... -->' line,
insert one immediately after it.
Usage:
  python inject_dates.py <entity_scan_dir> <chapter_dates.json>
chapter_dates.json shape: {"1": ["undated", null], "2": ["01-03-Tarsakh 1495 -> 01-04-Tarsakh 1495", "start"], ...}
The injection uses element[0] as the date string.
"""
import os, re, json, argparse

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('scan_dir')
    ap.add_argument('dates_json')
    a = ap.parse_args()
    cmap = {int(k): v[0] for k, v in json.load(open(a.dates_json)).items()}
    hdr = re.compile(r'^(## Chapter (\d+):.*)$')

    mod = anc = 0
    for fn in sorted(f for f in os.listdir(a.scan_dir) if f.endswith('.md')):
        p = os.path.join(a.scan_dir, fn)
        lines = open(p, encoding='utf-8', errors='replace').read().split('\n')
        out, changed = [], False
        i = 0
        while i < len(lines):
            ln = lines[i]
            m = hdr.match(ln)
            if m and i + 1 < len(lines) and '<!-- DATE:' not in lines[i+1]:
                ch = int(m.group(2))
                d = cmap.get(ch)
                out.append(ln)
                if d is not None:
                    out.append(f"<!-- DATE: {d} -->")
                    anc += 1
                    changed = True
                i += 1
            else:
                out.append(ln)
                i += 1
        if changed:
            open(p, 'w', encoding='utf-8').write('\n'.join(out))
            mod += 1
    print(f"Modified {mod} files, added {anc} date anchors.")

if __name__ == '__main__':
    main()
