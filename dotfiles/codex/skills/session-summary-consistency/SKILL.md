---
name: session-summary-consistency
description: Quote-level consistency check on scene_extractions_new/ or scene_extractions/ for VTT transcription errors, garbled phrases, proper-noun misspellings, and clarity issues in verbatim quote blocks. Use when the user asks for /session-summary-consistency [session-dir].
metadata:
  short-description: Check scene quote transcription consistency
---

# Session Summary Quote Consistency Check

Check the verbatim quote blocks in `scene_extractions_new/` or
`scene_extractions/` for VTT transcription errors, garbled phrases, proper-noun
misspellings, and pronoun or clarity issues. Propose fixes before touching
anything; apply only fixes the user approves.

This skill is quote-level only. It does not check scene summaries for canon
facts, mechanical accuracy, or prose quality, except for player-name scrubs
described below. It restores what was said, meaning it fixes transcription
errors; it does not smooth grammar, style, or voice. For higher-level campaign
consistency, use `consistency-check`. For VTT cleanup before extraction, use
`vtt-spell-pass` if available. Voice-aware sentence smoothing belongs to the
narration layer, not here.

This is the Codex port of the Claude skill. Do not edit
`~/src/mytools/dotfiles/claude/skills/session-summary-consistency/` when
changing this skill.

## Codex Compatibility

- Ask user questions in chat. Do not refer to Claude `AskUserQuestion`.
- Use `update_plan` for multi-step progress when useful.
- Use `apply_patch` for manual edits to tracked documents.
- Codex does not have the Claude Artifact review callback flow. If the user asks
  for batch review, write a normal Markdown or JSON review queue file in the
  session directory or present the queue in chat, then ask the user to provide
  decisions in chat.
- Do not apply edits merely because the workflow found likely fixes. User
  approval is the gate.

## Inputs

- `session-dir`: the `summaries/YYYYMMDD/` directory to check. Default to CWD
  only when it is already a session directory. If CWD is a campaign root, ask
  which session to use or choose the most recent `summaries/*/` that has a scene
  extraction directory.
- Scene files are in `<session-dir>/scene_extractions_new/` or
  `<session-dir>/scene_extractions/`. Detect whichever exists and call it
  `<scene-dir>`.
- Corrections glossary is at
  `<campaign-root>/notes/vtt_transcription_corrections.md`.

## Workflow

### 1. Locate Files

Find the scene extraction directory:

```bash
ls <session-dir>/scene_extractions_new/ 2>/dev/null || ls <session-dir>/scene_extractions/
```

If neither exists, tell the user and stop. Scene files are expected to be named
`NN_<slug>.md` and contain `## Verbatim moments` sections.

Walk up from `session-dir` to find the campaign root, usually the directory that
contains `notes/vtt_transcription_corrections.md`. Read that glossary; it is the
primary reference for known proper nouns and mishearing patterns.

Also check for `docs/entity_registry.yaml` or `docs/entity_inventory.md` at the
campaign root. The glossary documents mishearing patterns; the registry is the
identity authority for canonical spelling, aliases, and known entities. Use both
when a name-like garble's referent is uncertain.

### 2. Read Scene Files

Read every `*.md` in `<scene-dir>`. For each file:

- Extract every quote block under `## Verbatim moments`, usually lines inside
  Markdown blockquotes.
- Note the scene filename, line number, and speaker label above each quote.
- Sweep speaker labels and `## Scene summary` prose for player-name leaks.

Do not quote-correct or reword `## Scene summary`. The only exception is the
player-name scrub rule below. If a summary-level garble cannot be safely scrubbed
as a name replacement, flag it as an upstream scene-extract issue rather than
rewriting the summary.

### 3. Classify Quote Problems

For each quote problem, classify it:

| Category | Meaning | Action |
|---|---|---|
| VTT mishear | Single word or name is phonetically garbled and the correction is clear | Replace with corrected word |
| Proper noun error | Name is misspelled and canonical form is known | Replace with canonical form |
| Garbled phrase | Multi-word phrase is scrambled but meaning is reconstructable | Replace with reconstruction and bracket uncertain words |
| Unrecoverable | No reconstruction is possible | Replace with `[inaudible]` or `[inaudible -- probable "X"]` if a guess exists |
| Grammar/pronoun error | Wrong pronoun, article, or verb changes meaning | Replace with correct form |
| Duplicate across scenes | Same garbled line appears in multiple scene files | Flag each instance for the same fix |

Cross-reference rules:

- Check every proper noun in a quote against the glossary. If a name appears in
  a wrong-form column, consider the paired canonical correction.
- Context overrides the glossary for identity. The same garble can map to
  different names in different scenes, so confirm against the scene summary,
  surrounding dialogue, and entity registry before applying.
- Watch for glossary-substitution artifacts where an earlier replacement left
  doubled reads or false choices, such as the same referent appearing as both
  sides of an "X or Y" phrase.
- Do not assume a suspicious name variant is an authentic nickname. Check the
  registry, glossary nickname entries, and DO-NOT-CORRECT list first. If neither
  corroborates it, surface it for user ruling.
- Once a garble is confirmed, search the whole scene set for phonetically
  similar variants before calling the fix complete.
- Use the scene summary as ground-truth paraphrase for meaning, not exact
  wording.
- Use surrounding dialogue to resolve garbled phrases.

Speaker label and player-name rule:

- Speaker labels must use the character name or `GM`, never the player's real
  name.
- Use the campaign's own glossary `## Player names -> characters` section for
  the mapping. Do not hardcode player names; they vary by campaign.
- Label format varies across scenes, including `[GM]`, bold names, or other
  Markdown forms. Sweep every scene's labels before producing the report.
- Apply the same player-name scrub to `## Scene summary` prose. This is a name
  replacement, not a summary rewrite.
- Player names inside verbatim quote content may be left as-is when they are
  actual out-of-character table speech, but flag them as observations for the
  user.

Do not change:

- Genuine speech disfluencies, repetitions, false starts, `um`, or `uh`.
- Grammar, run-ons, or phrasing that reflect how someone actually spoke.
- Profanity or table vocabulary.
- Clearly marked out-of-character crosstalk.
- Numbers, dice results, or mechanics unless the transcription is plainly wrong
  and evidence settles it.
- Speaker attribution without user confirmation. Flag suspected attribution
  errors as notes.

### 4. Produce a Proposal Report

Group findings by scene file. For each issue, show:

```markdown
**Scene N - `filename.md`**

Line <N> - [Category] ([Speaker])
> Original: "quoted text with the problem"
> Proposed: "corrected text"
Reason: one sentence explaining the correction.
```

Include a summary table:

| Category | Count |
|---|---:|
| VTT mishear | N |
| Proper noun error | N |
| Garbled phrase | N |
| Unrecoverable -> [inaudible] | N |
| Grammar/pronoun | N |
| Duplicate across scenes | N |

Present the report in chat unless it is too large. For a large report, write it
to `<session-dir>/quote_consistency_review.md`, summarize counts in chat, and
ask the user whether to approve all, approve selected item ids, reject all, or
discuss specific items.

### 5. Wait for User Approval

After presenting the report, ask:

> Want me to apply all of these, or go through them selectively?

Supported responses:

- `apply all`: apply every proposed fix.
- `selective`: walk through the report item by item and apply only confirmed
  fixes.
- Item ids or ranges: apply only those accepted ids, and leave the rest.
- `none` or `just the report`: stop without editing.

### 6. Apply Fixes

For each approved fix, use `apply_patch` with enough surrounding context to make
the edit unique. If the exact string cannot be found because the file changed,
search for the current line and retry with fresh context.

After edits, verify that original target strings no longer remain:

```bash
grep -rn "<original garbled string>" <scene-dir>/
```

Any remaining hits mean a fix was missed or a duplicate variant exists. Inspect
and either apply the approved fix or report why it remains.

### 7. Feed Confirmed Garbles Back to the Glossary

After approved fixes are applied, identify new VTT patterns not already in
`notes/vtt_transcription_corrections.md` and ask:

> Found N new VTT patterns not yet in the glossary. Want me to add the safe ones?

Only add safe, non-word garbles. Real English words are context-dependent and
must not become global replacements because the applier is case-insensitive
across the whole transcript.

Safe examples:

- `glabbagel -> Glabbagool`
- `Ragum -> Grygum`
- `Hulkrist -> Alkrist`
- `Demonor('s) -> Deneir('s)`
- `Fembrance -> Fembris`
- `graffled -> grappled`
- `stinge -> singe`

Unsafe examples:

- `teeth -> tea`
- `high -> ki`
- `fake -> point`
- `snake -> sneak`
- `allowed -> Avowed`

Append only user-approved safe pairs to the appropriate glossary section. If the
user confirms a suspicious variant is authentic table speech or a nickname, add
it to the glossary's DO-NOT-CORRECT area instead of the garble table.

## Batch Review Queue

Use this when the report is too large for comfortable chat adjudication or the
user asks for a batch review artifact.

Create a review queue file such as
`<session-dir>/quote_consistency_review.json` or
`<session-dir>/quote_consistency_review.md`. Keep the shell/chat summary
visible with per-scene counts and category totals.

Use stable ids like `s03-04`: scene number, then the finding number within that
scene. Include:

```json
{
  "id": "s03-04",
  "file": "scene_extractions_new/03_example.md",
  "line": 120,
  "category": "VTT mishear",
  "speaker": "Brewbarry",
  "original": "Brube's world",
  "proposed": "Brewbarry's world",
  "reason": "The alternate transcript and surrounding dialogue identify Brewbarry.",
  "evidence": "Summarize supporting evidence without long transcript quotes."
}
```

Then stop and ask the user to provide decisions in chat. Map decisions this way:

| Decision | Action |
|---|---|
| approve | Apply with `apply_patch`, then run verification grep |
| reject | Leave the quote as transcribed and log the ruling |
| discuss + note | Follow the note; confirmed coinages go to DO-NOT-CORRECT |
| discuss without note | Bring the item back to chat for ruling |
| unmarked | Leave unchanged and mention it in the summary |

Auto-apply only after explicit user approval. Even in a batch queue, do not
silently edit files based on confidence.

## Conventions

- Bracket notation for preserved artifacts:
  `[Corrected form; VTT: "original garbled text"]`.
- Inaudible tag: `[inaudible]` for total loss;
  `[inaudible -- probable "X"]` when context suggests a likely word.
- Unclear tag: `[unclear -- possibly "X" or "Y"]` when two interpretations are
  equally plausible and the distinction matters.
- A quote can be garbled while the summary's paraphrase is accurate. Fix the
  quote to match the intended speech, not to copy the summary wording.
- This skill does not update session-summary or gm-assist docs. Flag any
  upstream errors as out-of-scope observations.
