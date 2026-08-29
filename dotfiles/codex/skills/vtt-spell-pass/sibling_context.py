#!/usr/bin/env python3
"""Look up what a SECOND, independent transcription says at a given span.

Companion to zoom_context.py. That script handles the aligned case: an
audio-to-vtt retranscription and the Zoom original it was derived from, paired
by filename and matched by cue-group timing. This script handles the unaligned
case -- two transcriptions of the same session produced by different tools,
with different segmentation, different wording, and no shared timestamps (e.g.
a voice-detection markdown export alongside a D&D-tuned WebVTT).

It matches on text instead of time: slide a window over the sibling's
utterances and return the best fuzzy match for the excerpt you pass in.

Why bother
----------
A second transcription is the cheapest adjudicator available for an ambiguous
candidate, and it resolves three distinct cases:

  * confirms a proposed canonical, when the sibling simply spells the name
    correctly at that span;
  * overturns a high-confidence fuzzy match, when the sibling shows the span
    was never that name at all;
  * rules a mangle out entirely, when BOTH systems produce the same odd
    string -- agreement between independent ASR means genuine audio, not an
    artifact, so there is nothing to "fix".

Usage
-----
    sibling_context.py --sibling <other-transcript> \
        --context "You can just barely see the Grygum"
    sibling_context.py --sibling <other> --context "..." --top 3
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

TIMESTAMP_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d+\s*-->\s*\d{2}:\d{2}:\d{2}\.\d+\s*$")
CUE_NUM_RE = re.compile(r"^\d+\s*$")
MD_LABEL_RE = re.compile(r"^\*\*([^*:]{1,40}):\*\*\s*")
PLAIN_LABEL_RE = re.compile(
    r"^\s*(?:[A-Z][\w'\-]+(?:\s+[A-Z][\w'\-]+){0,3}\s*\([^)]+\)"
    r"|[A-Z][\w'\-]+(?:\s+[A-Z][\w'\-]+){0,2})\s*:\s*")


def utterances(path: Path) -> list[tuple[int, str, str]]:
    """Return [(line_no, speaker_or_empty, text), ...] for any supported format."""
    out = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if s.upper() == "WEBVTT" or TIMESTAMP_RE.match(s) or CUE_NUM_RE.match(s):
            continue
        speaker = ""
        m = MD_LABEL_RE.match(s)
        if m:
            speaker = m.group(1).strip()
            s = MD_LABEL_RE.sub("", s).strip()
        elif PLAIN_LABEL_RE.match(s):
            speaker = PLAIN_LABEL_RE.match(s).group(0).strip().rstrip(":")
            s = PLAIN_LABEL_RE.sub("", s).strip()
        if s:
            out.append((line_no, speaker, s))
    return out


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


def best_matches(utts: list[tuple[int, str, str]], query: str, top: int):
    """Slide a window of consecutive utterances and score against the query.

    Windows are grown until they are at least as long as the query, because the
    sibling may split one spoken sentence across several short cues (a WebVTT
    cue is often 3-8 words) or merge several into one long line.
    """
    q = norm(query)
    if not q:
        return []
    target = len(q)
    scored = []
    for i in range(len(utts)):
        joined = ""
        for j in range(i, min(i + 12, len(utts))):
            joined = (joined + " " + norm(utts[j][2])).strip()
            if len(joined) < target * 0.6:
                continue
            ratio = difflib.SequenceMatcher(None, q, joined, autojunk=False).ratio()
            scored.append((ratio, i, j))
            if len(joined) > target * 1.8:
                break
    scored.sort(key=lambda x: -x[0])

    results, used = [], set()
    for ratio, i, j in scored:
        if any(k in used for k in range(i, j + 1)):
            continue
        used.update(range(i, j + 1))
        text = " ".join(u[2] for u in utts[i:j + 1])
        spk = [u[1] for u in utts[i:j + 1] if u[1]]
        results.append({
            "score": round(ratio, 3),
            "line": utts[i][0],
            "speakers": sorted(set(spk)),
            "text": text,
        })
        if len(results) >= top:
            break
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sibling", required=True, type=Path,
                    help="The OTHER transcription of the same session")
    ap.add_argument("--context", required=True,
                    help="Excerpt from the transcript being cleaned")
    ap.add_argument("--top", type=int, default=1)
    args = ap.parse_args()

    if not args.sibling.exists():
        print(f"sibling not found: {args.sibling}", file=sys.stderr)
        return 2

    utts = utterances(args.sibling)
    if not utts:
        print(f"no utterances parsed from {args.sibling}", file=sys.stderr)
        return 2

    results = best_matches(utts, args.context, args.top)
    if not results:
        print("null")
        return 0

    print(f"query:   {args.context}")
    print(f"sibling: {args.sibling} ({len(utts)} utterances)")
    for r in results:
        who = f" [{', '.join(r['speakers'])}]" if r["speakers"] else ""
        print(f"\n  score {r['score']:.3f}  line {r['line']}{who}")
        print(f"    {r['text']}")
    top = results[0]["score"]
    if top < 0.55:
        print("\n  NOTE: best score is low — the sibling may not cover this span, "
              "or the two transcriptions diverge here. Treat as inconclusive.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
