#!/usr/bin/env python3
"""Merge per-chapter entity .md files into one chapter-ordered file per entity.

Usage: merge_entity_files.py <parts_dir> <output_root>
  parts_dir   : directory containing chNN/ subdirs (one <Entity>.md per file)
  output_root : where to write the merged <Entity>.md files

Each chNN/<Entity>.md looks like:
  # <Entity>
  ## Chapter N: <title>
  - bullets...
We concatenate sections across chapters in numeric chapter order.
"""
import os, re, sys

def chnum(d):
    m = re.fullmatch(r'ch(\d+)', d)
    return int(m.group(1)) if m else 10**9

def main():
    parts_dir, out_root = sys.argv[1], sys.argv[2]
    os.makedirs(out_root, exist_ok=True)
    merged = {}
    for d in sorted(os.listdir(parts_dir)):
        dp = os.path.join(parts_dir, d)
        if not os.path.isdir(dp):
            continue
        for f in sorted(os.listdir(dp)):
            text = open(os.path.join(dp, f), encoding='utf-8', errors='replace').read()
            m = re.match(r'#\s*(.+?)\s*\n', text)
            ent = (m.group(1) if m else f[:-3]).strip()
            secs = re.split(r'\n(?=## Chapter \d+)', text)[1:]
            merged.setdefault(ent, [])
            for s in secs:
                if not s.strip():
                    continue
                mm = re.match(r'## Chapter (\d+)', s)
                n = int(mm.group(1)) if mm else 10**9
                merged[ent].append((n, s.rstrip()))

    count = 0
    for ent, blocks in merged.items():
        seen = set(); plist = []
        for n, b in sorted(blocks):
            sig = b[:80]
            if sig in seen:
                continue
            seen.add(sig); plist.append(b)
        content = f"# {ent}\n\n" + '\n\n'.join(plist) + '\n'
        open(os.path.join(out_root, ent.replace('/', '-') + '.md'), 'w').write(content)
        count += 1
    print(f"wrote {count} entity files to {out_root}")

if __name__ == '__main__':
    main()
