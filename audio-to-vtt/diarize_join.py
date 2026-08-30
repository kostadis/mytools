#!/usr/bin/env python3
"""Workstation-side join: diarization turns + the real-timeline (speakerless)
Whisper VTT + Zoom's speaker-labelled markdown  ->  a VTT with BOTH real
timestamps and real speaker names.

Why all three inputs are needed
-------------------------------
A Zoom session dir typically holds three views of one recording, and no
single one is usable on its own:

  *_Recording.md            speakers, NO timeline
  *.speakers.vtt            speakers, SYNTHETIC timeline (its own header
                            says so -- cue times are proportional to
                            utterance length, not real offsets)
  *.vtt.unused-no-speakers  real timeline (matches the .m4a duration), NO
                            speakers

Diarization supplies the missing join: it gives speaker *turns* on the real
timeline, which attach cleanly to the Whisper cues. The markdown is then used
only to put human NAMES on the anonymous SPEAKER_xx clusters.

This also sidesteps Zoom's mid-sentence speaker flips: those are an artifact
of Zoom's live text export segmenting on talk-detection, and simply do not
exist in the acoustically-segmented Whisper cues.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

_STOP = {"the", "and", "you", "that", "this", "was", "for", "are", "but",
         "not", "with", "have", "your", "its", "uh", "um", "like", "yeah",
         "okay", "just", "know", "got", "gonna", "right", "well", "all"}


def toks(s: str) -> list[str]:
    return [w for w in re.sub(r"[^a-z0-9 ]", " ", s.lower()).split()
            if len(w) > 2 and w not in _STOP]


def ts(t: str) -> float:
    h, m, rest = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def fmt(sec: float) -> str:
    h, rem = divmod(max(0.0, sec), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


def load_vtt(path: Path) -> list[dict]:
    """Cues from a WebVTT. Speaker prefix is stripped if present."""
    cues = []
    for block in path.read_text(encoding="utf-8", errors="replace").split("\n\n"):
        m = re.search(r"(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})", block)
        if not m:
            continue
        body = " ".join(l.strip() for l in block.split("\n")
                        if l.strip() and not re.match(r"^(WEBVTT|NOTE|\d+$|\d{2}:)", l.strip()))
        if not body:
            continue
        cues.append({"start": ts(m.group(1)), "end": ts(m.group(2)), "text": body})
    return cues


def load_md(path: Path) -> list[dict]:
    """Speaker-labelled utterances from Zoom's markdown export, in order."""
    out = []
    for m in re.finditer(r"^\*\*([^:*]+):\*\*\s*(.+?)\s*$", path.read_text(encoding="utf-8",
                                                                          errors="replace"), re.M):
        out.append({"speaker": m.group(1).strip(), "text": m.group(2).strip()})
    return out


def assign_clusters(cues: list[dict], turns: list[dict]) -> None:
    """Give each cue the diarization cluster with the most temporal overlap."""
    for c in cues:
        best, best_ov = None, 0.0
        for t in turns:
            ov = min(c["end"], t["end"]) - max(c["start"], t["start"])
            if ov > best_ov:
                best, best_ov = t["speaker"], ov
        c["cluster"] = best
        c["overlap"] = round(best_ov, 3)


def map_names(cues: list[dict], utts: list[dict]) -> dict[str, str]:
    """Vote each SPEAKER_xx cluster onto a human name.

    Both transcripts run in the same order, so this walks them monotonically
    with a bounded lookahead rather than doing a global best-match (which
    would happily pair a stray 'yeah' at minute 12 with one at minute 80).
    """
    votes: dict[str, Counter] = defaultdict(Counter)
    j = 0
    for c in cues:
        ct = set(toks(c["text"]))
        if not ct or not c.get("cluster"):
            continue
        best_k, best_score = None, 0.0
        for k in range(j, min(j + 25, len(utts))):
            ut = set(toks(utts[k]["text"]))
            if not ut:
                continue
            score = len(ct & ut) / max(1, min(len(ct), len(ut)))
            if score > best_score:
                best_k, best_score = k, score
        if best_k is not None and best_score >= 0.5:
            votes[c["cluster"]][utts[best_k]["speaker"]] += 1
            j = best_k
    return {cl: cnt.most_common(1)[0][0] for cl, cnt in votes.items() if cnt}, votes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", required=True, help="diarization result JSON")
    ap.add_argument("--vtt", required=True, help="real-timeline speakerless VTT")
    ap.add_argument("--md", required=True, help="Zoom speaker-labelled markdown")
    ap.add_argument("--output", required=True)
    a = ap.parse_args()

    turns = json.loads(Path(a.turns).read_text(encoding="utf-8"))["turns"]
    cues = load_vtt(Path(a.vtt))
    utts = load_md(Path(a.md))
    print(f"{len(turns)} turns | {len(cues)} cues | {len(utts)} md utterances")

    assign_clusters(cues, turns)
    unassigned = sum(1 for c in cues if not c.get("cluster"))
    names, votes = map_names(cues, utts)

    print("\ncluster -> name (vote margin):")
    for cl in sorted(votes):
        top = votes[cl].most_common(3)
        tot = sum(votes[cl].values())
        detail = ", ".join(f"{n}={v}" for n, v in top)
        print(f"  {cl:<14} -> {names.get(cl,'?'):<20} {top[0][1]}/{tot} ({detail})")
    if unassigned:
        print(f"\n{unassigned} cues had no overlapping turn (kept, speaker blank)")

    lines = ["WEBVTT", "",
             "NOTE Speakers from pyannote diarization of the source .m4a;",
             "NOTE timings are the real Whisper cue timings. Cluster->name",
             "NOTE mapping is a majority vote against Zoom's markdown export.", ""]
    for i, c in enumerate(cues, 1):
        who = names.get(c.get("cluster") or "", "")
        lines += [str(i), f"{fmt(c['start'])} --> {fmt(c['end'])}",
                  f"{who}: {c['text']}" if who else c["text"], ""]
    Path(a.output).write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {a.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
