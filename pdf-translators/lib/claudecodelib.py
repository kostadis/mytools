"""claudecodelib.py — drive a Claude *subscription* via the Claude Code CLI.

Third transport for pdf-translators, alongside ``claudelib`` (the Anthropic
Messages API) and ``dgxlib`` (the DGX Spark vLLM endpoint). Instead of billing
the Anthropic API per token, this shells out to the locally-installed ``claude``
CLI in headless print mode (``claude -p --output-format json``), which spends the
logged-in Claude Code **subscription** quota.

The seam matches the other two libs so :mod:`llm_backend` can wrap it uniformly:
``make_client()`` then ``call_api_full(client, system, user, model, max_tokens)``
returning ``(text, stop_reason)``.

Constraints vs the Messages API — callers must know these:

* **No ``max_tokens`` control / no truncation signal.** The CLI caps output at
  the model's own maximum and reports ``stop_reason: end_turn``; it never says
  ``max_tokens``. So ``call_api_full`` returns ``"stop"`` virtually always, and
  ``claude_api.call_claude``'s tail/split *truncation* retry can't fire for this
  provider (its validation/malformed-JSON retry still does).
* **No Batch API and no ``count_tokens``** — dry-run falls back to the local
  size estimate (``anthropic_client is None``).
* **Auth.** The child env has ``ANTHROPIC_API_KEY`` scrubbed so Claude Code uses
  the subscription login instead of silently falling back to API billing.
* **Neutral cwd.** The subprocess runs in a temp directory so it does not load a
  project ``CLAUDE.md`` as extra context (cuts harness overhead ~7x in testing).
* **Tools disabled** (``--allowedTools ''``): this is a pure text→JSON task.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass

DEFAULT_BINARY = "claude"
DEFAULT_TIMEOUT = 900.0  # seconds; a big chunk on a slow tier can run minutes
_RETRY_DELAYS = (10, 20, 40)


@dataclass
class ClaudeCodeClient:
    """Holds the resolved CLI path + per-call knobs (no network state)."""
    binary: str = DEFAULT_BINARY
    timeout: float = DEFAULT_TIMEOUT
    cwd: str = ""


def make_client(binary: str | None = None,
                timeout: float | None = None) -> ClaudeCodeClient:
    """Resolve the ``claude`` binary and return a reusable client config.

    Raises ``RuntimeError`` if the CLI is not on PATH.
    """
    name = binary or DEFAULT_BINARY
    resolved = shutil.which(name)
    if resolved is None:
        raise RuntimeError(
            f"claude CLI not found on PATH (looked for {name!r}). Install Claude "
            f"Code and run `claude login` with your subscription, or pass "
            f"--provider claude to use the Anthropic API instead."
        )
    return ClaudeCodeClient(
        binary=resolved,
        timeout=timeout or DEFAULT_TIMEOUT,
        cwd=tempfile.gettempdir(),
    )


def _norm_stop_reason(stop_reason: str | None) -> str:
    """Normalise to the shared two-value vocabulary used by the other transports.

    The CLI reports ``end_turn`` for a complete response; only an explicit
    ``max_tokens`` maps to truncation.
    """
    return "max_tokens" if stop_reason == "max_tokens" else "stop"


def call_api_full(
    client: ClaudeCodeClient,
    system: str,
    user: str,
    model: str,
    max_tokens: int,
) -> tuple[str, str]:
    """Run one ``claude -p`` completion and return ``(text, stop_reason)``.

    ``max_tokens`` is accepted for signature parity with the other transports but
    the CLI has no knob for it. The user content is passed on stdin (no length
    limit); the system prompt and flags are argv. ``ANTHROPIC_API_KEY`` is
    removed from the child env so the subscription login is used.

    Retries transient subprocess-level failures (timeout, non-zero exit,
    non-JSON output) with backoff. A structured ``is_error`` from the CLI (auth,
    usage/rate limit, bad request) is raised immediately — usage caps won't clear
    in seconds, so the caller should resume later with ``--reuse-responses``.
    """
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    cmd = [
        client.binary, "-p",
        "--output-format", "json",
        "--model", model,
        "--system-prompt", system,
        "--allowedTools", "",  # disable all tools — pure text->JSON, no harness work
    ]

    for attempt in range(len(_RETRY_DELAYS) + 1):
        # ``desc`` names the failure mode for the retry log (mirrors dgxlib's
        # _describe_error): a timeout, a non-zero exit, and non-JSON output are
        # distinct problems and the banner used to call all of them "unavailable".
        desc: str | None = None
        try:
            proc = subprocess.run(
                cmd, input=user, env=env, cwd=client.cwd,
                capture_output=True, text=True, timeout=client.timeout,
            )
        except subprocess.TimeoutExpired:
            desc = (f"timed out after {client.timeout:g}s — CLI ran but produced no "
                    f"result in time (generation likely exceeded the budget)")
        else:
            if proc.returncode != 0:
                desc = (f"CLI exited {proc.returncode}: "
                        f"{proc.stderr.strip()[:300] or '(no stderr)'}")
            else:
                try:
                    payload = json.loads(proc.stdout)
                except json.JSONDecodeError:
                    desc = f"non-JSON output: {proc.stdout[:300]!r}"
                else:
                    if payload.get("is_error"):
                        # Auth / usage cap / bad request — not transient, fail fast
                        # (a usage cap won't clear in 40s; resume with --reuse-responses).
                        subtype = payload.get("subtype")
                        detail = (payload.get("result")
                                  or payload.get("api_error_status") or subtype)
                        raise RuntimeError(f"claude CLI error ({subtype}): {detail}")
                    return (payload.get("result", ""),
                            _norm_stop_reason(payload.get("stop_reason")))

        # Reached only on a transient failure (desc set above).
        if attempt < len(_RETRY_DELAYS):
            delay = _RETRY_DELAYS[attempt]
            print(f"\n  [Claude Code {desc} — waiting {delay}s before retry "
                  f"{attempt + 1}/{len(_RETRY_DELAYS)}...]", flush=True)
            time.sleep(delay)
            continue
        raise RuntimeError(
            f"claude CLI failed after {len(_RETRY_DELAYS)} retries: {desc}")
