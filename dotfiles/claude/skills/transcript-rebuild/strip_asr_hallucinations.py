#!/usr/bin/env python3
"""Find and revert Whisper's training-data hallucinations in a re-transcribed VTT.

Whisper fills near-silent spans with text it saw a lot of during training:
YouTube outros ("Thanks for watching", "please subscribe", "hit the bell"),
caption-farm credits ("Subtitles by the Amara.org community"), and sometimes
foreign-language boilerplate. On a D&D recording these land as *quotable
dialogue attributed to a real player*, which is the worst possible failure —
`Wade Brown: Thank you for watching!` reads exactly like something Wade said.

They are not random. In Phandalin chapter 04 all 13 sat on cues of 0.16–0.8
seconds, in a recording where the transcript covers 61 of 100 minutes. Forcing
a decode of every cue-group, including the near-empty ones, is what produces
them — so a re-transcription that reuses cue boundaries is exactly the setup
that triggers this, while the original VAD-based transcription had none.

Reverting beats deleting: the original text for those spans is real, usually a
one-word acknowledgement ("Yeah.", "Okay.", "What?"). Pass --source to recover
it. Without --source the cue is marked [inaudible] instead, which is honest but
loses a real word.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Deliberately narrow. Every entry is a phrase Whisper emits on silence and
# that no D&D table says. Do not add generic words here: a false positive
# silently deletes real dialogue, which is worse than the hallucination.
PATTERNS = [
    r"thanks for watching",
    r"thank you for watching",
    r"please subscribe",
    r"hit the bell",
    r"like,? share,? (and )?subscribe",
    r"subtitles? by",
    r"amara\.org",
    r"transcription by",
    r"www\.[a-z]+\.[a-z]{2,}",
    r"videa\b",
    r"字幕",
    r"ご視聴ありがとうございました",
]
HALL = re.compile("|".join(PATTERNS), re.I)
TS = re.compile(r"(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})")
META = re.compile(r"^(WEBVTT|NOTE|\d+$|\d{2}:\d{2}:\d{2}\.)")


def secs(t: str) -> float:
    h, m, rest = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def parse(path: Path) -> list[dict]:
    out = []
    for block in path.read_text(encoding="utf-8", errors="replace").split("\n\n"):
        m = TS.search(block)
        if not m:
            continue
        body = [l for l in block.split("\n") if not META.match(l)]
        out.append({"s": secs(m.group(1)), "e": secs(m.group(2)),
                    "ts": m.group(0), "block": block,
                    "body": body, "text": " ".join(body).strip()})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("vtt", help="re-transcribed VTT to clean")
    ap.add_argument("--source", help="pre-re-transcription VTT to recover real text from")
    ap.add_argument("--output", help="write here (default: in place)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    path = Path(a.vtt)
    cues = parse(path)
    src = parse(Path(a.source)) if a.source else []

    hits = [c for c in cues if HALL.search(c["text"])]
    if not hits:
        print("no known hallucination phrases found")
        # Still worth reporting the risk surface.
        short = [c for c in cues if c["e"] - c["s"] < 1.0]
        print(f"({len(short)} of {len(cues)} cues are under 1s — the span where "
              f"these appear, so re-check after any re-transcription)")
        return 0

    print(f"{len(hits)} hallucinated cue(s) of {len(cues)}:\n")
    durs = [c["e"] - c["s"] for c in hits]
    print(f"  duration range: {min(durs):.2f}s – {max(durs):.2f}s "
          f"(median {sorted(durs)[len(durs)//2]:.2f}s)\n")

    text = path.read_text(encoding="utf-8", errors="replace")
    blocks = text.split("\n\n")
    replaced = 0
    for c in hits:
        speaker = ""
        if ":" in c["text"]:
            head = c["text"].split(":", 1)[0]
            if len(head) <= 40:
                speaker = head
        orig = ""
        if src:
            overlapping = [s for s in src if min(c["e"], s["e"]) - max(c["s"], s["s"]) > 0]
            orig = " ".join(re.sub(r"^[^:]{1,40}: ", "", s["text"]) for s in overlapping).strip()
        new_text = orig or "[inaudible]"
        new_line = f"{speaker}: {new_text}" if speaker else new_text
        print(f"  {c['ts'].split(' ')[0]}  ({c['e']-c['s']:.2f}s)")
        print(f"     was: {c['text'][:76]}")
        print(f"     now: {new_line[:76]}")
        if not a.dry_run:
            for i, b in enumerate(blocks):
                if b == c["block"]:
                    keep = [l for l in b.split("\n") if META.match(l)]
                    blocks[i] = "\n".join(keep + [new_line])
                    replaced += 1
                    break

    if a.dry_run:
        print("\n--dry-run: nothing written")
        return 0
    out = Path(a.output) if a.output else path
    out.write_text("\n\n".join(blocks), encoding="utf-8")
    print(f"\nreverted {replaced} cue(s) -> {out}")
    if not src:
        print("NOTE: no --source given, so those cues now read [inaudible]. "
              "Re-run with --source to recover the real words.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
