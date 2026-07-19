---
name: project_audio_to_vtt
description: audio-to-vtt tool (m4a -> accurate VTT via faster-whisper on the DGX Spark) and the real Spark/CUDA build findings from standing it up
metadata: 
  node_type: memory
  type: project
  originSessionId: 95497cf4-83b2-4ae6-98b1-3add34661b4f
  modified: 2026-07-19T15:50:22.424Z
---

Built `~/src/mytools/audio-to-vtt/` (2026-07-18/19): re-transcribes a D&D
session's Zoom `.m4a` into a more accurate WebVTT, reusing Zoom's existing
cue timing/speaker labels and biasing faster-whisper with the campaign's
own proper-noun vocabulary (glossary canonicals > entity registry aliases
> module inventory). Runs on the DGX Spark (`spark2`), not Ollama and not
the OpenAI API — deliberate choice to exercise the local hardware. Full
design in the project's own `CLAUDE.md`/`README.md`; a `/audio-to-vtt`
skill drives the dry-run -> smoke-test -> confirm -> full-run flow.

**Why:** Zoom's live captioning gets speaker/timing right but mangles
fantasy proper nouns; the existing `vtt-spell-pass` skill only fixes this
after the fact. This tool re-transcribes just the audio per cue-group with
vocabulary bias, then still runs the same glossary pass as a mandatory
cleanup step.

**Real hardware findings, likely relevant to any future Spark work, not
just this tool:**
- Ollama does not support real audio-in ASR models at all (confirmed via
  long-open upstream `ollama/ollama` feature requests) — ruled it out
  early rather than forcing a fit.
- No prebuilt CUDA-enabled `ctranslate2` wheel exists for aarch64 (the
  commonly-suggested `pypi.nvidia.com` fix doesn't work — that index
  doesn't host the package at all). Built ctranslate2 v4.8.1 from source
  on spark2 instead, targeting the GB10's real compute capability (12.1),
  inside a `docker run --gpus all nvidia/cuda:*-cudnn-devel` container.
  Gotchas hit: needs `-DOPENMP_RUNTIME=COMP` (no Intel libiomp5 on ARM),
  Ubuntu 24.04's PEP 668 blocks a bare `pip install` (build the wheel in
  its own venv), the compiled `.so` isn't inside the wheel and must be
  copied out of the bind-mounted build dir separately, and — most
  surprising — setting `os.environ["LD_LIBRARY_PATH"]` mid-process before
  `import ctranslate2` does **not** work on this system; the reliable fix
  is `ctypes.CDLL(path, mode=RTLD_GLOBAL)`-preloading each dependency by
  absolute path first.
- Found and fixed a 65x performance bug of my own making: `faster_whisper.
  transcribe()` decodes the **entire** input file on every call when
  given a file path (`clip_timestamps` only slices the already-decoded
  array afterward) — calling it once per cue-group was re-decoding a full
  87-minute recording on every one of ~600 calls. Measured RTF 4.2 (~6h
  projected) before the fix, RTF 0.06-0.11 (~9x real-time; ~9 min for an
  87-100 min session) after decoding once and slicing in Python.

**How to apply:** if extending this tool, touching the Spark's Python/CUDA
stack again, or debugging a similarly "runs but is mysteriously slow"
faster-whisper/ctranslate2 issue elsewhere, read this tool's `CLAUDE.md`
"Hardware notes" section first — it has the exact commands, not just the
summary above.

**Parakeet-TDT evaluation as a Whisper alternative (2026-07-19, CPU-only
spike on the workstation, not the Spark):** explored whether NVIDIA's
NeMo/Parakeet ASR family is worth porting to. Findings:
- **DGX Spark/GB10 (aarch64) is a genuinely rough NeMo target** — the
  official NVIDIA NIM Parakeet container is x86-only; forum reports on
  this exact hardware describe silent CUDA-not-found in plain pip
  installs and needing a custom Docker build pinned to NVIDIA's PyTorch
  25.10 container (25.12 breaks Lhotse's sampler init). Only the 1.1B
  CTC/RNNT checkpoints are reported Spark-GPU-compatible; the more
  accurate 0.6B TDT has reported GPU issues on this exact hardware.
  Skipped the GPU/Docker path for now given both Spark boxes were
  already at ~11GB unified-memory headroom with a documented OOM/kernel-
  panic history under memory pressure (see `~/src/dgx/current-setup.md`)
  — didn't want to risk the client-facing production `vllm-chat` boxes
  for a spike.
- **The workstation has an idle RTX 4080 (16GB, ~12GB free)** — standard
  x86_64, no aarch64 wheel drama, zero shared-production risk. Not used
  yet (spike was CPU-only by choice) but the obvious next step if a GPU
  comparison is wanted — much lower-risk than either Spark box.
- **`nemo_toolkit[asr]` needs Python <=3.11, not 3.12** — under Python
  3.12 pip/uv resolves `librosa` down to a `numba==0.53.1` /
  `llvmlite==0.36.0` pin that fails to build (`llvmlite` hard-guards
  Python <3.10 in its own setup.py). Fixed by creating the venv with
  `uv venv --python 3.11` instead of the system 3.12 — installed clean
  on the first try after that.
- **CPU-only result (`nvidia/parakeet-tdt-0.6b-v2`, no vocab biasing
  at all) on a real 85s clip from obelisk session 006:** loaded in 55s
  (cold, incl. the 2.4GB HF download), transcribed in 5.9s — **RTF 0.07,
  ~14x real-time, on CPU alone.** Quality on the same span already used
  for this project's own hotword-bias validation (`Sister Maela ...
  Pip ... Veyra`, ground truth per `notes/vtt_transcription_corrections.md`):
  Parakeet zero-shot got the proper nouns wrong the same way Zoom's
  original did ("Mela"/"Vera", expected with no vocab bias applied), but
  correctly transcribed "We will" where this project's own faster-whisper
  + hotwords run had hallucinated "Weeble" on the exact same span — i.e.
  Parakeet's raw output had *fewer* hallucinations than faster-whisper's
  biased output, even though it hasn't been given the vocabulary fix yet.
- **Word-boosting/context-biasing exists for TDT models** (GPU-accelerated
  phrase-boosting, NeMo 2.5+) — Python API confirmed working on CPU:
  `nemo.collections.asr.parts.context_biasing.BoostingTreeModelConfig(
  key_phrases_list=[...], depth_scaling=2.0, use_triton=False)` assigned to
  `model.cfg.decoding.greedy.boosting_tree` (needs `OmegaConf.set_struct(
  decoding_cfg, False)` first — the loaded checkpoint's decoding config is
  struct-locked and rejects new keys otherwise) + `boosting_tree_alpha`,
  then `model.change_decoding_strategy(decoding_cfg)`. Real integration
  work (a fusion-weight config, not a one-line `hotwords="..."` kwarg like
  faster-whisper), but not a blocker.
- **Boosting_tree_alpha swept 0.5/1.0/2.0/4.0/8.0 on the full 546-term
  obelisk campaign vocabulary, same clip, same "Maela"/"Veyra" ground
  truth — the knob is a genuinely narrow, precision-sensitive tradeoff,
  not "more is better":**
  - **0.5:** fixed "Sister Mela" → "Sister Maela" (correct) but left
    "Vera" unfixed (should be "Veyra") — partial win.
  - **1.0–2.0:** "Vera"/"Veyra" still never flips, AND new collateral
    damage appears ("boss" → "Bashudu", "doors" → "drowses", "Vera" →
    "Verno") — degrading unrelated words while not fixing the target.
  - **4.0–8.0:** severe over-triggering — the model starts hallucinating
    unrelated campaign vocabulary wholesale ("Order of the Gauntlet",
    "Gundren Rockseeker", "Truths of the Inward Facing Mind Flayer
    Clairvoyant" at 4.0; at 8.0 the output is pure vocabulary word-salad,
    no longer a transcription of the actual audio at all).
  - **No alpha in this sweep both fixed the target name and left the rest
    of the transcript intact** — the useful range (if one exists for this
    campaign's ~546-term list) is narrower than 0.5–8.0, and errs toward
    catastrophic hallucination faster than toward under-correction. This
    is the "LLM Pipeline Design Rule" precision-decision risk playing out
    concretely at the ASR layer, not just at the LLM layer: an
    over-aggressive bias doesn't just fail to help, it actively invents
    content that isn't in the audio.
- **Final verdict (user, 2026-07-19): Parakeet ruled out for this project.**
  "Good at plain English, not at the kind of work I need" — i.e. strong
  general ASR quality/speed but the fantasy-proper-noun precision this
  tool exists for is exactly where it falls down, and the boosting-tree
  sweep above is *why*: no tuning found in this project made it reliably
  fix rare names without hallucinating others. **faster-whisper + hotwords
  remains the tool for audio-to-vtt.** Don't re-propose Parakeet/NeMo for
  this project without new information (e.g. a NeMo release that
  materially changes context-biasing precision) — this was a real,
  reasonably thorough trial, not an abandoned-early one.

**Added `diff_review.py` (2026-07-19):** a vocabulary-aware triage step
between retranscription and `/vtt-spell-pass`. Diffs each cue-group's
Zoom-original text against the final (post-glossary-pass) text using
`vtt_scaffold.CueGroup.original_text` (already aligned 1:1 with the
retranscription by index — no separate alignment step needed); skips
cues that are identical once case/punctuation are ignored; splits the
rest into HIGH priority (a changed word doesn't match the campaign
vocabulary — likely hallucination or an uncatalogued fix) vs. LOW
(every changed word matches known vocabulary — likely an intended
hotword fix). Wired into `retranscribe.py`'s end-of-run flow, writing
`<cleaned-stem>.review.md`; also runnable standalone
(`diff_review.py <zoom.vtt> <new.vtt> --campaign-root <dir>`) against
any already-completed run. Deliberately kept separate from
`vtt-spell-pass` (different inputs — vtt-spell-pass works on one VTT in
isolation and only catches proper-noun misspellings against a known-names
set; this needs the Zoom/retranscription pair and catches non-proper-noun
hallucinations too, e.g. "We will" → "Weeble").
Validated against the real obelisk session 006 files (662 cue groups,
507 changed, 155 identical-skip): correctly bucketed real hotword fixes
as LOW ("Sister Mela"→"Maela", "great brand"→"Redbrand",
"Zenimon"→"Zenvon") and a genuine hallucination as HIGH ("...it's still
hot **Albrek**" appended to an unrelated AC conversation). **Known
limitation, not yet fixed:** the vocab-match check is purely word-level,
so a large-magnitude rewrite that happens to consist entirely of
vocabulary words can still land LOW even when the sheer size of the
change (e.g. "Okay, okay." → "Albrek, Lord Albrek") is itself suspicious
— word-level matching can't yet tell "targeted name fix" from "a
hallucination that happens to hit real vocabulary."
