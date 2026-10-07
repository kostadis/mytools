#!/usr/bin/env python3
"""Move a '## <SECTION>' block to sit immediately before '## <TARGET>' in every
.md file of a directory. Lossless: every non-blank line preserved verbatim;
only the section block's position changes. Idempotent via an already-ordered
guard. Verified on 53 Phandalin summary files (move MM before NPCs).

Usage:
  SECTION='Memorable Moments' TARGET='NPCs' ANCHOR='Scenes' python3 move_markdown_section.py [--apply]

Dry-run (no --apply) prints moved/skipped counts and per-file VERIFY FAILs
without writing. After applying, re-run dry-run: must report moved=0.
"""
import sys, os, re
from collections import Counter

DIR = os.environ.get("DIR", "/home/kostadis/phandalin/Phandalin/docs/summaries")
SECTION = os.environ.get("SECTION", "Memorable Moments")
TARGET = os.environ.get("TARGET", "NPCs")        # insert block right before this
ANCHOR = os.environ.get("ANCHOR", "Scenes")      # block must end up AFTER this

def hidx(lines, name):
    return [i for i, l in enumerate(lines) if re.match(rf"^## {re.escape(name)}\s*$", l)]

def process(path, apply=False):
    fn = os.path.basename(path)
    text = open(path, encoding="utf-8").read()
    lines = text.split("\n")
    heads = [i for i, l in enumerate(lines) if re.match(r"^## ", l)]
    sec = hidx(lines, SECTION)
    tgt = hidx(lines, TARGET)
    anc = hidx(lines, ANCHOR)
    if not sec or not tgt:
        return {"file": fn, "skip": True}
    sec, tgt = sec[0], tgt[0]
    if anc and anc[0] < sec < tgt:
        return {"file": fn, "skip": True, "flags": ["already ordered"]}
    nxt = [i for i in heads if i > sec]
    sec_end = nxt[0] if nxt else len(lines)
    block = lines[sec:sec_end]
    before = lines[:sec]
    after = lines[sec_end:]
    while before and before[-1].strip() == "":
        before.pop()
    before.append("")
    joined = before + after
    ti = next(i for i, l in enumerate(joined) if re.match(rf"^## {re.escape(TARGET)}\s*$", l))
    out = joined[:ti] + block + joined[ti:]
    new_text = re.sub(r"\n{3,}", "\n\n", "\n".join(out))
    report = {"file": fn, "moved": True}
    if Counter(l for l in lines if l.strip()) != Counter(l for l in new_text.split("\n") if l.strip()):
        report["verify"] = "FAIL"
        print(f"VERIFY FAIL {path}", file=sys.stderr)
        return report
    report["verify"] = "OK"
    if apply:
        open(path, "w", encoding="utf-8").write(new_text)
    return report

if __name__ == "__main__":
    apply = "--apply" in sys.argv
    files = sorted(os.path.join(DIR, f) for f in os.listdir(DIR) if f.endswith(".md"))
    moved = skipped = 0
    for f in files:
        r = process(f, apply)
        if r.get("skip"):
            skipped += 1
        else:
            moved += 1
            if r["verify"] != "OK":
                print("FAIL", r)
    print(f"moved={moved} skipped={skipped} apply={apply}")
