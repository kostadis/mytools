# audio-to-vtt

Re-transcribes a D&D session's Zoom `.m4a` recording into a more accurate
WebVTT transcript, using the campaign's own proper-noun vocabulary to fix
the fantasy-name errors generic speech-to-text mangles ("Cryovain" ->
"Cryovane", "Thorin" -> "Thorne") -- while keeping Zoom's existing,
reliable speaker attribution and cue timing. Counterpart to the sibling
[`vtt-to-tts/`](../vtt-to-tts) project (that one goes VTT -> speech; this
one goes audio -> VTT).

## Why

Zoom's live captioning gets *who said what, when* right; it's the
transcribed *words* that are unreliable, especially invented fantasy
names. Re-diarizing from scratch would solve a problem that doesn't
exist here. Instead, this tool keeps Zoom's cue boundaries/speaker labels
and only replaces the text: it re-runs just the audio for each cue through
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) (on the DGX
Spark), biased toward the campaign's real names via Whisper's `hotwords`
mechanism, then applies the campaign's existing hand-verified misspelling
glossary as a deterministic cleanup pass.

See [`CLAUDE.md`](CLAUDE.md) for the full design rationale and the real
hardware/build gotchas hit getting faster-whisper running with GPU
acceleration on this specific hardware (DGX Spark, GB10, aarch64) -- worth
reading before touching the Spark side, especially if a future faster-whisper
version bump means redoing the from-source CUDA build.

## How it works

1. Parses the existing Zoom `.vtt`, groups consecutive same-speaker cues
   (capped at 25s per group -- long enough for real acoustic context,
   short enough to stay clear of a known faster-whisper clip-length bug on
   longer clips).
2. Skips re-transcription for Zoom's own "Audio shared by X" system-caption
   cues (a screen/audio-share window, not a participant talking) -- these
   keep Zoom's original text unchanged, since faster-whisper reliably
   hallucinates video-outro phrases there instead of transcribing real
   speech.
3. Gathers a ranked vocabulary list from the campaign: known-misspelling
   glossary canonicals first, then the entity registry's names/aliases,
   then module-inventory vocabulary.
4. Ships the audio + cue-group plan + vocabulary to the Spark, where
   faster-whisper (on GPU) re-transcribes each cue-group's audio slice,
   using the vocabulary as a hotword bias.
5. Splices the corrected text back into the original cue timestamps and
   speaker labels.
6. Runs the campaign's misspelling glossary as a mandatory cleanup pass
   (the same script `/vtt-spell-pass` already uses).
7. Checks whether the retranscription's vocabulary-biased text found a
   campaign name that Zoom's own transcript doesn't have, and writes a
   report of just those spots (`proper_noun_review.py`) -- Zoom's transcript
   stays the base text; nothing is rewritten automatically.
8. Tells you to run `/vtt-spell-pass` next, so any genuinely new unknowns
   get the usual human-confirmation loop rather than being silently
   trusted.

## Setup

One-time, on the Spark box:

```bash
scp spark/setup_spark_venv.sh spark2:~/
ssh spark2 'bash ~/setup_spark_venv.sh'
scp spark/transcribe_remote.py spark2:~/audio-to-vtt-transcribe-remote.py
```

**Note:** `setup_spark_venv.sh` alone only gets you a CPU-only
`ctranslate2` -- no prebuilt CUDA wheel exists for aarch64 (verified; see
`CLAUDE.md`). Real GPU acceleration requires compiling `ctranslate2` from
source against the CUDA/cuDNN toolchain -- `CLAUDE.md`'s "Hardware notes"
section walks through the exact steps and every gotcha hit doing this the
first time (OpenMP runtime flag, Python packaging, missing runtime
libraries, a glibc loader quirk). `transcribe_remote.py` falls back to CPU
automatically if CUDA isn't available, so the tool still runs either way
-- just much slower without GPU. Measured on this hardware once the build
and a real performance bug were both fixed: **~9x real-time** on GPU (an
87-minute session transcribes in about 9 minutes).

On the workstation:

```bash
pip install -r requirements.txt
```

## Usage

```bash
cd ~/campaigns/<campaign>/summaries/<date>
python ~/src/mytools/audio-to-vtt/retranscribe.py \
  <recording>.m4a \
  <recording>.transcript.vtt
```

Campaign root, Spark host, model size, and compute type all default
sensibly. If the audio/VTT aren't sitting inside a campaign checkout yet,
pass `--campaign-root` explicitly:

```bash
python ~/src/mytools/audio-to-vtt/retranscribe.py \
  ~/GMT20260718-212700_Recording.m4a \
  ~/GMT20260718-212700_Recording.transcript.vtt \
  --campaign-root ~/campaigns/obelisk
```

### Recommended first run on new hardware or a new session shape

```bash
# 1. See the cue-group plan and vocabulary without touching the Spark
retranscribe.py <audio> <vtt> --dry-run

# 2. Confirm the Spark actually engages GPU, get a real timing estimate
retranscribe.py <audio> <vtt> --smoke-test

# 3. Full run (smoke-test above prompts to continue, or just re-run without it)
retranscribe.py <audio> <vtt>
```

Or use the `/audio-to-vtt` Claude Code skill, which drives this same
dry-run -> smoke-test -> confirm -> full-run sequence for you.

## Output

Never overwrites the existing Zoom-text pipeline's files
(`....transcript.vtt`, `....transcript.cleaned.vtt`). Produces new
siblings next to the original VTT:

- `<stem>.retranscribed.vtt` -- raw faster-whisper output, same cue
  timestamps/speakers as the original, new text.
- `<stem>.retranscribed.cleaned.vtt` -- the above, after the campaign's
  `vtt_transcription_corrections.md` glossary is applied (mandatory
  unless `--skip-glossary-pass`).
- `<stem>.retranscribed.cleaned.proper_nouns.md` -- a report (not an edit)
  flagging cue groups where the retranscription's vocabulary match doesn't
  appear anywhere in Zoom's own text for that same span. Only genuine misses
  get listed -- see [`proper_noun_review.py`](#files) below for why this
  isn't just a diff of the two transcripts.

Giving a four-way audit trail on disk: Zoom's text, Whisper's text,
Whisper's text after the known-corrections pass, and a targeted list of
spots worth double-checking against the recording.

Always finish with `/vtt-spell-pass <output>.retranscribed.cleaned.vtt`.

## Options

| Flag | Default | Meaning |
|---|---|---|
| `--campaign-root` | auto-detected | Walks up from `<vtt>` looking for `docs/entity_registry.yaml` or `notes/vtt_transcription_corrections.md` |
| `--model-size` | `large-v3` | faster-whisper model |
| `--compute-type` | `int8_float16` | ctranslate2 compute type |
| `--spark-host` | `auto` | `auto` picks whichever of spark2/spark has enough free memory |
| `--min-free-gb` | `4` | Pre-flight abort threshold |
| `--max-group-seconds` | `25` | Cap on merged same-speaker cue-group duration |
| `--token-budget` | `200` | Hotwords token budget (headroom under Whisper's ~224 ceiling) |
| `--output` | alongside `<vtt>` | Raw output path override |
| `--skip-glossary-pass` | off | Opt out of the mandatory glossary post-pass |
| `--dry-run` | off | Print the plan, no Spark contact |
| `--smoke-test [SECONDS]` | off, default 300 if bare | Transcribe only the first N seconds first, report measured RTF, confirm before the full run |

## Requirements

- **Workstation:** Python 3.9+, `PyYAML` (`pip install -r requirements.txt`),
  SSH access to a DGX-Spark-style box (`spark`/`spark2` host aliases).
- **Spark:** `faster-whisper` (`pip install -r requirements-spark.txt`,
  via `setup_spark_venv.sh`); a from-source CUDA build of `ctranslate2`
  for real GPU speed (see `CLAUDE.md`), or accept the automatic CPU
  fallback.

## Files

- `retranscribe.py` -- main CLI / orchestrator (workstation side).
- `vtt_scaffold.py` -- Zoom VTT parsing/cue-grouping/rendering.
- `vocab.py` -- campaign vocabulary gathering (glossary/registry/inventory).
- `proper_noun_review.py` -- flags cue groups where the retranscription's
  vocabulary-biased text found a campaign name Zoom's transcript doesn't
  have. Wired into `retranscribe.py`'s end-of-run flow; also runnable
  standalone against an already-completed pair:
  `proper_noun_review.py <zoom.vtt> <retranscribed.vtt> --campaign-root <dir>`.
  Deliberately not a text diff of the two transcripts -- two independent ASR
  passes disagree on phrasing, fillers, and punctuation almost everywhere,
  so a plain diff is mostly noise. This anchors on campaign-vocabulary
  membership instead: a cue group is only flagged when the retranscription
  confidently contains a vocabulary term that doesn't appear verbatim
  anywhere in Zoom's text for that same span.
- `spark_runner.py` -- SSH/SCP orchestration to the Spark.
- `spark/transcribe_remote.py` -- the actual faster-whisper worker,
  deployed to the Spark via `scp` (flat-copy, not git-synced -- see
  `CLAUDE.md`).
- `spark/setup_spark_venv.sh` -- one-time Spark venv bootstrap.
