"""
claude_api.py — Shared Claude API utilities for all pdf-to-5etools converters.

All converter-specific logic (system prompts, text pre/post-processing) stays in
each converter.  This module contains only the pieces that would otherwise be
duplicated verbatim: response parsing, partial recovery, retry logic, the
single constant for output-token budget, and shared prompt fragments.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import anthropic

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_OUTPUT_TOKENS = 20_000

# Shared prompt fragment — tag rules injected into every converter's SYSTEM_PROMPT.
# Update here when the set of supported 5etools inline tags changes.
COMMON_TAG_RULES = """\
- Use {@b text} for bold, {@i text} for italic.
- Use {@creature Name} when a monster name appears.
- Use {@spell Name} for spell names, {@item Name} for magic item names \
(including scrolls: {@item scroll of X}).
- Use {@dice NdN} for dice expressions.
- Only use the tags above — do NOT invent tags like {@scroll}, {@npc}, {@room}, etc."""

# Shared prompt fragment — nesting rules injected into every converter's SYSTEM_PROMPT.
# Update here when section/entries nesting behaviour needs to change across all converters.
COMMON_NESTING_RULES = """\
- Use {"type":"section"} ONLY for major top-level chapters or named locations \
(e.g. "Chapter 1", "A. Prison Facility").
- Sub-areas within a location (e.g. A1, A2, B3 rooms; sub-sections of a chapter) \
must use {"type":"entries"} nested inside their parent section — never as top-level sections.
- Nest sub-sections inside their parent section's entries array.
- In the contents[] TOC, a section's "headers" array lists named sub-sections a reader \
would navigate to. Rules for headers[]:
  - Do NOT repeat the section's own name as a header entry.
  - Named sub-rooms within a location (e.g. A1, A2, C3, E7) go as \
{"header": "name", "depth": 1} objects, not flat strings.
  - Do NOT include generic sub-headings: "Creatures", "Treasure", "Development", \
"Trap", "Hazard", "Tactics", "Morale", "Reward", or stat-block / NPC / \
encounter-group names (e.g. "Klaven Shocktroopers (2)", "Maulvorge")."""


# ---------------------------------------------------------------------------
# Response parsing helpers
# ---------------------------------------------------------------------------

def _recover_partial_json(raw: str) -> list[Any]:
    """Try to salvage complete JSON entries from a truncated or malformed array.

    Scans backwards for the last top-level closing brace and tries to close the
    array at that position.  Returns [] when nothing can be recovered.
    """
    start = raw.find('[')
    if start == -1:
        return []
    body = raw[start:]
    for sep in ['\n  },', '\n  }', '},', '}']:
        pos = body.rfind(sep)
        if pos == -1:
            continue
        candidate = body[:pos + len(sep.rstrip(','))] + '\n]'
        try:
            result = json.loads(candidate)
            if isinstance(result, list) and result:
                return result
        except json.JSONDecodeError:
            continue
    return []


def _parse_claude_response(raw: str, verbose: bool,
                            debug_dir: Path | None = None,
                            chunk_id: str = "") -> tuple[list[Any], bool]:
    """Parse a raw Claude text response into a JSON list.

    Returns ``(entries, parse_ok)``.  ``parse_ok`` is ``False`` when the raw
    JSON was malformed; ``entries`` may still be non-empty if partial recovery
    succeeded.
    """
    raw = raw.strip()
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / f"{chunk_id}-response.txt").write_text(raw, encoding="utf-8")

    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        result = json.loads(raw)
        if not isinstance(result, list):
            result = [result]
        if debug_dir:
            (debug_dir / f"{chunk_id}-parsed.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        return result, True
    except json.JSONDecodeError as e:
        print(f"    [WARN] JSON parse error in {chunk_id}: {e}", flush=True)
        print(f"    Raw response (first 400 chars): {raw[:400]}", flush=True)
        if debug_dir:
            (debug_dir / f"{chunk_id}-parse-error.txt").write_text(
                f"Error: {e}\n\n{raw}", encoding="utf-8"
            )
        recovered = _recover_partial_json(raw)
        if recovered:
            print(f"    [RECOVER] Salvaged {len(recovered)} entries from partial JSON.",
                  flush=True)
        return recovered, False


# ---------------------------------------------------------------------------
# Core API call with retry logic
# ---------------------------------------------------------------------------

def call_claude(client: anthropic.Anthropic, chunk_text: str,
                model: str, system_prompt: str, verbose: bool,
                debug_dir: Path | None = None,
                chunk_id: str = "chunk-0000") -> list[Any]:
    """Send *chunk_text* to Claude and return a parsed JSON list of entries.

    Handles two truncation scenarios automatically:

    * ``max_tokens`` with parseable output  — re-processes the second half of
      the *input* chunk to capture sections that Claude didn't reach.
    * ``max_tokens`` or ``end_turn`` with malformed / empty JSON output — splits
      the input chunk in two and retries each half independently.

    The ``system_prompt`` parameter lets each converter inject its own prompt
    without duplicating any of this logic.
    """
    if verbose:
        print(f"    Sending {len(chunk_text):,} chars to Claude...", flush=True)
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / f"{chunk_id}-input.txt").write_text(chunk_text, encoding="utf-8")

    message = client.messages.create(
        model=model,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": chunk_text}],
    )
    result, parse_ok = _parse_claude_response(
        message.content[0].text, verbose, debug_dir=debug_dir, chunk_id=chunk_id
    )

    half = len(chunk_text) // 2
    split_point = chunk_text.rfind('\n--- Page', 0, half + 1)
    if split_point == -1:
        split_point = half

    def _split_retry(reason: str) -> None:
        nonlocal result
        print(f"    [RETRY] {chunk_id} {reason} — splitting and retrying both halves...",
              flush=True)
        result = []
        for part_idx, part in enumerate([chunk_text[:split_point], chunk_text[split_point:]]):
            if not part.strip():
                continue
            sub_id = f"{chunk_id}-part{part_idx}"
            print(f"      Retrying {sub_id} ({len(part):,} chars)...", flush=True)
            result.extend(call_claude(client, part, model, system_prompt, verbose,
                                      debug_dir=debug_dir, chunk_id=sub_id))

    if message.stop_reason == 'max_tokens':
        if result:
            # Valid JSON but output was cut off — re-process only the tail.
            print(f"    [WARN] {chunk_id} hit max_tokens with {len(result)} entries captured"
                  f" — re-processing tail to recover missing content...", flush=True)
            tail = chunk_text[split_point:]
            if tail.strip():
                result.extend(call_claude(client, tail, model, system_prompt, verbose,
                                          debug_dir=debug_dir, chunk_id=f"{chunk_id}-tail"))
        else:
            _split_retry("hit max_tokens with no parseable output")
    elif not parse_ok and not result:
        # JSON-shaped response that failed to parse — could be end_turn misreported
        # or genuine malformation.  Retry if it looks like JSON; warn if refusal.
        raw_text = message.content[0].text
        stripped = re.sub(r"^```(?:json)?\s*", "", raw_text.strip())
        if stripped.startswith('[') or stripped.startswith('{'):
            _split_retry(f"returned malformed JSON (stop_reason={message.stop_reason!r})")
        else:
            print(f"    [WARN] {chunk_id} returned no parseable JSON "
                  f"(stop_reason={message.stop_reason!r}).", flush=True)
            print(f"    Response preview: {raw_text[:300]!r}", flush=True)
            if not debug_dir:
                print("    [TIP]  Re-run with --debug-dir DIR to save full API responses.",
                      flush=True)
    elif not parse_ok and result:
        print(f"    [WARN] {chunk_id} JSON was truncated; partial recovery kept "
              f"{len(result)} entries. Some content may be missing.", flush=True)
    elif not result:
        raw_preview = message.content[0].text[:300] if message.content else "(empty)"
        print(f"    [WARN] {chunk_id} returned no parseable JSON "
              f"(stop_reason={message.stop_reason!r}).", flush=True)
        print(f"    Response preview: {raw_preview!r}", flush=True)
        if not debug_dir:
            print("    [TIP]  Re-run with --debug-dir DIR to save full API responses.",
                  flush=True)

    return result
