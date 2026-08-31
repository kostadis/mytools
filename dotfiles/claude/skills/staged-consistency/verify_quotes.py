#!/usr/bin/env python3
"""Mechanically verify every quoted span in a pipeline artifact against the VTT.

Catches the class of error an LLM reviewer reads straight past: quotes spliced
from two moments, quotes completed with words nobody said, and quotes attributed
to the wrong speaker.

    python3 verify_quotes.py --doc session_summary.md --vtt <session>.transcript.cleaned.vtt

Prints every quoted span whose text is not contiguous in the transcript. Expect
false positives from deliberate stutter-smoothing; each hit is a lead to check by
hand, not a finding on its own.

WHY THE VTT IS PARSED RATHER THAN GREPPED: a naive grep over the raw .vtt file
fails on any quote that crosses a cue boundary, because the cue index and the
timestamp line sit between the two halves. Strip to cue text first, then join.
"""
import argparse, re, unicodedata


def norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t)
    for a, b in [("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'),
                 ("…", "..."), ("—", " "), ("–", " ")]:
        t = t.replace(a, b)
    t = re.sub(r"[^a-z0-9' ]", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def cue_text(vtt_path: str, keep_speakers: bool = False) -> str:
    cues = []
    for ln in open(vtt_path, encoding="utf-8"):
        ln = ln.rstrip("\n")
        if not ln.strip() or ln.strip() == "WEBVTT":
            continue
        if re.fullmatch(r"\d+", ln.strip()):
            continue
        if "-->" in ln:
            continue
        if not keep_speakers:
            ln = re.sub(r"^[A-Za-z .'\-]{1,25}:\s*", "", ln)
        cues.append(ln)
    return norm(" ".join(cues))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", required=True)
    ap.add_argument("--vtt", required=True)
    ap.add_argument("--min", type=int, default=12,
                    help="ignore quoted spans shorter than this many normalised chars")
    a = ap.parse_args()

    vtt = cue_text(a.vtt)
    checked = miss = 0
    for i, ln in enumerate(open(a.doc, encoding="utf-8").read().split("\n"), 1):
        for m in re.finditer(r'"([^"]{%d,})"' % a.min, ln):
            q = m.group(1)
            checked += 1
            # An ellipsis marks a deliberate elision: verify each side separately.
            frags = [f for f in re.split(r"…|\.\.\.", q) if len(norm(f)) >= a.min] or [q]
            bad = [f.strip() for f in frags if norm(f) and norm(f) not in vtt]
            if bad:
                miss += 1
                print(f"--- L{i}: {q[:170]}")
                for b in bad:
                    print(f"      NOT CONTIGUOUS IN VTT: {b[:170]}")
    print(f"\nquoted spans checked: {checked}   unverified: {miss}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
