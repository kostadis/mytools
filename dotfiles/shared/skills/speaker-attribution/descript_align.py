#!/usr/bin/env python3
"""Give a sparse Descript export real turn spans by aligning it to a timed VTT.

descript_turns.py needs a timestamp stream through the body. Some exports do not
have one: a Descript .md uploaded to Google Drive becomes a Google Doc, and the
Markdown exported back out keeps only a marker per minute
(`**ben:** \\[00:16:00\\] ...`). descript_turns.py then parses zero utterances.

This keeps Descript's speaker LABELS, which are its own voice clustering and so
still independent of pyannote, and borrows the TIMES from a VTT on the same
timeline. Words are matched in order (difflib, runs of --min-run or more);
word times inside a cue are interpolated linearly across the cue. An utterance
with no matched word gets no turn.

The output is the same envelope descript_turns.py --turns writes, so it goes to
diarize_label.py --md unchanged. Say in the output header that the spans are
borrowed: agreement then means the two tools' LABELS agree, not their timing.

    python3 descript_align.py --md descript.md --vtt transcript.vtt \\
        --turns descript_turns.json --audio-duration 2357.6
"""
import argparse
import difflib
import json
import re
import sys


def norm(w: str) -> str:
    return re.sub(r"[^a-z0-9']", "", w.lower())


def secs(s: str) -> float:
    h, m, rest = s.split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


CUE = re.compile(r"(\d+:\d+:\d+\.\d+) --> (\d+:\d+:\d+\.\d+)")
LABEL = re.compile(r"\*\*([^*:]+):\*\*\s*(.*)")
STAMP = re.compile(r"\\?\[\d+:\d+:\d+(?:\.\d+)?\\?\]")


def vtt_words(path: str):
    words, times = [], []
    for block in open(path, encoding="utf-8").read().split("\n\n"):
        lines = block.strip().splitlines()
        for i, ln in enumerate(lines):
            m = CUE.match(ln)
            if not m:
                continue
            s, e = secs(m.group(1)), secs(m.group(2))
            text = " ".join(lines[i + 1:])
            text = re.sub(r"^[^:\n]{1,40}?(?: \[\?\])?: ", "", text)  # drop a label
            ws = [w for w in (norm(x) for x in text.split()) if w]
            for k, w in enumerate(ws):
                words.append(w)
                times.append((s + (e - s) * k / len(ws), s + (e - s) * (k + 1) / len(ws)))
            break
    return words, times


def descript_utterances(path: str):
    utts = []
    for ln in open(path, encoding="utf-8"):
        ln = STAMP.sub(" ", ln).strip()
        m = LABEL.match(ln)
        if m:
            utts.append([m.group(1).strip(), m.group(2)])
        elif ln and utts and not ln.startswith("#"):
            utts[-1][1] += " " + ln  # a continuation paragraph: same speaker
    return utts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--md", required=True, help="Descript Markdown export (**name:** labels)")
    ap.add_argument("--vtt", required=True, help="timed VTT on the SAME timeline")
    ap.add_argument("--turns", required=True, help="output turns JSON")
    ap.add_argument("--audio-duration", type=float, required=True)
    ap.add_argument("--min-run", type=int, default=2,
                    help="shortest matched word run that counts (default 2)")
    a = ap.parse_args()

    vw, vt = vtt_words(a.vtt)
    utts = descript_utterances(a.md)
    if not utts or not vw:
        print(f"nothing to align: {len(utts)} Descript utterances, {len(vw)} VTT words",
              file=sys.stderr)
        return 1
    dw, owner = [], []
    for ui, (_, text) in enumerate(utts):
        for w in (norm(x) for x in text.split()):
            if w:
                dw.append(w)
                owner.append(ui)

    hit, matched = {}, 0
    sm = difflib.SequenceMatcher(None, dw, vw, autojunk=False)
    for blk in sm.get_matching_blocks():
        if blk.size < a.min_run:
            continue
        for k in range(blk.size):
            hit.setdefault(owner[blk.a + k], []).append(vt[blk.b + k])
            matched += 1

    turns = [{"start": round(min(t[0] for t in hit[i]), 3),
              "end": round(max(t[1] for t in hit[i]), 3), "speaker": spk}
             for i, (spk, _) in enumerate(utts) if i in hit]
    turns.sort(key=lambda t: t["start"])
    labels = sorted({t["speaker"] for t in turns})
    json.dump({"turns": turns, "audio_duration": a.audio_duration,
               "model": "descript (spans aligned to VTT words)",
               "num_speakers_requested": None, "device_used": None},
              open(a.turns, "w", encoding="utf-8"), indent=1)
    pct = matched / len(dw)
    print(f"{len(utts)} utterances, {len(turns)} with a span; "
          f"{matched}/{len(dw)} Descript words matched ({pct:.1%})")
    print(f"labels: {', '.join(labels)}")
    if pct < 0.7:
        print("⚠ under 70% of words matched — check the two files are the same recording "
              "and the same edit before joining.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
