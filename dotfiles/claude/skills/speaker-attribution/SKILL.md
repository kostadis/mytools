---
name: speaker-attribution
description: Put trustworthy speaker names on a session recording — either when the transcripts carry no usable attribution (the single-room case, where everyone shared one microphone so Zoom labelled all 866 cues with the host's name and the editor produced six anonymous clusters for three people), or when they carry real names that are a voice-profile GUESS and are known to be wrong, where the job is auditing an existing name→voice mapping instead of naming anonymous ones. Verifies first that each transcript actually belongs to the recording it sits next to (filenames lie) and that a second 'transcript' is not just a derivative of the first, diarizes on the DGX Spark, cross-validates two independent clusterings against each other, mines the transcript for direct address, and hands back a ranked disagreement queue rather than a silent relabel. Invoke as /speaker-attribution [session-dir].
---

# speaker-attribution

Put evidence-backed **player** names on a session recording, in one of two
cases:

- **Naming.** The transcripts carry no usable attribution. Everyone shared one
  microphone, so Zoom put the host's name on every cue and the editor produced
  anonymous clusters. Diarization is the only acoustic signal, and the names
  come from the GM.
- **Auditing.** The transcripts carry real names, but they are a voice-profile
  guess the GM knows to be wrong. The job is auditing that name→voice mapping
  against an independent clustering and handing back a ranked disagreement
  queue, not a relabelled file.

If the transcripts carry reliable per-speaker names and only their timeline is
wrong, stop: that is `/transcript-rebuild` (provenance.md has the routing table).

The three references hold the detail, and under each rule the incident and
numbers that justify it. They are shared byte-for-byte with the Codex copy, so
they speak of "the skill's scripts directory" and "ask the GM"; this file
supplies the Claude mechanics.

- [references/provenance.md](references/provenance.md) — routing, fingerprints,
  derivatives, text layers, Descript conversion, chat sidecars.
- [references/acoustic-workflow.md](references/acoustic-workflow.md) — the
  Spark run and its landmines, the join, agreement, fragments, `--md-label`,
  single source.
- [references/identity-review.md](references/identity-review.md) — naming
  clusters, audits, the strong clues, GM decisions, writing, verification, the
  run record.

## Where this sits

**No audio?** When neither the recording nor acoustic turns exist, this skill
cannot run; use `/speaker-attribution-text`, which infers labels from the
conversation itself and marks every label as an inference.

**Neighbours:** after any `/audio-to-vtt` or `/transcript-rebuild`; next is
`/vtt-spell-pass` on the **unlabelled** tape (then re-apply this skill's
approved mapping to the `.cleaned.vtt`), then `enhance_summary` and
`/staged-consistency` phase 0/1. The whole order, and why, is in
`~/src/CampaignGenerator/docs/design/SkillPipelineOrder.md` — the single statement of it; this skill keeps no copy.

The labels this skill writes are **short player names**; the session_doc
pipeline's pre-flight wants `config/players.yaml` display names.
`/session-doc-run` does that mapping — do not rename the file this skill
produces. Run it **before** `/scene-extract`. After means re-extracting.

## Setup

```bash
SKILL_DIR=~/.claude/skills/speaker-attribution
RUN=$(mktemp -d "<scratchpad>/speaker-attribution.XXXXXX")   # the session's scratchpad directory
```

The five helpers use only Python's standard library. Use participant facts the
GM already gave (people, GM included; player/PC mapping) and do not ask for
them again. A known PC owner is not an acoustic cluster ID.

## Rules that hold throughout

- **Report first; drafts stay in scratch.** Every report, cluster-ID VTT and
  queue lives in `$RUN`. Nothing named goes into the session directory before
  the GM approves the name→voice mapping. The final `<stem>.speakers.vtt` is
  written **once**, after approval, as a new file. Originals are never modified.
- **Cross-validation stands** unless the GM explicitly accepts **"single
  acoustic source, no independent cross-validation"**. Descript used as the
  primary (no GPU free) leaves one source, so ask. With that acceptance the
  output header says so; without it, report an unvalidated cluster report only.
- **Strong clues, not decisions.** A dominant cluster (possible collapse, or a
  GM-heavy session), identical turn tallies (likely derivative), the
  chat-sidecar absence probe (who went quiet), two PC names on one cluster
  (one person may have run both), a voice profile named for someone off the
  roster (likely a mislabelled player), and one cluster using two PCs'
  abilities (two players merged) are put to the GM with the clue, its strength
  and the incident behind it. Never auto-select a voice, discard a transcript,
  or re-cluster on one clue alone.
- **The agreement percentage is a disagreement measure, not an error rate.**
  Report it with its denominator and the largest single disagreement. Accepting
  it never approves relabelling the disagreeing cues; they stay `[?]` unless
  ruled.
- **Gated pyannote models** (`segmentation-3.0`, `speaker-diarization-3.1`,
  `speaker-diarization-community-1`): access must already exist. If it fails,
  stop and tell the GM which licence to accept themselves. Never accept terms.
- **Ask with `AskUserQuestion`** at every checkpoint. An unanswered, ambiguous
  or timed-out question is not a decision: ask again.

## 1. Provenance — never skip

Read provenance.md, then:

```bash
python3 "$SKILL_DIR/transcript_provenance.py" <session-dir-or-summaries-tree>
```

A filename is an assertion, not evidence. Look for MISFILED, SPANS MULTIPLE
RECORDINGS and "sits beside audio it does NOT transcribe"; confirm matches by
endpoints (same words within a second or two; mvhd duration recipe in the
reference). A warning on every transcript in a directory is the stem-vouching
rule, not a finding. `sha256sum` every transcript first (a "RAW" and a cleaned
export can be the same bytes), check for derivatives with the tally command,
choose the best text layer, convert Descript with `descript_turns.py`, and note
any `GMT<date>_RecordingnewChat.txt` sidecar. A Descript `.md` that went through
Google Drive comes back as a Google Doc with only minute markers, and
`descript_turns.py` parses nothing. Fetch it through the Drive connector and
give it spans with `descript_align.py` (provenance.md). **Count Descript's
profiles against the party**: a player who is addressed by name but has no
profile has been merged into someone else's (acoustic-workflow.md, *The reverse
merge*).

**Audio far longer than every transcript** has two causes with opposite fixes
(provenance.md): the audio belongs to another session (check the `GMT<date>`
stamp against the directory, then the neighbouring session's endpoint), or it is
the raw recording and the transcripts come from a Descript-edited export. Ask the
GM which. For the edited case, the options in order are: export the edited
audio; project raw diarization by words (step 2); or a single source.

**Checkpoint 1:** if provenance reports MISFILED or a stray transcript, the GM
decides what moves where. Do not relocate files on your own reading. Identical
tallies go to the GM as a strong clue, not a discard.

## 2. Diarize on the Spark

Read acoustic-workflow.md. It has the staging commands, the manifest and the
run line. The short version, every item of which was hit for real: resolve the
remote home and use absolute paths (no `~` in the manifest); re-`scp`
`diarize_remote.py` every run; verify staging positively, not by silence; set
`HF_HOME=~/.cache/diarize-hf` because the shared cache is root-owned;
`community-1`, never `3.1`; `num_speakers` = people; try CUDA even when the GPU
looks busy and confirm `running on cuda` in the log; launch detached, redirect
to a log, never pipe through `tail`; never stop another GPU workload.

Use `Bash` with `run_in_background` for the remote job, and read its log file
rather than waiting on buffered output. Launch with `ssh -f` and redirect all
three remote streams (`</dev/null >/dev/null 2>&1 &`); otherwise the local call
hangs until it times out. Only spark2 has the `diarize` and `audio-to-vtt`
environments, so run Spark jobs one after another there. After one CUDA OOM,
retry once before falling back.

**Raw audio, edited transcript:** diarize the raw audio, run
`audio-to-vtt/spark/words_remote.py` on spark2 for word timestamps, then
`python3 "$SKILL_DIR/project_turns.py" --words … --vtt <best-text>.vtt --turns
<raw turns> --output "$RUN/turns.json"`. The join below then runs unchanged.
Report the unlabelled-cue count (acoustic-workflow.md, *Raw audio, edited
transcript*).

## 3. Join and cross-validate (report only)

```bash
python3 "$SKILL_DIR/diarize_label.py" \
  --turns "$RUN/turns.json" --vtt <best-text>.vtt \
  --md "$RUN/descript_turns.json" --limit-seconds <recording seconds>
```

No `--output` yet. Pass `--md` the Descript **turns JSON** (real spans), not the
`.md`. `--limit-seconds` is a prefix cut, not an offset. Show the GM the speech
split, the confusion matrix, the join type, and agreement with its denominator
and largest single disagreement. Read small clusters' lines before dismissing
them (the coffee-room voice).

**When the GM's voice splits into several clusters** (narration vs.
conversation), the headline leaves the GM out: that row has no qualifying
mapping, so the GM's words are dropped from agreement and no GM cue gets `[?]`.
Two players can also end up merged in the bin the split took (acoustic-workflow.md,
*A GM's registers*). After the mapping is approved, compute agreement by name
and give the GM the full list of disagreeing cues.

**Checkpoint 2:** the GM confirms the agreement percentage and the speech split
before anything is built on them. A collapsed clustering looks exactly like a
valid one downstream. An existing acceptance of these exact results need not
be asked again.

Then write the anonymous draft to scratch only:

```bash
python3 "$SKILL_DIR/diarize_label.py" --turns "$RUN/turns.json" --vtt <best-text>.vtt \
  --md "$RUN/descript_turns.json" --output "$RUN/clusters.vtt"
```

## 4. Name the clusters, or audit the names

Read identity-review.md.

- **Anonymous:** `python3 "$SKILL_DIR/name_clusters.py" "$RUN/clusters.vtt"
  --name <real names>` and again with the PC names people actually say. A
  `SPLIT` stays unresolved; close it with the GM, using the chat sidecar
  absence probe and representative exchanges as evidence.
- **Named voice profiles:** check the bijection and shares, then build the
  disagreement queue (GM-confirmed mapping, 75% coverage floor, ranked by words,
  directional bias) instead of a relabelled VTT.
- **`Room (not at table)`** and any other voice named only by the second
  clustering must be GM-confirmed before `--md-label` applies it. Its speech is
  kept. That voice can be a **player** pyannote merged into someone else's
  cluster; check every profile name against the roster first (OOTA ch02:
  `<non-player>` was Mike).

**Checkpoint 3:** the cluster→name mapping and any cue-level rulings. This is
the precision decision the skill exists to serve; nothing further along
re-checks speaker identity.

**Batch review.** When there are mapping or cue decisions to make, ask with
`AskUserQuestion` whether the GM wants the shared review page or one question
at a time; never default to the page. For the page, follow
`~/.claude/skills/_shared/review-artifact/CONTRACT.md` with
`$RUN/review_items.json`: **one card per mapping or cue decision** (ids that
round-trip, such as `map-SPEAKER_00` or `cue-<index>` with a sidecar map to the
cue), each card's `y`/`n` naming what is written
where, the quotes and timestamps (HTML-escaped) in `ev`. Never pre-fill a
verdict; a recommendation goes in the card text. Publish with
`capabilities: {"artifact": {}}`, stop, and read the decisions back with
`read_decisions.py --items`. An unmarked card stays unresolved; Discuss comes
back to chat as one grouped pass.

## 5. Write once, verify, record

Save the approved mapping to `$RUN/approved_names.json` (plus any approved
`--md-label` map to `$RUN/approved_md_labels.json` and any per-cue rulings to
`$RUN/approved_cue_labels.json`) and hash each one. Confirm the
inputs still match the reviewed hashes, then re-run the join **on the original
speakerless text**, never on a labelled file:

```bash
python3 "$SKILL_DIR/diarize_label.py" \
  --turns "$RUN/turns.json" --vtt <best-text>.vtt --md "$RUN/descript_turns.json" \
  --names "$RUN/approved_names.json" \
  [--md-label "$RUN/approved_md_labels.json" --md-label-coverage 0.5] \
  [--cue-labels "$RUN/approved_cue_labels.json"] \
  [--limit-seconds <recording seconds>] \
  --note "Labels identify human players, not characters." \
  --note "Mapping approved by the GM: <date>, $RUN/approved_names.json sha256 <hash>." \
  --output <session-dir>/<stem>.speakers.vtt
```

`--md-label` needs real spans (the turns JSON) and a coverage of 0.5–1.0. For a
GM-accepted single-source run, drop `--md`/`--md-label` and add
`--note "GM accepted: single acoustic source, no independent cross-validation."`
Where a player's real name collides with their PC's, label with the nickname
and add a `--note` saying why. Unmapped voices stay raw cluster IDs or
`UNKNOWN`.

**Verify** with the script in identity-review.md: selected cue count; exact
dialogue payloads apart from the inserted labels; timestamps; spoken numbers,
crosstalk, `UNKNOWN` labels and `[?]` markers preserved; every cue omitted by
a time limit reported; no original file changed (re-hash the inputs).

**Run record:** write `<stem>.speakers.run.json` beside the output with the
input paths and SHA-256 hashes, model and speaker count, provenance findings,
independent-source status or the GM's single-source acceptance, join method,
agreement with its denominator, the GM's decisions and the hash of the approved
decisions file, and the unresolved cues.

Report the file, the run record, and what remains uncertain. Next in the
pipeline: `/vtt-spell-pass`, then `/session-doc-run` (see *Where this sits*).
