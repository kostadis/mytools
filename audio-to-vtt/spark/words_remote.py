#!/usr/bin/env python3
"""Spark-side worker: full-file faster-whisper pass with WORD timestamps.

Unlike transcribe_remote.py (which re-transcribes cue groups and returns text
per group), this transcribes a whole recording once and emits every word with
its own start/end. Its consumer is speaker-attribution's project_turns.py,
which aligns these words to an edited-timeline transcript to project raw-audio
diarization onto it. The text is an alignment anchor, not a deliverable.

Deployed flat via scp, same as transcribe_remote.py (re-copy before every run):

  scp spark/words_remote.py spark2:~/audio-to-vtt-words-remote.py
  ssh spark2 '~/.venvs/audio-to-vtt/bin/python ~/audio-to-vtt-words-remote.py \\
      /abs/path/audio.m4a /abs/path/words.json > words.log 2>&1'

Measured 2026-09-25 on spark2 beside a 103 GB vLLM: large-v3 int8_float16 on
cuda, 85.3 min of audio in 213 s (~24x real time), 11,243 words.
"""

import ctypes
import json
import os
import sys
import time
from pathlib import Path

# Same two workarounds as transcribe_remote.py: a user-writable HF cache (the
# shared one is root-owned), and preloading the CUDA libs by absolute path
# before ctranslate2 is imported (LD_LIBRARY_PATH set mid-process is ignored).
os.environ.setdefault("HF_HOME", str(Path.home() / ".cache" / "audio-to-vtt-hf"))
_venv = Path(sys.prefix)
_sp = _venv / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
for _lib in [_sp / "nvidia" / "cublas" / "lib" / "libcublas.so.12",
             _sp / "nvidia" / "cudnn" / "lib" / "libcudnn.so.9",
             _venv / "native-libs" / "libctranslate2.so.4"]:
    if _lib.exists():
        ctypes.CDLL(str(_lib), mode=ctypes.RTLD_GLOBAL)

from faster_whisper import WhisperModel  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        sys.exit("usage: words_remote.py AUDIO OUTPUT_JSON")
    audio, out = sys.argv[1], sys.argv[2]
    model = WhisperModel("large-v3", device="cuda", compute_type="int8_float16")
    print("[words] loaded large-v3 on cuda", file=sys.stderr, flush=True)
    segments, info = model.transcribe(audio, language="en", word_timestamps=True,
                                      condition_on_previous_text=False,
                                      vad_filter=True, beam_size=5)
    words, t0 = [], time.monotonic()
    for seg in segments:
        words.extend([round(w.start, 2), round(w.end, 2), w.word] for w in seg.words)
        print(f"[words] at {seg.end:.0f}s / {info.duration:.0f}s "
              f"({time.monotonic() - t0:.0f}s)", file=sys.stderr, flush=True)
    Path(out).write_text(json.dumps({"duration": info.duration, "model": "large-v3",
                                     "words": words}), encoding="utf-8")
    print(f"[words] done: {len(words)} words", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
