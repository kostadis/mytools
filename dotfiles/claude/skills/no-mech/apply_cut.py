#!/usr/bin/env python3
"""Deterministic apply for /no-mech: remove table-mechanical quotes from a
voice-smoothed scene extraction and leave an audit note in their place.

Renders exactly what was confirmed in the human checkpoint. No reinterpretation
at apply time, no LLM, no network.

HARD INVARIANT, enforced below and not overridable by a flag: this writes ONLY
to a *_smoothed/ scene file. The verbatim record in scene_extractions/ is the
pipeline's permanent record of what was said and is never touched here.
"""
import argparse, json, re, sys
from pathlib import Path

QUOTE = re.compile(r'^>\s*"')
LABEL = re.compile(r'^\*\*\[?([^*\]]+?)\]?\*\*')
BARE  = re.compile(r'^>\s*"(yes|no|yeah|yep|okay|ok|right|sure|correct|got it)[.!?]*"\s*$', re.I)


def guard(path: Path):
    parts = [p.lower() for p in path.parts]
    if not any(p.endswith("_smoothed") for p in parts):
        sys.exit(f"REFUSED: {path} is not inside a *_smoothed/ directory.\n"
                 "  /no-mech only ever edits the derived smoothed layer. The verbatim\n"
                 "  scene_extractions/ record must remain untouched.")


def cut_all(text, note):
    i = text.index("## Voiced moments")
    return text[:i] + "## Voiced moments\n\n" + note.rstrip() + "\n", None


def cut_spans(text, cut_lines, note):
    head, body = text.split("## Voiced moments", 1)
    offset = head.count("\n") + 1
    lines = body.split("\n")
    cut = set(cut_lines)

    # Every requested line must actually BE a quote line. A stale line number
    # (the file drifted since the scan) silently deletes prose otherwise.
    bad = [n for n in sorted(cut)
           if not (0 <= n - offset < len(lines) and QUOTE.match(lines[n - offset]))]
    if bad:
        sys.exit(f"REFUSED: these --cut lines are not quote lines: {bad}\n"
                 "  Re-run scan_quotes.py; the file has drifted since the scan.")

    kept, warnings, prev_kept_quote, prev_cut = [], [], None, False
    for idx, line in enumerate(lines):
        n = idx + offset
        if n in cut:
            prev_cut = True
            continue
        if QUOTE.match(line):
            # A bare acknowledgement whose question was just removed is now an
            # orphan: it answers nothing. Real case, obelisk ch10 scene 08 --
            # a lone "Yes." left behind after "Roll again - the Perception?"
            if prev_cut and BARE.match(line):
                warnings.append(f"  line {n}: orphaned acknowledgement {line.strip()} "
                                f"-- its preceding quote was cut")
            prev_kept_quote, prev_cut = n, False
        elif line.strip() and not LABEL.match(line):
            # A speaker label between a cut quote and the next one does NOT
            # break the adjacency -- the orphan sits under its own **GM**
            # header. Resetting here missed the real ch10 scene 08 case.
            prev_cut = False
        kept.append(line)

    # Drop speaker labels that no longer introduce anything.
    out, i = [], 0
    while i < len(kept):
        line = kept[i]
        if LABEL.match(line):
            j = i + 1
            while j < len(kept) and not kept[j].strip():
                j += 1
            if j >= len(kept) or not QUOTE.match(kept[j]):
                i += 1
                continue          # empty label block; drop it
        out.append(line); i += 1

    body_out = "\n".join(out)
    body_out = re.sub(r"\n{3,}", "\n\n", body_out)
    return head + "## Voiced moments\n\n" + note.rstrip() + "\n" + body_out, warnings


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", required=True, help="the *_smoothed/ scene .md to edit")
    ap.add_argument("--mode", choices=["all", "spans"], required=True,
                    help="'all' cuts the whole Voiced moments section; "
                         "'spans' cuts only the --cut lines")
    ap.add_argument("--cut", type=int, nargs="*", default=[], metavar="LINE",
                    help="line numbers to cut (mode=spans), from scan_quotes.py")
    ap.add_argument("--note", required=True,
                    help="the audit note (italic markdown) recording what was cut and why")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = Path(a.file); guard(path)
    text = path.read_text(encoding="utf-8")
    if "## Voiced moments" not in text:
        sys.exit(f"REFUSED: {path} has no '## Voiced moments' section.")

    before = text.split("## Voiced moments", 1)[1].count('> "')
    new, warnings = (cut_all(text, a.note) if a.mode == "all"
                     else cut_spans(text, a.cut, a.note))
    after = new.split("## Voiced moments", 1)[1].count('> "')

    print(f"{path.name}: {before} quotes -> {after} ({before - after} cut)")
    for w in warnings or []:
        print("WARNING" + w)
    if warnings:
        print("  Orphans are a NEW proposal, not a free fix. Take them back to the\n"
              "  GM as their own decision rather than folding them in silently.")
    if a.dry_run:
        print("(dry run; nothing written)"); return
    path.write_text(new, encoding="utf-8")
    print(f"wrote: {path}")


if __name__ == "__main__":
    main()
