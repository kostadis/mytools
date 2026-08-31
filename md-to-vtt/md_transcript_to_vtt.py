#!/usr/bin/env python3
"""Convert a speaker-labelled Zoom markdown transcript into WebVTT.

The Zoom `.md` export (`**speaker:** text` per utterance) is the decisive
record of who said what, but CampaignGenerator's Stage 1/2 (`enhance_summary`,
`scene_extract`) only read `*.vtt` — and the whisper-derived `session_*.vtt`
siblings carry no speaker labels at all.

`session_doc.io.parse_vtt` strips the WEBVTT header, cue numbers, timestamps
and NOTE blocks, keeping every other non-blank line verbatim. So the payload
this writes — `speaker: text` — is exactly what reaches the model.

Two markdown shapes are handled, and they time the output differently:

  `**kostadis:** text`               -> SYNTHETIC times, monotonic and
                                        proportional to utterance length.
  `[01:30:40] **kostadis:** text`    -> REAL times, from the source, at the
                                        one-second resolution it records.

In the timestamped shape the source gives a start and no end, so an end is
derived: it never runs past the next utterance's start, and never stretches a
short line across a silence. Bare `[HH:MM:SS]` markers *inside* a line are the
exporter's minute ticks, not speech, and are stripped from the text.

Usage:
  md_transcript_to_vtt.py IN.md OUT.vtt
"""

import re
import sys
from pathlib import Path

#: `[00:12:34] **kostadis:** text` — the timestamp is optional.
UTTERANCE_RE = re.compile(
    r"^(?:\[(\d{2}):(\d{2}):(\d{2})\]\s*)?\*\*([^*]+?):\*\*\s*(.*)$"
)
#: `[00:12:34] text` — timestamped, but the exporter lost the speaker label.
STAMPED_RE = re.compile(r"^\[(\d{2}):(\d{2}):(\d{2})\]\s*(.*)$")
#: The exporter's minute ticks, sprinkled mid-sentence. Position, not speech.
INLINE_MARKER_RE = re.compile(r"\[\d{2}:\d{2}:\d{2}\]")
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


def clean_body(text: str) -> str:
    """Drop the exporter's inline minute markers and tidy the whitespace."""
    return re.sub(r"\s+", " ", INLINE_MARKER_RE.sub(" ", text)).strip()


def parse_markdown(text: str):
    """Return (utterances, merged) — [[start|None, speaker, text]], and a log."""
    utterances: list[list] = []
    merged: list[str] = []

    def append_to_previous(lineno: int, line: str) -> None:
        body = clean_body(line)
        if not body:
            return
        if utterances:
            utterances[-1][2] = (utterances[-1][2] + " " + body).strip()
            merged.append(f"  line {lineno}: {body!r} -> appended to "
                          f"{utterances[-1][1]!r}")
        else:
            merged.append(f"  line {lineno}: {body!r} -> DROPPED (no preceding speaker)")

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or HEADING_RE.match(line):
            continue
        m = UTTERANCE_RE.match(line)
        if m:
            hh, mm, ss, speaker, body = m.groups()
            start = None if hh is None else int(hh) * 3600 + int(mm) * 60 + int(ss)
            utterances.append([start, speaker.strip(), clean_body(body)])
            continue
        # Timestamped but unlabelled, or a dangling continuation: both are text
        # whose speaker the source does not state. Append to the preceding
        # utterance and say so — never drop it, never guess an attribution.
        stamped = STAMPED_RE.match(line)
        append_to_previous(lineno, stamped.group(4) if stamped else line)

    return [u for u in utterances if u[2]], merged


def assign_real_times(utterances) -> list[tuple[float, float]]:
    """Turn one start-per-utterance into (start, end) pairs.

    The source stamps a start at one-second resolution and nothing else, so
    consecutive utterances routinely share a second. Each run of equal starts
    divides the interval up to the next distinct start, in proportion to how
    much text each carries — so cues stay ordered and never overlap. The
    interval is capped by the spoken-length estimate, so a line followed by
    five minutes of silence gets its own length, not the silence.
    """
    times: list[tuple[float, float]] = []
    n = len(utterances)
    i = 0
    while i < n:
        start = utterances[i][0]
        j = i
        while j < n and utterances[j][0] == start:
            j += 1
        nxt = utterances[j][0] if j < n else None
        estimates = [max(MIN_CUE_SECONDS, len(u[2]) / CHARS_PER_SECOND)
                     for u in utterances[i:j]]
        total = sum(estimates)
        span = total if nxt is None else min(total, float(nxt - start))
        t = float(start)
        for est in estimates:
            dur = span * (est / total)
            times.append((t, t + dur))
            t += dur
        i = j
    return times


def assign_synthetic_times(utterances) -> list[tuple[float, float]]:
    times: list[tuple[float, float]] = []
    t = 0.0
    for _, _, body in utterances:
        dur = max(MIN_CUE_SECONDS, len(body) / CHARS_PER_SECOND)
        times.append((t, t + dur))
        t += dur + GAP_SECONDS
    return times


def to_vtt(utterances, source_name: str) -> tuple[str, bool]:
    """Render the tape. Returns (text, real_times)."""
    real = all(u[0] is not None for u in utterances)
    times = assign_real_times(utterances) if real else assign_synthetic_times(utterances)

    # One-line NOTE comments, not a NOTE block: session_doc.io.parse_vtt drops
    # only lines that START with NOTE, so a multi-line block would leak its
    # continuation lines straight into the dialogue handed to the model.
    comments = [
        f"Converted from the speaker-labelled Zoom transcript {source_name}.",
        "Speaker labels and utterance text are verbatim from that source.",
    ]
    if real:
        comments += [
            "Cue STARTS are the source's own timestamps, at its one-second",
            "resolution. Cue ENDS are derived: the source records no end, so each",
            "cue runs for its estimated spoken length, clipped at the next cue's",
            "start. Utterances sharing a second split that second between them.",
        ]
    else:
        comments += [
            "Timestamps are SYNTHETIC. The source markdown carries no timing, so",
            "cue times are monotonic and proportional to utterance length only;",
            "they do not correspond to real recording offsets.",
        ]

    out = ["WEBVTT", ""]
    for comment in comments:
        out += [f"NOTE {comment}", ""]
    for i, ((_, speaker, body), (start, end)) in enumerate(zip(utterances, times), 1):
        out += [str(i), f"{timestamp(start)} --> {timestamp(end)}",
                f"{speaker}: {body}", ""]
    return "\n".join(out), real


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    utterances, merged = parse_markdown(src.read_text(encoding="utf-8"))
    if not utterances:
        print(f"Error: no `**speaker:**` utterances found in {src}", file=sys.stderr)
        return 1
    text, real = to_vtt(utterances, src.name)
    dst.write_text(text, encoding="utf-8")

    speakers: dict[str, int] = {}
    for _, s, _ in utterances:
        speakers[s] = speakers.get(s, 0) + 1
    print(f"{src.name}\n  -> {dst.name}")
    print(f"  {len(utterances):,} cues, {dst.stat().st_size:,} bytes")
    print(f"  timing: {'REAL (from the source stamps)' if real else 'SYNTHETIC'}")
    print("  speakers: " + ", ".join(f"{s} ({n})" for s, n in
                                     sorted(speakers.items(), key=lambda kv: -kv[1])))
    if merged:
        print(f"  {len(merged)} unattributed line(s) merged into the previous cue:")
        for line in merged:
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
