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

from adventure_model import BuildContext, ValidationMode, parse_entry

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

MAX_VALIDATION_RETRIES = 1   # how many times to retry when validation finds errors


# ---------------------------------------------------------------------------
# Entry validation helper
# ---------------------------------------------------------------------------

def validate_entries(entries: list[Any], chunk_id: str = "") -> list[str]:
    """Validate a list of parsed JSON entries through the adventure model.

    Returns a list of error messages (empty = valid).
    """
    ctx = BuildContext(mode=ValidationMode.WARN)
    for i, entry in enumerate(entries):
        parse_entry(entry, ctx, f"{chunk_id}[{i}]" if chunk_id else f"[{i}]")
    return ctx.result.errors


def _partition_errors(errors: list[str]) -> tuple[list[str], list[str]]:
    """Split validator errors into (tag_errors, structural_errors).

    Tag errors are deterministic substitutions ({@scroll} -> {@item scroll of X},
    {@npc X} -> plain text, etc.) and are safe to auto-fix via a retry prompt.
    Structural errors (".entries must be an array", "null entry", "image has no
    href", etc.) are scope/shape decisions and must not trigger an LLM retry —
    the project's global CLAUDE.md rule requires a human checkpoint for those.

    The marker ``": unknown tag '{@"`` is the exact substring produced by
    ``adventure_model.validate_tags``; no other error string contains it.
    """
    tag_errs: list[str] = []
    struct_errs: list[str] = []
    for e in errors:
        if ": unknown tag '{@" in e:
            tag_errs.append(e)
        else:
            struct_errs.append(e)
    return tag_errs, struct_errs


def _retry_preserves_shape(original: list[Any], retry: list[Any]) -> bool:
    """Check that a tag-fix retry didn't restructure the entries.

    We require: same length, same top-level entry types in the same order.
    Bare string entries count as type ``"str"``.  Any other shape change
    (added/removed/reordered entries, changed type field, non-dict entries)
    causes the retry to be rejected and the original result kept.
    """
    if len(original) != len(retry):
        return False

    def _shape(e: Any) -> str:
        if isinstance(e, str):
            return "str"
        if isinstance(e, dict):
            return str(e.get("type", "<no-type>"))
        return f"<{type(e).__name__}>"

    return [_shape(e) for e in original] == [_shape(e) for e in retry]


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
                chunk_id: str = "chunk-0000",
                _retry_count: int = 0,
                validate: bool = True) -> list[Any]:
    """Send *chunk_text* to Claude and return a parsed JSON list of entries.

    Handles two truncation scenarios automatically:

    * ``max_tokens`` with parseable output  — re-processes the second half of
      the *input* chunk to capture sections that Claude didn't reach.
    * ``max_tokens`` or ``end_turn`` with malformed / empty JSON output — splits
      the input chunk in two and retries each half independently.

    The ``system_prompt`` parameter lets each converter inject its own prompt
    without duplicating any of this logic.

    ``validate=True`` (default) runs :func:`validate_entries` on the parsed
    result and issues a narrow tag-fix retry on unknown-tag errors. Pass
    ``validate=False`` for payloads whose entry schema is not the
    adventure/entries type — notably bestiary monster objects, which use
    ``type`` as a dict (e.g. ``{"type": "humanoid", "tags": [...]}``) and
    would crash the adventure-entry validator.
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
                                      debug_dir=debug_dir, chunk_id=sub_id,
                                      validate=validate))

    if message.stop_reason == 'max_tokens':
        if result:
            # Valid JSON but output was cut off — re-process only the tail.
            print(f"    [WARN] {chunk_id} hit max_tokens with {len(result)} entries captured"
                  f" — re-processing tail to recover missing content...", flush=True)
            tail = chunk_text[split_point:]
            if tail.strip():
                result.extend(call_claude(client, tail, model, system_prompt, verbose,
                                          debug_dir=debug_dir, chunk_id=f"{chunk_id}-tail",
                                          validate=validate))
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

    # --- Validation retry: narrowly auto-fix unknown tags, surface the rest --
    # See plan: tag errors are deterministic substitutions and safe to delegate
    # to a second LLM pass; structural errors are scope decisions and require a
    # human checkpoint (project global CLAUDE.md rule).
    if validate and result and _retry_count < MAX_VALIDATION_RETRIES:
        errors = validate_entries(result, chunk_id)
        if errors:
            tag_errs, struct_errs = _partition_errors(errors)

            if struct_errs:
                print(f"    [VALIDATE] {chunk_id}: {len(struct_errs)} "
                      f"structural error(s) found — NOT auto-retrying "
                      f"(human review required):", flush=True)
                for e in struct_errs[:5]:
                    print(f"      {e}", flush=True)
                if len(struct_errs) > 5:
                    print(f"      ... and {len(struct_errs) - 5} more",
                          flush=True)
                if debug_dir:
                    (debug_dir / f"{chunk_id}-structural-errors.txt").write_text(
                        "\n".join(struct_errs), encoding="utf-8"
                    )
                # Fall through: keep ``result`` as-is so the human sees the
                # issue at assembly/save time rather than a silent rewrite.

            elif tag_errs:
                result = _retry_tag_fixes(
                    client, result, tag_errs, model, system_prompt,
                    verbose, debug_dir, chunk_id, _retry_count,
                )

    return result


def _retry_tag_fixes(client: anthropic.Anthropic,
                     original_result: list[Any],
                     tag_errors: list[str],
                     model: str, system_prompt: str, verbose: bool,
                     debug_dir: Path | None, chunk_id: str,
                     _retry_count: int) -> list[Any]:
    """Issue a narrowly-scoped retry to fix unknown-tag errors only.

    Hands the model the exact JSON it just produced plus the list of tag
    errors, with an explicit forbid-list against any other change.  After
    the retry, verifies the entry shape is preserved; if not, keeps the
    original result.
    """
    print(f"    [VALIDATE] {chunk_id}: {len(tag_errors)} tag error(s) — "
          f"retrying with narrowed correction prompt...", flush=True)
    for e in tag_errors[:5]:
        print(f"      {e}", flush=True)
    if len(tag_errors) > 5:
        print(f"      ... and {len(tag_errors) - 5} more", flush=True)

    prior_json = json.dumps(original_result, indent=2, ensure_ascii=False)
    correction_prompt = (
        "Your previous response contained unknown {@tag} references.\n"
        "\n"
        "Return the SAME JSON array below with ONLY the listed tag "
        "substitutions applied. Do NOT:\n"
        "  - restructure, reorder, add, remove, merge, or split entries\n"
        "  - change any entry's \"type\" field\n"
        "  - rename sections or headers\n"
        "  - rewrite, rephrase, or re-translate any prose\n"
        "  - edit any text that is not inside an unknown {@tag}\n"
        "\n"
        "Valid replacements: see the tag rules in the system prompt "
        "(e.g. {@scroll X} -> {@item scroll of X}; {@npc X} -> plain text "
        "or {@creature X}).\n"
        "\n"
        "Errors to fix:\n"
        + "\n".join(f"- {e}" for e in tag_errors) +
        "\n\n"
        "Previous JSON:\n"
        f"{prior_json}\n"
    )
    if debug_dir:
        (debug_dir / f"{chunk_id}-tag-errors.txt").write_text(
            "\n".join(tag_errors), encoding="utf-8"
        )

    retry_result = call_claude(
        client, correction_prompt, model, system_prompt, verbose,
        debug_dir=debug_dir, chunk_id=f"{chunk_id}-fix",
        _retry_count=_retry_count + 1,
    )

    if not _retry_preserves_shape(original_result, retry_result):
        print(f"    [VALIDATE] {chunk_id}: retry changed entry shape — "
              f"rejecting retry and keeping original result.", flush=True)
        return original_result
    return retry_result


# ---------------------------------------------------------------------------
# Pricing helpers (shared by dry_run across all converters)
# ---------------------------------------------------------------------------

_PRICE = {
    "haiku":  {"input": 0.80,  "output": 4.00},
    "sonnet": {"input": 3.00,  "output": 15.00},
    "opus":   {"input": 15.00, "output": 75.00},
}


def _model_tier(model: str) -> str:
    m = model.lower()
    if "haiku"  in m: return "haiku"
    if "sonnet" in m: return "sonnet"
    if "opus"   in m: return "opus"
    return "sonnet"


# ---------------------------------------------------------------------------
# Batch API
# ---------------------------------------------------------------------------

def call_claude_batch(
    client: anthropic.Anthropic,
    chunks: list[str],
    model: str,
    system_prompt: str,
    verbose: bool,
    debug_dir: Path | None = None,
    validate: bool = True,
) -> list[list[Any]]:
    """Submit all chunks as a single Batch API request (50% cheaper, async).

    Polls until complete, then returns results in chunk order.

    See :func:`call_claude` for the ``validate`` parameter — pass
    ``validate=False`` for bestiary monster payloads whose ``type`` field
    is a dict.
    """
    import time as _time

    print(f"  Submitting {len(chunks)} requests to Batch API...", flush=True)

    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        for i, text in enumerate(chunks):
            (debug_dir / f"chunk-{i:04d}-input.txt").write_text(text, encoding="utf-8")
        print(f"  [DEBUG] Saved {len(chunks)} chunk inputs to {debug_dir}/", flush=True)

    requests = [
        {
            "custom_id": f"chunk-{i:04d}",
            "params": {
                "model": model,
                "max_tokens": MAX_OUTPUT_TOKENS,
                "system": system_prompt,
                "messages": [{"role": "user", "content": text}],
            },
        }
        for i, text in enumerate(chunks)
    ]

    batch = client.messages.batches.create(requests=requests)
    batch_id = batch.id
    print(f"  Batch ID: {batch_id}", flush=True)
    print("  Waiting for batch to complete (polls every 15 s)...", flush=True)

    while True:
        batch = client.messages.batches.retrieve(batch_id)
        status = batch.processing_status
        counts = batch.request_counts
        print(
            f"    status={status}  "
            f"processing={counts.processing}  "
            f"succeeded={counts.succeeded}  "
            f"errored={counts.errored}",
            flush=True,
        )
        if status == "ended":
            break
        _time.sleep(15)

    results_map: dict[str, list[Any]] = {}
    for result in client.messages.batches.results(batch_id):
        cid = result.custom_id
        if result.result.type == "succeeded":
            msg = result.result.message
            if msg.stop_reason == "max_tokens":
                print(f"    [WARN] {cid} hit max_tokens — response may be truncated. "
                      f"Try --pages-per-chunk with a smaller value.", flush=True)
            results_map[cid], _ = _parse_claude_response(
                msg.content[0].text, verbose, debug_dir=debug_dir, chunk_id=cid
            )
        else:
            print(f"    [WARN] {cid} failed: {result.result.type}", flush=True)
            if debug_dir:
                (debug_dir / f"{cid}-api-error.txt").write_text(
                    str(result.result), encoding="utf-8"
                )
            results_map[cid] = []

    ordered = [results_map.get(f"chunk-{i:04d}", []) for i in range(len(chunks))]

    print(f"\n  Chunk results summary:", flush=True)
    total_validation_errors = 0
    for i, entries in enumerate(ordered):
        cid = f"chunk-{i:04d}"
        flag = "  ← EMPTY — check debug files" if not entries else ""
        # Validate entries (skipped for non-adventure payloads like bestiary)
        if validate and entries:
            errors = validate_entries(entries, cid)
            if errors:
                flag = f"  ← {len(errors)} validation error(s)"
                total_validation_errors += len(errors)
                if debug_dir:
                    (debug_dir / f"{cid}-validation-errors.txt").write_text(
                        "\n".join(errors), encoding="utf-8"
                    )
        print(f"    {cid}: {len(entries)} entries{flag}", flush=True)
    if total_validation_errors:
        print(f"\n  [VALIDATE] {total_validation_errors} total validation error(s) across "
              f"batch results. Re-run without --batch to enable automatic retry.",
              flush=True)
    print(flush=True)

    return ordered


# ---------------------------------------------------------------------------
# Dry-run cost estimator
# ---------------------------------------------------------------------------

def dry_run(
    client: anthropic.Anthropic,
    chunk_texts: list[str],
    chunks: list,
    model: str,
    system_prompt: str,
    use_batch: bool,
    verbose: bool,
) -> None:
    """Count tokens for every chunk and print a cost estimate. No inference."""
    tier     = _model_tier(model)
    prices   = _PRICE.get(tier, _PRICE["sonnet"])
    discount = 0.5 if use_batch else 1.0

    print(f"\n[DRY-RUN] Token count + cost estimate")
    print(f"  Model  : {model}  ({'Batch API -50%%' if use_batch else 'Standard API'})")
    print(f"  Pricing: ${prices['input']:.2f} / ${prices['output']:.2f} per M tokens "
          f"(in/out){'  ×0.5 batch discount' if use_batch else ''}")
    print()

    total_input = 0
    est_output_per_chunk = 1_000
    skipped = 0

    for i, chunk_text in enumerate(chunk_texts):
        if not chunk_text.strip():
            skipped += 1
            continue

        resp = client.messages.count_tokens(
            model=model,
            system=system_prompt,
            messages=[{"role": "user", "content": chunk_text}],
        )
        tok = resp.input_tokens
        total_input += tok

        if verbose or len(chunk_texts) <= 12:
            try:
                if chunks and hasattr(chunks[i][0], "__getitem__"):
                    page_nums = [p["page_num"] for p in chunks[i]]
                else:
                    page_nums = [p for p, _ in chunks[i]]
                label = f"pages {page_nums[0]}–{page_nums[-1]}"
            except Exception:
                label = f"chunk {i}"
            print(f"  chunk-{i:04d}  ({label})  →  {tok:,} input tokens")

    total_output = est_output_per_chunk * (len(chunk_texts) - skipped)
    cost_input   = total_input  / 1_000_000 * prices["input"]  * discount
    cost_output  = total_output / 1_000_000 * prices["output"] * discount
    cost_total   = cost_input + cost_output

    print()
    print(f"  ─────────────────────────────────────────")
    print(f"  Chunks          : {len(chunk_texts) - skipped} ({skipped} empty/skipped)")
    print(f"  Total input     : {total_input:,} tokens  →  ${cost_input:.4f}")
    print(f"  Est. output     : ~{total_output:,} tokens  →  ${cost_output:.4f}")
    print(f"  ─────────────────────────────────────────")
    print(f"  Estimated total : ${cost_total:.4f}  "
          f"({'with' if use_batch else 'without'} batch discount)")
    print(f"  ─────────────────────────────────────────")
    print()
    print("  No API inference was performed. Remove --dry-run to convert.")
