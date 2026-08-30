#!/usr/bin/env python3
"""Spark-side speaker diarization. Counterpart of transcribe_remote.py.

Reads a manifest JSON, decodes the audio ONCE with PyAV (bundled ffmpeg --
there is no system ffmpeg on the Spark boxes), runs pyannote.audio's
speaker-diarization pipeline on the GPU, and writes speaker turns as JSON.

Why this exists: audio-to-vtt/CLAUDE.md asserts Zoom's speaker attribution
is reliable and re-diarizing "would be solving a problem that doesn't
exist". Phandalin chapter 04 disproves that -- Zoom's live *text* export
flips speaker mid-sentence under crosstalk, and the audio-aligned Whisper
transcript (which has correct sentence boundaries) carries no speaker
labels at all. Diarization supplies the missing join.

HF_HOME is redirected to a project-owned cache: the shared
~/.cache/huggingface/hub on these boxes is root-owned (populated by the
Docker vLLM containers), so a user-level process cannot write model dirs
there. Same workaround transcribe_remote.py uses.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Must precede any huggingface_hub / pyannote import.
os.environ.setdefault("HF_HOME", os.path.expanduser("~/.cache/diarize-hf"))


def decode_audio_mono16k(path: str):
    """Decode any container to mono 16 kHz float32 via PyAV.

    pyannote wants a (channel, sample) tensor. Decoding here -- rather than
    handing pyannote a file path -- keeps us off torchcodec's system-ffmpeg
    dependency, which is absent on these boxes.
    """
    import av
    import numpy as np

    with av.open(path) as container:
        stream = container.streams.audio[0]
        resampler = av.audio.resampler.AudioResampler(
            format="s16", layout="mono", rate=16000
        )
        chunks = []
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        # flush
        for out in resampler.resample(None):
            chunks.append(out.to_ndarray().reshape(-1))

    if not chunks:
        raise RuntimeError(f"decoded no audio from {path}")
    pcm = np.concatenate(chunks).astype("float32") / 32768.0
    return pcm


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    audio_path = manifest["audio_path"]
    token_path = manifest.get("hf_token_path")
    num_speakers = manifest.get("num_speakers")
    model_id = manifest.get("model", "pyannote/speaker-diarization-3.1")
    device_req = manifest.get("device", "cuda")

    token = None
    if token_path:
        token = Path(os.path.expanduser(token_path)).read_text(encoding="utf-8").strip()

    print(f"[diarize] decoding {audio_path} ...", file=sys.stderr, flush=True)
    pcm = decode_audio_mono16k(audio_path)
    dur = len(pcm) / 16000.0
    print(f"[diarize] decoded {dur:.1f}s ({dur/60:.1f} min)", file=sys.stderr, flush=True)

    import torch
    from pyannote.audio import Pipeline

    print(f"[diarize] loading {model_id} ...", file=sys.stderr, flush=True)
    try:
        pipeline = Pipeline.from_pretrained(model_id, token=token)
    except TypeError:
        # pyannote < 4 used use_auth_token
        pipeline = Pipeline.from_pretrained(model_id, use_auth_token=token)

    if pipeline is None:
        raise RuntimeError(
            f"Pipeline.from_pretrained({model_id!r}) returned None -- this "
            "almost always means the HF token has not accepted the model's "
            "gated user conditions. Visit the model page and accept, then retry."
        )

    device_used = "cpu"
    if device_req == "cuda" and torch.cuda.is_available():
        pipeline.to(torch.device("cuda"))
        device_used = "cuda"
    print(f"[diarize] running on {device_used} "
          f"(num_speakers={num_speakers}) ...", file=sys.stderr, flush=True)

    waveform = torch.from_numpy(pcm).unsqueeze(0)  # (1, samples)
    kwargs = {}
    if num_speakers:
        kwargs["num_speakers"] = int(num_speakers)

    try:
        from pyannote.audio.pipelines.utils.hook import ProgressHook
        with ProgressHook() as hook:
            diarization = pipeline(
                {"waveform": waveform, "sample_rate": 16000}, hook=hook, **kwargs
            )
    except Exception:
        diarization = pipeline(
            {"waveform": waveform, "sample_rate": 16000}, **kwargs
        )

    # pyannote 4.x returns a DiarizeOutput dataclass; 3.x returned the
    # Annotation directly. Both expose itertracks() on the annotation.
    def as_turns(ann):
        if ann is None:
            return []
        return [
            {"start": round(seg.start, 3), "end": round(seg.end, 3), "speaker": label}
            for seg, _, label in ann.itertracks(yield_label=True)
        ]

    annotation = getattr(diarization, "speaker_diarization", diarization)
    exclusive = getattr(diarization, "exclusive_speaker_diarization", None)

    turns = as_turns(annotation)
    turns_exclusive = as_turns(exclusive)

    speakers = sorted({t["speaker"] for t in turns})
    total = sum(t["end"] - t["start"] for t in turns)

    # Overlapping speech is exactly where Zoom's talk-detection flips speaker
    # mid-sentence, so record it: it tells us which splits were real crosstalk
    # rather than an attribution bug.
    overlaps = []
    for i, a in enumerate(turns):
        for b in turns[i + 1:]:
            if b["start"] >= a["end"]:
                break
            if b["speaker"] != a["speaker"]:
                overlaps.append({"start": round(max(a["start"], b["start"]), 3),
                                 "end": round(min(a["end"], b["end"]), 3),
                                 "speakers": sorted([a["speaker"], b["speaker"]])})

    print(f"[diarize] {len(turns)} turns, {len(speakers)} speakers, "
          f"{total/60:.1f} min of speech, {len(overlaps)} overlap regions",
          file=sys.stderr, flush=True)

    Path(args.output).write_text(json.dumps({
        "audio_path": audio_path,
        "audio_duration": round(dur, 3),
        "model": model_id,
        "device_used": device_used,
        "num_speakers_requested": num_speakers,
        "speakers": speakers,
        "turns": turns,
        "turns_exclusive": turns_exclusive,
        "overlaps": overlaps,
    }), encoding="utf-8")
    print(f"[diarize] wrote {args.output}", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
