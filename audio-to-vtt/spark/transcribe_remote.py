#!/usr/bin/env python3
"""Spark-side worker: re-transcribe cue-group audio spans with faster-whisper.

Deployed via scp to the Spark home dir (flat-copy, NOT git-synced — see
audio-to-vtt/CLAUDE.md: editing the repo copy of this file does nothing
until it is re-scp'd). Reads a manifest JSON (audio path, cue groups,
ranked vocabulary, model/runtime settings), loads WhisperModel ONCE, trims
vocabulary to the model's real token budget using its own tokenizer, then
loops cue groups calling transcribe() with clip_timestamps/hotwords per
group. condition_on_previous_text=False so every group decodes
independently (avoids known cross-clip context bleeding, see plan §1 /
SYSTRAN/faster-whisper#839 and #1355). No persistent server — this process
loads, runs, writes its output, and exits.

IMPORTANT (found empirically, 2026-07-18): faster_whisper.transcribe()
decodes its ENTIRE input file into memory on every call when given a file
path -- `clip_timestamps` only slices the already-fully-decoded array
afterward (see faster_whisper/transcribe.py: `if not isinstance(audio,
np.ndarray): audio = decode_audio(...)` runs unconditionally before
clip_timestamps is consulted). Calling transcribe(audio_path,
clip_timestamps=...) once per cue-group, as an earlier version of this
script did, re-decodes the full multi-hour recording on every single call
-- measured RTF 4.2 (i.e. 4x SLOWER than real time) on a real 87-minute
session, dominated by this repeated full-file decode, not by GPU compute.
The fix: decode the audio ONCE via faster_whisper.audio.decode_audio(),
then slice that in-memory numpy array per cue-group and pass the slice
(not the file path) to transcribe() -- skips decode_audio() entirely on
every call after the first.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# The Spark's shared ~/.cache/huggingface/hub is root-owned (populated by the
# Docker-based vLLM containers) -- a user-level process can't write new model
# dirs there. Give this project its own cache rather than touching shared
# infra used by the production chat LLM. Must be set before `faster_whisper`
# (and the huggingface_hub it pulls in) is imported.
os.environ.setdefault("HF_HOME", str(Path.home() / ".cache" / "audio-to-vtt-hf"))

# No prebuilt CUDA-enabled ctranslate2 wheel exists for aarch64 (verified
# empirically on this exact hardware -- see CLAUDE.md's "Hardware notes").
# This venv carries a from-source CUDA build instead (see
# spark/setup_spark_venv.sh / CLAUDE.md), whose runtime .so -- plus the
# nvidia-cudnn-cu12 / nvidia-cublas-cu12 pip packages' bundled libraries --
# aren't on the default loader path.
#
# Setting os.environ["LD_LIBRARY_PATH"] here does NOT work, despite being a
# common assumption -- verified empirically: glibc's dynamic linker does not
# re-consult a mid-process environment change for dlopen()'s dependent-library
# search on this system. The reliable fix is to ctypes.CDLL-preload each
# dependency by absolute path (RTLD_GLOBAL) BEFORE `ctranslate2` is imported,
# in dependency order -- once a library with a given soname is already loaded
# into the process, the dynamic linker resolves later implicit references to
# it by soname match regardless of search path.
import ctypes  # noqa: E402

_venv_root = Path(sys.prefix)
_site_packages = _venv_root / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
for _lib_path in [
    _site_packages / "nvidia" / "cublas" / "lib" / "libcublas.so.12",
    _site_packages / "nvidia" / "cudnn" / "lib" / "libcudnn.so.9",
    _venv_root / "native-libs" / "libctranslate2.so.4",
]:
    if _lib_path.exists():
        ctypes.CDLL(str(_lib_path), mode=ctypes.RTLD_GLOBAL)


def _trim_to_token_budget(model, names: list[str], token_budget: int) -> str:
    """Walk `names` in priority order, accumulating into a comma-joined
    hotwords string, stopping once the built string would exceed
    `token_budget` tokens per the model's own tokenizer. Falls back to a
    ~4-chars/token estimate if model.hf_tokenizer isn't reachable the way
    expected — this fallback path should never silently become the norm;
    audio-to-vtt/CLAUDE.md records how this was verified empirically."""
    def count_tokens(s: str) -> int:
        try:
            return len(model.hf_tokenizer.encode(s).ids)
        except Exception:
            return max(1, len(s) // 4)

    kept: list[str] = []
    for name in names:
        candidate = ", ".join([*kept, name])
        if count_tokens(candidate) > token_budget:
            if kept:
                break
            continue  # a single name alone blows the budget; skip it, try the next
        kept.append(name)
    return ", ".join(kept)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))

    from faster_whisper import WhisperModel

    requested_device = manifest.get("device", "cuda")
    compute_type = manifest.get("compute_type", "int8_float16")
    model_size = manifest.get("model_size", "large-v3")

    print(f"[transcribe_remote] loading {model_size} device={requested_device} "
          f"compute_type={compute_type} ...", file=sys.stderr, flush=True)
    load_start = time.monotonic()
    device_used = requested_device
    try:
        model = WhisperModel(model_size, device=requested_device, compute_type=compute_type)
    except Exception as e:
        print(f"[transcribe_remote] {requested_device} load failed ({e}); "
              f"falling back to cpu/int8", file=sys.stderr, flush=True)
        device_used = "cpu"
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
    print(f"[transcribe_remote] model loaded in {time.monotonic() - load_start:.1f}s "
          f"(device_used={device_used})", file=sys.stderr, flush=True)

    token_budget = manifest.get("token_budget", 200)
    vocabulary = manifest.get("vocabulary", [])
    hotwords = _trim_to_token_budget(model, vocabulary, token_budget) if vocabulary else ""
    preview = hotwords[:200] + ("..." if len(hotwords) > 200 else "")
    print(f"[transcribe_remote] hotwords ({len(hotwords)} chars, from "
          f"{len(vocabulary)} candidates): {preview}", file=sys.stderr, flush=True)

    audio_path = manifest["audio_path"]
    language = manifest.get("language", "en")
    cue_groups = manifest["cue_groups"]

    smoke_test_seconds = manifest.get("smoke_test_seconds")
    if smoke_test_seconds:
        cue_groups = [g for g in cue_groups if g["start"] < smoke_test_seconds]
        print(f"[transcribe_remote] smoke-test: {len(cue_groups)} cue groups within "
              f"first {smoke_test_seconds}s", file=sys.stderr, flush=True)

    from faster_whisper.audio import decode_audio

    decode_start = time.monotonic()
    sampling_rate = model.feature_extractor.sampling_rate
    full_audio = decode_audio(audio_path, sampling_rate=sampling_rate)
    print(f"[transcribe_remote] decoded full audio ({full_audio.shape[0] / sampling_rate:.1f}s) "
          f"once in {time.monotonic() - decode_start:.1f}s", file=sys.stderr, flush=True)

    results = []
    run_start = time.monotonic()
    for i, group in enumerate(cue_groups):
        start, end = group["start"], group["end"]
        clip = full_audio[int(start * sampling_rate):int(end * sampling_rate)]
        segments, _info = model.transcribe(
            clip,
            language=language,
            hotwords=hotwords or None,
            condition_on_previous_text=False,
            word_timestamps=True,
            beam_size=5,
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        results.append({"start": start, "end": end, "speaker": group["speaker"], "text": text})
        if (i + 1) % 10 == 0 or (i + 1) == len(cue_groups):
            elapsed = time.monotonic() - run_start
            print(f"[transcribe_remote] {i + 1}/{len(cue_groups)} groups "
                  f"({elapsed:.1f}s elapsed)", file=sys.stderr, flush=True)

    elapsed_total = time.monotonic() - run_start
    audio_seconds = (cue_groups[-1]["end"] - cue_groups[0]["start"]) if cue_groups else 0
    # elapsed / audio_seconds: below 1.0 means faster than real time.
    rtf = (elapsed_total / audio_seconds) if audio_seconds else None

    output = {
        "results": results,
        "hotwords_used": hotwords,
        "device_used": device_used,
        "model_size": model_size,
        "compute_type": compute_type,
        "elapsed_seconds": elapsed_total,
        "audio_seconds_covered": audio_seconds,
        "real_time_factor": rtf,
    }
    args.output.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"[transcribe_remote] wrote {args.output} ({len(results)} groups, "
          f"{elapsed_total:.1f}s, RTF={rtf})", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
