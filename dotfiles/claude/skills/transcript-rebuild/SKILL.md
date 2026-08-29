---
name: transcript-rebuild
description: Rebuild a session transcript that has correct timings OR correct speakers but not both — the split-brain case where `*.speakers.vtt` carries fabricated timestamps and Zoom's live text export flips speaker mid-sentence, shredding one person's sentence across three labels. Diagnoses which file is the timing authority and which is the speaker authority, transfers labels onto real cue boundaries by token alignment, optionally cross-validates with pyannote diarization on the DGX Spark, and strips Whisper's silence hallucinations before anything downstream sees them. Invoke as /transcript-rebuild [session-dir].
---

# transcript-rebuild

A session directory usually holds several transcripts of one recording. **None
of them is usable alone**, and the one the pipeline defaults to is the worst of
the set. This rebuilds a single transcript that has real timings *and* real
speakers, so scene extraction inherits correct attribution instead of
manufacturing a review queue out of it.

## The problem, concretely

```
GMT<date>_Recording.md            speakers ✓   timeline ✗ (none at all)
*.speakers.vtt                    speakers ✓   timeline ✗ (SYNTHETIC)
*.vtt(.unused-no-speakers)        speakers ✗   timeline ✓ (matches the .m4a)
```

`*.speakers.vtt` is generated *from the markdown*, and says so in its own
header: *"Timestamps are SYNTHETIC ... they do not correspond to real recording
offsets."* It looks like an ordinary WebVTT. The pipeline reads it. Everything
derived from audio that gets aligned against it is silently wrong.

And Zoom's live text export segments on **talk-detection**, so under crosstalk
it flips speaker mid-sentence:

```
Zoom .md:   **gary:**     Balthina would like to go through the most brightly
            **kostadis:** lit, uh, path possible. At both
            **dave:**     paths. Oh, just, just go straight.

Whisper:    01:25:38.949 --> 01:25:43.189
            Valfina would like to go through the most brightly lit path possible.
```

One sentence, one speaker — chopped three ways by Zoom, intact in the
acoustically-segmented transcript. Phandalin chapter 04 had **47** of these
across two scenes.

**The splits are not repairable by text heuristics and must not be smoothed.**
Punctuating `GM: "lit, uh, path possible."` into a clean sentence turns a
segmentation artifact into a quotable GM line. Attribution is a precision
decision; rendering it fluently is the exact failure the pipeline rule warns
about.

## Where this sits

```
audio + transcripts
  → [THIS SKILL] diagnose → label transfer → (diarize) → (re-transcribe) → strip hallucinations
      → /vtt-spell-pass        name garbles, with sibling adjudication
      → /scene-extract         now inherits correct speakers
      → /session-summary-consistency → /voice-smooth → narration
```

Run this **before** `/scene-extract`. Running it after means re-extracting.

## Phase 0 — diagnose. Never skip.

```bash
python ~/.claude/skills/transcript-rebuild/diagnose_transcripts.py <session-dir>
```

Reports, per transcript: whether the timeline is `REAL` / `SYNTHETIC` /
`NO TIMELINE`, which speakers it carries, and which file is the timing
authority vs the speaker authority.

Two independent tells for a synthetic timeline, both checked:

1. **A declared NOTE** — some generators say so outright.
2. **No silences.** Real table talk has pauses. Chapter 04's synthetic file:
   1441 cues, largest inter-cue gap **0.2s**, zero gaps over 1s. Nobody talks
   that way. If an `.m4a` is present, the real transcript's end lands within a
   percent or two of the audio duration; the synthetic one will not.

If it prints **"Split brain"**, continue. If one file already has real timings
*and* speakers, you are done — stop here.

## Phase 1 — transfer labels onto real cue boundaries (the core fix, no audio)

```bash
python ~/src/mytools/audio-to-vtt/label_transfer.py \
  --vtt <real-timeline speakerless VTT> \
  --md  <speaker-labelled markdown> \
  --output <session-dir>/<stem>.labelled.vtt
```

Both transcripts cover the same words in the same order, so it aligns them as
token streams (`difflib.SequenceMatcher`) and awards each Whisper cue to the
speaker who contributed most of its words. **The mid-sentence flips dissolve by
construction** — a split sentence is one cue, and one speaker owns the majority
of it.

Check the output before trusting it:

- **Token alignment ≥ ~90%.** Chapter 04: 93.4%.
- **Speaker distribution matches the markdown's own utterance counts.** If the
  markdown says 40/28/17/15 and the transfer says 46/25/13/13, that is a match.
  If one speaker takes 80%, the alignment failed — stop.
- **`[CONTESTED]` cues** are where two speakers' words land in one cue. That is
  genuine crosstalk, and Phase 2 is what resolves it.

## Phase 2 — diarization as a *second opinion* (optional; DGX Spark)

Not a replacement. Zoom's labels are ~93% right; discarding a 93%-correct
signal for a model that is at best 90% on 4-way crosstalk is a downgrade
dressed as a fix. Use diarization only to settle what Phase 1 could not:
contested cues, `UNKNOWN`, and unnamed `Speaker N`.

```bash
scp ~/src/mytools/audio-to-vtt/spark/diarize_remote.py spark2:~/audio-to-vtt-diarize-remote.py
ssh spark2 'export HF_HOME=~/.cache/diarize-hf; cd <workdir> && \
  ~/.venvs/diarize/bin/python ~/audio-to-vtt-diarize-remote.py \
    --manifest diarize-manifest.json --output turns.json'
```

**Use `pyannote/speaker-diarization-community-1`, not 3.1.** Measured on the
same 100-minute mono Zoom recording:

| model | largest cluster | verdict |
|---|---|---|
| `speaker-diarization-3.1` | **84%** of all speech | collapsed, unusable |
| `speaker-diarization-community-1` | 47.9 / 23.8 / 17.0 / 11.3 | matches ground truth |

Pass `num_speakers` when you know it — it is a large accuracy win. Runtime for
100 minutes on a GB10: **~4 minutes**.

**Cross-validate, do not just consume.** Overlap each diarization cluster with
Phase 1's named cues and check they agree. Chapter 04: every cluster mapped to
one name at 78–92%, and the two signals agreed on **82.2%** of uncontested
cues. That number means something because the signals share no information —
one is words, the other is voice timbre. If agreement is low, one of them is
broken; find out which before proceeding.

## Phase 3 — vocabulary re-transcription (optional) + hallucination strip (MANDATORY)

`/audio-to-vtt` re-transcribes each cue's audio with the campaign's proper-noun
vocabulary, fixing name garbles at source. Feed it the Phase-1/2 output as
scaffold. In chapter 04 it fixed `Valfina`/`Balthina` → **Valphine** (17
occurrences) and eliminated a phantom entity.

**It also fabricates, and you must strip that before anything else reads it.**

```bash
python ~/.claude/skills/transcript-rebuild/strip_asr_hallucinations.py \
  <retranscribed.vtt> --source <pre-retranscription.vtt> --dry-run
```

Whisper fills near-silent spans with training-data boilerplate — YouTube outros
and caption-farm credits — attributed to a **real player**:

```
Wade Brown: Thank you for watching!
Kostadis Roussos: Subtitles by the Amara.org community
```

Chapter 04: **13 fabricated cues, zero of them in the pre-re-transcription
file.** All sat on spans of 0.16–0.8s. Reusing cue boundaries forces a decode
of every span including the near-empty ones, which is exactly what triggers
this — the original VAD-based transcription had none. Reverting with
`--source` recovers the real text, which is usually a one-word acknowledgement
("Yeah.", "Okay.", "What?").

Re-transcription is **not uniformly better**: it also turned a correct
`Vacuous truth` into `Vacuous Troop`. Diff before/after on a sample rather
than assuming improvement.

## Phase 4 — drop contentless unknown speakers

Leftover `UNKNOWN` / `Speaker N` / non-player labels **become characters** if
you let them through. Chapter 04's previous extraction contains, in canon:

```
**Speaker 7**
> "Vacuous truth"
```

Zoom failed to identify someone and the pipeline promoted that failure to a
participant. Check what those lines actually say. If they are contentless
acknowledgements or off-table room chatter (a partner sharing a meme), drop
them from a **derived** extraction input — never from the record — and say so.
If any carry real content, they need a human ruling instead.

## Phase 5 — re-extract, then verify

Run `/scene-extract` against the rebuilt transcript. Then verify two things
deterministically, and **never with a second LLM**:

**Splits are gone.** Count cross-speaker mid-sentence splits (a quote ending
without terminal punctuation, followed by a lowercase-initial quote under a
*different* speaker). Chapter 04: 47 → 1.

**No fabricated quotes.** For every extracted quote of ≥4 words, check that a
majority of its 6-grams occur in the source VTT. Chapter 04: 583/583, 100%.
This campaign has a recorded incident of LLM quote blocks inventing
canon-plausible dialogue that *passed fact-checking* — an n-gram diff is the
only thing that catches it.

## Landmines

Every one of these was hit for real.

- **Align by timestamp, never by cue number.** Re-transcription groups
  consecutive same-speaker cues and renumbers: 2110 cues in, 1024 out. Cue *N*
  in one file is not cue *N* in the other, and the drift is invisible for the
  first few cues.
- **A relative-overlap matcher favours short cues.** Scoring
  `len(shared)/len(shorter)` makes a two-word cue like "Yeah" beat everything.
  It produced a clean-looking 45/47 table that was simply false. Require a
  minimum *absolute* token overlap, and for split repair require evidence from
  **both** halves.
- **Exit codes get masked by pipes.** `cmd | grep ...` reports grep's status.
  A run that died on a gated-model 403 reported exit 0. Redirect to a log and
  check `$?` before the pipe.
- **`prepare_input.py` reports "no speakers detected" on plain-labelled VTTs.**
  Its `speakers()` only counts markdown-bold `**dave:**`, never its own
  `PLAIN_LABEL_RE`. `--exclude-speaker` no-ops for the same reason.
- **`speaker_map(players, party)` wants the `PartyConfig` object,** not a list
  of names. Passing a list yields `{}` for every player while the GM still
  maps — which looks exactly like a broken config.
- **One player voicing two PCs has no deterministic fix.**
  `players_config.py:312` maps display names to *the first* of their `plays`
  that the roster has. When someone covers an absent player's character, every
  line lands on one PC. That is a human checkpoint (`/scene-extract` phase 6),
  not a config problem. Pre-sort the queue by content — rage/halberd/Cleave vs
  Healing Word/Sacred Flame separated them perfectly.
- **PyTorch on aarch64 CUDA is trivial; `ctranslate2` was the hard one.** A
  plain `pip install torch` gives CUDA on a GB10 (`sm_121`) in one command —
  no Docker, no CMake, no `ctypes.CDLL` preloading. The pain documented in
  `audio-to-vtt/CLAUDE.md` is ctranslate2-specific, not architecture-specific.
- **pyannote models are gated, and 3.1 pulls from community-1.** Accept
  conditions on `segmentation-3.0`, `speaker-diarization-3.1` **and**
  `speaker-diarization-community-1`. A fine-grained HF token also needs *"Read
  access to contents of all public gated repos"* or it 403s after acceptance.
- **The shared HF cache is root-owned.** Set `HF_HOME` to a project-owned
  directory or you get `PermissionError` that reads like an auth failure.

## Human checkpoints

Three, and none is optional:

1. **After Phase 1** — confirm the alignment percentage and speaker
   distribution look right before building on them.
2. **Before Phase 4 deletions** — dropping lines from the extraction input is
   the GM's call, even when the lines are contentless.
3. **After Phase 5** — the attribution queue for multi-voiced PCs. A
   misattributed line that survives it gets baked into the wrong narrator's
   POV, and nothing downstream checks speaker identity.

## Why this design

The rebuild is *reconstruction from two partial records*, not generation. Phase
1 is deterministic text alignment. Phase 2 is an independent signal used only
to break ties, and cross-validated rather than trusted. Phases 3–4 are
deterministic strips with a named source to revert to. The only LLM step is
extraction itself, and its output is verified by n-gram containment against the
source rather than by another model.

That is the house pattern — *deterministic extraction → human checkpoint → LLM
renders inside the verified structure* — applied to the layer where speaker
identity is decided.
