#!/usr/bin/env python3
"""Parse a Zoom WebVTT transcript into timestamped, speaker-grouped cue
groups, and render (cue groups + replacement text) back into the same
WebVTT shape (WEBVTT header, numbered cues, HH:MM:SS.mmm --> HH:MM:SS.mmm,
"Speaker: text" body) that ``vtt-to-tts/transcript_to_mp3.py``'s
``_VTT_SPEAKER`` parser expects, so this stays a drop-in input for the
rest of the pipeline.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_VTT_TIMESTAMP = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})"
)
_VTT_SPEAKER = re.compile(r"^([^:\n]+?):\s*(.*)$", re.DOTALL)

# Zoom's own system-generated caption label for a screen/audio-share window
# (e.g. "Audio shared by Kostadis Roussos: ..."), not a real participant.
# Found empirically (2026-07-19, obelisk session 006): faster-whisper
# reliably hallucinates video-outro phrases ("Thanks for watching!",
# "Audio shared by X: [fabricated content]") when re-transcribing these
# spans, regardless of clip length -- there's often no real speech there
# to transcribe. Keep Zoom's own text unchanged instead.
_SYSTEM_CAPTION_SPEAKER_RE = re.compile(r"^Audio shared by\b", re.IGNORECASE)


def is_system_caption_speaker(speaker: str) -> bool:
    """True for Zoom's own system-caption speaker labels rather than a real
    participant. Cue-groups with this speaker should keep Zoom's original
    text unchanged and never be sent to the Spark for re-transcription."""
    return bool(_SYSTEM_CAPTION_SPEAKER_RE.match(speaker.strip()))


@dataclass
class Cue:
    start: float
    end: float
    speaker: str
    text: str


@dataclass
class CueGroup:
    start: float
    end: float
    speaker: str
    original_text: str
    cue_count: int = 1


def _ts_to_seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def seconds_to_timestamp(seconds: float) -> str:
    seconds = max(seconds, 0.0)
    total_ms = round(seconds * 1000)
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def parse_zoom_vtt(text: str) -> list[Cue]:
    """Parse a Zoom WebVTT export into a flat list of timestamped cues.

    Continuation cues (a cue body with no "Speaker:" prefix — Zoom wraps a
    long utterance across consecutive cues) are merged into the previous
    cue, extending its end time and appending its text, mirroring how
    transcript_to_mp3.py's parse_webvtt treats the same continuations.
    """
    cues: list[Cue] = []
    for block in re.split(r"\n\s*\n", text):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        ts_idx = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if ts_idx is None:
            continue
        m = _VTT_TIMESTAMP.search(lines[ts_idx])
        if not m:
            continue
        start = _ts_to_seconds(*m.groups()[0:4])
        end = _ts_to_seconds(*m.groups()[4:8])
        body = " ".join(ln.strip() for ln in lines[ts_idx + 1:]).strip()
        if not body:
            continue
        sm = _VTT_SPEAKER.match(body)
        if sm:
            speaker = sm.group(1).strip()
            content = sm.group(2).strip()
            if content:
                cues.append(Cue(start=start, end=end, speaker=speaker, text=content))
        elif cues:
            prev = cues[-1]
            prev.text = f"{prev.text} {body}".strip()
            prev.end = end
    return cues


def _split_long_cue(cue: Cue, max_group_seconds: float) -> list[Cue]:
    """A single Zoom cue whose own duration already exceeds the cap gets
    pre-split into sequential sub-clips — faster-whisper clips >30s are a
    known rough edge (SYSTRAN/faster-whisper#1355), so we never hand it one
    that long."""
    duration = cue.end - cue.start
    if duration <= max_group_seconds:
        return [cue]
    n = math.ceil(duration / max_group_seconds)
    step = duration / n
    return [
        Cue(start=cue.start + i * step, end=cue.start + (i + 1) * step,
            speaker=cue.speaker, text=cue.text)
        for i in range(n)
    ]


def group_cues(cues: list[Cue], max_group_seconds: float = 25.0) -> list[CueGroup]:
    """Merge consecutive same-speaker cues into groups capped at
    max_group_seconds of total span, giving faster-whisper more acoustic
    context per call than Zoom's often-tiny individual cues, while staying
    safely under Whisper's native 30s window."""
    expanded: list[Cue] = []
    for cue in cues:
        expanded.extend(_split_long_cue(cue, max_group_seconds))

    groups: list[CueGroup] = []
    for cue in expanded:
        if groups:
            last = groups[-1]
            if cue.speaker == last.speaker and (cue.end - last.start) <= max_group_seconds:
                last.end = cue.end
                last.original_text = f"{last.original_text} {cue.text}".strip()
                last.cue_count += 1
                continue
        groups.append(CueGroup(start=cue.start, end=cue.end, speaker=cue.speaker,
                                original_text=cue.text))
    return groups


def render_vtt(groups: list[CueGroup], texts: list[str]) -> str:
    """Render cue groups with replacement `texts` (same order/length as
    `groups`) into a WebVTT string matching the ``Speaker: text`` shape
    ``transcript_to_mp3.py``'s ``_VTT_SPEAKER`` regex parses."""
    if len(texts) != len(groups):
        raise ValueError(f"texts length {len(texts)} != groups length {len(groups)}")
    lines = ["WEBVTT", ""]
    for i, (group, text) in enumerate(zip(groups, texts), start=1):
        lines.append(str(i))
        lines.append(f"{seconds_to_timestamp(group.start)} --> {seconds_to_timestamp(group.end)}")
        lines.append(f"{group.speaker}: {text}")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"
