#!/usr/bin/env python3
"""Normalise a Descript plain-text export into the two shapes this skill reads.

Descript is the most useful second clustering available here: it is an
independent acoustic model that picks its OWN speaker count, so unlike pyannote
it can surface a voice you did not know was in the room. But its .txt export
matches neither script's input format, so it has to be converted first.

What it emits (a per-word timestamp stream, labels not bolded):

    [00:17:16] Speaker 2: You're gonna be [00:17:17] there for two [00:17:18] weeks?

    [00:18:10] Speaker 3: So unfortunately, I [00:18:11] did not write [00:18:12] a backstory yet

What this writes:

    --md     [00:17:16] **Speaker 2:** You're gonna be there for two weeks?
             ... the form diarize_label.py --md parses for cross-validation.

    --turns  {"turns": [{"start": 1036.0, "end": 1039.0, "speaker": "Speaker 2"}, ...]}
             ... the form diarize_label.py --turns parses. Lets Descript stand in
             as the PRIMARY clustering when no GPU is free — both Sparks running
             a tensor-parallel vLLM leaves nothing to diarize with.

**Start times are anchored on words, not on the block header.** A block's header
stamp is when the block begins, which is not when anyone speaks: leading silence
is timestamped too. The opening block of a real session was headed 00:00:00 and
its first actual word landed at 00:16:16 — sixteen minutes of drift on the one
cue most likely to be a greeting that names somebody. 24% of blocks in that file
needed the correction. Taking the header would smear those onto the wrong cues.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

TS = re.compile(r"\[(\d\d):(\d\d):(\d\d)\]")
# Any label, not just "Speaker N" -- Descript keeps the name once you rename a
# cluster in the editor, and a named export must not silently parse as zero turns.
HEAD = re.compile(r"^\[(\d\d:\d\d:\d\d)\]\s*([^:\n]{1,40}):\s*(.*)$", re.S)

FRAGMENT_SHARE = 0.03  # below this share of words, a cluster is not a person


def sec(hms: str) -> int:
    return int(hms[0:2]) * 3600 + int(hms[3:5]) * 60 + int(hms[6:8])


def word_stamps(header: str, body: str) -> list[str]:
    """Timestamps that actually bracket a word, in order.

    Walks the interleaved stream and keeps a stamp only once a word has appeared
    after it, so runs of bare stamps (silence) contribute nothing.
    """
    stamps, pos, cur = [], 0, header
    for m in TS.finditer(body):
        if re.search(r"[A-Za-z0-9]", body[pos:m.start()]):
            stamps.append(cur)
        cur, pos = m.group(0)[1:-1], m.end()
    if re.search(r"[A-Za-z0-9]", body[pos:]):
        stamps.append(cur)
    return stamps


def parse(path: Path) -> tuple[list[dict], int, int]:
    turns, skipped, shifted = [], 0, 0
    raw = path.read_text(encoding="utf-8", errors="replace")
    for block in raw.split("\n\n"):
        b = block.strip()
        if not b:
            continue
        m = HEAD.match(b)
        if not m:
            skipped += 1
            continue
        header, who, body = m.group(1), m.group(2).strip(), m.group(3)
        stamps = word_stamps(header, body)
        text = re.sub(r"\s+", " ", TS.sub(" ", body)).strip()
        if not stamps or not text:
            continue
        if stamps[0] != header:
            shifted += 1
        turns.append({"start": float(sec(stamps[0])),
                      "end": float(sec(stamps[-1]) + 1),
                      "speaker": who, "text": text})
    turns.sort(key=lambda t: t["start"])
    return turns, skipped, shifted


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="Descript .txt export")
    ap.add_argument("--md", help="write the [ts] **Speaker:** form (for --md)")
    ap.add_argument("--turns", help="write a turns.json envelope (for --turns)")
    ap.add_argument("--audio-duration", type=float,
                    help="seconds; recorded in the turns envelope for reporting")
    args = ap.parse_args()

    turns, skipped, shifted = parse(Path(args.input))
    if not turns:
        print("no utterances parsed — is this a Descript export? expected lines like")
        print('   [00:17:16] Speaker 2: You\'re gonna be [00:17:17] there ...')
        return 1

    if args.md:
        Path(args.md).write_text(
            "\n\n".join(f"[{t['start']//3600:02.0f}:{t['start']//60%60:02.0f}:"
                        f"{t['start']%60:02.0f}] **{t['speaker']}:** {t['text']}"
                        for t in turns) + "\n", encoding="utf-8")

    if args.turns:
        Path(args.turns).write_text(json.dumps({
            "turns": [{k: t[k] for k in ("start", "end", "speaker")} for t in turns],
            "audio_duration": args.audio_duration or turns[-1]["end"],
            "model": "descript-editor-clustering (acoustic, vendor; speaker count chosen by Descript)",
            "num_speakers_requested": None,
            "device_used": "descript-cloud",
        }, indent=1), encoding="utf-8")

    words = Counter()
    for t in turns:
        words[t["speaker"]] += len(t["text"].split())
    total = sum(words.values())
    span = sum(t["end"] - t["start"] for t in turns)

    print(f"{len(turns)} turns · {total} words · {span/60:.1f} min spanned · "
          f"{skipped} non-utterance block(s) skipped")
    if shifted:
        print(f"{shifted} block(s) ({100*shifted/len(turns):.0f}%) had a header stamp "
              f"ahead of their first word — anchored on the word")
    print()
    frags = []
    for who, n in words.most_common():
        share = n / total
        tag = ""
        if share < FRAGMENT_SHARE:
            tag = "   ← fragment, not a person"
            frags.append(who)
        print(f"   {who:<14}{n:>6} words {100*share:>6.1f}%{tag}")
    if frags:
        print(f"\n{len(frags)} fragment cluster(s): {', '.join(frags)}")
        print("Usually one person's second register (a GM doing NPC voices) — or a")
        print("real FIFTH voice in the room who is not at the table. Read their lines")
        print("before deciding; do not promote one to a participant on size alone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
