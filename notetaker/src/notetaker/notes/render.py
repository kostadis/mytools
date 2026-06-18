"""
Single LLM render call with retry, structured per-attempt logging, and cost
reporting. See contracts/notes_file.md and contracts/render_log_records.md.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from notetaker.config import Config
from notetaker.utils.logging import get_logger

logger = get_logger(__name__)


# Sonnet 4.6 pricing (USD per million tokens). Update if the project's pricing
# convention changes; mirrors the constants in stages/synthesis/summarizer.py.
_SONNET_INPUT_PRICE_PER_MILLION = 3.0
_SONNET_OUTPUT_PRICE_PER_MILLION = 15.0


@dataclass
class RenderResult:
    text: str
    model: str
    total_attempts: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    outcome: str  # "success" | "persistent_failure"


_RENDER_PROMPT = """\
You are turning a working doc into polished meeting notes. The working doc has
two sections:

1. **Slides** — content extracted by a vision model from each unique slide
   shown during the meeting, in the order each slide first appeared. Each
   slide has a title, bullet points, and a description of any visual.
2. **Transcript** — verbatim utterances captured from the meeting, with
   speaker labels and HH:MM:SS timestamps measured from the start of the
   meeting.

Note: slide order is *first-appearance order*, and slides may have been
revisited later in the meeting. The transcript is strictly chronological. So
topic flow in the transcript can revisit earlier slides; do not assume one
contiguous block of transcript belongs to one slide. (FR-008)

Your task: produce meeting notes in Markdown that someone who missed the
meeting could read to understand:
- What this meeting was about and who was involved (named participants from
  the transcript).
- What was discussed, organised around the natural topical structure shown by
  the slide titles. Use slide titles as section headings when there is a
  clear topical match, otherwise group related discussion under a heading
  you write.
- What was decided, attributed to the speaker who said it. (FR-009)
- What action items or follow-ups came out of it.
- What open questions or disagreements were raised but not resolved.

Constraints:
- Do not fabricate. If the transcript doesn't say a thing, don't claim it
  was said. Flag uncertainty rather than invent attribution. (FR-009)
- When attributing a decision, statement, or question to a person, name
  them (the transcript has speakers).
- If a slide's content was clearly never discussed, you can omit it from
  the narrative — but mention at the end that some slides were shown
  without discussion (and list which titles).
- Prefer concrete detail (specific numbers, names, decisions) over generic
  prose.
- Output Markdown only — no preamble or trailing commentary. Start with a
  `#` heading.

Working doc follows.
---

{working_doc}
"""


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens / 1_000_000 * _SONNET_INPUT_PRICE_PER_MILLION
        + output_tokens / 1_000_000 * _SONNET_OUTPUT_PRICE_PER_MILLION
    )


def _is_retryable(exc: Exception) -> bool:
    name = exc.__class__.__name__
    if name in {"APIConnectionError", "APITimeoutError", "RateLimitError",
                "InternalServerError", "ServiceUnavailableError"}:
        return True
    return False


def render_notes(
    working_doc_text: str,
    config: Config,
    client=None,
) -> RenderResult:
    """
    Run exactly one *successful* LLM render call. Retry transient failures per
    the project's existing retry policy (config.api.retry_count /
    retry_delay_seconds). Emit `notes.render_attempt` per attempt and one
    `notes.render_complete` summary record.
    """
    if client is None:
        import anthropic
        client = anthropic.Anthropic()

    model = config.resolved_notes_model()
    max_tokens = config.notes.max_output_tokens
    max_attempts = max(1, config.api.retry_count)
    delay = config.api.retry_delay_seconds

    prompt = _RENDER_PROMPT.format(working_doc=working_doc_text)

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
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            in_tok = getattr(getattr(response, "usage", None), "input_tokens", 0) or 0
            out_tok = getattr(getattr(response, "usage", None), "output_tokens", 0) or 0
            cost = _estimate_cost(in_tok, out_tok)
            total_in += in_tok
            total_out += out_tok
            total_cost += cost
            elapsed = time.monotonic() - t0

            logger.info(
                "notes.render_attempt",
                attempt=attempt,
                model=model,
                input_tokens=in_tok,
                output_tokens=out_tok,
                elapsed_seconds=elapsed,
                cost_usd=cost,
                outcome="success",
            )
            text = response.content[0].text
            logger.info(
                "notes.render_complete",
                event_category="command_end",
                model=model,
                total_attempts=total_attempts,
                total_cost_usd=total_cost,
                outcome="success",
            )
            return RenderResult(
                text=text,
                model=model,
                total_attempts=total_attempts,
                total_input_tokens=total_in,
                total_output_tokens=total_out,
                total_cost_usd=total_cost,
                outcome="success",
            )
        except Exception as exc:
            elapsed = time.monotonic() - t0
            retryable = _is_retryable(exc) and attempt < max_attempts
            last_error = f"{exc.__class__.__name__}: {exc}"
            outcome = "retryable" if retryable else "persistent_failure"
            attempt_log = logger.warning if retryable else logger.error
            attempt_log(
                "notes.render_attempt",
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

    logger.error(
        "notes.render_complete",
        event_category="command_end",
        model=model,
        total_attempts=total_attempts,
        total_cost_usd=total_cost,
        outcome="persistent_failure",
        error=last_error,
    )
    raise RenderFailedError(
        f"render failed after {total_attempts} attempt(s): {last_error}"
    )


class RenderFailedError(RuntimeError):
    """Raised when all retry attempts on the LLM render call failed."""
