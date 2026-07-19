#!/usr/bin/env python3
"""Workstation-side orchestration: picks a Spark box, prechecks free memory
over SSH, scp's the audio + a JSON manifest over, ssh-invokes the deployed
spark/transcribe_remote.py, and scp's the result JSON back.

No persistent server, no dgxlib — faster-whisper is a plain Python library
call, not an HTTP endpoint (see audio-to-vtt/CLAUDE.md for why). This
mirrors the existing ``ssh spark2 'bash ~/spin-up-vllm-...sh'`` deployment
pattern already used for the Spark's vLLM spin-up scripts: SSH-invoke a
one-shot script, no standing footprint between runs.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

SPARK_HOSTS = ["spark2", "spark"]  # preference order: spark2 is the documented batch box
REMOTE_WORKDIR = "~/audio-to-vtt-work"
REMOTE_VENV_PYTHON = "~/.venvs/audio-to-vtt/bin/python"
REMOTE_SCRIPT = "~/audio-to-vtt-transcribe-remote.py"


class SparkRunError(RuntimeError):
    pass


def _ssh(host: str, remote_cmd: str, timeout: int = 15) -> str:
    proc = subprocess.run(["ssh", host, remote_cmd], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise SparkRunError(f"ssh {host} failed: {proc.stderr.strip()}")
    return proc.stdout


def _remote_home(host: str) -> str:
    """Resolve the remote $HOME as an absolute path. `~` only expands inside
    a shell -- the manifest's audio_path is read directly by Python's
    av.open() on the far side, which does not expand it (verified
    empirically: a literal '~/...' path raises FileNotFoundError there)."""
    return _ssh(host, "echo $HOME").strip()


def free_gb(host: str) -> float:
    """Available memory in GB, from `free`'s "available" column (accounts
    for reclaimable cache — the number this project's plan checked live
    against both boxes before committing to the design)."""
    out = _ssh(host, "free -m | awk '/^Mem:/{print $7}'")
    return int(out.strip()) / 1024.0


def pick_host(preferred: str, min_free_gb: float) -> str:
    hosts = SPARK_HOSTS if preferred == "auto" else [preferred]
    checked = []
    for host in hosts:
        try:
            gb = free_gb(host)
        except Exception as e:
            checked.append(f"{host}: unreachable ({e})")
            continue
        checked.append(f"{host}: {gb:.1f} GB free")
        if gb >= min_free_gb:
            return host
    raise SparkRunError(f"No Spark host has >= {min_free_gb} GB free. Checked: {'; '.join(checked)}")


def _scp_to(local: Path, host: str, remote: str) -> None:
    proc = subprocess.run(["scp", "-q", str(local), f"{host}:{remote}"], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SparkRunError(f"scp {local} -> {host}:{remote} failed: {proc.stderr.strip()}")


def _scp_from(host: str, remote: str, local: Path) -> None:
    proc = subprocess.run(["scp", "-q", f"{host}:{remote}", str(local)], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SparkRunError(f"scp {host}:{remote} -> {local} failed: {proc.stderr.strip()}")


def run_remote_transcription(audio_path: Path, manifest: dict, *, host: str,
                              session_id: str, progress=print) -> dict:
    """Runs one manifest through the Spark. Returns the parsed result JSON."""
    remote_dir = f"{REMOTE_WORKDIR}/{session_id}"
    _ssh(host, f"mkdir -p {remote_dir}")

    # The manifest's audio_path is read directly by Python (av.open()) on
    # the far side, with no shell in between to expand '~' -- unlike the
    # ssh/scp remote-path arguments below, which do pass through a remote
    # shell. Resolve to an absolute path for this one field.
    remote_home = _remote_home(host)
    remote_dir_abs = remote_dir.replace("~", remote_home, 1) if remote_dir.startswith("~") else remote_dir

    manifest = dict(manifest)
    manifest["audio_path"] = f"{remote_dir_abs}/{audio_path.name}"
    manifest_local = Path(f"/tmp/{session_id}-manifest.json")
    manifest_local.write_text(json.dumps(manifest), encoding="utf-8")

    progress(f"Copying audio ({audio_path.stat().st_size / 1_048_576:.1f} MB) to {host}:{remote_dir}/ ...")
    _scp_to(audio_path, host, f"{remote_dir}/{audio_path.name}")
    _scp_to(manifest_local, host, f"{remote_dir}/manifest.json")

    progress(f"Running transcription on {host} ...")
    remote_output = f"{remote_dir}/result.json"
    remote_cmd = (f"{REMOTE_VENV_PYTHON} {REMOTE_SCRIPT} "
                  f"--manifest {remote_dir}/manifest.json --output {remote_output}")
    proc = subprocess.run(["ssh", host, remote_cmd], text=True)
    if proc.returncode != 0:
        raise SparkRunError(f"remote transcription on {host} exited {proc.returncode}")

    local_output = Path(f"/tmp/{session_id}-result.json")
    _scp_from(host, remote_output, local_output)
    return json.loads(local_output.read_text(encoding="utf-8"))
