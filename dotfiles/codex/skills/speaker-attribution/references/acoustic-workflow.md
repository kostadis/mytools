# Acoustic workflow

Read when generating or joining acoustic turns. The local join helpers use only
Python's standard library. New diarization uses the separately maintained
`~/src/mytools/audio-to-vtt/spark/diarize_remote.py`; inspect that project's
instructions and current CLI before deploying. If it is missing, report the
dependency. Existing valid turn files still support the local workflow: reuse
suitable saved turns after verifying their recording and timeline.

Commands below use `$SKILL_DIR` for the skill's scripts directory and `$RUN`
for the run's scratch directory; SKILL.md says how each is resolved.

## Spark execution

Remote execution is a genuine dependency only when generating new clusters.
Check the helper, host, environment and available resources before launching,
and do not launch remote work just to inspect this skill. Use the configured
host (historically `spark2`), not an inferred IP.

**Only spark2 has the Python environments.** `~/.venvs/diarize` (pyannote) and
`~/.venvs/audio-to-vtt` (faster-whisper, a CUDA ctranslate2 build from source)
exist on spark2 and not on spark1, which has no `~/.venvs` at all (checked
2026-09-25). Having two boxes does not give two diarization hosts. Run the
Spark jobs one after another on spark2 rather than building a second
environment mid-task.

**Resolve the remote home once and build absolute paths from it.**

```bash
ssh spark2 'printf "%s\n" "$HOME"'
```

*Evidence:* `ssh host "mkdir -p $WD"` with `WD=~/...` expands the tilde
*locally*. It tried to create `/home/<local-user>/...` on the Spark and failed,
and the manifest then pointed at a path that did not exist. Store the remote
home in a task-specific variable; never repurpose `HOME` or a harness home
variable.

**Stage the helper, the audio and a manifest into a unique remote working
directory, and re-copy the helper before every run.** It is deployed flat, not
via git, so editing the repo copy does nothing on the Spark: the same
deployment-drift trap the audio-to-vtt project documents for its vLLM scripts.

```bash
scp ~/src/mytools/audio-to-vtt/spark/diarize_remote.py spark2:~/audio-to-vtt-diarize-remote.py
ssh spark2 'mkdir -p ~/audio-to-vtt-work/<session>'
scp <audio>.m4a spark2:/home/kostadis/audio-to-vtt-work/<session>/audio.m4a
```

(The single-quoted remote commands expand `~` on the Spark, which is correct;
the trap is a double-quoted local variable.)

**Verify staging positively.** Check every command's exit code, then list the
remote directory and compare sizes or hashes against the local files. *Evidence:*
`set -e` does not save you across a pipeline; a cell whose `scp`s all failed
still printed `STAGED OK`. Verify by looking, not by the absence of a complaint.

**Manifest: absolute remote paths, no `~`.** JSON readers and `av.open()` on the
far side do not expand `~` at all.

```json
{ "audio_path": "/home/kostadis/audio-to-vtt-work/<session>/audio.m4a",
  "hf_token_path": "/home/kostadis/.hf-token-diarize",
  "num_speakers": 3,
  "model": "pyannote/speaker-diarization-community-1",
  "device": "cuda" }
```

Replace the paths and speaker count with the actual session values. Use the
configured token **path**; never print or inline its contents.

**Run with a writable Hugging Face cache.** The shared HF cache is root-owned;
without `HF_HOME` pointing somewhere writable you get a `PermissionError` that
reads like an authentication failure.

```bash
ssh spark2 'export HF_HOME=~/.cache/diarize-hf; cd ~/audio-to-vtt-work/<session> && \
  ~/.venvs/diarize/bin/python ~/audio-to-vtt-diarize-remote.py \
    --manifest diarize-manifest.json --output turns.json > diarize.log 2>&1'
```

**Gated models: access must already exist.** `pyannote/segmentation-3.0`,
`pyannote/speaker-diarization-3.1` and `pyannote/speaker-diarization-community-1`
are gated on Hugging Face. The token's account must already have accepted their
conditions. If loading fails on gated access, stop and tell the GM which
model's licence they need to accept themselves. The agent never accepts model
terms on anyone's behalf.

Distinguish the three failure kinds rather than treating all as authentication
errors: filesystem permissions (the cache above), gated-model access, and GPU
memory.

### Model and speaker count

**`community-1`, never `3.1`.** *Evidence:* on the same mono room recording,
`3.1` collapsed to one cluster holding 84% of speech; `community-1` gave
48/28/24.

**Pass `num_speakers`, and make it the count of *people*** (GM included), not of
characters or of clusters any tool reports. It is a large accuracy win, and the
number is known. *Evidence:* Descript said six speakers; there were three
people. Extra NPC voices do not add participants, and two people can voice an
entire party. An unknown room voice will still be forced into one of the
requested bins (see "Only the second clustering can see an unbudgeted voice").

**A GM's registers can use up the bins meant for players.** `num_speakers`
equal to the number of people is the default, not a guarantee. A GM who switches
between conversation, read-aloud boxed text and NPC voices can take two or three
bins, and then two players share one. *Evidence — OOTA ch02, five people:*

| `num_speakers` | GM | Ben | Joe | Gabe + Mike |
|---|---|---|---|---|
| 5 | 2 clusters (conversation 65% / narration 32% of the GM's words) | 94% | 87% | **one cluster** |
| 6 (GM-approved re-run) | 3 clusters (47 / 39 / 12%) | 93% | 88% | **still one cluster** |

The sixth bin went to another GM register, not to the merged players. Adding
bins does not reliably split two similar remote voices. Descript did separate
them, under a wrongly named profile (identity-review.md), so the fix was
`--md-label` (below), not more bins. Read a merged cluster's lines against the
PC sheets: the tell was one cluster both breathing fire as Zalthir and casting
Shape Water, a spell on Daz's sheet only.

Timing: 93 minutes of audio on a GB10 took ~4 minutes wall clock, almost all of
it the embedding pass.

### A busy GPU

**A GPU that looks busy may not be free, and one that looks full may still
work.** Each Spark runs a vLLM holding ~100–105 GB of 121 GB (the layout
changes: one tensor-parallel model across both boxes until 2026-09-10, one
single-box model per box since; `/spark-status` has the current state), and
`nvidia-smi` can truncate that to `10528...` in the process table, which reads
as 10 GB. Check `free -g` and
`nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv`.

Expect pyannote to OOM on `pipeline.to("cuda")` *after* it has decoded the
audio, so the log looks like it got further than it did.

**But try CUDA anyway before falling back.** *Evidence:* on 2026-09-03 spark2 had
~11–12 GB free beside a 100,809 MiB vLLM and `community-1` ran fine: 98 minutes
of audio in 4 minutes wall clock, no OOM. The failure is fast and cheap (at
model load, right after the decode), so trying costs a couple of minutes
against 30–60+ minutes on CPU or losing the second clustering entirely. Grep the
log for `running on cuda` to confirm; fall back only once it actually throws.
**After one OOM, retry CUDA once before falling back.** Free memory beside vLLM
changes from minute to minute. *Evidence:* on 2026-09-25 spark2 showed ~13 GB
available beside a 103,000 MiB `qwen38-flash`. `community-1` OOMed at
`pipeline.to("cuda")`, and the same manifest ran on cuda a few minutes later,
85 min of audio in ~4 min. The no-GPU fallback is Descript turns
(`descript_turns.py --turns`) or another already authorized backend.

**Never stop or shut down another GPU workload to make room.**

### Keep the job observable

Launch detached, redirect to a log file, and read the log in short polls so the
GM gets progress. **Never pipe a long background job through `tail`**: it
buffers to completion, so there is no interim progress for the whole run. Quote
remote shell paths properly; do not use `JSON.stringify` as shell escaping.

**Detach the remote side completely**, or the local `ssh` stays open until the
job ends. A remote `nohup … &` still holds the ssh channel while any of its
standard streams is open. *Evidence:* two launches without redirection hung the
local call until its 120 s timeout. This returns immediately:

```bash
ssh -f spark2 "cd $RW && nohup bash -c '<job> > job.log 2>&1; echo EXIT \$? >> job.log' \
  </dev/null >/dev/null 2>&1 &"
```

Appending `EXIT <status>` to the log gives the local poll loop something to wait
for (`until ssh spark2 'grep -q ^EXIT …/job.log'; do sleep 20; done`).

### Validate the returned turns

Retrieve the turn envelope and validate it against the selected recording
before joining: times finite, ordered, in range, end after start, and the
requested people not collapsed into a single voice. `diarize_label.py` rejects
empty turn lists and invalid intervals or blank speakers.

## Raw audio, edited transcript

When the transcripts are on an edited timeline and only the raw recording
exists (provenance.md, *Edited-timeline transcripts*), diarize the **raw** audio
as usual. Then move the turns onto the edited timeline **word by word** before
the join. Shifting each constant-offset stretch by its offset is not precise
enough. *Evidence:* OOTA ch02's ~124 cuts left 1–6 s of drift inside stretches
that looked constant, which is longer than most cues.

1. **Word timestamps for the raw audio.** On spark2, after the diarization job
   (they share the GPU headroom), stage and run
   `~/src/mytools/audio-to-vtt/spark/words_remote.py` in the `audio-to-vtt`
   environment. It is a full-file faster-whisper `large-v3` pass with word
   timestamps and VAD. Deploy it flat and re-copy it every run, like
   `diarize_remote.py`. *Measured:* 85.3 min of audio in 213 s, 11,243 words.
2. **Project.**

   ```bash
   python3 "$SKILL_DIR/project_turns.py" --words "$RUN/words_raw.json" \
     --vtt "$BEST_VTT" --turns "$RUN/turns_raw.json" --output "$RUN/turns.json"
   ```

   It aligns the edited VTT's tokens to the raw words (exact runs of 4 or more),
   looks up the diarization speaker at each anchored word's own raw timestamp,
   and gives each cue the duration-weighted majority. A cue with no anchor gets
   a bounded local search between its anchored neighbours, or an interpolation
   when no cut falls between them. Otherwise it gets no turn and ends up
   `UNKNOWN`. Each turn records `how` (`word` / `local` / `interp`) and its vote
   share.
3. **Join as usual.** `$RUN/turns.json` is on the edited timeline, the same as
   the Descript turns, so `diarize_label.py` and its cross-validation run
   unchanged.

*Evidence — OOTA ch02:* 6317 of 7795 edited words anchored exactly (81%). 950 of
1036 cues were labelled (824 by word, 124 by local search, 2 by interpolation),
and 86 were not. Of the 86 left unlabelled, most are one- to three-word
backchannels. The check that the projection is sound is the cross-validation:
Descript's independent labels agreed with the projected clusters at 87–99% for
every cleanly separated player. A misaligned projection scatters that matrix.
Report the unlabelled count to the GM. Those cues are unresolved, not errors.

## Join and cross-validate

**Report-only first.** Omit `--output`; nothing is written until the report has
been read.

```bash
python3 "$SKILL_DIR/diarize_label.py" \
  --turns "$RUN/turns.json" --vtt "$BEST_VTT" \
  --md "$RUN/descript_turns.json" --limit-seconds <recording seconds>
```

`--limit-seconds` is optional; it defaults to the envelope's `audio_duration`
and is a prefix cut, not an offset (provenance.md). `--output` refuses to
overwrite any input.

Each cue takes the diarization speaker holding the greatest overlapping duration
of the cue. The result is then checked against the second clustering: one is
pyannote's speaker embedding, the other Descript's, and they share no
information, so agreement means something. That holds only if the second
source is genuinely independent (not a derivative) and on the same recording.

**Pass `--md` the Descript turns JSON, not the `.md`.** Both parse, but they
join differently:

| `--md` given | join | ch02 agreement | `[?]` cues |
|---|---|---|---|
| `descript.md` (starts only) | nearest preceding utterance | 79.5% | 522 |
| `descript_turns.json` (real spans) | max overlap, same rule as the diarization | **89.9%** | 347 |

*Evidence (Phandalin ch02):* the `.md` form carries no end times, so every cue
inherits whoever spoke last, including cues sitting in a silence gap. That
misassignment is not real disagreement between the tools, and it depressed the
headline by about ten points. The raw Descript `.txt` parses as **zero**
utterances either way; the script says so and exits.

### Reading the report

Show the GM the speech split, coverage, the confusion matrix, the join type the
script prints, and the agreement among mapped words.

**Mapping rule.** The confusion matrix counts transcript words, not word-level
speaker truth. A second-source cluster is mapped only when it contributes at
least 5% of compared words and one diarization cluster owns at least 60% of its
row. Agreement is computed only on words with a qualifying mapping. The tool's
mapping is statistical and does not establish player names.

**Agreement bands.** Historical runs: ~80% word-level agreement with starts-only
joins (81.2%, and 82.2% on Phandalin ch04) and ~90% with real spans (89.9% on
Phandalin ch02). These are diagnostic examples, not guaranteed accuracy, and
the two joins are not on the same scale: read the join line before comparing
runs. Below ~70% either way (the script warns), one of the signals has failed;
find out which before labelling anything.

**The percentage is a disagreement measure, not an error rate.** Report it with
its denominator (the script prints `X% (mapped/all words mapped)`; excluded
words are not successes), the unmapped fragments, and the largest single
disagreement. "4.7%, largest single disagreement 16 words" is a decision the GM
can take in one breath; 202 raw findings is not. Accepting the percentage never
approves relabelling the disagreeing cues: they stay flagged `[?]` unless the GM
rules on them.

**`[?]` is disagreement, not a demonstrated error.** *Evidence:* 297 of 1379
cues were flagged on one session, almost all short crosstalk fragments on turn
boundaries ("Yeah.", "Okay."); long narrative cues are rarely flagged. Do not
"fix" them in bulk.

**A dominant cluster is a STRONG CLUE, not a verdict.** The script warns when the
largest cluster holds more than 70% of speech. It may be a collapsed clustering
(*evidence:* `3.1` put 84% of a three-person mono recording in one cluster),
and a collapsed clustering looks exactly like a valid one downstream. It may
equally be a GM-heavy session: a GM can legitimately dominate a two-person
table. State the clue, its strength and the incident, and ask the GM. Never
re-cluster, switch model or discard the run on this clue alone.

Do not infer cross-validation from a second file's existence. With no
comparable spans or no qualifying mapping, agreement is unavailable, and the
script says so.

**When one person spans several clusters, the headline leaves them out.** The
mapping rule needs one diarization cluster to own 60% of a row, so a GM split
across registers has no qualifying mapping. The GM's words drop out of the
denominator, and **no `[?]` is set on any GM cue**, including cues where the
second clustering says a player is speaking. *Evidence — OOTA ch02:* the script
reported 93.5% over only 2050 of 7778 words. After the GM-approved mapping
merged the three GM clusters, name-level agreement was about 96% over 7348
words. 90 cues (296 words) disagreed by name, and only 42 of them carried `[?]`.
In that case, compute agreement **by name, after the approved mapping**: join
each labelled cue to the Descript turn with the most overlap, translate both
through the mappings, and list every cue where the names differ. Report that
count and the largest single cue next to the tool's figure, and give the GM the
list. The unflagged ones are the ones nobody will look at otherwise.

### Clusters versus people

*Evidence — Descript found six speakers for three people:*

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
**Fragments are usually not people.** They are most often one person's second
register (a GM doing NPC voices splitting off), which must not be promoted to a
participant. With two people, do not assume the longest cluster is the GM or
force cues to alternate.

**But read their lines before dismissing them.** *Evidence — the coffee-room
voice (Phandalin ch02):* two Descript fragments (89 words, 1.5%) were a real
fifth voice, someone in the GM's room, not at the table:

```
[01:36:54] Speaker 6: Are you gonna make coffee?
[01:36:56] Speaker 4: No, there's a whole other bag of coffee there.
[01:39:04] Speaker 7: Tell Dave that when he says polymorphism it's beautiful
```

Domestic, addressed to the GM, and answered by him: a person, not a register
split. The size test alone would have thrown them away; the content test takes
ten seconds and is the one that informs the GM's decision. Such a voice is
labelled `Room (not at table)` so scene extraction cannot attribute coffee to a
PC, **but only after the GM confirms it** (below). Its speech is retained unless
the GM asks for removal.

### Only the second clustering can see an unbudgeted voice

pyannote is told `num_speakers=N` and has exactly N bins, so a surprise voice is
forced into somebody. *Evidence:* on ch02 the room voice landed in the player
whose cluster it least resembled semantically. Raising to `num_speakers=5` did
**not** recover it: agreement fell 79.5% → 72.1% and the fifth cluster split
the *GM* (37%/50%, no clear home) instead. Keep `num_speakers` at the number of
people you know about, and let Descript find the ones you do not.

### `--md-label`: naming a voice the diarization cannot see

For a voice isolated only by the second clustering, and only after the GM has
confirmed who or what it is (including `Room (not at table)`), name its cues
from the second clustering's id, with the approved mapping saved as a JSON file:

```bash
--md-label "$RUN/approved_md_labels.json"   # {"Speaker 6": "Room (not at table)", "Speaker 7": "Room (not at table)"}
```

The voice can be a **player**, not only an outsider: someone pyannote merged
into another player's cluster but Descript kept apart. *Evidence — OOTA ch02:*
the diarization cluster labelled Gabe also held Mike. The GM approved
`{"<non-player>": "Mike", "mike": "Mike"}` (Descript's mislabelled profiles), and 28
cues were named Mike from the second clustering. State the limit in the header:
wherever Descript itself put Mike under another name, the file inherits that
error.

- The override applies only where the named cluster holds at least
  `--md-label-coverage` of the cue (default 0.5; the script accepts 0.5–1.0),
  so short backchannels stay with whoever actually holds them: a coverage rule
  hand-editing gets wrong.
- Coverage needs real spans, so `--md-label` requires `--md` to be Descript turns
  JSON; given a starts-only `.md` the script refuses rather than relabelling
  every cue in the cluster.
- The override wins outright and drops the `[?]` for those cues: the
  disagreement is the reason the cue is named from the other tool. Do not
  bulk-clear unrelated flags.
- The output header records which cluster each override came from.

*Evidence — the 32→24 comparison (ch02):* relabelling every cue the room voice
merely *overlapped* claimed 32 cues; requiring it to be the dominant speaker
gave 24. The 8 it gave back were Kostadis answering the room person ("All right,
we'll tell it to them in a little bit"), not the room person speaking.

## Single acoustic source

Two text exports from the same diarization are one signal, and Descript used as
the primary leaves no second. Cross-validation is the default and stands unless
the GM explicitly accepts **"single acoustic source, no independent
cross-validation"**. Until then, produce only an explicitly unvalidated cluster
report that says what is missing; never report independent agreement. After
acceptance, omit `--md`: the script writes "Single acoustic source; no
independent cross-validation." into the header, and a `--note` records that the
GM accepted it. Keep that fact in every report and header of the run.
