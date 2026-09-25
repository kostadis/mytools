---
name: speaker-attribution-text
description: Infer best-effort human speaker labels from a session transcript, story context, and labeled transcripts of the same people in other sessions when audio or the original speaker-labeled export is missing. Use for text-based speaker attribution, requests to learn participants' phrasing from neighboring sessions, or $speaker-attribution-text. Produces contextual guesses with provenance, not acoustic voice identification. Output is written losslessly to a NEW file; the source transcript is never modified. When audio or acoustic turns exist, use speaker-attribution instead.
---

# Text Speaker Attribution

Turn a speakerless transcript into a useful attributed working copy by reading
the conversation in context and comparing labeled reference sessions. This
captures the workflow used for Obelisk session 001 when its Zoom transcript was
missing. The roster, character ownership, and reference paths are inputs; do
not carry that session's identities into other campaigns.

Use this skill when the user wants approximate attribution from text. If they
want acoustic verification and have audio or acoustic turns, use the separate
`speaker-attribution` skill. A summary supplies story context, not a second
recording or independent speaker evidence. Describe text-derived labels as
inferences even when the user accepts them for use.

## Establish the inputs and intended use

Inspect the supplied session and reference directories with `rg --files`. Reuse
the user's participant names, GM identity, player/character ownership, chosen
references, and prior rulings. Count physical people, including the GM; one
person may voice several NPCs and party members. Do not insist on a missing
Zoom file or audio when text inference is already the requested approach.

Choose the output mode from the user's instructions:

- **Provisional:** write named proposals with qualitative confidence. Keep
  `UNKNOWN` or `MIXED` where a single name is not useful. A review is optional;
  prioritize meaningful ambiguous exchanges if the user wants to review.
- **Best guess accepted for use:** when the user says to use best judgment,
  finish the guesses, or dismisses the remaining uncertainties, assign every
  cue to the most plausible person. Do not request another attribution
  approval or leave unknown labels solely because the evidence is weak. Keep
  weak assignments low confidence and record the user's authorization.

Request missing facts only if available context cannot support useful progress.
Do not require a mode questionnaire. Acceptance of approximate attribution is
not confirmation of every identity, and does not authorize new spelling or
canon changes in a separate workflow.

## Prepare a traceable source

Select one original labeled transcript per reference session. Do not count
cleaned copies, retranscriptions, concatenated copies, or generated summaries
as additional independent evidence. Record source paths and hashes. Check that
the references concern the same people; similarly named anonymous clusters
across sessions do not establish identity.

The standard-library helper provides a cue manifest and lossless output writer.
Resolve `SKILL_DIR` to this installed skill, create a unique scratch directory,
and use a speakerless source:

```bash
python3 "$SKILL_DIR/scripts/attribution.py" prepare \
  --source "$SOURCE" --speaker Kostadis --speaker Nikhil \
  --reference "$REFERENCE_002" --reference "$REFERENCE_003" \
  --context "$SUMMARY" --output "$RUN/decisions.json"
```

Use the actual roster and paths. `--reference` and `--context` are optional and
repeatable. For Markdown or another format, follow the same workflow with an
appropriate lossless writer; this helper supports WebVTT only. Auditing existing
labels needs an explicit relabeling procedure, not nested speaker prefixes.

## Build reference evidence

Read [evidence.md](references/evidence.md) for normalization, the optional text
classifier used in the original run, and concrete attribution traps.

Normalize known export labels to short human names using an explicit mapping.
Exclude screen-share channels and unidentified bins from training. Inspect
representative exchanges by each person across sessions, including ordinary
questions, explanations, action declarations, corrections, and acknowledgments.
Record examples with their source and timestamp. Learn recurring phrasing and
interaction habits; do not turn phrases into identity rules.

A word/character TF-IDF classifier can supply secondary style hints when there
are enough labeled examples. It is optional: missing dependencies or sparse
references should not block contextual work. If a particular session genuinely
needs the classifier, say why and ask before stopping. Its score is not the probability
that a cue belongs to that person. Verify across whole held-out sessions when
reporting its performance; do not present reference-label agreement as accuracy
on the target transcript.

## Read and assign the whole conversation

Read every target cue in order, in manageable chunks with overlapping context.
Keep stable one-based cue indices across chunks. Use the summary to locate
scenes and understand who is present, but use the transcript for actual speech.

- Start from strong contextual anchors: a GM setting a scene, a player choosing
  an action, an addressed question with its answer, or explicit self-reference.
- Carry continuity across adjacent fragments when they form one utterance.
  Cue boundaries and alternating lines are not speaker changes.
- Attribute quoted NPC speech to the person voicing it. First-person character
  dialogue is not automatically the owner of the main PC. GM explanations,
  sidekick turns, rules talk, and map troubleshooting can all sound player-like.
- Treat short replies such as “yeah,” “okay,” and “I know” as weak evidence.
  Resolve them from the nearby exchange in best-guess mode, retaining low
  confidence even if a style classifier strongly prefers one person.
- For apparent within-cue changes, preserve all words and the existing span.
  In provisional mode use `MIXED` if helpful. In accepted best-guess mode choose
  the apparent dominant speaker and set `possible_mixed: true`; do not invent
  split timestamps or imply all the words were certainly spoken by one person.
- Override style hints when scene or conversational evidence is stronger.
  Check surprising runs and transitions, but do not force a balanced split;
  the GM may legitimately dominate a two-person session.

Fill each manifest cue's `speaker`, `confidence`, and `evidence_note`. Use
`high`, `medium`, `low`, or `unresolved` as qualitative textual confidence.
Keep factual scene context, speaker candidates, and model hints distinct.
Record character ownership and reference observations in `method_notes` or
additional manifest fields. Do not alter the source fields or cue text.

## Write, verify, and hand off

For accepted best guesses, set `mode` to `best_guess`, copy or accurately
summarize the user's instruction into `authorization`, and set
`review_required: false`. Leave `gm_confirmed: false` unless the GM actually
confirmed that cue. The helper distinguishes acceptance for use from identity
confirmation. An optional review page should never reintroduce a checkpoint
the user has already waived.

```bash
python3 "$SKILL_DIR/scripts/attribution.py" render \
  --decisions "$RUN/decisions.json" \
  --output "$SESSION/transcript.speakers.vtt" \
  --record "$SESSION/speaker_attribution_text/attribution.json"
```

Use `.speakers.provisional.vtt` for a draft. Both output paths must be new. The
helper rejects stale input hashes, missing or duplicate cue assignments,
unrecognized people, altered dialogue, and unresolved labels in best-guess
mode. It verifies exact source-byte recovery after removing only its inserted
NOTE and speaker prefixes, including cue identifiers, settings, numeric-only
dialogue, multiline payloads, and original line endings.

If the user wants to review ambiguous cues in a batch rather than in chat, use
the shared review page (`../_shared/review-page/CONTRACT.md`): one page for the
run, returned as the GM's Copy or Save export and validated with
`read_decisions.py --items`; there is no save callback. A review page must never
reintroduce a checkpoint the user has already waived: in accepted best-guess
mode there is nothing to gate, so offer the page only as a record or for the
genuinely ambiguous subset.

Preserve original transcripts, summaries, and reference files. Keep corrections
and prose smoothing in their own passes. Save source/reference hashes, method,
authorization, cue-level confidence and reasons, possible mixed cues, counts,
and verification alongside the attributed VTT. If earlier drafts exist, identify
the current working transcript clearly and mark old review artifacts historical
in the handoff. Report the file, speaker totals, and that attribution is inferred
from text. Do not launch extraction or narration unless already requested.
