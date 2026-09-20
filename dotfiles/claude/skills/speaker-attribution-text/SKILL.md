---
name: speaker-attribution-text
description: Infer best-effort human speaker labels for a speakerless session transcript by reading the conversation in context and comparing labeled transcripts of the same people from other sessions. For when audio or the original speaker-labelled export is missing. Produces contextual guesses carrying explicit provenance and per-cue confidence — inferences, never acoustic voice identification, and never a second independent recording. Output is written losslessly to a NEW file; the source transcript is never modified. When audio or acoustic turns exist, use /speaker-attribution instead. Invoke as /speaker-attribution-text [session-dir].
tools: Read, Bash, Glob, Grep, Write, AskUserQuestion
---

# Text Speaker Attribution

Turn a speakerless transcript into a useful attributed working copy by reading
the conversation in context and comparing labeled reference sessions. This
captures the workflow used for Obelisk session 001 when its Zoom transcript was
missing. The roster, character ownership, and reference paths are **inputs** —
do not carry that session's identities into another campaign.

Use this skill when the user wants approximate attribution from text. If they
want acoustic verification and have audio or acoustic turns, use
`/speaker-attribution`. A summary supplies story context, not a second
recording and not independent speaker evidence. Describe text-derived labels as
inferences even when the user accepts them for use.

## Establish the inputs and intended use

Inspect the supplied session and reference directories with `rg --files`. Reuse
the user's participant names, GM identity, player/character ownership, chosen
references, and prior rulings. Count physical people, **including the GM**; one
person may voice several NPCs and party members. Do not insist on a missing
Zoom file or audio when text inference is already the requested approach.

Choose the output mode from the user's instructions:

- **Provisional** — write named proposals with qualitative confidence. Keep
  `UNKNOWN` or `MIXED` where a single name is not useful. Review is optional;
  if the user wants one, prioritize the meaningful ambiguous exchanges.
- **Best guess accepted for use** — when the user says to use best judgment,
  finish the guesses, or dismisses the remaining uncertainties, assign every
  cue to the most plausible person. Do not request another attribution approval
  or leave unknown labels solely because the evidence is weak. Keep weak
  assignments at low confidence and record the user's authorization.

Request missing facts only if the available context cannot support useful
progress. Do not require a mode questionnaire. Acceptance of approximate
attribution is not confirmation of every identity, and does not authorize new
spelling or canon changes in a separate workflow.

## Prepare a traceable source

Select **one** original labeled transcript per reference session. Cleaned
copies, retranscriptions, concatenated copies, and generated summaries are not
additional independent evidence. Record source paths and hashes. Check that the
references concern the same people; similarly named anonymous clusters across
sessions do not establish identity.

The bundled helper provides a cue manifest and a lossless output writer. It
uses only the standard library. Create a unique scratch directory and use a
speakerless source:

```bash
SKILL_DIR=~/.claude/skills/speaker-attribution-text
python3 "$SKILL_DIR/scripts/attribution.py" prepare \
  --source "$SOURCE" --speaker Kostadis --speaker Nikhil \
  --reference "$REFERENCE_002" --reference "$REFERENCE_003" \
  --context "$SUMMARY" --output "$RUN/decisions.json"
```

Use the actual roster and paths. `--reference` and `--context` are optional and
repeatable. The helper supports **WebVTT only**; for Markdown or another
format, follow the same workflow with an appropriate lossless writer. Auditing
existing labels needs an explicit relabeling procedure, not nested speaker
prefixes.

## Build reference evidence

Read [evidence.md](references/evidence.md) for normalization, the optional text
classifier used in the original run, and concrete attribution traps.

Normalize known export labels to short human names with an explicit mapping.
Exclude screen-share channels and unidentified bins from training. Inspect
representative exchanges by each person across sessions — ordinary questions,
explanations, action declarations, corrections, acknowledgments. Record
examples with their source and timestamp. Learn recurring phrasing and
interaction habits; do not turn phrases into identity rules.

A word/character TF-IDF classifier can supply secondary style hints when there
are enough labeled examples. It is optional: missing dependencies or sparse
references must not block contextual work. **Its score is not the probability
that a cue belongs to that person.** Verify across whole held-out sessions when
reporting its performance; do not present reference-label agreement as accuracy
on the target transcript.

## Read and assign the whole conversation

Read every target cue in order, in manageable chunks with overlapping context.
Keep stable one-based cue indices across chunks. Use the summary to locate
scenes and understand who is present, but use the transcript for actual speech.

- Start from strong contextual anchors: a GM setting a scene, a player choosing
  an action, an addressed question with its answer, explicit self-reference.
- Carry continuity across adjacent fragments that form one utterance. Cue
  boundaries and alternating lines are not speaker changes.
- Attribute quoted NPC speech to the person voicing it. First-person character
  dialogue is not automatically the owner of the main PC. GM explanations,
  sidekick turns, rules talk, and map troubleshooting can all sound
  player-like.
- Treat short replies — "yeah", "okay", "I know" — as weak evidence. Resolve
  them from the nearby exchange in best-guess mode, retaining low confidence
  even if a style classifier strongly prefers one person.
- For an apparent within-cue speaker change, preserve all words and the
  existing span. In provisional mode use `MIXED` if helpful. In accepted
  best-guess mode choose the apparent dominant speaker and set
  `possible_mixed: true`; do not invent split timestamps or imply all the words
  were certainly spoken by one person.
- Override style hints when scene or conversational evidence is stronger. Check
  surprising runs and transitions, but do not force a balanced split — the GM
  may legitimately dominate a two-person session.

Fill each manifest cue's `speaker`, `confidence`, and `evidence_note`. Use
`high`, `medium`, `low`, or `unresolved` as qualitative textual confidence.
Keep factual scene context, speaker candidates, and model hints distinct.
Record character ownership and reference observations in `method_notes` or
additional manifest fields. Do not alter the source fields or cue text.

## Write, verify, and hand off

For accepted best guesses, set `mode` to `best_guess`, copy or accurately
summarize the user's instruction into `authorization`, and set
`review_required: false`. Leave `gm_confirmed: false` unless the GM actually
confirmed that cue — the helper distinguishes acceptance for use from identity
confirmation.

```bash
python3 "$SKILL_DIR/scripts/attribution.py" render \
  --decisions "$RUN/decisions.json" \
  --output "$SESSION/transcript.speakers.vtt" \
  --record "$SESSION/speaker_attribution_text/attribution.json"
```

Use `.speakers.provisional.vtt` for a draft. **Both output paths must be new.**
The helper rejects stale input hashes, missing or duplicate cue assignments,
unrecognized people, altered dialogue, and unresolved labels in best-guess
mode. It verifies exact source-byte recovery after removing only its inserted
NOTE and speaker prefixes — cue identifiers, settings, numeric-only dialogue,
multiline payloads, and original line endings included.

If the user wants to review ambiguous cues in a batch rather than in chat, use
the shared review artifact
(`~/.claude/skills/_shared/review-artifact/CONTRACT.md`) — one page for the
run, published with `capabilities: {"artifact": {}}`, then stop and wait for
the save. A review page must never reintroduce a checkpoint the user has
already waived: in accepted best-guess mode there is nothing to gate, so offer
the page only as a record or for the genuinely ambiguous subset.

Preserve original transcripts, summaries, and reference files. Keep corrections
and prose smoothing in their own passes. Save source/reference hashes, method,
authorization, cue-level confidence and reasons, possible mixed cues, counts,
and verification alongside the attributed VTT. If earlier drafts exist,
identify the current working transcript clearly and mark old review artifacts
historical in the handoff. Report the file, speaker totals, and that
attribution is **inferred from text**. Do not launch extraction or narration
unless already requested.
