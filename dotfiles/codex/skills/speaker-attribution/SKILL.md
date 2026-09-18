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

Use this before scene extraction and narration. If existing speaker identities
are reliable and only their timestamps need alignment, that is a transcript
alignment/rebuild task. Do not redo identity attribution to fix a timeline.

## Inputs and scope

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
- **Independent clustering:** use one when available. Two text exports from
  the same diarization are one signal. If only one acoustic source exists,
  prepare an explicitly unvalidated cluster report and explain what is missing.
  Obtain the GM's acceptance of that limitation and the actual name mapping
  before producing named output; never report independent agreement.
- **Output:** preserve originals. Work in a unique scratch directory and write
  the approved result to a new `<stem>.speakers.vtt`. Existing-name audits first
  produce a disagreement queue, not a replacement transcript.

Resolve `SKILL_DIR` to the loaded directory, normally
`${CODEX_HOME:-$HOME/.codex}/skills/speaker-attribution`. Create a unique run
directory with `mktemp -d` under an allowed scratch root. Use resolved, quoted
paths in all commands. The four Python helpers use the standard library.

## 1. Establish provenance

Read [provenance.md](references/provenance.md), then run:

```bash
python3 "$SKILL_DIR/transcript_provenance.py" "$SESSION_DIR"
```

Widen to adjacent session directories when a match is unclear. This compares
transcript fingerprints; it does **not** listen to audio or prove a filename's
claim. Confirm a candidate recording by opening/closing words and timing.
Duration alone and matching speaker tallies are clues, not proof.

Keep summaries out of the second-transcript inventory. Check for derivatives,
concatenations, timeline offsets, and Descript labels masquerading as verified
names. Convert Descript exports to turn spans using the reference instructions.

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
when required. Do not stop other GPU services or accept model-license terms on
the user's behalf. Do not launch remote work just to inspect this skill.

If only Descript turns are available, they can be the primary acoustic source.
Do not reuse their derivative Markdown as an independent second clustering.

## 3. Join and compare

Use report-only mode first. `--md` accepts a **turns JSON** and prefers real
start/end spans; its Markdown alternative only carries starts.

```bash
python3 "$SKILL_DIR/diarize_label.py" \
  --turns "$RUN/turns.json" --vtt "$BEST_VTT" \
  --md "$RUN/descript_turns.json"
```

Omit `--md` when there is no independent source and state the limitation. For
concatenated text, use the recording's actual timeline and `--limit-seconds`;
that option selects a prefix, not an arbitrary offset. Verify any slicing or
retiming separately before joining.

Show the speech split, coverage, confusion matrix, join type, and agreement
among mapped words. Historical runs measured about 80% with starts-only joins
and 90% with spans; these are diagnostic examples, not guaranteed accuracy.
Investigate low agreement, a collapsed cluster, or unmapped voices. A GM can
legitimately dominate a two-person session, so a large share alone is not proof
of collapse. Read small clusters' dialogue before calling them register splits
or identifying them as people outside the game.

**GM checkpoint:** confirm the agreement and speech split before using them to
name voices. Present missing corroboration or suspicious patterns explicitly.
An existing acceptance of these exact results need not be requested again.

Then write an anonymous, clearly provisional VTT into scratch with `--output`
for the naming pass. `[?]` means disagreement, not a demonstrated mistake.

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

**GM checkpoint:** obtain the cluster-to-player mapping or exact audit rulings
before writing real names. Ask in Codex chat; use an available clarification
tool where appropriate. Do not reference Claude question tools, Artifacts,
callbacks, or Claude task APIs. If the user requests batch review, use the
installed shared review-page contract when available, one mapping or cue change
per item, and accept only explicit returned decisions as approval.

## 5. Write and verify the approved result

Save the approved mapping in a JSON file. Re-run the join on the original
speakerless text, adding `--names "$RUN/approved_names.json"` and a new output
path. Do not feed a labelled result back in as unlabelled speech. For a named
audit, preserve labels until the exact changes are approved; prepare a separate
unlabelled comparison copy if needed, stripping only recognized metadata.

Include `--note "Labels identify human players, not characters."` and a note
identifying the GM-approved mapping. If only one acoustic source was accepted,
record that explicit limitation as well.

Use **short player names** for physical speakers, never PC names inferred from
ownership. Record known player/PC relationships separately. Label a confirmed
outside voice `Room (not at table)` and retain its speech unless removal was
requested. `--md-label` requires real second-source spans and a dominant share
of at least 50%; a brief overlap does not own a whole cue.

Verify the selected cue count, exact dialogue payloads (apart from inserted
labels), and timestamps against the source. Preserve spoken numbers, crosstalk,
unresolved `UNKNOWN` labels, and disagreement markers. Report every omission
caused by a selected time limit. Check that no original file changed.

Save a run record beside the new output with source paths/hashes, model and
speaker count, provenance findings, independent-source status, join method,
agreement denominator, GM decisions, and unresolved cues. Report the resulting
file and uncertainty. Downstream extraction may map approved short names to
`config/players.yaml` display names using that pipeline's actual capabilities;
do not assume Claude-only downstream skills are installed or start them
automatically. Resume any pending spell pass within its existing review rules.
