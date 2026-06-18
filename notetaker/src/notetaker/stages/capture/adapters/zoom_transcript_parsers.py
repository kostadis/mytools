"""
Format-detection dispatcher and three parsers that all produce a
TranscriptSchema. Lives under capture/adapters/ because the three input
formats are all rooted in Zoom workflows (Article I.2 — platform-specific
knowledge stays in the adapters layer).

Public surface:
    parse_transcript_file(path, recording_url="") -> TranscriptSchema

Detection order (research.md D3):
    1. WebVTT     -> first non-blank line begins with "WEBVTT"
    2. JSON       -> file parses as JSON AND validates as TranscriptSchema
    3. Block      -> contains the documented "\\n\\n----\\n\\n" separator
                     OR first non-blank line is followed by an HH:MM:SS line
    4. otherwise  -> raise UnsupportedTranscriptFormatError with the
                     verbatim message from contracts/transcript_input.md
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from notetaker.contracts.transcript import TranscriptSchema, Utterance


_BLOCK_SEPARATOR = "\n\n----\n\n"
# Accepts both HH:MM:SS (recordings >= 1h) and MM:SS (sub-1h), since the
# Zoom Audio Transcript panel shortens to MM:SS for recordings under an
# hour and the documented browser snippet harvests whatever the panel shows.
_BLOCK_TIMESTAMP_RE = re.compile(r"^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})$")
_VTT_TIMESTAMP_RE = re.compile(
    r"^(\d{1,2}:)?(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\s*-->\s*"
    r"(\d{1,2}:)?(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?"
)
_VTT_VOICE_RE = re.compile(r"<v\s+([^>]+)>(.*?)(?:</v>|$)", re.DOTALL)

_REFUSAL_MESSAGE = (
    "Unsupported transcript format. Expected one of:\n"
    "  - browser-scrape block format (.txt produced by the documented browser snippet)\n"
    "  - WebVTT (.vtt downloaded from Zoom Cloud Recording)\n"
    "  - notetaker transcript.json (produced by a successful live capture)\n"
    "\n"
    "See HOWTO.md \"Obtaining a transcript\" for the supported procedures."
)


class UnsupportedTranscriptFormatError(ValueError):
    """Raised when the transcript file matches none of the three supported shapes."""


def parse_transcript_file(path: Path, recording_url: str = "") -> TranscriptSchema:
    text = path.read_text(encoding="utf-8")
    captured_at = _file_captured_at(path)

    fmt = _detect_format(text)
    if fmt == "vtt":
        return _parse_vtt(text, recording_url=recording_url, captured_at=captured_at)
    if fmt == "transcript_json":
        return _parse_transcript_json(text)
    if fmt == "block":
        return _parse_block(text, recording_url=recording_url, captured_at=captured_at)
    raise UnsupportedTranscriptFormatError(_REFUSAL_MESSAGE)


def detect_format(path: Path) -> str:
    """Detect the transcript file's format. Returns the format name or raises."""
    fmt = _detect_format(path.read_text(encoding="utf-8"))
    if fmt is None:
        raise UnsupportedTranscriptFormatError(_REFUSAL_MESSAGE)
    return fmt


def _detect_format(text: str) -> str | None:
    stripped = text.lstrip()
    if stripped.startswith("WEBVTT"):
        return "vtt"
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            try:
                TranscriptSchema.model_validate(data)
                return "transcript_json"
            except Exception:
                pass
    if _BLOCK_SEPARATOR in text:
        return "block"
    lines = [ln for ln in stripped.splitlines() if ln.strip()]
    if len(lines) >= 2 and _BLOCK_TIMESTAMP_RE.match(lines[1].strip()):
        return "block"
    return None


def _file_captured_at(path: Path) -> str:
    try:
        ts = path.stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except OSError:
        return datetime.now(timezone.utc).isoformat()


def _parse_block(text: str, *, recording_url: str, captured_at: str) -> TranscriptSchema:
    utterances: list[Utterance] = []
    blocks = text.split(_BLOCK_SEPARATOR)
    current_speaker = "Unknown"
    current_start: float = 0.0
    saw_speaker = False

    for raw_block in blocks:
        block = raw_block.strip("\n")
        if not block.strip():
            continue
        lines = block.split("\n")
        if len(lines) >= 3 and _BLOCK_TIMESTAMP_RE.match(lines[1].strip()):
            current_speaker = lines[0].strip()
            h, m, s = _BLOCK_TIMESTAMP_RE.match(lines[1].strip()).groups()
            current_start = (int(h) if h else 0) * 3600 + int(m) * 60 + int(s)
            body = "\n".join(lines[2:]).strip()
            saw_speaker = True
        else:
            if not saw_speaker:
                continue
            body = block.strip()
        if not body:
            continue
        utterances.append(
            Utterance(
                start_seconds=float(current_start),
                end_seconds=float(current_start) + 5.0,
                speaker=current_speaker,
                text=body,
            )
        )

    return TranscriptSchema(
        recording_url=recording_url,
        captured_at=captured_at,
        utterances=utterances,
        transcript_unavailable=False,
    )


def _parse_vtt(text: str, *, recording_url: str, captured_at: str) -> TranscriptSchema:
    utterances: list[Utterance] = []
    blocks = re.split(r"\n\s*\n", text.strip())
    for block in blocks:
        if not block.strip() or block.strip().startswith("WEBVTT"):
            continue
        if block.strip().startswith("NOTE"):
            continue
        lines = [ln for ln in block.split("\n") if ln.strip()]
        ts_idx = None
        for idx, line in enumerate(lines):
            if _VTT_TIMESTAMP_RE.search(line):
                ts_idx = idx
                break
        if ts_idx is None:
            continue
        ts_match = _VTT_TIMESTAMP_RE.search(lines[ts_idx])
        start_seconds = _vtt_ts_to_seconds(*ts_match.groups()[:4])
        end_seconds = _vtt_ts_to_seconds(*ts_match.groups()[4:])
        if end_seconds <= start_seconds:
            end_seconds = start_seconds + 0.001

        payload_lines = lines[ts_idx + 1 :]
        if not payload_lines:
            continue
        payload = "\n".join(payload_lines).strip()

        speaker, body = _vtt_extract_speaker(payload)
        body = body.strip()
        if not body:
            continue
        utterances.append(
            Utterance(
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                speaker=speaker,
                text=body,
            )
        )

    return TranscriptSchema(
        recording_url=recording_url,
        captured_at=captured_at,
        utterances=utterances,
        transcript_unavailable=False,
    )


def _vtt_ts_to_seconds(hours: str | None, minutes: str, seconds: str, millis: str | None) -> float:
    h = int(hours.rstrip(":")) if hours else 0
    m = int(minutes)
    s = int(seconds)
    ms = int((millis or "0").ljust(3, "0")[:3])
    return h * 3600 + m * 60 + s + ms / 1000.0


def _vtt_extract_speaker(payload: str) -> tuple[str, str]:
    voice_match = _VTT_VOICE_RE.search(payload)
    if voice_match:
        speaker = voice_match.group(1).strip()
        before = payload[: voice_match.start()]
        inside = voice_match.group(2)
        after = payload[voice_match.end():]
        body = (before + inside + after).strip()
        return speaker, body
    return "Unknown", payload


def _parse_transcript_json(text: str) -> TranscriptSchema:
    return TranscriptSchema.model_validate(json.loads(text))
