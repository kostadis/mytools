"""
Deterministic Markdown assembly: slide content + parsed transcript -> working doc.

This is a pure function. Identical inputs produce byte-identical output. There
are no timestamps, no env reads, no random ordering — the function exists so the
LLM render call (which is non-deterministic) has a stable, inspectable input
artifact.

See contracts/working_doc.md for the complete structure and invariants.
"""

from __future__ import annotations

from notetaker.contracts.slide_content import SlideContent, SlideContentSchema
from notetaker.contracts.transcript import TranscriptSchema, Utterance


def build_working_doc(
    slide_content: SlideContentSchema,
    transcript: TranscriptSchema,
) -> str:
    slides = slide_content.slides
    utterances = transcript.utterances

    out: list[str] = []
    out.append("# Working Doc — slides + transcript")
    out.append("")
    out.append(
        "This is a deterministic concatenation of the recovered slide content and "
        "the meeting transcript. It is the input to a single LLM render pass that "
        "produces the polished notes."
    )
    out.append("")
    out.append(f"- Slides: {len(slides)} unique, in extraction order")
    out.append(f"- Utterances: {len(utterances)}")
    if utterances:
        out.append(
            f"- Transcript span: {_fmt_hms(utterances[0].start_seconds)} → "
            f"{_fmt_hms(utterances[-1].start_seconds)}"
        )
    out.append("")
    out.append("## Slides")
    out.append("")
    for idx, slide in enumerate(slides, start=1):
        out.append(_format_slide(idx, slide))
        out.append("")

    out.append("## Transcript")
    out.append("")
    out.append(_format_transcript(utterances))

    return "\n".join(out).rstrip("\n") + "\n"


def _format_slide(idx: int, slide: SlideContent) -> str:
    title = slide.title.strip() or "(no title)"
    bullets = slide.bullets or []
    visual = slide.visual_description.strip()
    raw_ocr = slide.raw_ocr.strip()

    parts: list[str] = []
    parts.append(f"### Slide {idx} (`{slide.slide_id}`): {title}")

    if bullets:
        parts.append("")
        parts.extend(f"- {b}" for b in bullets)

    if visual:
        parts.append("")
        parts.append(f"_Visual:_ {visual}")

    has_structure = bool(slide.title.strip() or bullets or visual)
    if not has_structure and raw_ocr:
        # FR-006 raw-OCR fallback — surface verbatim when no structured fields landed.
        parts.append("")
        parts.append("_Raw text on slide:_")
        parts.append("")
        parts.append(raw_ocr)

    return "\n".join(parts)


def _format_transcript(utterances: list[Utterance]) -> str:
    if not utterances:
        return "(transcript empty)\n"

    parts: list[str] = []
    last_speaker: str | None = None
    last_start: float | None = None
    for u in utterances:
        if u.speaker != last_speaker or u.start_seconds != last_start:
            if parts:
                parts.append("")
            parts.append(f"**{u.speaker} [{_fmt_hms(u.start_seconds)}]**")
            parts.append("")
            last_speaker = u.speaker
            last_start = u.start_seconds
        parts.append(u.text)
    return "\n".join(parts)


def _fmt_hms(seconds: float) -> str:
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"
