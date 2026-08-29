#!/usr/bin/env python3
"""Look up Zoom's original text for a cue group in a retranscribed VTT.

Only useful when the VTT being spell-passed is itself an audio-to-vtt
retranscription output (`*.retranscribed.vtt` / `*.retranscribed.cleaned.vtt`)
-- lets the skill cross-check an ambiguous unknown-token candidate against
what Zoom's own (unbiased) transcription heard at the exact same moment.
This is the same manual technique used during the obelisk session 006 pass:
it identified "Zerabira" as a mangled "Veyra" (Zoom's original at that cue
said "Vera is a 19") and reversed a wrong "Redbrand Exo" -> Redbrand call
once Zoom's original turned out to be unrelated gibberish at that exact
timestamp ("Welcome Maxwell Press PS6 Short Short Short") -- in both cases
the retranscribed text alone, without the comparison, was not enough to
tell a real correction from ASR noise that happened to resemble one.

Reuses audio-to-vtt's vtt_scaffold.py cue-grouping so the group boundaries
here exactly match what retranscribe.py produced -- no separate alignment
logic. --max-group-seconds must match whatever retranscribe.py was run
with for this pair (default 25.0, same as retranscribe.py's own default).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "audio-to-vtt"))
import vtt_scaffold  # noqa: E402

_RETRANSCRIBED_SUFFIXES = (".retranscribed.cleaned", ".retranscribed")


def zoom_original_path(vtt_path: Path) -> Path | None:
    """'<x>.transcript.retranscribed.cleaned.vtt' or
    '<x>.transcript.retranscribed.vtt' -> '<x>.transcript.vtt'. Returns None
    if `vtt_path` doesn't look like a retranscription output at all (plain
    Zoom/Otter VTTs have no Zoom-original sibling to cross-check against --
    they ARE the original)."""
    stem = vtt_path.stem  # strips .vtt
    for suffix in _RETRANSCRIBED_SUFFIXES:
        if stem.endswith(suffix):
            return vtt_path.with_name(stem[: -len(suffix)] + ".vtt")
    return None


def find_zoom_original(
    vtt_path: Path, context: str, max_group_seconds: float = 25.0,
) -> dict | None:
    """Return {"start", "end", "speaker", "zoom_text", "retranscribed_text"}
    for the cue group whose retranscribed text contains `context`
    (case-insensitive substring), or None if there's no Zoom-original
    sibling, the pair doesn't align (different --max-group-seconds than the
    original retranscribe.py run), or no cue matches."""
    zoom_path = zoom_original_path(vtt_path)
    if zoom_path is None or not zoom_path.exists():
        return None

    retr_cues = vtt_scaffold.parse_zoom_vtt(
        vtt_path.read_text(encoding="utf-8", errors="replace"))
    zoom_cues = vtt_scaffold.parse_zoom_vtt(
        zoom_path.read_text(encoding="utf-8", errors="replace"))
    zoom_groups = vtt_scaffold.group_cues(zoom_cues, max_group_seconds=max_group_seconds)

    if len(retr_cues) != len(zoom_groups):
        return None

    context_lower = context.strip().lower()
    if not context_lower:
        return None
    for i, cue in enumerate(retr_cues):
        if context_lower in cue.text.lower():
            g = zoom_groups[i]
            return {
                "start": vtt_scaffold.seconds_to_timestamp(g.start),
                "end": vtt_scaffold.seconds_to_timestamp(g.end),
                "speaker": g.speaker,
                "zoom_text": g.original_text,
                "retranscribed_text": cue.text,
            }
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vtt", required=True, type=Path,
                     help="The retranscribed/cleaned VTT being spell-passed")
    ap.add_argument("--context", required=True,
                     help="A short substring from the candidate's context "
                          "(e.g. find_unknowns.py's context excerpt) to locate the cue group")
    ap.add_argument("--max-group-seconds", type=float, default=25.0,
                     help="Must match whatever retranscribe.py used to produce --vtt")
    args = ap.parse_args()

    result = find_zoom_original(args.vtt, args.context, args.max_group_seconds)
    if result is None:
        print(json.dumps(None))
        return 0
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
