#!/usr/bin/env python3
"""Transfer Zoom's speaker labels onto Whisper's cue boundaries by aligning
the two transcripts as token sequences. No audio, no model.

The problem this solves
-----------------------
A Zoom session dir gives you two half-answers:

  *_Recording.md            speaker labels, but Zoom's live text export
                            segments on TALK-DETECTION, so it flips speaker
                            mid-sentence under crosstalk:
                              **gary:** ...through the most brightly
                              **kostadis:** lit, uh, path possible. At both

  *.vtt.unused-no-speakers  real timings and ACOUSTIC segmentation, so the
                            same moment is one clean cue:
                              Valfina would like to go through the most
                              brightly lit path possible.
                            ...but no speaker labels at all.

Whisper's boundaries are the correct ones. Zoom's labels are ~93% correct.
So: align the two token streams, and for each Whisper cue award it to the
Zoom speaker who contributed most of that cue's words. The mid-sentence
flips dissolve by construction -- a split sentence is one cue, and one
speaker owns the majority of it.

Cues where the vote is close are reported as CONTESTED rather than guessed:
those are the genuine crosstalk moments, and they are a human's call.
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path


def norm_tokens(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9 ]", " ", text.lower()).split()


def ts(t: str) -> float:
    h, m, rest = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def fmt(sec: float) -> str:
    h, rem = divmod(max(0.0, sec), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


def load_vtt(path: Path) -> list[dict]:
    cues = []
    for block in path.read_text(encoding="utf-8", errors="replace").split("\n\n"):
        m = re.search(r"(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})", block)
        if not m:
            continue
        body = " ".join(l.strip() for l in block.split("\n")
                        if l.strip() and not re.match(r"^(WEBVTT|NOTE|\d+$|\d{2}:)", l.strip()))
        if body:
            cues.append({"start": ts(m.group(1)), "end": ts(m.group(2)), "text": body})
    return cues


def load_md(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return [{"speaker": m.group(1).strip(), "text": m.group(2).strip()}
            for m in re.finditer(r"^\*\*([^:*]+):\*\*\s*(.+?)\s*$", text, re.M)]


def build_streams(cues, utts):
    """Flatten both sides to token streams, remembering each token's owner."""
    a_tok, a_owner = [], []          # whisper side -> cue index
    for i, c in enumerate(cues):
        for t in norm_tokens(c["text"]):
            a_tok.append(t)
            a_owner.append(i)
    b_tok, b_owner = [], []          # zoom side -> speaker
    for u in utts:
        for t in norm_tokens(u["text"]):
            b_tok.append(t)
            b_owner.append(u["speaker"])
    return a_tok, a_owner, b_tok, b_owner


def transfer(cues, utts, contested_margin: float):
    a_tok, a_owner, b_tok, b_owner = build_streams(cues, utts)
    sm = SequenceMatcher(a=a_tok, b=b_tok, autojunk=False)

    votes = [Counter() for _ in cues]
    matched = 0
    for ai, bi, size in sm.get_matching_blocks():
        for k in range(size):
            votes[a_owner[ai + k]][b_owner[bi + k]] += 1
            matched += 1

    contested, unlabelled = [], []
    for i, c in enumerate(cues):
        v = votes[i]
        if not v:
            c["speaker"] = None
            unlabelled.append(i)
            continue
        ranked = v.most_common()
        top, top_n = ranked[0]
        total = sum(v.values())
        c["speaker"] = top
        c["confidence"] = top_n / total
        c["votes"] = dict(ranked)
        if len(ranked) > 1 and (top_n - ranked[1][1]) / total < contested_margin:
            contested.append(i)
    return matched, len(a_tok), contested, unlabelled


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vtt", required=True, help="real-timeline speakerless VTT")
    ap.add_argument("--md", required=True, help="Zoom speaker-labelled markdown")
    ap.add_argument("--output", required=True)
    ap.add_argument("--contested-margin", type=float, default=0.34,
                    help="report a cue as contested when the winner's lead is "
                         "below this fraction of its votes")
    a = ap.parse_args()

    cues = load_vtt(Path(a.vtt))
    utts = load_md(Path(a.md))
    matched, total, contested, unlabelled = transfer(cues, utts, a.contested_margin)

    print(f"{len(cues)} whisper cues | {len(utts)} zoom utterances")
    print(f"token alignment: {matched}/{total} whisper tokens matched "
          f"({matched/total*100:.1f}%)")
    dist = Counter(c["speaker"] for c in cues if c.get("speaker"))
    print("\nspeaker distribution over cues:")
    for s, n in dist.most_common():
        print(f"  {s:<22} {n:5d} cues ({n/len(cues)*100:5.1f}%)")
    print(f"\ncontested (winner's lead < {a.contested_margin:.0%}): {len(contested)}")
    print(f"unlabelled (no aligned tokens):                {len(unlabelled)}")

    lines = ["WEBVTT", "",
             "NOTE Speaker labels transferred from Zoom's markdown export onto",
             "NOTE Whisper's acoustic cue boundaries by token alignment.",
             "NOTE Timings are Whisper's (real). CONTESTED marks cues where two",
             "NOTE speakers' words both land in one cue -- genuine crosstalk.", ""]
    for i, c in enumerate(cues, 1):
        who = c.get("speaker") or "UNKNOWN"
        tag = " [CONTESTED]" if (i - 1) in contested else ""
        lines += [str(i), f"{fmt(c['start'])} --> {fmt(c['end'])}",
                  f"{who}{tag}: {c['text']}", ""]
    Path(a.output).write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {a.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
