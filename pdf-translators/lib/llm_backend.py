"""llm_backend.py — provider-agnostic completion backend for pdf-translators.

`claude_api.py` no longer talks to the Anthropic SDK directly. It calls a small
``Backend`` object that wraps one of the three transport libraries:

* :mod:`claudelib` — the Anthropic Messages API (``../lib`` in this repo).
* :mod:`dgxlib` — the DGX Spark's OpenAI-compatible vLLM endpoint
  (editable install, github.com/kostadis/dgx-fun).
* :mod:`claudecodelib` — the local ``claude`` CLI in headless mode, which spends
  the Claude Code **subscription** quota instead of billing the API.

This mirrors the provider-dispatch pattern in ``rpg-lib/pdf_enricher.py``, but
applied at the transport seam so pdf-translators keeps its own 5etools-specific
retry / recovery / validation logic on top.

Both backends expose a uniform :meth:`Backend.complete` that returns
``(text, stop_reason)`` where ``stop_reason`` is normalised by the shared libs to
``"max_tokens"`` (truncated) vs ``"stop"`` — the one distinction
``claude_api.call_claude`` needs for its tail/split retry.

The Anthropic-only features (Batch API, ``count_tokens`` cost estimation) reach
the raw client through :attr:`Backend.anthropic_client`; it is ``None`` for DGX,
and callers gate on :attr:`Backend.supports_batch`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

import claudelib  # noqa: E402

try:
    import dgxlib  # noqa: E402  (editable install — github.com/kostadis/dgx-fun)
    _dgxlib_available = True
except ModuleNotFoundError:
    dgxlib = None  # type: ignore[assignment]
    _dgxlib_available = False

import lib.claudecodelib as claudecodelib  # noqa: E402  (local — Claude Code CLI subscription transport)

# Re-export DGX discovery helpers so the entry point can resolve the served model
# id without importing dgxlib itself.
DEFAULT_ENDPOINT: str = dgxlib.DEFAULT_ENDPOINT if _dgxlib_available else "http://192.168.1.147:8001/v1"


def discover_model(endpoint: str | None = None) -> str:
    """Discover the model served at the DGX endpoint. Requires dgxlib."""
    if not _dgxlib_available:
        raise RuntimeError(
            "dgxlib not installed (pip install -e git+https://github.com/kostadis/dgx-fun). "
            "Required for --provider dgx."
        )
    return dgxlib.discover_model(endpoint)


class Backend:
    """A provider-agnostic non-streaming completion backend.

    Construct via :func:`anthropic_backend` or :func:`dgx_backend`; do not
    instantiate directly.

    Attributes:
        kind: ``"claude"``, ``"dgx"``, or ``"claude-code"``.
        anthropic_client: the raw ``anthropic.Anthropic`` client for the Batch /
            ``count_tokens`` paths, or ``None`` for DGX.
        supports_batch: ``True`` only for the Anthropic backend.
        label: human-readable description for log output.
    """

    def __init__(
        self,
        kind: str,
        *,
        complete_fn: Callable[[str, str, str, int], tuple[str, str]],
        anthropic_client=None,
        supports_batch: bool = False,
        label: str = "",
    ):
        self.kind = kind
        self._complete_fn = complete_fn
        self.anthropic_client = anthropic_client
        self.supports_batch = supports_batch
        self.label = label

    def complete(self, system: str, user: str, model: str,
                 max_tokens: int) -> tuple[str, str]:
        """Return ``(text, stop_reason)`` for one chat completion.

        ``stop_reason`` is ``"max_tokens"`` when the output was truncated by the
        token cap, else ``"stop"``.
        """
        return self._complete_fn(system, user, model, max_tokens)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<Backend {self.kind}: {self.label}>"


def anthropic_backend(api_key: str | None = None) -> Backend:
    """Build a Backend backed by the Anthropic Messages API (``claudelib``)."""
    client = claudelib.make_client(api_key)

    def _complete(system: str, user: str, model: str,
                  max_tokens: int) -> tuple[str, str]:
        return claudelib.call_api_full(client, system, user, model, max_tokens)

    return Backend(
        "claude",
        complete_fn=_complete,
        anthropic_client=client,
        supports_batch=True,
        label="Anthropic API",
    )


def dgx_backend(endpoint: str | None = None) -> Backend:
    """Build a Backend backed by the DGX Spark vLLM endpoint (``dgxlib``)."""
    if not _dgxlib_available:
        raise RuntimeError(
            "dgxlib not installed (pip install -e git+https://github.com/kostadis/dgx-fun). "
            "Required for --provider dgx."
        )
    endpoint = endpoint or DEFAULT_ENDPOINT
    client = dgxlib.make_client(endpoint)

    def _complete(system: str, user: str, model: str,
                  max_tokens: int) -> tuple[str, str]:
        # thinking=False: a reasoning slot would wrap the answer in <think> tags
        # and break JSON parsing — the converter never wants reasoning traces.
        return dgxlib.call_api_full(client, system, user, model, max_tokens,
                                    thinking=False)

    return Backend(
        "dgx",
        complete_fn=_complete,
        anthropic_client=None,
        supports_batch=False,
        label=f"DGX Spark ({endpoint})",
    )


def claude_code_backend(binary: str | None = None) -> Backend:
    """Build a Backend backed by the local Claude Code CLI (``claudecodelib``).

    Spends the logged-in Claude Code subscription quota rather than the Anthropic
    API. No Batch API and no ``count_tokens`` (``anthropic_client`` is ``None``,
    so dry-run uses the local size estimate). See :mod:`claudecodelib` for the
    constraints (no ``max_tokens``/truncation signal, API-key scrubbing).
    """
    client = claudecodelib.make_client(binary)

    def _complete(system: str, user: str, model: str,
                  max_tokens: int) -> tuple[str, str]:
        return claudecodelib.call_api_full(client, system, user, model, max_tokens)

    return Backend(
        "claude-code",
        complete_fn=_complete,
        anthropic_client=None,
        supports_batch=False,
        label="Claude Code (subscription)",
    )
