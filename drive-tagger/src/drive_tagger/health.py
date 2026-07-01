"""Pre-flight connectivity and configuration checks.

Call check_all() to get a list of CheckResult objects for every endpoint
and API key relevant to the current configuration.  Used by the 'check'
CLI command and by runner.run() before starting a batch.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import CONFIG


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _http_get(url: str, timeout: int = 3) -> tuple[bool, str]:
    """Return (reachable, detail_string).  Any HTTP response counts as reachable."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        # 401/403/etc. still means the server answered
        return True, f"HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return False, str(exc.reason)
    except OSError as exc:
        return False, str(exc)


def _check_gdrive_bin() -> CheckResult:
    from . import gdrive

    try:
        path = gdrive._resolve_bin()
        return CheckResult("gdrive-cli binary", True, path)
    except gdrive.GDriveError as exc:
        return CheckResult("gdrive-cli binary", False, str(exc))


def _check_gdrive_token() -> CheckResult:
    token_path = Path.home() / ".config" / "gdrive-cli" / "token.json"
    if token_path.exists():
        return CheckResult("gdrive OAuth token", True, str(token_path))
    return CheckResult(
        "gdrive OAuth token",
        False,
        f"no token at {token_path} — run `gdrive-cli google auth`",
    )


def _check_llm_endpoint(label: str, endpoint: str) -> CheckResult:
    url = f"{endpoint.rstrip('/')}/models"
    ok, detail = _http_get(url)
    return CheckResult(label, ok, f"{url}  ({detail})" if ok else f"{url}  — {detail}")


def _check_env(var: str, label: str) -> CheckResult:
    if os.environ.get(var, "").strip():
        masked = "****" + os.environ[var][-4:]
        return CheckResult(label, True, f"{var}={masked}")
    return CheckResult(label, False, f"{var} is not set")


def check_all() -> list[CheckResult]:
    """Return checks for every endpoint / key relevant to the current config."""
    results: list[CheckResult] = []

    # gdrive-cli is always required
    results.append(_check_gdrive_bin())
    results.append(_check_gdrive_token())

    # LLM provider
    provider = CONFIG.provider
    if provider == "dgx":
        results.append(_check_llm_endpoint(f"DGX chat  ({CONFIG.dgx_endpoint})", CONFIG.dgx_endpoint))
    elif provider == "openrouter":
        results.append(_check_env("OPENROUTER_API_KEY", "OpenRouter API key"))
        results.append(_check_llm_endpoint(f"OpenRouter ({CONFIG.openrouter_base_url})", CONFIG.openrouter_base_url))
    elif provider == "anthropic":
        results.append(_check_env("ANTHROPIC_API_KEY", "Anthropic API key"))
    elif provider == "cursor":
        results.append(_check_env("CURSOR_API_KEY", "Cursor API key"))

    # Embed provider
    if CONFIG.embed_provider == "dgx":
        results.append(_check_llm_endpoint(f"DGX embed ({CONFIG.dgx_embed_endpoint})", CONFIG.dgx_embed_endpoint))

    return results
