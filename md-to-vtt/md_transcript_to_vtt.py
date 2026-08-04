#!/usr/bin/env python3
"""Convert a speaker-labelled Zoom markdown transcript into WebVTT.

The Zoom `.md` export (`**speaker:** text` per utterance) is the decisive
record of who said what, but CampaignGenerator's Stage 1/2 (`enhance_summary`,
`scene_extract`) only read `*.vtt` — and the whisper-derived `session_*.vtt`
siblings carry no speaker labels at all.

`session_doc.io.parse_vtt` strips the WEBVTT header, cue numbers, timestamps
and NOTE blocks, keeping every other non-blank line verbatim. So the payload
this writes — `speaker: text` — is exactly what reaches the model.

Timestamps are SYNTHETIC. The source markdown has none. They are monotonic and
proportional to utterance length so the file is well-formed WebVTT; they do NOT
correspond to real recording offsets. Nothing downstream reads them (parse_vtt
discards them), and the file says so in a NOTE block.

Usage:
  md_transcript_to_vtt.py IN.md OUT.vtt
"""

import re
import sys
from pathlib import Path

UTTERANCE_RE = re.compile(r"^\*\*([^*]+?):\*\*\s*(.*)$")
HEADING_RE = re.compile(r"^#{1,6}\s")

CHARS_PER_SECOND = 15.0   # ~180 wpm conversational
MIN_CUE_SECONDS = 1.0
GAP_SECONDS = 0.2


def timestamp(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def parse_markdown(text: str):
    """Return (utterances, merged) — [(speaker, text)], and merge log lines."""
    utterances: list[list[str]] = []
    merged: list[str] = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or HEADING_RE.match(line):
            continue
        m = UTTERANCE_RE.match(line)
        if m:
            speaker = m.group(1).strip()
            body = m.group(2).strip()
            utterances.append([speaker, body])
            continue
        # Dangling continuation of the previous utterance (Zoom splits a few
        # mid-sentence). Append rather than drop or invent a speaker.
        if utterances:
            utterances[-1][1] = (utterances[-1][1] + " " + line).strip()
            merged.append(f"  line {lineno}: {line!r} -> appended to "
                          f"{utterances[-1][0]!r}")
        else:
            merged.append(f"  line {lineno}: {line!r} -> DROPPED (no preceding speaker)")
    return [(s, t) for s, t in utterances if t], merged


def to_vtt(utterances, source_name: str) -> str:
    # One-line NOTE comments, not a NOTE block: session_doc.io.parse_vtt drops
    # only lines that START with NOTE, so a multi-line block would leak its
    # continuation lines straight into the dialogue handed to the model.
    out = ["WEBVTT", ""]
    for comment in [
        f"Converted from the speaker-labelled Zoom transcript {source_name}.",
        "Speaker labels and utterance text are verbatim from that source.",
        "Timestamps are SYNTHETIC. The source markdown carries no timing, so cue",
        "times are monotonic and proportional to utterance length only; they do",
        "not correspond to real recording offsets.",
    ]:
        out += [f"NOTE {comment}", ""]
    t = 0.0
    for i, (speaker, body) in enumerate(utterances, 1):
        dur = max(MIN_CUE_SECONDS, len(body) / CHARS_PER_SECOND)
        out += [str(i), f"{timestamp(t)} --> {timestamp(t + dur)}",
                f"{speaker}: {body}", ""]
        t += dur + GAP_SECONDS
    return "\n".join(out)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    utterances, merged = parse_markdown(src.read_text(encoding="utf-8"))
    if not utterances:
        print(f"Error: no `**speaker:**` utterances found in {src}", file=sys.stderr)
        return 1
    dst.write_text(to_vtt(utterances, src.name), encoding="utf-8")

    speakers: dict[str, int] = {}
    for s, _ in utterances:
        speakers[s] = speakers.get(s, 0) + 1
    print(f"{src.name}\n  -> {dst.name}")
    print(f"  {len(utterances):,} cues, {dst.stat().st_size:,} bytes")
    print("  speakers: " + ", ".join(f"{s} ({n})" for s, n in
                                     sorted(speakers.items(), key=lambda kv: -kv[1])))
    if merged:
        print(f"  {len(merged)} continuation line(s) merged into the previous cue:")
        for line in merged:
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
