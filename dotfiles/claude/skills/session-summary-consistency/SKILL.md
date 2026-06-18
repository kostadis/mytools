---
name: session-summary-consistency
description: Quote-level consistency check on scene_extractions_new/ — flags VTT transcription errors, garbled phrases, and clarity issues in verbatim quote blocks, then proposes corrections for user approval. Invoke as /session-summary-consistency [session-dir].
tools: Read, Bash, Edit
---

# Session Summary Quote Consistency Check

Check the verbatim quote blocks in `scene_extractions_new/` for VTT transcription errors, garbled phrases, proper-noun misspellings, and pronoun/clarity issues. Propose all fixes before touching anything; apply only on user approval.

This skill is **quote-level only** — it does not check scene summaries, canon facts, or mechanical accuracy. For higher-level consistency (facts against campaign state), use `/consistency-check`. For VTT cleanup before extraction, use `/vtt-spell-pass`.

## Inputs

- **session-dir** — the `summaries/YYYYMMDD/` directory to check. Default: CWD.
- Scene files are in `<session-dir>/scene_extractions_new/`.
- Corrections glossary is at `<campaign-root>/notes/vtt_transcription_corrections.md`.

## Workflow

### 1. Locate files

```bash
ls <session-dir>/scene_extractions_new/
```

If the directory is missing, tell the user and stop. Scene files are expected to be named `NN_<slug>.md` and must contain `## Verbatim moments` sections.

Walk up from `session-dir` to find the campaign root (the directory containing `notes/vtt_transcription_corrections.md`). Read the glossary — it defines canonical forms for all known proper nouns and is the primary reference for this check.

### 2. Read all scene files

Read every `*.md` in `scene_extractions_new/`. For each file:

- Extract every quote block (lines inside `> "..."` under `## Verbatim moments`)
- Note the scene filename and the speaker label above each quote

Do not read or evaluate the `## Scene summary` section — that is out of scope for this skill.

### 3. Classify each quote problem

For each quote that has a problem, classify it into one of these categories:

| Category | What it means | Action |
|---|---|---|
| **VTT mishear** | Single word/name phonetically garbled — clear correction exists | Replace with corrected word |
| **Proper noun error** | Name misspelled — canonical form is in the glossary | Replace with canonical |
| **Garbled phrase** | Multi-word phrase scrambled but meaning reconstructable from context | Replace with reconstruction, bracket uncertain words |
| **Unrecoverable** | No reconstruction possible | Replace with `[inaudible]` or `[inaudible — probable "X"]` if a guess exists |
| **Grammar/pronoun error** | Wrong pronoun, article, or verb that changes meaning | Replace with correct form |
| **Duplicate across scenes** | Same garbled line appears in multiple scene files | Flag both instances for the same fix |

**Cross-reference rules:**
- Check every proper noun in a quote against the glossary. If a name appears in the "Wrong" column of any table, apply the "Right" correction.
- Use the scene summary (verbatim in the same file) as a ground-truth paraphrase — if a quote's meaning is unclear, the summary often reveals what was intended.
- Use surrounding dialogue as context for garbled phrases.

**Speaker label rule — player names never appear:**
Speaker labels must always use the **character name**, never the player's real name (full or partial). Check every speaker label in the file:
- `Wade Brown` / `Wade` → `Soma`
- `Stéphane Bourdeaud` / `Stéphane` → `Brewbarry`
- `Gary Young` / `Gary` → `Valphine` (or `Brewbarry` depending on who is speaking)
- `David Mendenhall` / `Dave` → `Vukradin`
- `Kostadis Roussos` → `GM`
Apply these as a sweep before producing the proposal report. Player names inside verbatim quote *content* (e.g. a PC addressing the player directly OOC) may be left as-is, but flag them as an observation.

**What NOT to change:**
- Genuine speech disfluencies (repetitions, false starts, "um/uh") — these are authentic VTT captures and have value for voice files
- Profanity — reproduce faithfully; "passes" → "asses" only when the correction is already in the glossary
- Out-of-character crosstalk that is already clearly marked as OOC
- Numbers and dice results, even if oddly phrased

### 4. Produce a proposal report

Group findings by scene file. For each issue, show:

```
**Scene N — `filename.md`**

Line <N> — [Category] ([Speaker])
> Original: "quoted text with the problem"
> Proposed: "corrected text"
Reason: one sentence explaining the correction.
```

Include a summary table at the end:

| Category | Count |
|---|---|
| VTT mishear | N |
| Proper noun error | N |
| Garbled phrase | N |
| Unrecoverable → [inaudible] | N |
| Grammar/pronoun | N |
| Duplicate across scenes | N |

Output the full report in the conversation. Do not apply any edits yet.

### 5. Wait for user approval

After presenting the report, ask:

> "Want me to apply all of these, or go through them selectively?"

- **"apply all"** — apply every proposed fix using the Edit tool, one per Edit call. Do fixes to different files in parallel; fixes within the same file sequentially.
- **"selective"** — walk through the report item by item and apply only what the user confirms.
- **"none"** / **"just the report"** — stop here.

### 6. Apply fixes

For each approved fix, use the Edit tool with enough surrounding context to make the old_string unique in the file. If the exact string cannot be found (file was edited between reading and applying), use `grep -n` to locate the current line, then retry.

After all edits, run a verification grep to confirm no target strings remain:

```bash
grep -rn "<list of original garbled strings>" <session-dir>/scene_extractions_new/
```

Any remaining hits mean an edit was missed — investigate and retry.

### 7. Update the corrections glossary (optional)

If any newly discovered VTT errors are not yet in the glossary, offer to add them:

> "Found N new VTT patterns not yet in the glossary. Want me to add them?"

If yes, append the wrong→right pairs to the appropriate section of `notes/vtt_transcription_corrections.md`.

## Conventions

- **Bracket notation for preserved artifacts**: when the VTT text is kept for reference but a correction is applied alongside it, use `[Corrected form; VTT: "original garbled text"]`.
- **Inaudible tag format**: `[inaudible]` for total loss; `[inaudible — probable "X"]` when context suggests a likely word but confirmation would require audio review.
- **Unclear tag**: `[unclear — possibly "X" or "Y"]` when two interpretations are equally plausible and the distinction matters.
- The scene summary is ground truth for the *meaning* of a quote, not for the *wording*. A quote can be garbled while the summary's paraphrase is accurate — fix the quote to match the intent, not to copy the summary's wording.
- Do not change speaker attributions. If a quote appears under the wrong speaker, flag it as a note but do not re-attribute without user confirmation.
- This skill does not update the session-summary or gm-assist docs — those are upstream of the scene extractions. Flag any summary-level errors you notice as out-of-scope observations; the user can address them separately.
