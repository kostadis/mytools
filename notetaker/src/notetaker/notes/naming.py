"""
Notes-filename derivation and component sanitization (spec 005, contracts/notes-naming.md).

Pure functions — no IO, no logging. The orchestrator in notes/__init__.py is
responsible for the actual file rename / write; this module only computes the
target filename.
"""

from __future__ import annotations

import re

from notetaker.contracts.recording_meta import RecordingMetaSchema


_DISALLOWED = re.compile(r"[/\\:*?\"<>|\x00-\x1F\x7F]")
_WHITESPACE_RUN = re.compile(r"\s+")
_FALLBACK_TITLE = "untitled"
_FALLBACK_SUMMARY = "no-summary"
_FALLBACK_DATE = "undated"


def sanitize_component(
    raw: str | None,
    *,
    max_chars: int,
    fallback: str,
) -> str:
    """
    Apply the sanitization pipeline from contracts/notes-naming.md.

    Steps:
      1. None → fallback.
      2. Strip leading/trailing whitespace.
      3. Replace disallowed characters with a single space.
      4. Collapse whitespace runs.
      5. Strip leading dots (avoid hidden files on Unix).
      6. Truncate to max_chars (word-boundary cut if a boundary exists in the
         last 25% of the truncated window).
      7. Empty after pipeline → fallback.
    """
    if raw is None:
        return fallback
    s = raw.strip()
    s = _DISALLOWED.sub(" ", s)
    s = _WHITESPACE_RUN.sub(" ", s).strip()
    s = s.lstrip(".")
    if len(s) > max_chars:
        cutoff = max_chars
        # Look for a word boundary in the last quarter of the window.
        window_start = max(0, cutoff - max(1, max_chars // 4))
        space_idx = s.rfind(" ", window_start, cutoff)
        if space_idx > 0:
            s = s[:space_idx]
        else:
            s = s[:cutoff]
        s = s.rstrip()
    if not s:
        return fallback
    return s


def _resolve_date(meta: RecordingMetaSchema) -> str:
    if meta.recording_date:
        return meta.recording_date
    # created_at is ISO-8601; the date is the first 10 characters.
    if meta.created_at and len(meta.created_at) >= 10 and meta.created_at[4] == "-" and meta.created_at[7] == "-":
        return meta.created_at[:10]
    return _FALLBACK_DATE


def derive_notes_filename(
    meta: RecordingMetaSchema,
    *,
    max_chars: int,
    summary_max_chars: int,
    collision_suffix: str | None = None,
) -> str:
    """
    Compose the human-readable notes filename per contracts/notes-naming.md.

    Returns a filename (no directory part). The total length excluding ".md"
    is ≤ max_chars; the ".md" suffix is always appended.
    """
    date = _resolve_date(meta)
    summary = sanitize_component(
        meta.summary, max_chars=summary_max_chars, fallback=_FALLBACK_SUMMARY
    )

    # Compute the title budget: total - date - separators - summary - suffix.
    fixed_overhead = (
        len(date)
        + len("--")
        + len("--")
        + len(summary)
    )
    if collision_suffix is not None:
        fixed_overhead += len("--") + len(collision_suffix)
    title_budget = max(1, max_chars - fixed_overhead)

    title = sanitize_component(
        meta.meeting_title, max_chars=title_budget, fallback=_FALLBACK_TITLE
    )

    parts = [date, title, summary]
    if collision_suffix is not None:
        parts.append(collision_suffix)
    name = "--".join(parts) + ".md"

    # Defensive: if title fallback itself overflows the budget, hard-cap.
    if len(name) - len(".md") > max_chars:
        # Trim the title to fit. This branch is reachable only when the
        # fallback is longer than the computed budget (extremely rare).
        overflow = (len(name) - len(".md")) - max_chars
        title = title[: max(1, len(title) - overflow)]
        parts[1] = title
        name = "--".join(parts) + ".md"
    return name
