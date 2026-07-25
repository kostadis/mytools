# audio-to-vtt -- Claude instructions

Re-transcribes a D&D session's Zoom `.m4a` recording into a more accurate
WebVTT, reusing the existing Zoom `.vtt`'s cue boundaries/speaker labels
(reliable) and biasing faster-whisper -- run on the DGX Spark -- with
campaign-specific proper-noun vocabulary (unreliable in the original Zoom
transcription). Counterpart of the sibling `vtt-to-tts/` project (that one
goes VTT -> speech; this one goes audio -> VTT).

## Why this design

- **Reuse Zoom's cue boundaries/speaker labels; only replace the text.**
  Zoom's own speaker attribution and cue timing are already reliable --
  the transcribed *words* are what's wrong (fantasy proper nouns get
  anglicized/mangled). Re-diarizing from scratch would be solving a
  problem that doesn't exist here. `vtt_scaffold.py` parses the existing
  `.vtt`, groups consecutive same-speaker cues (capped at
  `--max-group-seconds`, default 25s -- safely under Whisper's native 30s
  window and under a known >30s clip bug, SYSTRAN/faster-whisper#1355).
  The audio is decoded ONCE (via `faster_whisper.audio.decode_audio()`) and
  each cue-group's slice of that in-memory array is passed directly to
  `transcribe()` -- no ffmpeg, no cut files, and critically, no per-call
  `clip_timestamps` (see the decode-once finding further down: passing a
  file path + `clip_timestamps` instead re-decodes the ENTIRE recording on
  every single call).
- **Zoom's own "Audio shared by X" system-caption cues are never
  re-transcribed.** Found empirically (obelisk session 006, 2026-07-19):
  faster-whisper reliably hallucinates video-outro phrases ("Thanks for
  watching!", "Audio shared by X: [fabricated content]") on these spans,
  regardless of clip length -- there's often no real speech there (they
  mark a screen/audio-share window, not a participant talking).
  `vtt_scaffold.is_system_caption_speaker()` detects the
  `^Audio shared by\b` speaker-label pattern; `retranscribe.py` excludes
  matching cue-groups from the Spark manifest entirely and keeps Zoom's
  original text for them unchanged in the output. If Zoom ever uses a
  different system-caption wording, extend that one regex, not the
  calling code.
- **`condition_on_previous_text=False`.** Each cue-group's decode is
  independent. The alternative (`True`, faster-whisper's default) is
  documented to cause cross-clip hallucination bleeding
  (SYSTRAN/faster-whisper#839) -- and independently, our design goal is
  "re-transcribe this segment on its own merits," not build one
  continuous narrative.
- **Vocabulary bias via `hotwords`, not `initial_prompt`.** `hotwords`
  applies persistently across every decode window; `initial_prompt` only
  biases a call's *first* window, which is meaningless once every call
  already *is* a first window (each cue-group is its own short
  `transcribe()` call). See `vocab.py`'s docstring for the ranked source
  order (glossary canonicals > registry aliases > module inventory) and
  why the glossary's wrong-forms must never be fed in.
- **Token-budget trimming happens on the Spark, not the workstation.**
  Whisper's practical hotword budget is ~224 tokens; a full campaign
  registry is an order of magnitude larger. `vocab.py` ships the full,
  ranked, uncapped candidate list in the manifest; `spark/transcribe_remote.py`
  trims it against the *loaded model's own tokenizer* (a word-count guess
  would be wrong -- fantasy names routinely split into 2-4 BPE subwords).
- **No persistent server on the Spark.** faster-whisper is a plain Python
  library call, not an HTTP API -- there's no chat-completions-shaped
  surface for `dgxlib` to wrap, and a standing server would mean 24/7
  memory reservation on boxes that are already tight, plus the
  `current-setup.md`/`dgxlib/models.yaml` update obligations
  `~/src/dgx/CLAUDE.md` mandates for any new long-running service. Instead
  `spark_runner.py` mirrors the existing `ssh spark2 'bash ~/spin-up-vllm-...sh'`
  pattern: SSH-invoke a one-shot script that loads, runs, writes its
  output, and exits.
- **Flagging missed proper nouns is vocabulary-anchored, not a text diff.**
  `proper_noun_review.py` compares Zoom's transcript against the
  retranscription per cue group, but does not diff the two texts directly --
  two independent ASR passes over the same audio disagree on phrasing,
  fillers, and punctuation almost everywhere, so a plain diff is mostly
  noise unrelated to proper nouns. Instead, for each cue group: if a
  campaign vocabulary term is confidently present in the retranscription
  (fuzzy match, since hotword bias isn't perfect) but does **not** appear
  verbatim anywhere in Zoom's text for that same span, it's flagged. The
  "already present in Zoom" check is deliberately exact-match, not fuzzy --
  a fuzzy threshold there would treat a near-miss like "Toblin" against
  canonical "Toblen" as *close enough* and silently skip it, which is
  exactly the class of one-or-two-letter mangle this tool exists to catch.
  Zoom's transcript is never rewritten by this pass; it only produces a
  `<cleaned-stem>.proper_nouns.md` report for the GM to check by hand,
  wired into `retranscribe.py`'s end-of-run flow and also runnable
  standalone against an already-completed pair.
- **Not Ollama.** Verified before building this: Ollama does not support
  real audio-in ASR models (long-open, unresolved upstream feature
  requests -- `ollama/ollama` issues #8202, #7976, #4168, #1168, #2815 --
  and the "whisper" models listed on ollama.com, e.g. `dimavz/whisper-tiny`,
  are mislabeled text-only chat models that never accept audio input).

## Deployment drift -- read this before debugging a stale result

`spark/transcribe_remote.py` is deployed to the Spark via a flat `scp`,
**not** a git checkout. Editing the repo copy in
`~/src/mytools/audio-to-vtt/spark/` does **nothing** on the Spark until
you re-`scp` it to `~/audio-to-vtt-transcribe-remote.py` on the target
box. `~/src/dgx/CLAUDE.md` carries the identical warning for the vLLM
spin-up scripts -- same failure mode, same fix: re-copy before you trust a
change took effect. There is no sync step in this tool; do it by hand:

```bash
scp spark/transcribe_remote.py spark2:~/audio-to-vtt-transcribe-remote.py
```

## No `current-setup.md` / `dgxlib/models.yaml` update needed

Because no persistent container or service is added (see "why this
design" above), this project does not touch `~/src/dgx/current-setup.md`
or `dgxlib/models.yaml`. If this ever evolves into a standing/low-latency
transcription endpoint rather than an occasional batch job, *that* change
would re-trigger both of those update obligations per `~/src/dgx/CLAUDE.md`'s
own rules -- and would reopen the 24/7-memory-reservation cost this design
currently avoids on purpose.

## Reused, not reimplemented

- `vtt_scaffold.py`'s cue parsing mirrors `vtt-to-tts/transcript_to_mp3.py`'s
  `parse_webvtt`/`_VTT_SPEAKER` regex -- same target VTT shape.
- `vocab.py` imports `parse_glossary` directly from
  `dotfiles/claude/skills/vtt-spell-pass/find_unknowns.py` rather than
  re-deriving glossary-table parsing.
- `retranscribe.py`'s mandatory post-pass shells out to
  `dotfiles/claude/skills/vtt-spell-pass/apply_replacements.py` as-is --
  no glossary-matching logic lives in this project.
- The tool's last line of output is always "run `/vtt-spell-pass` on
  `<output>`" -- that skill's human-confirmation loop is the real backstop,
  not a suggestion.

## Hardware notes (DGX Spark, GB10, aarch64)

- Both boxes commonly run tight on unified memory (they're serving a
  Qwen3-Next-80B chat model on vLLM) -- `spark_runner.py`'s
  `--min-free-gb` pre-flight check is not optional. Check current state
  with `ssh spark2 'free -m'` before assuming headroom.
- The shared `~/.cache/huggingface/hub` on both boxes is **root-owned**
  (populated by the Docker-based vLLM containers) -- a user-level
  faster-whisper process cannot write new model dirs there
  (`PermissionError`). `transcribe_remote.py` sets `HF_HOME` to
  `~/.cache/audio-to-vtt-hf` (a project-owned cache) before importing
  `faster_whisper`, rather than touching the shared cache's ownership.
- **No prebuilt CUDA-enabled `ctranslate2` wheel exists for aarch64 --
  confirmed empirically on spark2, 2026-07-18.** `--extra-index-url
  https://pypi.nvidia.com` (the fix suggested by
  speaches-ai/speaches#620) does NOT work: that index does not host
  `ctranslate2` at all (`curl https://pypi.nvidia.com/ctranslate2/` ->
  `NoSuchKey`), so pip silently falls back to the default PyPI wheel,
  which is CPU-only. Loading `WhisperModel(..., device="cuda")` on this
  hardware raises `ValueError('This CTranslate2 package was not compiled
  with CUDA support')`.
- **This project built ctranslate2 v4.8.1 from source with CUDA on
  spark2 (2026-07-18) and it works.** Compiled inside a
  `docker run --gpus all nvidia/cuda:12.6.3-cudnn-devel-ubuntu24.04`
  container (GPU access during the build is what lets CMake's
  `-DCUDA_ARCH_LIST=Auto` correctly detect the live GB10 -- compute
  capability **12.1**). Real gotchas hit along the way, in case this
  needs redoing for a version bump:
  - `-DWITH_MKL=OFF -DWITH_DNNL=OFF -DWITH_ACCELERATE=OFF -DWITH_OPENBLAS=OFF`
    -- MKL is x86-only; ctranslate2 already vendors Google's `ruy` for
    ARM CPU GEMM, so none of the x86 backends are needed.
  - `-DOPENMP_RUNTIME=COMP` -- without this, CMake configure fails
    looking for Intel's `libiomp5`, which doesn't exist on ARM. `COMP`
    uses GCC's `libgomp` instead.
  - The Python wheel build needs its own venv inside the build
    container (Ubuntu 24.04's system pip is "externally managed",
    PEP 668) -- `python3 -m venv /tmp/build-venv` before `pip install -r
    install_requirements.txt && python setup.py bdist_wheel`.
  - `make install` writes `libctranslate2.so.4` to `/usr/local/lib`
    *inside* the container -- that's not bind-mounted, so a `--rm`
    container loses it. Copy the already-compiled `.so` straight out of
    the bind-mounted `build/` dir instead of re-running `make install`
    in a fresh container (which also needs `--gpus all`/cmake present
    again -- easy to trip over).
  - The built wheel only contains the *Python bindings* extension; it
    still dynamically links `libctranslate2.so.4`, `libcudnn.so.9`,
    `libcublas.so.12` at runtime. `libcudnn`/`libcublas` are NOT on this
    box outside of pip -- `pip install nvidia-cudnn-cu12
    nvidia-cublas-cu12` (real aarch64 wheels exist, ~1.4 GB combined)
    supplies them, bundled under `.../site-packages/nvidia/{cudnn,cublas}/lib/`.
  - **Setting `os.environ["LD_LIBRARY_PATH"]` mid-process, before
    `import ctranslate2`, does NOT work** on this system -- verified
    empirically, despite this being common assumed-to-work advice.
    glibc's dynamic linker does not re-consult a mid-process environment
    change for `dlopen()`'s dependency search here. The reliable fix,
    used in `transcribe_remote.py`: `ctypes.CDLL(path,
    mode=ctypes.RTLD_GLOBAL)`-preload each dependency by absolute path,
    in dependency order, before the `ctranslate2` import -- once a
    library is already loaded into the process, later implicit
    references to its soname resolve by identity, regardless of search
    path.
  - The built `.so` and the venv it was installed into are both
    machine-specific (compiled against this exact GPU/driver/CUDA
    combination) -- they don't belong in the repo and don't travel with
    a plain `pip install -r requirements-spark.txt`. Rebuilding is a
    manual, hands-on-the-Spark step, not part of `setup_spark_venv.sh`.
  - `transcribe_remote.py` still falls back to `device="cpu",
    compute_type="int8"` automatically if a CUDA load ever fails again
    (e.g. after a driver update) -- the tool degrades gracefully rather
    than hard-failing.
- **`faster_whisper.transcribe()` decodes its ENTIRE input file on every
  call when given a file path -- `clip_timestamps` only slices the
  already-fully-decoded array afterward.** Calling `transcribe(audio_path,
  clip_timestamps=...)` once per cue-group, as an early version of this
  tool did, re-decodes the full multi-hour recording on every single call.
  Measured on the real 87-minute obelisk session, large-v3, this exact
  GPU: **RTF 4.2 (slower than real time; ~6 hours extrapolated)** with the
  broken per-call-full-decode pattern, vs. **RTF 0.065 (~15x real time;
  ~5.6 min extrapolated)** once fixed to decode once via
  `faster_whisper.audio.decode_audio()` and slice the in-memory numpy
  array per cue-group. A ~65x difference from one calling-convention fix
  -- confirms the from-source CUDA build itself is genuinely fast; the
  first smoke-test's bad number was this bug, not the hardware or the
  build.
- Runtime is bimodal: GPU engaged vs. not is the difference between
  "run and wait ~15-40 min" and "run overnight" for a 3-4 hour session.
  Given the CUDA finding above, expect the CPU path by default on this
  hardware today. Always run `--smoke-test` before committing to an
  unattended full run, and check `device_used` in its output.
