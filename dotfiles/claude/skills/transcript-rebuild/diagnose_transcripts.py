#!/usr/bin/env python3
"""Inventory every transcript in a session directory and say, per file, whether
its TIMESTAMPS are real and whether it carries SPEAKER labels.

Why this exists
---------------
A Zoom session dir routinely holds three views of one recording, and none of
them is usable alone:

  *_Recording.md            speakers, NO timeline
  *.speakers.vtt            speakers, SYNTHETIC timeline
  *.vtt(.unused-no-speakers) real timeline, NO speakers

The synthetic one is the trap: it looks like an ordinary WebVTT, the pipeline
defaults to it, and its timestamps are fabricated. Anything derived from audio
(diarization, cue slicing, re-transcription) that is aligned against it is
silently wrong.

Two independent tells, both checked here:

1. **A declared NOTE.** Generators sometimes say so outright
   ("Timestamps are SYNTHETIC ... do not correspond to real recording offsets").
2. **No silences.** Real conversation has pauses. A transcript whose largest
   inter-cue gap is a fraction of a second, across a thousand cues, was
   reflowed onto a synthetic timeline -- nobody talks that way. Chapter 04:
   1441 cues, max gap 0.2s, zero gaps over 1s.

If an audio file is present, the real transcript's end should land near the
audio duration. The synthetic one typically will not.
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
from pathlib import Path

TS = re.compile(r"(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})")
MD_LABEL = re.compile(r"^\*\*([^:*]{1,40}):\*\*", re.M)
VTT_LABEL = re.compile(r"^([A-Za-z][A-Za-z0-9 ._'-]{0,40}):\s", re.M)
SYNTH_NOTE = re.compile(r"synthetic|do not correspond to real", re.I)


def secs(t: str) -> float:
    h, m, rest = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def mp4_duration(path: Path) -> float | None:
    """Duration from the mvhd box, without ffprobe (absent on some hosts)."""
    try:
        data = path.open("rb").read(300_000)
    except OSError:
        return None
    i = data.find(b"mvhd")
    if i < 0:
        return None
    off = i + 4
    try:
        if data[off] == 0:
            ts, dur = struct.unpack(">II", data[off + 12:off + 20])
        else:
            ts, dur = struct.unpack(">IQ", data[off + 20:off + 32])
        return dur / ts if ts else None
    except struct.error:
        return None


def speaker_labels(text: str) -> list[str]:
    """Recurring speaker labels only.

    A one-off ``Something:`` at line start is prose, not a speaker. Requiring a
    label to recur is what separates ``Kostadis Roussos:`` from
    ``NOTE  contested cues  :`` and from a sentence that happens to contain a
    colon. Threshold is deliberately low so a player with three lines still
    shows up -- the goal is to notice them, not to count them.
    """
    from collections import Counter
    raw = MD_LABEL.findall(text)
    if not raw:
        raw = [m for m in VTT_LABEL.findall(text)
               if m not in ("WEBVTT", "NOTE") and not m.startswith("NOTE")]
    counts = Counter(raw)
    return sorted(n for n, c in counts.items() if c >= 3)


def inspect(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    cues = [(secs(a), secs(b)) for a, b in TS.findall(text)]
    labels = speaker_labels(text)
    info = {
        "path": path,
        "cues": len(cues),
        "speakers": sorted(set(labels)),
        "declared_synthetic": bool(SYNTH_NOTE.search(text[:2000])),
        "start": cues[0][0] if cues else None,
        "end": cues[-1][1] if cues else None,
        "max_gap": None,
        "gaps_over_1s": None,
    }
    if len(cues) > 1:
        gaps = [cues[i + 1][0] - cues[i][1] for i in range(len(cues) - 1)]
        info["max_gap"] = max(gaps)
        info["gaps_over_1s"] = sum(1 for g in gaps if g > 1.0)
    return info


def verdict(info: dict, audio_dur: float | None) -> tuple[str, str]:
    """(timing verdict, reason)"""
    if not info["cues"]:
        return "NO TIMELINE", "no cues"
    if info["declared_synthetic"]:
        return "SYNTHETIC", "the file's own NOTE says so"
    if info["gaps_over_1s"] == 0 and info["cues"] > 50:
        return "SYNTHETIC", (f"{info['cues']} cues and not one gap over 1s "
                            f"(max {info['max_gap']:.2f}s) — no silences")
    if audio_dur and info["end"]:
        drift = abs(audio_dur - info["end"])
        if drift < max(30.0, audio_dur * 0.02):
            return "REAL", f"ends {info['end']:.0f}s ≈ audio {audio_dur:.0f}s"
        return "SUSPECT", (f"ends {info['end']:.0f}s but audio is "
                           f"{audio_dur:.0f}s ({drift:.0f}s adrift)")
    return "PLAUSIBLE", f"{info['gaps_over_1s']} real gaps, max {info['max_gap']:.1f}s"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("session_dir")
    ap.add_argument("--audio", help="explicit audio path (else auto-detected)")
    a = ap.parse_args()
    d = Path(a.session_dir)
    if not d.is_dir():
        print(f"not a directory: {d}", file=sys.stderr)
        return 2

    audio = Path(a.audio) if a.audio else next(iter(sorted(d.glob("*.m4a"))), None)
    audio_dur = mp4_duration(audio) if audio else None
    if audio:
        print(f"audio: {audio.name}"
              + (f"  {audio_dur:.1f}s ({audio_dur/60:.1f} min)" if audio_dur else "  (duration unknown)"))
    else:
        print("audio: none found — timing verdicts fall back to gap structure")
    print()

    cands = sorted(p for p in d.iterdir()
                   if p.is_file() and (".vtt" in p.name or p.suffix == ".md")
                   and "proper_nouns" not in p.name)
    timing_authority = speaker_authority = None
    rows = []
    for p in cands:
        info = inspect(p)
        # A transcript has cues, or has several recurring speakers. Session
        # summaries and reports have neither and must not be listed as
        # candidate authorities.
        if not info["cues"] and len(info["speakers"]) < 2:
            continue
        rows.append((p, info))
    for p, info in rows:
        v, why = verdict(info, audio_dur)
        spk = f"{len(info['speakers'])} speakers" if info["speakers"] else "NO speakers"
        print(f"  {p.name}")
        print(f"      timing: {v:<10} {why}")
        print(f"      {spk}" + (f": {', '.join(info['speakers'][:6])}" if info["speakers"] else ""))
        if info["cues"]:
            print(f"      {info['cues']} cues, {info['start']:.1f}s..{info['end']:.1f}s")
        # Authorities: the timing one is the earliest REAL file that has NO
        # speakers (a REAL file that already has speakers is a finished
        # rebuild, not an input). The speaker one is whatever carries labels
        # on a timeline we do not trust.
        if v == "REAL" and not info["speakers"] and timing_authority is None:
            timing_authority = p
        if info["speakers"] and v in ("SYNTHETIC", "NO TIMELINE") and speaker_authority is None:
            speaker_authority = p
        print()

    print("─" * 62)
    print(f"  timing authority : {timing_authority.name if timing_authority else 'NONE FOUND'}")
    print(f"  speaker authority: {speaker_authority.name if speaker_authority else 'NONE FOUND'}")
    if timing_authority and speaker_authority:
        print("\n  Split brain: neither file is usable alone. Run label_transfer.py")
        print("  to put the speaker labels onto the real cue boundaries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
