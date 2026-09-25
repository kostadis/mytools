---
name: speaker-attribution
description: Add or audit speaker attribution in campaign session transcripts whose labels are missing, anonymous, shared under one microphone, or unreliable voice-profile guesses. Check recording provenance, compare independent acoustic speaker clusters, and obtain GM rulings before assigning player names. Use for $speaker-attribution, /speaker-attribution, or requests to identify who spoke in a session. Requires recording audio or existing acoustic speaker turns; text alone cannot establish voice identity.
metadata:
  short-description: Review and restore session speaker attribution
---

# Speaker Attribution

Produce evidence-backed player labels for session dialogue, or a ranked review
queue when existing labels disagree with independent acoustic evidence. This
is the Codex port of the Claude skill. Its helpers are local to this directory;
using it never requires editing the Claude collection.

Two cases: **naming** anonymous clusters (one shared microphone, so the
transcript has no usable names), and **auditing** real names that are a
voice-profile guess the GM knows to be wrong. Use this before scene extraction
and narration; running it after means re-extracting. If existing speaker
identities are reliable and only their timestamps need alignment, that is a
transcript alignment/rebuild task. Do not redo identity attribution to fix a
timeline.

The three references hold the detail, the worked incidents and the numbers
behind every rule below. They are shared byte-for-byte with the Claude copy.

## Inputs and scope

**No audio?** When neither the recording nor acoustic turns exist, this skill
cannot run; use `speaker-attribution-text`, which infers labels from the
conversation itself and marks every label as an inference.

Use the supplied session directory or transcript. Inspect its audio, VTT,
Descript exports, saved acoustic turns, and Zoom chat sidecars. Use `rg --files`
before searching adjacent sessions for misplaced files. Read applicable
`AGENTS.md`, participant configuration, and existing GM rulings.

- **Participants:** use the user's stated people and player/character mapping.
  Count people, including the GM, rather than characters or anonymous bins.
  Two people can voice an entire party. Do not ask again for facts already
  provided, or equate a known PC owner with an acoustic cluster ID.
- **Audio or acoustic turns:** required to generate speaker evidence. Missing
  Zoom text is not itself a blocker. A speakerless VTT and a summary, without
  audio or saved acoustic turns, are insufficient to identify voices. Report
  that specific missing input; do not fabricate labels from dialogue style,
  alternating cues, narration, or character names.
- **Independent clustering:** cross-validation against an independent second
  clustering is the default. Two text exports from the same diarization are
  one signal. A single acoustic source is allowed only after the GM explicitly
  accepts **"single acoustic source, no independent cross-validation"**; until
  then, prepare only an explicitly unvalidated cluster report that says what is
  missing. With that acceptance, the output header says so. Never report
  independent agreement you do not have.
- **Output:** report first; drafts stay in scratch. Preserve originals. Work in
  a unique scratch directory. Nothing named goes into the session directory
  before the GM approves the name→voice mapping; the final
  `<stem>.speakers.vtt` is then written **once**, as a new file. Existing-name
  audits first produce a disagreement queue, not a replacement transcript.

Resolve `SKILL_DIR` to the loaded directory, normally
`${CODEX_HOME:-$HOME/.codex}/skills/speaker-attribution`. Create a unique run
directory `RUN` with `mktemp -d` under an allowed scratch root. Use resolved,
quoted paths in all commands. The five Python helpers use the standard library.

## Strong clues, not decisions

Six signals are **strong clues to put to the GM, never auto-decisions**: a
dominant cluster (possible collapse, or a GM-heavy session), identical turn
tallies (likely derivative), the chat-sidecar absence probe (who went quiet),
two PC names on one cluster (one person may have run both), a voice profile
named for someone off the roster (likely a mislabelled player), and one
cluster using two PCs' abilities (two players merged). State the clue,
its strength and the incident behind it, and ask. Never auto-select a voice,
discard a transcript, or re-cluster on one clue alone. The references give the
incidents.

## 1. Establish provenance

Read [provenance.md](references/provenance.md), then run:

```bash
python3 "$SKILL_DIR/transcript_provenance.py" "$SESSION_DIR"
```

Widen to adjacent session directories when a match is unclear. This compares
transcript fingerprints; it does **not** listen to audio or prove a filename's
claim. Confirm a candidate recording by opening/closing words (within a second
or two) and timing. Duration alone and matching speaker tallies are clues, not
proof.

Keep summaries out of the second-transcript inventory. Hash every transcript
first (a "RAW" and a cleaned export can be the same bytes). Check for
derivatives, concatenations, timeline offsets, and Descript labels
masquerading as verified names; a profile name may not even be a participant.

Audio far longer than every transcript has two causes with opposite fixes: the
audio belongs to another session (check the `GMT<date>` stamp against the
directory, then the neighbouring session's endpoint), or it is the raw
recording and the transcripts come from a Descript-edited export. Ask the GM
which. For the edited case, prefer exporting the edited audio; otherwise
project raw diarization onto the edited timeline by words (step 2). Choose the best text layer, and convert Descript exports to turn spans,
using the reference instructions.

**GM checkpoint:** if a file appears misplaced, show the evidence and ask how
to resolve it before relocating anything. Missing stem matches across a whole
directory can be a naming convention rather than misfiling.

## 2. Obtain acoustic clusters

Read [acoustic-workflow.md](references/acoustic-workflow.md) when running
diarization or preparing an existing Descript clustering. Reuse suitable saved
turns after verifying their recording and timeline. Otherwise use the existing
`audio-to-vtt/spark/diarize_remote.py` on the configured Spark with
`pyannote/speaker-diarization-community-1` and the known number of people.

Remote execution is a genuine dependency only when generating new clusters.
Check the helper, host, environment, and available resources before launching.
Use existing authorization for the requested run; follow environment approvals
when required. Do not stop other GPU services. Do not launch remote work just to
inspect this skill.

**Gated models:** access to `segmentation-3.0`, `speaker-diarization-3.1` and
`speaker-diarization-community-1` must already exist. If it fails, stop and tell
the GM which licence to accept themselves. Never accept model-licence terms on
the user's behalf.

Only spark2 has the `diarize` and `audio-to-vtt` environments; run Spark jobs
one after another there. Detach remote jobs fully (`ssh -f`, all three streams
redirected) and retry CUDA once after an OOM before falling back.

**Raw audio, edited transcript:** diarize the raw audio, get word timestamps
with `audio-to-vtt/spark/words_remote.py` on spark2, then run
`python3 "$SKILL_DIR/project_turns.py" --words … --vtt "$BEST_VTT" --turns
<raw turns> --output "$RUN/turns.json"`. The join then runs unchanged. Report the
unlabelled-cue count.

If only Descript turns are available, they can be the primary acoustic source,
which makes this a single-source run (see Inputs and scope). Do not reuse their
derivative Markdown as an independent second clustering.

## 3. Join and compare

Use report-only mode first (no `--output`). `--md` accepts a **turns JSON** and
prefers real start/end spans; its Markdown alternative only carries starts.

```bash
python3 "$SKILL_DIR/diarize_label.py" \
  --turns "$RUN/turns.json" --vtt "$BEST_VTT" \
  --md "$RUN/descript_turns.json"
```

Omit `--md` only for a GM-accepted single-source run. For concatenated text,
use the recording's actual timeline and `--limit-seconds`; that option selects
a prefix, not an arbitrary offset. Verify any slicing or retiming separately
before joining.

Show the speech split, coverage, confusion matrix, join type, and agreement
among mapped words. Historical runs measured about 80% with starts-only joins
and 90% with spans; these are diagnostic examples, not guaranteed accuracy.
Investigate agreement below ~70%, a dominant cluster, or unmapped voices. Read
small clusters' dialogue before calling them register splits or identifying
them as people outside the game.

The agreement percentage is a **disagreement measure, not an error rate**.
Report it with its denominator (mapped/all words) and the largest single
disagreement. Accepting it never approves relabelling the disagreeing cues:
they stay flagged `[?]` unless ruled.

When the GM (or anyone) splits across several diarization clusters, the
headline leaves them out: that row has no qualifying mapping, so the GM's words
are dropped from agreement and no GM cue gets `[?]`. Two players can also end up
merged in the bin the split took. After the mapping is approved, compute
agreement by name and give the GM the full list of disagreeing cues.

**GM checkpoint:** confirm the agreement and speech split before using them to
name voices. Present missing corroboration or suspicious patterns explicitly.
An existing acceptance of these exact results need not be requested again.

Then write an anonymous, clearly provisional cluster-ID VTT into scratch
(`--output "$RUN/clusters.vtt"`) for the naming pass. `[?]` means disagreement,
not a demonstrated mistake.

## 4. Review identity evidence

Read [identity-review.md](references/identity-review.md).

For anonymous clusters, mine both player names and the PC names actually spoken:

```bash
python3 "$SKILL_DIR/name_clusters.py" "$RUN/clusters.vtt" \
  --name Kostadis --name Nikhil --name Zenvon
```

Use the actual session roster. Present ranked candidates with verbatim exchanges
and timestamps. A `SPLIT` is unresolved evidence; do not select the largest bin.
Typed chat sidecars, known absences, and representative audio can help the GM
identify voices. Neither silence nor a vocative match decides identity alone.

For named voice-profile exports, inspect the independent mapping and produce a
ranked disagreement queue with source/target labels, spans, coverage, words at
stake, verbatim dialogue, and directional bias. Ask the GM to review specific
changes or explicitly accept the measured unresolved disagreement.

A `Room (not at table)` label, or any other voice named from the second
clustering with `--md-label`, must be GM-confirmed before `--md-label` applies
it. That voice can be a player pyannote merged into someone else's cluster;
check every profile name against the roster first.

**GM checkpoint:** obtain the cluster-to-player mapping or exact audit rulings
before writing real names. Ask in Codex chat; use an available clarification
tool where appropriate. Do not reference Claude question tools, Artifacts,
callbacks, or Claude task APIs. If the user requests batch review, read
`${CODEX_HOME:-$HOME/.codex}/skills/_shared/review-page/CONTRACT.md` and use the
shared review page: one card per mapping or cue decision, never pre-filled.
Accept only explicit returned decisions as approval; an unmarked card stays
unresolved.

## 5. Write and verify the approved result

Save the approved mapping in a JSON file. Re-run the join on the original
speakerless text, adding `--names "$RUN/approved_names.json"` (and any approved
`--md-label` JSON file, which requires real spans and a `--md-label-coverage`
of 0.5–1.0) and the new session-directory output path. This is the one write
into the session directory. Do not feed a labelled result back in as unlabelled
speech. For a named audit, preserve labels until the exact changes are
approved; prepare a separate unlabelled comparison copy if needed, stripping
only recognized metadata.

Include `--note "Labels identify human players, not characters."` and a note
identifying the GM-approved mapping. For a single-source run, add
`--note "GM accepted: single acoustic source, no independent cross-validation."`

Use **short player names** for physical speakers, never PC names inferred from
ownership. Record known player/PC relationships separately. A GM-confirmed
outside voice is `Room (not at table)` and keeps its speech unless removal was
requested. Unmapped voices stay anonymous or `UNKNOWN`.

Verify the selected cue count, exact dialogue payloads (apart from inserted
labels), and timestamps against the source. Preserve spoken numbers, crosstalk,
unresolved `UNKNOWN` labels, and disagreement markers. Report every omission
caused by a selected time limit. Check that no original file changed. The
reference has a verification script.

Save a run record beside the new output with source paths/hashes, model and
speaker count, provenance findings, independent-source status, join method,
agreement denominator, GM decisions with the hash of the approved decisions,
and unresolved cues. Report the resulting file and uncertainty. Downstream
extraction may map approved short names to `config/players.yaml` display names
using that pipeline's actual capabilities; do not rename the output for it, do
not assume Claude-only downstream skills are installed, and do not start them
automatically. Resume any pending spell pass within its existing review rules.
