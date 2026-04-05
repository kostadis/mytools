"""Generic Anthropic Claude API wrapper with retry logic.

Provides client creation, non-streaming and streaming API calls with
automatic retry on transient errors (rate limits, server errors, timeouts).

Extracted from CampaignGenerator's campaignlib.py for cross-project reuse.
"""

import sys
import time

DEFAULT_MODEL = "claude-sonnet-4-20250514"


def make_client():
    """Return an Anthropic client, exiting with a helpful message if not installed."""
    try:
        import anthropic
    except ImportError:
        print("Error: anthropic not installed. Run: pip install anthropic", file=sys.stderr)
        sys.exit(1)
    return anthropic.Anthropic()


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


def call_api(client, system: str, content, model: str = DEFAULT_MODEL,
             max_tokens: int = 8096) -> str:
    """Non-streaming API call. Returns full response text.

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
            return response.content[0].text
        except Exception as e:
            if _is_retryable(e) and attempt < len(delays):
                continue
            raise


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
