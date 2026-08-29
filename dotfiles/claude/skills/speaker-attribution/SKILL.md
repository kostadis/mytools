---
name: speaker-attribution
description: Put speaker names on a session recording when the transcripts carry no usable attribution — the single-room case, where everyone shared one microphone so Zoom labelled all 866 cues with the host's name, and the editor's diarization produced six anonymous clusters for three people. Verifies first that each transcript actually belongs to the recording it sits next to (filenames lie), diarizes on the DGX Spark, cross-validates two independent clusterings against each other, and mines the transcript for direct address to name the clusters. Invoke as /speaker-attribution [session-dir].
---

# speaker-attribution

Sibling of `transcript-rebuild`, and the two assume opposite things. Read this
first:

| | `transcript-rebuild` | **this skill** |
|---|---|---|
| Zoom's speaker labels | ~93% correct, keep them | **zero information** — one name on every cue |
| Diarization | second opinion, breaks ties | **the only signal** |
| The hard part | aligning labels onto real cue boundaries | **finding out who anyone is** |

If the transcripts carry real per-speaker names and the problem is that they sit
on the wrong timeline, stop — that is `transcript-rebuild`. Use this when
everyone was in one room on one mic, so there are no names anywhere.

## Where this sits

```
audio + transcripts
  → [THIS SKILL] provenance → diarize → cross-validate → name clusters
      → /vtt-spell-pass      name garbles
      → /scene-extract       inherits real speakers instead of a review queue
      → /session-summary-consistency → /voice-smooth → narration
```

Run it **before** `/scene-extract`. After means re-extracting.

## Phase 0 — provenance. Never skip. This is the one that bites.

**A filename is an assertion, not evidence.** Before attributing anything,
prove each transcript actually transcribes the `.m4a` it sits beside.

```bash
python ~/.claude/skills/speaker-attribution/transcript_provenance.py <summaries-dir>
```

Fingerprints every transcript by 4-gram set overlap, `|A∩B| / min(|A|,|B|)`.
Two ASR passes over the same audio disagree on fillers and proper nouns
everywhere, so this never nears 100% — but the separation is an order of
magnitude and has never been ambiguous:

| | overlap |
|---|---|
| same audio, Zoom ASR vs Descript ASR | 49.9% |
| same audio, Zoom ASR vs Whisper | 61.4% |
| **different sessions** — same campaign, same players, same NPC names | **0.8 – 3.0%** |

Set comparison, so it is order-independent: an offset, a truncated tail, or a
concatenation cannot fake a match or hide one.

It reports three things that matter:

- **MISFILED** — one recording's transcripts spread across directories.
- **SPANS MULTIPLE RECORDINGS** — a whole-day transcript that is two
  back-to-back recordings concatenated. It matches both halves while the halves
  match each other at the noise floor.
- **sits beside audio it does NOT transcribe** — the genuinely dangerous one.
  Reads as a matched pair to every human and every downstream tool.

On the real Hillsfar tree this found a July 27 transcript filed under Aug 8 with
a `session_20260808_` prefix. Diarizing the Aug 8 audio and joining it to that
file would have produced 1145 confidently-labelled cues, every one wrong, with
no error anywhere. **The best text for the Aug 8 recording turned out to live in
a third directory** — a whole-day file under Aug 10.

Endpoint check to confirm a match by hand: the two files should open and close
on the same words within a second or two.

## Phase 1 — choose the text layer

Three transcripts of one recording are normal, and the best text is rarely the
one named after the session:

```
GMT<date>_Recording.transcript.vtt   Zoom ASR    real timeline, mangled text
GMT<date>_Recording.md               Descript    real timeline, decent text, anonymous clusters
session_<date>_transcript.vtt        Whisper     real timeline, best text, NO speakers
```

Take timings and text from the best ASR; take nothing from Zoom but the fact of
the recording. Quality is visible at a glance — Zoom rendered `Lodge of Faces`
as *"the best answer for why"* and `Szith Morcane` not at all.

If the chosen file is a **concatenation**, pass `--limit-seconds` so only the
portion covering this `.m4a` is used. Without it, cues from the afternoon
session get joined against morning diarization turns.

## Phase 2 — diarize on the Spark

```bash
scp ~/src/mytools/audio-to-vtt/spark/diarize_remote.py spark2:~/audio-to-vtt-diarize-remote.py
ssh spark2 'mkdir -p ~/audio-to-vtt-work/<session>'
scp <audio>.m4a spark2:/home/kostadis/audio-to-vtt-work/<session>/audio.m4a
```

Manifest — **absolute remote paths, no `~`** (see landmines):

```json
{ "audio_path": "/home/kostadis/audio-to-vtt-work/<session>/audio.m4a",
  "hf_token_path": "/home/kostadis/.hf-token-diarize",
  "num_speakers": 3,
  "model": "pyannote/speaker-diarization-community-1",
  "device": "cuda" }
```

```bash
ssh spark2 'export HF_HOME=~/.cache/diarize-hf; cd ~/audio-to-vtt-work/<session> && \
  ~/.venvs/diarize/bin/python ~/audio-to-vtt-diarize-remote.py \
    --manifest diarize-manifest.json --output turns.json'
```

**`community-1`, never `3.1`.** On the same mono room recording, `3.1` collapses
to one cluster holding 84% of speech; `community-1` gives 48/28/24. **Pass
`num_speakers`** — a large accuracy win, and you know the number. 93 minutes on
a GB10: ~4 minutes wall clock, almost all of it the embedding pass.

## Phase 3 — join and cross-validate

```bash
python ~/.claude/skills/speaker-attribution/diarize_label.py \
  --turns turns.json --vtt <best-text>.vtt --md <descript>.md \
  --limit-seconds 5610 --output <stem>.speakers.vtt
```

Each cue takes the diarization speaker holding the most of its duration. Then —
and this is the point — the result is checked against the editor's **own**
clustering. The two share no information: one is pyannote's speaker embedding,
the other is Descript's. Agreement therefore means something.

**Expect ~80% word-level agreement.** Measured: 81.2% here, 82.2% on Phandalin
ch04. Below ~70%, one of the two has failed — find out which before labelling
anything.

The confusion matrix also sorts real clusters from artefacts. Descript found six
speakers for three people:

```
                 SPEAKER_00   SPEAKER_01   SPEAKER_02     share
Speaker                 410          332         4488   8% / 6% / 86%
Speaker 3               188         2021          309   7% / 80% / 12%
Speaker 4              1189          214          335   68% / 12% / 19%
Speaker 2               105           16           21   ← 142 words, no clear home
Speaker 5                22            0            0   ← 22 words, spurious split
Speaker 6                 4            0            0   ← 4 words, spurious split
```

Three clusters at 86/80/68% and three fragments totalling 2.6% of words.
**Fragments are not people.** They are usually one person's NPC voices — a GM
doing a different register splits off — which is exactly what you would expect
and exactly what you must not promote to a participant.

## Phase 4 — name the clusters. Human checkpoint, not automation.

Diarization gives you three voices, never three names. The names are in the
text, because people address each other:

```
[91:05] SPEAKER_02: Daein. Sorry. Felkur's not there, right?
[91:08] SPEAKER_00: Everyone's there.
```

```bash
python ~/.claude/skills/speaker-attribution/name_clusters.py <stem>.speakers.vtt \
  --name Daein --name Felkur --name Bramgrim --name Akritas --name Nicholas
```

Ranks each candidate by **who answers when the name is spoken**, scoring
mentions for vocative shape so GM narration ("Daein convinced Korkan to lead a
charge") does not drown the actual address. It reports; it does not decide.

Read the output honestly. On the real session it produced:

- `Felkur → SPEAKER_00, 100% of 3 vocative answers` — correct, decided.
- `Bramgrim → SPLIT` and `Akritas → SPLIT` — **correct, and the finding.** Those
  two PCs had no owner; they were reassigned per scene ("do you want to bring
  Bramgrim or Akritas?"). A name can map to a *scene*, not a person.
- `Daein → SPLIT, 50%` — the tool could not close it, and was right not to. The
  player's real name **is** Daein, so every narration mention looks like an
  address. A human closed it in one sentence.

That last case is the skill working, not failing. Then re-run Phase 3 with
`--names '{"SPEAKER_00":"Nicholas",...}'`.

**Label with players, not characters,** and say so in the header. Characters
move between players; the voice does not. Where a player's real name collides
with their PC's, label with the nickname and note why.

## Landmines

Every one of these was hit for real.

- **`ssh host "mkdir -p $WD"` where `WD=~/...`** — the tilde expands *locally*.
  It tried to create `/home/<local-user>/...` on the Spark and failed; the
  manifest then pointed at a path that did not exist. Resolve the remote home
  once with `ssh host 'echo $HOME'` and build absolute paths from it. The
  manifest's `audio_path` is read by `av.open()` on the far side, which does not
  expand `~` at all.
- **`set -e` does not save you across a pipeline.** A cell whose `scp`s all
  failed still printed `STAGED OK`. Verify with `ssh host 'ls -la <workdir>'`,
  not with the absence of a complaint.
- **Never pipe a long background job through `tail`.** It buffers to completion,
  so there is no interim progress for the whole run. Redirect to a file and read
  it.
- **Re-`scp` `diarize_remote.py` before every run.** It is deployed flat, not
  via git. Editing the repo copy does nothing on the Spark — the same
  deployment-drift trap `audio-to-vtt/CLAUDE.md` documents for the vLLM scripts.
- **The shared HF cache is root-owned.** Set `HF_HOME=~/.cache/diarize-hf` or you
  get a `PermissionError` that reads like an auth failure. pyannote models are
  gated: accept conditions on `segmentation-3.0`, `speaker-diarization-3.1` *and*
  `speaker-diarization-community-1`.
- **A whole-day transcript breaks two things at once.** It defeats transitive
  grouping in provenance (it matches two recordings that do not match each
  other) and it silently mis-joins in Phase 3 (afternoon cues against morning
  turns). Detect it, then slice it with `--limit-seconds`.
- **`num_speakers` is the count of *people*, not of clusters any tool reports.**
  Descript said six. There were three.
- **Do not infer PC ownership from a speaker label.** Verify per scene when the
  party splits; `party.md` listing every PC under one D&D Beyond account is a
  strong tell that characters float.
- **A `[?]` cue is a disagreement, not an error.** 297 of 1379 here, almost all
  short crosstalk fragments on turn boundaries ("Yeah.", "Okay."). Long
  narrative cues are rarely flagged. Do not "fix" them in bulk.

## Human checkpoints

Three, and none is optional:

1. **After Phase 0** — if provenance reports MISFILED or a stray transcript,
   the GM decides what moves where. Do not relocate files on your own reading.
2. **After Phase 3** — confirm the agreement percentage and the speech split
   before building on them. A collapsed clustering looks exactly like a valid
   one downstream.
3. **After Phase 4** — the cluster→name mapping. This is the precision decision
   the whole skill exists to serve. A name written in here is inherited by every
   extraction, quote and narration downstream, and nothing further along
   re-checks speaker identity.

## Why this design

Attribution is a scope-and-identity decision, so no LLM makes one here. Phase 0
is set arithmetic. Phase 2 is an acoustic model with a known failure mode and a
guard against it. Phase 3 is a deterministic join whose only claim —
*these two independent clusterings agree* — is a number you can check. Phase 4
is an evidence table with the quotes attached, ranked but explicitly undecided,
handed to the person who was in the room.

The house pattern, applied to the layer where speaker identity is decided:
*deterministic extraction → human checkpoint → LLM renders inside the verified
structure.* The rough pass is the ceiling. A confident label on the wrong voice
is worse than no label, because nothing downstream will ever question it.
