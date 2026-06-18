"""
Post-render Haiku summary call (spec 005, T010).

After the main Sonnet render produces the notes Markdown, this module makes a
small Haiku call asking for a one-line ≤50-char summary of the rendered notes.
The output feeds the human-readable notes filename, NOT another LLM step — per
the LLM Pipeline Design Rule, the call is safe because it labels already
human-reviewable content.

On any failure (API error, JSON parse error, summary still over the cap after
defensive truncation), the call returns a SummaryResult with
outcome="fallback" and text="no-summary" — the caller proceeds and the notes
file still gets written.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

from notetaker.config import Config
from notetaker.utils.logging import get_logger

logger = get_logger(__name__)


_FALLBACK_TEXT = "no-summary"
_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


@dataclass
class SummaryResult:
    text: str
    outcome: str  # "success" | "fallback"
    model: str
    total_attempts: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float


_SUMMARY_PROMPT = """\
Read the meeting notes below and produce a single short label that names the
meeting concisely. The label will be used as part of a filename, so it must:

- Be ≤ 50 characters.
- Be a single line, no newlines.
- Use plain words (commas and basic punctuation are fine; avoid slashes,
  colons, or special characters).
- Capture what the meeting was *about* (e.g. "Roadmap, headcount, OKR rollovers"),
  not who attended or how long it ran.

Respond with a single JSON object on one line: {{"summary": "<your label>"}}
No markdown fences, no preamble.

Notes follow.
---
{notes}
"""


def _estimate_cost(input_tokens: int, output_tokens: int, config: Config) -> float:
    return (
        input_tokens / 1_000_000 * config.notes.summary_input_token_price_per_million
        + output_tokens / 1_000_000 * config.notes.summary_output_token_price_per_million
    )


def _is_retryable(exc: Exception) -> bool:
    name = exc.__class__.__name__
    return name in {
        "APIConnectionError",
        "APITimeoutError",
        "RateLimitError",
        "InternalServerError",
        "ServiceUnavailableError",
    }


def _parse_response(raw_text: str) -> str | None:
    """Strip optional code fences and parse {"summary": "..."}; return None on failure."""
    cleaned = _JSON_FENCE_RE.sub("", raw_text).strip()
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    val = obj.get("summary")
    if not isinstance(val, str):
        return None
    return val.strip()


def _truncate_to_cap(text: str, cap: int) -> str:
    """Cut at the last word boundary ≤ cap; otherwise hard-cut at cap."""
    if len(text) <= cap:
        return text
    window_start = max(0, cap - max(1, cap // 4))
    space_idx = text.rfind(" ", window_start, cap)
    if space_idx > 0:
        return text[:space_idx].rstrip()
    return text[:cap].rstrip()


def _fallback_result(
    *,
    model: str,
    attempts: int,
    in_tok: int,
    out_tok: int,
    cost: float,
    reason: str,
    error: str | None = None,
) -> SummaryResult:
    logger.warning(
        "notes.summary_fallback",
        model=model,
        reason=reason,
        error=error,
    )
    return SummaryResult(
        text=_FALLBACK_TEXT,
        outcome="fallback",
        model=model,
        total_attempts=attempts,
        total_input_tokens=in_tok,
        total_output_tokens=out_tok,
        total_cost_usd=cost,
    )


def generate_summary(
    notes_text: str,
    config: Config,
    *,
    client=None,
) -> SummaryResult:
    """
    Make one successful Haiku summary call (with retries on transient failures).
    On exhaustion or any non-retryable error, return a fallback SummaryResult
    rather than raising — the caller is the notes orchestrator and must keep
    going regardless.
    """
    if client is None:
        import anthropic
        client = anthropic.Anthropic()

    model = config.notes.summary_model
    max_attempts = max(1, config.api.retry_count)
    delay = config.api.retry_delay_seconds
    summary_cap = config.notes.summary_max_chars

    prompt = _SUMMARY_PROMPT.format(notes=notes_text)

    total_attempts = 0
    total_in = 0
    total_out = 0
    total_cost = 0.0
    last_error: str | None = None

    for attempt in range(1, max_attempts + 1):
        total_attempts = attempt
        t0 = time.monotonic()
        try:
            response = client.messages.create(
                model=model,
                # Summary fits well under 200 tokens; cap defensively.
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            in_tok = getattr(getattr(response, "usage", None), "input_tokens", 0) or 0
            out_tok = getattr(getattr(response, "usage", None), "output_tokens", 0) or 0
            cost = _estimate_cost(in_tok, out_tok, config)
            total_in += in_tok
            total_out += out_tok
            total_cost += cost
            elapsed = time.monotonic() - t0

            raw_text = response.content[0].text
            parsed = _parse_response(raw_text)

            logger.info(
                "notes.summary_render",
                attempt=attempt,
                model=model,
                input_tokens=in_tok,
                output_tokens=out_tok,
                elapsed_seconds=elapsed,
                cost_usd=cost,
                outcome="success" if parsed is not None else "parse_error",
            )

            if parsed is None:
                return _fallback_result(
                    model=model,
                    attempts=total_attempts,
                    in_tok=total_in,
                    out_tok=total_out,
                    cost=total_cost,
                    reason="parse_error",
                )

            if len(parsed) > summary_cap:
                logger.debug(
                    "notes.summary_overlong",
                    raw_len=len(parsed),
                    cap=summary_cap,
                )
                parsed = _truncate_to_cap(parsed, summary_cap)
                # Defensive: if the truncated form is empty (would only happen
                # if the model returned all whitespace after the cap window),
                # fall back rather than ship an empty label.
                if not parsed:
                    return _fallback_result(
                        model=model,
                        attempts=total_attempts,
                        in_tok=total_in,
                        out_tok=total_out,
                        cost=total_cost,
                        reason="over_length",
                    )

            return SummaryResult(
                text=parsed,
                outcome="success",
                model=model,
                total_attempts=total_attempts,
                total_input_tokens=total_in,
                total_output_tokens=total_out,
                total_cost_usd=total_cost,
            )
        except Exception as exc:
            elapsed = time.monotonic() - t0
            last_error = f"{exc.__class__.__name__}: {exc}"
            retryable = _is_retryable(exc) and attempt < max_attempts
            outcome = "retryable" if retryable else "api_error"
            attempt_log = logger.warning if retryable else logger.error
            attempt_log(
                "notes.summary_render",
                attempt=attempt,
                model=model,
                input_tokens=None,
                output_tokens=None,
                elapsed_seconds=elapsed,
                cost_usd=0.0,
                outcome=outcome,
                error=last_error,
            )
            if retryable:
                time.sleep(delay)
                continue
            break

    return _fallback_result(
        model=model,
        attempts=total_attempts,
        in_tok=total_in,
        out_tok=total_out,
        cost=total_cost,
        reason="api_error",
        error=last_error,
    )
