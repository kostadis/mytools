"""OpenAI-compatible client for the DGX Spark vLLM endpoint.

Mirrors the surface of ``lib.claudelib`` (``make_client`` / ``call_api``) so
callers can swap providers without restructuring.

The DGX Spark serves one chat model at a time on an OpenAI-compatible API at
``http://192.168.1.147:8001/v1`` (see ``~/src/dgx-fun/current-setup.md``).
The served model id changes when the slot is swapped (Gemma 4, Nemotron 3
Nano, Llama 3.3, ...). Use :func:`discover_model` to read the id from
``/v1/models`` so callers don't need to hard-code it.
"""

import json
import sys
import time
import urllib.error
import urllib.request

DEFAULT_ENDPOINT = "http://192.168.1.147:8001/v1"
DEFAULT_MAX_TOKENS = 16384  # generous floor; reasoning models can burn a lot
DEFAULT_TIMEOUT = 600.0     # seconds; long batches under reasoning are slow


class DgxClient:
    def __init__(self, endpoint: str = DEFAULT_ENDPOINT,
                 timeout: float = DEFAULT_TIMEOUT):
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout


def make_client(endpoint: str = DEFAULT_ENDPOINT,
                timeout: float = DEFAULT_TIMEOUT) -> DgxClient:
    return DgxClient(endpoint, timeout)


def discover_model(endpoint: str = DEFAULT_ENDPOINT,
                   timeout: float = 10.0) -> str:
    """Return the first model id advertised by ``GET /v1/models``.

    vLLM serves a single chat model per container; that model's id is what
    every request must use or the server returns 400.
    """
    url = endpoint.rstrip("/") + "/models"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Could not reach DGX endpoint at {url}: {e}. "
            f"Is vllm-chat running on the Spark?"
        ) from e
    models = data.get("data") or []
    if not models:
        raise RuntimeError(f"No models advertised at {url}")
    return models[0]["id"]


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return 500 <= exc.code < 600
    if isinstance(exc, urllib.error.URLError):
        return True
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    return False


def call_api(client: DgxClient, system: str, content, model: str,
             max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
    """Non-streaming chat completion. Returns ``choices[0].message.content``.

    Mirrors :func:`lib.claudelib.call_api` so the caller can pick a provider
    via dispatch. Retries transient connection errors (the Spark warm-restart
    takes several minutes; tolerate it).
    """
    url = client.endpoint + "/chat/completions"
    body = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
    }).encode("utf-8")

    delays = [10, 20, 40]
    for attempt, delay in enumerate([-1] + delays):
        if delay >= 0:
            print(f"\n  [DGX unavailable — waiting {delay}s before retry "
                  f"{attempt}/{len(delays)}...]", flush=True)
            time.sleep(delay)
        try:
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=client.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return payload["choices"][0]["message"]["content"]
        except Exception as e:
            if _is_retryable(e) and attempt < len(delays):
                continue
            raise
