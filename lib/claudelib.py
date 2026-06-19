"""Generic Anthropic Claude API wrapper with retry logic.

Provides client creation, non-streaming and streaming API calls with
automatic retry on transient errors (rate limits, server errors, timeouts).

Extracted from CampaignGenerator's campaignlib.py for cross-project reuse.
"""

import sys
import time

DEFAULT_MODEL = "claude-sonnet-4-20250514"


def make_client(api_key: str | None = None):
    """Return an Anthropic client, exiting with a helpful message if not installed.

    ``api_key`` overrides the ``ANTHROPIC_API_KEY`` env var when provided;
    otherwise the SDK reads the key from the environment as usual.
    """
    try:
        import anthropic
    except ImportError:
        print("Error: anthropic not installed. Run: pip install anthropic", file=sys.stderr)
        sys.exit(1)
    return anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()


def _norm_stop_reason(stop_reason: str | None) -> str:
    """Normalise an Anthropic ``stop_reason`` to the shared two-value vocabulary.

    ``"max_tokens"`` means the response was truncated by the output-token cap;
    everything else (``"end_turn"``, ``"stop_sequence"``, ``"tool_use"``, ...)
    collapses to ``"stop"``. Callers only need to distinguish truncation from a
    natural finish; mirrors dgxlib's finish-reason normalisation.
    """
    return "max_tokens" if stop_reason == "max_tokens" else "stop"


def _is_retryable(exc) -> bool:
    """Return True for transient API errors that are worth retrying."""
    try:
        import anthropic
        if isinstance(exc, (
            anthropic.RateLimitError,
            anthropic.InternalServerError,
            anthropic.APIConnectionError,
            anthropic.APITimeoutError,
        )):
            return True
        if isinstance(exc, anthropic.APIStatusError) and exc.status_code == 529:
            return True  # overloaded_error
    except ImportError:
        pass
    try:
        import httpx
        if isinstance(exc, (
            httpx.RemoteProtocolError,
            httpx.ConnectError,
            httpx.ReadError,
            httpx.TimeoutException,
        )):
            return True
    except ImportError:
        pass
    return False


def call_api_full(client, system: str, content, model: str = DEFAULT_MODEL,
                  max_tokens: int = 8096) -> tuple[str, str]:
    """Non-streaming API call. Returns ``(text, stop_reason)``.

    ``stop_reason`` is normalised to the shared vocabulary: ``"max_tokens"`` when
    the response was truncated by the output-token cap, else ``"stop"`` (see
    :func:`_norm_stop_reason`). Callers that need to detect truncation — e.g. to
    re-process a tail — use the second element; :func:`call_api` discards it.

    content — a string or a list of content blocks (for multimodal/vision calls).
    Retries on transient errors with exponential backoff (3 retries: 10/20/40s).
    """
    messages = [{"role": "user", "content": content}]
    delays = [10, 20, 40]
    for attempt, delay in enumerate([-1] + delays):
        if delay >= 0:
            print(f"\n  [API unavailable — waiting {delay}s before retry {attempt}/{len(delays)}...]",
                  flush=True)
            time.sleep(delay)
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            return response.content[0].text, _norm_stop_reason(response.stop_reason)
        except Exception as e:
            if _is_retryable(e) and attempt < len(delays):
                continue
            raise


def call_api(client, system: str, content, model: str = DEFAULT_MODEL,
             max_tokens: int = 8096) -> str:
    """Non-streaming API call. Returns full response text.

    Thin wrapper over :func:`call_api_full` that drops the stop-reason — kept for
    callers that only want the text (e.g. CampaignGenerator, pdf_enricher).
    """
    text, _ = call_api_full(client, system, content, model, max_tokens)
    return text


def stream_api(client, system: str, user: str, model: str = DEFAULT_MODEL,
               max_tokens: int = 8096, silent: bool = False,
               verbose: bool = False) -> str:
    """Stream a Claude API call, printing each token as it arrives. Returns full response.

    Retries on transient errors with exponential backoff (3 retries: 60/120/240s).
    Pass silent=True to suppress output. Pass verbose=True to print prompts before calling.
    """
    if verbose:
        print("\n" + "=" * 60)
        print("SYSTEM PROMPT:")
        print(system)
        print("-" * 60)
        print("USER PROMPT:")
        print(user)
        print("=" * 60 + "\n")

    delays = [60, 120, 240]
    for attempt, delay in enumerate([-1] + delays):
        if delay >= 0:
            print(f"\n  [API unavailable — waiting {delay}s before retry {attempt}/{len(delays)}...]",
                  flush=True)
            time.sleep(delay)
        try:
            chunks = []
            with client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            ) as stream:
                for text in stream.text_stream:
                    if not silent:
                        print(text, end="", flush=True)
                    chunks.append(text)
            if not silent:
                print()
            return "".join(chunks)
        except Exception as e:
            if _is_retryable(e) and attempt < len(delays):
                continue
            raise
