"""Thin subprocess wrapper around the Rust ``gdrive-cli`` binary.

All Google Drive I/O goes through this module: listing (scan), exporting native
Docs to text, downloading binary content, reading/writing app-private tags.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from .config import CONFIG


class GDriveError(RuntimeError):
    """Raised when a gdrive-cli invocation fails."""


def _resolve_bin() -> str:
    """Return a runnable gdrive-cli path, preferring the configured binary."""
    configured = CONFIG.gdrive_cli_bin
    if configured and Path(configured).is_file():
        return configured
    found = shutil.which("gdrive-cli")
    if found:
        return found
    raise GDriveError(
        f"gdrive-cli not found at {configured!r} and not on PATH. "
        "Build it with `cargo build --release` in mytools/gdrive-cli, "
        "or set DT_GDRIVE_CLI to the binary path."
    )


def _run(args: list[str], *, capture_bytes: bool = False) -> bytes | str:
    bin_path = _resolve_bin()
    proc = subprocess.run(
        [bin_path, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")
        raise GDriveError(f"gdrive-cli {' '.join(args)} failed (exit {proc.returncode}):\n{stderr}")
    return proc.stdout if capture_bytes else proc.stdout.decode("utf-8", errors="replace")


def scan(out: Optional[Path] = None, *, all_drives: bool = False) -> Path:
    """Run ``google scan`` and return the JSONL output path."""
    out = out or CONFIG.scan_path
    out.parent.mkdir(parents=True, exist_ok=True)
    args = ["google", "scan", "--out", str(out)]
    if all_drives:
        args.append("--all-drives")
    _run(args)
    return out


def export(file_id: str, *, mime: str = "text/plain") -> str:
    """Export a native Google editor file (Docs/Sheets/Slides) to text."""
    out = _run(["google", "export", file_id, "--mime", mime])
    assert isinstance(out, str)
    return out


def cat(file_id: str) -> bytes:
    """Download raw (binary-safe) file content."""
    out = _run(["google", "cat", file_id], capture_bytes=True)
    assert isinstance(out, bytes)
    return out


def get(file_id: str) -> dict:
    """Read a file's metadata + appProperties as a dict."""
    out = _run(["google", "get", file_id])
    assert isinstance(out, str)
    return json.loads(out) if out.strip() else {}


def tag(file_id: str, props: dict[str, str], *, execute: bool = False) -> Optional[dict]:
    """Set app-private appProperties on a file.

    Dry-run by default; returns the resulting appProperties dict when executed.
    """
    args = ["google", "tag", file_id]
    for key, value in props.items():
        args += ["--set", f"{key}={value}"]
    if execute:
        args.append("--execute")
    out = _run(args)
    assert isinstance(out, str)
    if execute and out.strip():
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return None
    return None
