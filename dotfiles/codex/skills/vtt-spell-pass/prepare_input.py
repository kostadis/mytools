#!/usr/bin/env python3
"""Normalise a session transcript into something the spell pass can scan.

The scanner (find_unknowns.py) assumes an Otter/Zoom WebVTT. Real sessions
also arrive as markdown exports from voice-detection tools, as plain text, and
sometimes with the whole session recorded twice in one file. This script
detects which of those you have, reports it, and emits the two derived files
the rest of the pass wants:

  --scan-copy      speaker labels and cue metadata stripped, for find_unknowns
  --dedup-output   the input in its ORIGINAL format with a duplicated body
                   removed (only written when duplication is detected)

Why a scan copy is needed
-------------------------
find_unknowns.py strips ``Name:`` / ``Name (Player):`` labels at line start.
It does NOT strip markdown-bold labels (``**dave:**``), so with a markdown
export the label text and its capitalisation leak into the proper-noun scan.
Stripping them up front keeps the candidate list honest.

Why duplication matters
-----------------------
A doubled body does not break replacement (both copies get fixed) but it
doubles every occurrence count, which silently inflates the evidence behind
every question you put to the GM -- a "26x" that is really 13. Downstream it
double-counts every quote. Detect it before Phase 1, not after.

Usage
-----
    prepare_input.py --input <transcript> --json
    prepare_input.py --input <transcript> --scan-copy "$SCRATCH/scan.txt"
    prepare_input.py --input <transcript> --dedup-output <clean>.dedup.md
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

# ``**dave:**`` / ``**Thorin (Joe):**`` -- markdown-bold speaker labels
MD_LABEL_RE = re.compile(r"^\*\*([^*:]{1,40}):\*\*\s*", re.M)
# ``Thorin (Joe):`` / ``Kostadis:`` -- the form find_unknowns already handles
PLAIN_LABEL_RE = re.compile(
    r"^\s*(?:[A-Z][\w'\-]+(?:\s+[A-Z][\w'\-]+){0,3}\s*\([^)]+\)"
    r"|[A-Z][\w'\-]+(?:\s+[A-Z][\w'\-]+){0,2})\s*:\s*", re.M)
TIMESTAMP_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d+\s*-->\s*\d{2}:\d{2}:\d{2}\.\d+\s*$")
CUE_NUM_RE = re.compile(r"^\d+\s*$")
HEADING_RE = re.compile(r"^#")


def detect_format(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            if line.strip().upper().startswith("WEBVTT"):
                return "webvtt"
            break
    if MD_LABEL_RE.search(text):
        return "labelled_markdown"
    if PLAIN_LABEL_RE.search(text):
        return "labelled_text"
    return "plain"


def speakers(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for m in MD_LABEL_RE.finditer(text):
        name = m.group(1).strip()
        counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def dialogue_lines(text: str, fmt: str) -> list[str]:
    """Content lines only -- no cue metadata, no headings, no blanks."""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or HEADING_RE.match(s):
            continue
        if fmt == "webvtt":
            if s.upper() == "WEBVTT" or TIMESTAMP_RE.match(s) or CUE_NUM_RE.match(s):
                continue
        out.append(s)
    return out


def drop_speakers(text: str, exclude: set[str]) -> tuple[str, int]:
    """Remove whole utterances belonging to excluded speakers.

    Not everyone captured by the recording is at the table. A partner, a child,
    or a housemate wandering through contributes real speech that is not
    campaign content, and every proper noun in it ("Ben didn't find this
    funny") becomes a candidate misspelling the GM then has to dismiss by hand.
    Dropping these BEFORE the scan is the difference between a false positive
    the GM must rule on and one they never see.

    Only the scan copy is filtered. The delivered transcript keeps every line:
    what is noise for name-gathering is still a record of who was in the room,
    and that is the GM's call to cut, not ours.
    """
    if not exclude:
        return text, 0
    lower = {e.lower() for e in exclude}
    out, dropped, skipping = [], 0, False
    for line in text.splitlines():
        m = MD_LABEL_RE.match(line)
        if m:
            skipping = m.group(1).strip().lower() in lower
            if skipping:
                dropped += 1
        elif not line.strip():
            skipping = False
        if not skipping:
            out.append(line)
    return "\n".join(out) + "\n", dropped


def make_scan_copy(text: str, fmt: str, exclude: set[str] | None = None) -> str:
    """Strip speaker labels and headings so only spoken words remain.

    Cue metadata is left for find_unknowns.py, which already skips it.
    """
    if exclude and fmt == "labelled_markdown":
        text, _ = drop_speakers(text, exclude)
    if fmt == "labelled_markdown":
        text = MD_LABEL_RE.sub("", text)
    text = re.sub(r"^#.*$", "", text, flags=re.M)
    return text


def find_duplication(lines: list[str]) -> dict | None:
    """Detect a body recorded twice.

    Anchors on the second occurrence of the first dialogue line, then aligns
    the two halves with difflib. A naive midpoint split is not enough: a single
    inserted or split utterance shifts everything after it and makes an
    otherwise-clean duplicate look ~60% similar.
    """
    if len(lines) < 20:
        return None
    first = lines[0]
    repeats = [i for i, l in enumerate(lines[1:], 1) if l == first]
    for start in repeats:
        a, b = lines[:start], lines[start:]
        if min(len(a), len(b)) < len(lines) * 0.3:
            continue
        ratio = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
        if ratio >= 0.90:
            sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
            identical = sum(i2 - i1 for t, i1, i2, _, _ in sm.get_opcodes() if t == "equal")
            return {
                "duplicated": True,
                "copy2_starts_at_dialogue_line": start,
                "copy1_lines": len(a),
                "copy2_lines": len(b),
                "alignment_ratio": round(ratio, 4),
                "identical_lines": identical,
            }
    return None


def dedup(text: str, lines: list[str], dup: dict) -> str:
    """Drop copy 2, preserving the original file's formatting and header."""
    target = dup["copy2_starts_at_dialogue_line"]
    seen = 0
    raw = text.splitlines()
    cut = None
    for i, line in enumerate(raw):
        s = line.strip()
        if not s or HEADING_RE.match(s):
            continue
        if TIMESTAMP_RE.match(s) or CUE_NUM_RE.match(s) or s.upper() == "WEBVTT":
            continue
        if seen == target:
            cut = i
            break
        seen += 1
    if cut is None:
        raise RuntimeError("could not map dialogue index back to a file line")
    kept = raw[:cut]
    while kept and not kept[-1].strip():
        kept.pop()
    return "\n".join(kept) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--scan-copy", type=Path, help="Write label-stripped copy here")
    ap.add_argument("--dedup-output", type=Path,
                    help="Write de-duplicated original-format file here (if duplicated)")
    ap.add_argument("--filtered-output", type=Path,
                    help="Write the transcript with --exclude-speaker utterances REMOVED. "
                         "Unlike --scan-copy this keeps speaker labels and format, so it "
                         "can feed apply_replacements.py and become the deliverable. Use "
                         "only when the GM has said those lines should not ship.")
    ap.add_argument("--exclude-speaker", nargs="*", default=[],
                    help="Speaker labels whose utterances are not campaign content "
                         "(people in the room but not at the table). Filtered from "
                         "the scan copy only; the original is never modified.")
    ap.add_argument("--json", action="store_true", help="Machine-readable report")
    args = ap.parse_args()

    text = args.input.read_text(encoding="utf-8")
    fmt = detect_format(text)
    lines = dialogue_lines(text, fmt)
    dup = find_duplication(lines)
    exclude = set(args.exclude_speaker)

    report = {
        "input": str(args.input),
        "format": fmt,
        "dialogue_lines": len(lines),
        "dialogue_words": sum(len(l.split()) for l in lines),
        "speakers": speakers(text) if fmt == "labelled_markdown" else {},
        "duplication": dup or {"duplicated": False},
    }

    if exclude:
        _, n = drop_speakers(text, exclude)
        report["excluded_speakers"] = {"labels": sorted(exclude), "utterances_dropped": n}

    if args.scan_copy:
        args.scan_copy.write_text(make_scan_copy(text, fmt, exclude), encoding="utf-8")
        report["scan_copy"] = str(args.scan_copy)

    if args.filtered_output:
        filtered, n = drop_speakers(text, exclude)
        args.filtered_output.write_text(filtered, encoding="utf-8")
        report["filtered_output"] = {"path": str(args.filtered_output),
                                     "utterances_removed": n}

    if args.dedup_output:
        if dup:
            args.dedup_output.write_text(dedup(text, lines, dup), encoding="utf-8")
            report["dedup_output"] = str(args.dedup_output)
        else:
            report["dedup_output"] = None

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print(f"{args.input}")
    print(f"  format:         {fmt}")
    print(f"  dialogue lines: {len(lines)}  ({report['dialogue_words']} words)")
    if report["speakers"]:
        who = ", ".join(f"{k} ({v})" for k, v in report["speakers"].items())
        print(f"  speakers:       {who}")
    else:
        print(f"  speakers:       none detected — no attribution available from this file")
    if exclude:
        ex = report["excluded_speakers"]
        print(f"  excluded:       {', '.join(ex['labels'])} "
              f"({ex['utterances_dropped']} utterances, scan copy only)")
    if dup:
        print(f"  DUPLICATED:     body recorded twice; copy 2 starts at dialogue line "
              f"{dup['copy2_starts_at_dialogue_line']}")
        print(f"                  alignment {dup['alignment_ratio']:.4f}, "
              f"{dup['identical_lines']}/{dup['copy1_lines']} lines identical")
        print(f"                  every occurrence count in this file is DOUBLED")
        if not args.dedup_output:
            print(f"                  re-run with --dedup-output to write a single-copy file")
    else:
        print(f"  duplication:    none detected")
    if args.scan_copy:
        print(f"  scan copy:      {args.scan_copy}")
    if args.dedup_output and dup:
        print(f"  deduplicated:   {args.dedup_output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
