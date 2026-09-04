---
name: speaker-attribution
description: Put trustworthy speaker names on a session recording — either when the transcripts carry no usable attribution (the single-room case, where everyone shared one microphone so Zoom labelled all 866 cues with the host's name and the editor produced six anonymous clusters for three people), or when they carry real names that are a voice-profile GUESS and are known to be wrong, where the job is auditing an existing name→voice mapping instead of naming anonymous ones. Verifies first that each transcript actually belongs to the recording it sits next to (filenames lie) and that a second 'transcript' is not just a derivative of the first, diarizes on the DGX Spark, cross-validates two independent clusterings against each other, mines the transcript for direct address, and hands back a ranked disagreement queue rather than a silent relabel. Invoke as /speaker-attribution [session-dir].
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
      → /session-doc-run     relabels to display names + the players.yaml override
      → /scene-extract       inherits real speakers instead of a review queue
      → /session-summary-consistency → /voice-smooth → narration
```

The labels this skill writes are **short player names**; the session_doc
pipeline's pre-flight wants `config/players.yaml` display names. `/session-doc-run`
does that mapping — do not rename the file this skill produces.

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

**If it flags EVERY transcript in a directory, that is the vouching rule, not a
finding.** Vouching is per group and it is done by *filename stem*: some member
of the group has to be named after the `.m4a`. A session whose transcripts are
all named something else — `Chapter 08.md`, `descript_transcript.md`,
`session_<date>_transcript.vtt` beside `GMT<date>_Recording.m4a` — has nothing
to vouch it, so all four get the warning at once. One stray transcript among
matched pairs is the real signal; a clean sweep of the whole directory is the
absence of a stem match. Settle it by endpoints and move on:

| | ends |
|---|---|
| `GMT20250813-040058_Recording.m4a` (mvhd) | 01:38:02.8 |
| `session_20250812_transcript.vtt` last cue | 01:38:01.1 |
| `descript_transcript.md` last word | 01:38:02 |

No `ffprobe` on the box is not a blocker — parse the MP4 `mvhd` atom directly
(`timescale` and `duration` are two big-endian u32 at a fixed offset).

### A high-scoring "transcript" may be a DERIVATIVE, not a second reading

4-gram grouping tells you two files describe the same audio. It does **not**
tell you whether one was *derived from* the other, and a derivative is worth
nothing as a second opinion — it carries the parent's every attribution error,
by construction. On Phandalin ch08 a directory held what looked like three
transcripts; `Chapter 08.cleaned.md` and `Chapter 08.md` were
`descript_transcript.md` with the inline per-word timestamps stripped and a
spell-pass applied. Two real text layers, not four.

The tell is not the overlap score — the timestamp stream depresses it
misleadingly (69% against its own parent, *lower* than the 98% between the two
siblings). The tell is the **speaker tallies being byte-identical**:

```bash
for f in *.md; do echo "== $f"; grep -oP '^\**\K[a-z]+(?=:)' "$f" | sort | uniq -c | sort -rn; done
```

```
kostadis 466   dave 466   wade 323   gary 202      <- all three files, exactly
```

Independent ASR passes never agree on turn counts. If they match to the digit,
one is a copy. Say so before Phase 3, because "cross-validated against a second
clustering" is a false claim when the second clustering is the first one.

Three transcripts of one recording are normal, and the best text is rarely the
one named after the session:

```
GMT<date>_Recording.transcript.vtt   Zoom ASR    real timeline, mangled text
GMT<date>_Recording.md/.txt          Descript    real timeline, decent text, anonymous clusters
session_<date>_transcript.vtt        Whisper     real timeline, best text, NO speakers
```

Take timings and text from the best ASR; take nothing from Zoom but the fact of
the recording. Quality is visible at a glance — Zoom rendered `Lodge of Faces`
as *"the best answer for why"* and `Szith Morcane` not at all.

### Descript: convert it before anything reads it

Descript is the second clustering, and the only one that picks its **own**
speaker count — so it is the only tool here that can tell you a voice exists
that you did not budget for. But its `.txt` export matches no input format in
this skill: labels are not bolded, and a per-word timestamp stream runs through
the body. Convert once, up front:

**Normalise bolded labels first, or the parse is silently wrong.** `HEAD` is
`^\[(\d\d:\d\d:\d\d)\]\s*([^:\n]{1,40}):\s*(.*)$`, so a Markdown-styled export
(`[00:04:01] **dave:** Hello`) parses the label as `**dave` and leaves `**` on
the front of the text. It does not error. Strip the bold into the plain form the
script documents:

```bash
sed -E 's/^\[([0-9:]{8})\] \*\*([^:]+):\*\*/[\1] \2:/' descript_transcript.md > descript_plain.txt
```

Then check the label inventory it reports matches what you expect before going on.

```bash
python ~/.claude/skills/speaker-attribution/descript_turns.py \
  --input GMT<date>_Recording.txt \
  --md descript.md --turns turns_descript.json --audio-duration 6894
```

- `--md` → the `[ts] **Speaker:** text` form `diarize_label.py --md` parses.
- `--turns` → a turns envelope, so **Descript can stand in as the primary
  clustering when no GPU is free.** Both Sparks running one tensor-parallel
  vLLM leaves ~4 GB of 121 GB, and pyannote OOMs on the model load.

It reports the cluster shares and marks anything under 3% as a fragment. Read
those lines before dismissing them — see Phase 3.

**It anchors start times on words, not on the block header.** A header stamp is
when the block begins, and leading silence is timestamped too: the opening block
of one session was headed `00:00:00` while its first word landed at `00:16:16`.
24% of blocks in that file needed the correction, and the worst offender was the
greeting that named a player.

If the chosen file is a **concatenation**, pass `--limit-seconds` so only the
portion covering this `.m4a` is used. Without it, cues from the afternoon
session get joined against morning diarization turns.

While you are here, note whether `GMT<date>_RecordingnewChat.txt` exists. It is
not a text layer and it is usually one or two lines, but it is the only place in
the whole session where a **real name** is attached to a **timestamp** by the
person themselves. Keep it for Phase 4 — see *Closing a SPLIT*.

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
  --turns turns.json --vtt <best-text>.vtt --md descript.md \
  --limit-seconds 5610 --output <stem>.speakers.vtt
```

**Pass `--md` the `--turns` JSON, not the `.md`.** Both parse, but they join
differently and it is worth ~10 points:

| `--md` given | join | ch02 agreement | `[?]` cues |
|---|---|---|---|
| `descript.md` (starts only) | nearest preceding utterance | 79.5% | 522 |
| `descript_turns.json` (real spans) | max overlap, same rule as the diarization | **89.9%** | 347 |

The `.md` form carries no end times, so every cue inherits whoever spoke last —
including cues sitting in a silence gap. That misassignment is not real
disagreement between the two tools, and it was depressing the headline number.
The raw Descript `.txt` parses as **zero** utterances either way.

### `--md-label` — naming a voice the diarization cannot see

pyannote has exactly `num_speakers` bins, so a voice you did not budget for is
forced into somebody. Descript picks its own count and keeps it separate. When
the fragment turns out to be a real person (Phase 3), name it from the second
clustering's id:

```bash
--md-label '{"Speaker 6": "Room (not at table)", "Speaker 7": "Room (not at table)"}'
```

The override wins outright and drops the `[?]`: the disagreement that flag marks
is the *reason* this cue is being named from the other tool, not something the
reader can act on. It applies only where the named cluster holds ≥50% of the cue
(`--md-label-coverage`), so short backchannels stay with whoever actually holds
them — a coverage rule that hand-editing gets wrong. On ch02, relabelling every
cue the room voice merely *overlapped* claimed 32 cues; requiring it to be the
dominant speaker gives 24, and the 8 it gives back are Kostadis answering the
room person ("All right, we'll tell it to them in a little bit") rather than the
room person speaking. The header records which cluster each override came from.

Each cue takes the diarization speaker holding the most of its duration. Then —
and this is the point — the result is checked against the editor's **own**
clustering. The two share no information: one is pyannote's speaker embedding,
the other is Descript's. Agreement therefore means something.

**Expect ~80% word-level agreement**, and ~90% when `--md` is given real spans:
81.2% here and 82.2% on Phandalin ch04 (both nearest-preceding), 89.9% on ch02
with a `descript_turns.json`. Read the join line the tool prints before comparing
runs — the two joins are not on the same scale. Below ~70% either way, one of the
signals has failed; find out which before labelling anything.

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
**Fragments are not people** — *usually.* They are most often one person's second
register, a GM doing NPC voices splitting off, which you must not promote to a
participant.

**But read their lines before you dismiss them.** On Phandalin ch02 two Descript
fragments (89 words, 1.5%) were a real fifth voice: someone in the GM's room, not
at the table.

```
[01:36:54] Speaker 6: Are you gonna make coffee?
[01:36:56] Speaker 4: No, there's a whole other bag of coffee there.
[01:39:04] Speaker 7: Tell Dave that when he says polymorphism it's beautiful
```

Domestic, addressed to the GM, and answered by him. That is not a register split;
it is a person. Label them **`Room (not at table)`** so `/scene-extract` cannot
attribute coffee to a PC. The size test alone would have thrown them away — the
content test takes ten seconds and is the one that decides.

**Only Descript can see this, and only because it picks its own speaker count.**
pyannote is told `num_speakers=N` and has exactly N bins, so a surprise voice is
forced into somebody: here it landed in the player whose cluster it least
resembled semantically. Raising to `num_speakers=5` did **not** recover it —
agreement fell 79.5% → 72.1% and the fifth cluster split the *GM* (37%/50%, no
clear home) instead. So: keep `num_speakers` at the number of people you know
about, and let Descript find the ones you do not.

## Phase 4 — name the clusters. Human checkpoint, not automation.

### When the second clustering ALREADY has names

Descript names clusters once someone builds voice profiles, and the export then
reads `**kostadis:**`, `**dave:**` — real people, not `Speaker 3`. **This does
not mean the work is done, and it does not mean the names are right.** Voice
profiles are a recognition guess, and the GM will usually tell you so. The job
changes shape: you are no longer *naming anonymous clusters*, you are
**auditing an existing name→voice mapping** against an independent one.

Everything upstream is unchanged — still diarize, still cross-validate. What
changes is how you read the confusion matrix. A clean bijection at the usual
agreement band means the *mapping* is right and the residual is boundary noise:

```
SPEAKER_00 ↔ kostadis  84%      33.5% speech  vs  35.8% words
SPEAKER_03 ↔ dave      82%      27.7%             27.8%
SPEAKER_01 ↔ wade      91%      27.7%             24.5%
SPEAKER_02 ↔ gary      81%      11.1%             11.9%
```

Two things make this trustworthy rather than circular: the shares agree as well
as the labels do, and each row has exactly one dominant column. A row that
splits across two columns is a merged or swapped profile — a different and much
worse problem than a few misplaced turns.

Then produce the thing the GM actually needs, which is **not** a relabelled VTT:
a **disagreement queue**, ranked by words at stake. Take each named utterance,
compute the diarization's dominant speaker over its span, and list the ones that
disagree above a coverage floor:

```
202 turns disagree at >=75% coverage (of 1457 turns, 586 words = 4.7%)
   dave     -> wade      99      kostadis -> wade      79
   gary     -> wade      70      dave     -> kostadis  61
```

Report the **directional bias** — 248 of those words leaked *into* one speaker —
because a lopsided table means a profile is over-claiming, which is actionable,
whereas a symmetric one is just turn boundaries. Then ask the GM whether to walk
it or accept a stated error rate. "4.7%, largest single disagreement 16 words"
is a decision they can make in one breath; 202 raw findings is not.

### When nobody is named

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
`--names '{"SPEAKER_00":"Nicholas",...}'` (inline JSON, or a path to a JSON
file — both work).

### Closing a SPLIT: the chat sidecar is a real-name anchor

`name_clusters.py` scores **who answers when the name is spoken**, so it is blind
to exactly one case: **a player who is not in the room.** An absent player never
answers his own vocative. The replies that follow his name are other people
noticing he is gone, and the tool spreads them across every cluster and reports
`SPLIT`. That is correct behaviour and you cannot fix it from the audio.

Zoom's chat export closes it. Look for the sidecar beside the recording:

```
GMT<date>_RecordingnewChat.txt
00:26:59<TAB>Gary Young:<TAB>Kid needs a phonecall. Sorry a few minutes please
```

That is a **human-written real name on the session clock** — the only such anchor
when both transcripts are anonymous, and it does not care that the person was
silent. Use it as an absence probe: find the cluster that goes quiet across the
window, and that is the person.

```bash
python - turns.json <<'PY'          # speech per cluster inside the stated window
import json,sys; from collections import defaultdict
d=json.load(open(sys.argv[1])); per=defaultdict(float)
A,B = 1266, 1885                    # the chat timestamp, padded either side
for t in d["turns"]:
    if t["end"]>A and t["start"]<B:
        per[t["speaker"]] += min(t["end"],B)-max(t["start"],A)
for k,v in sorted(per.items()): print(f"{k}: {v:6.1f}s")
PY
```

Phandalin ch02, where `Gary → SPLIT` and the tool could not close it:

```
SPEAKER_00: 155.7s   SPEAKER_01: 126.7s   SPEAKER_02:   8.2s   SPEAKER_03: 157.1s
```

`SPEAKER_02`, and its single longest silence of the whole session (5.6 min,
00:25:09→00:30:48) sits on the chat timestamp. Decided, on the diarization's own
timeline, with no reference to the second clustering.

Two properties make this worth reaching for before you give up on a SPLIT: the
name is **typed by the person themselves**, so it cannot be an ASR garble; and it
is **evidence from silence**, so it works precisely when vocative scoring cannot.
Check `git log` or the directory for the sidecar during Phase 0 — it is small,
easy to miss, and it is often the only real name in the whole session.

### Probe with the names people actually say

`name_clusters.py` scores who *answers*, so it can only score names that get
spoken. At a table that is usually **PC names, not real ones** — on Phandalin
ch08 only one of four real first names was ever used vocatively, while every PC
name was. Run both passes and weight the evidence by how much there is:

```bash
python .../name_clusters.py <stem>.speakers.vtt --name Dave --name Wade --name Gary --name Kostadis
python .../name_clusters.py <stem>.speakers.vtt --name Vukradin --name Soma --name Valphine --name Brewbarry
```

Expect the real-name pass to be nearly empty and the PC pass to carry the run.
Expect, too, that a player's **own** PC comes back `SPLIT` — nobody addresses
him by it, so every hit is third-person narration. That is the tool working.

**Two PC names resolving to the same cluster is a finding, not a collision.** It
means one person ran both, and it is *stronger* evidence than the campaign's own
notes: `Brewbarry` (47%) and `Valphine` (38%) both landing on SPEAKER_02 proved
Gary covered an absent player, from the audio, with no reference to `CLAUDE.md`
— which elsewhere records a session where the **GM** did the covering instead.
Derive it per session; never carry it forward.

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
- **A GPU that is "free" may not be.** Both Sparks run one tensor-parallel vLLM
  (TP0 on .147, TP1 on .121) holding ~105 GB of 121 GB each, and `nvidia-smi`
  truncates that to `10528...` in the process table — which reads as 10 GB. Check
  `free -g` and `--query-compute-apps`, and expect pyannote to OOM on
  `pipeline.to("cuda")` *after* it has decoded the audio, so the log looks like
  it got further than it did. Descript via `descript_turns.py --turns` is the
  no-GPU fallback.
  **But try CUDA anyway before falling back.** On 2026-09-03 spark2 had ~11-12 GB
  free beside a 100,809 MiB vLLM and `community-1` ran fine — 98 min of audio in
  4 min wall clock, no OOM. The failure is fast and cheap (it happens at model
  load, right after the decode), so the cost of trying is a couple of minutes
  against 30-60+ min for CPU or losing the second clustering entirely. Launch it
  detached, redirect to a file, and grep the log for `running on cuda`; only fall
  back once it actually throws.
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
