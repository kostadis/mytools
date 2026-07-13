---
name: session-summary-consistency
description: Quote-level consistency check on scene_extractions_new/ — flags VTT transcription errors, garbled phrases, and clarity issues in verbatim quote blocks, then proposes corrections for user approval. Invoke as /session-summary-consistency [session-dir].
tools: Read, Bash, Edit
---

# Session Summary Quote Consistency Check

Check the verbatim quote blocks in `scene_extractions_new/` for VTT transcription errors, garbled phrases, proper-noun misspellings, and pronoun/clarity issues. Propose all fixes before touching anything; apply only on user approval.

This skill is **quote-level only** — it does not check scene summaries, canon facts, or mechanical accuracy. It restores *what was said* (fixes the transcriber's errors); it does **not** smooth grammar or voice. For higher-level consistency (facts against campaign state), use `/consistency-check`. For VTT cleanup before extraction, use `/vtt-spell-pass`. Voice-aware sentence smoothing belongs to the **narration** layer (`session_doc` + `/voice-critic`), not here.

## Inputs

- **session-dir** — the `summaries/YYYYMMDD/` directory to check. Default: CWD — but CWD is often the campaign root, not a session dir. If so, ask which session (or use the most recent `summaries/*/` that has a scene-extraction dir).
- Scene files are in `<session-dir>/scene_extractions_new/` **or** `<session-dir>/scene_extractions/` — the suffix varies by pipeline version. Detect whichever exists and call it `<scene-dir>`.
- Corrections glossary is at `<campaign-root>/notes/vtt_transcription_corrections.md`.

## Workflow

### 1. Locate files

```bash
ls <session-dir>/scene_extractions_new/ 2>/dev/null || ls <session-dir>/scene_extractions/
```

Use whichever of `scene_extractions_new/` / `scene_extractions/` exists (the suffix varies by pipeline version) and treat it as `<scene-dir>` throughout. If neither exists, tell the user and stop. Scene files are expected to be named `NN_<slug>.md` and must contain `## Verbatim moments` sections.

Walk up from `session-dir` to find the campaign root (the directory containing `notes/vtt_transcription_corrections.md`). Read the glossary — it defines canonical forms for all known proper nouns and is the primary reference for this check.

### 2. Read all scene files

Read every `*.md` in `<scene-dir>`. For each file:

- Extract every quote block (lines inside `> "..."` under `## Verbatim moments`)
- Note the scene filename and the speaker label above each quote

Do not quote-correct or reword the `## Scene summary` section — its wording and facts are out of scope. **One exception (learned the hard way):** apply the player-name scrub to it too — see the speaker-label rule below. The summaries leak the GM's real name (`Kostadis laid out three options…`) and can carry Otter garbles (`go to "LI"` → A'lai).

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
- **Context overrides the glossary for name identity.** The same garble can map to *different* names in different spots — e.g. `Alley`/`Alle` phonetically matches the glossary alias for **A'lai**, but the scene summary made one instance clearly **Alkrist** ("…didn't realize what was going on"). Never blind-apply a glossary alias to a name-garble; confirm against the summary and surrounding dialogue, and surface identity calls for the user to rule on.
- **Watch for glossary-substitution artifacts.** A prior `wrong → right` mapping can leave doubled/redundant reads downstream — e.g. `Semenor`/`Fembidor → Fembris Lancer` produced "one of **Fembris Lancer** or, **Fembris Lancer**" and "**Fembris Lancer**, sorry, **Fembris Lancer**." Reconstruct these to a single clean form.
- Use the scene summary (verbatim in the same file) as a ground-truth paraphrase — if a quote's meaning is unclear, the summary often reveals what was intended.
- Use surrounding dialogue as context for garbled phrases.

**Speaker label rule — player names never appear:**
Speaker labels must always use the **character name** (or `GM`), never the player's real name (full or partial). **Use the campaign's own glossary `## Player names → characters` section for the mapping** — do not hardcode names, they differ per campaign (Out of the Abyss: `Joe → Thorin`, `Gabe → Zalthir`, `Mike → Daz`, `Ben → Grygum`, `Kostadis (Roussos) → GM`).

Two things this pass revealed:
- **Label FORMAT varies across scenes** — some use `[GM]`, others bold `**Name**`. Sweep for the real name in *any* format (one scene labelled the GM `**Kostadis Roussos**` 47× while its siblings used `[GM]`).
- **Sweep every scene's labels** before producing the report; a single scene can leak the real name even when the others are clean.
- **Scrub player names from the `## Scene summary` prose too, not just the labels.** The summaries leak the GM's real name (`Kostadis laid out three options…`, `per Kostadis`, `Kostadis:`) and Otter garbles (`go to "LI"` → A'lai). Apply the same name → character/GM scrub to the summary text (it's a name replacement, not a quote rewrite) and **flag** any garble you can't safely scrub — its true source is gm-assist / the scene-extract step, so it needs an upstream fix (and will otherwise reappear on the next extraction). Everything else in the summary stays untouched.

Player names inside verbatim quote *content* (e.g. a PC addressing the player OOC) may be left as-is, but flag them as an observation.

**What NOT to change:**
- Genuine speech disfluencies (repetitions, false starts, "um/uh") — these are authentic VTT captures and have value for voice files
- **Grammar and sentence structure.** Do NOT "clean up" a player's actual grammar, run-ons, or phrasing — not even to improve readability, and not even using the voice files. The verbatim quote is a *record*, and it is the raw material the voice files are built from; grammar-smoothing it here would erase the very evidence that calibrates them (and mutate a record that should stay raw). Voice-aware smoothing is the **narration** layer's job — `session_doc` renders the quotes into voice-appropriate prose on a *derived* copy, and `/voice-critic` checks that prose against the voice spec. Restore what was *said*; leave *how they said it* alone.
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
grep -rn "<list of original garbled strings>" <session-dir>/<scene-dir>/
```

Any remaining hits mean an edit was missed — investigate and retry.

### 7. Feed confirmed garbles back to the glossary (the vtt-spell-pass loop)

This pass catches classes that `vtt-spell-pass`'s deterministic scanner structurally **cannot** — lowercase name-garbles (`glabbagel`), sentence-initial one-offs it filters out (`Ragum`, `Dorin`, `Hulkrist`, `Demonor`, `Fembrance`), and meaning-dependent real-word swaps (`fake`→point, `teeth`→tea). So it is the natural place to grow the glossary. After the user approves fixes, offer:

> "Found N new VTT patterns not yet in the glossary. Want me to add the safe ones?"

**Only add SAFE (non-word) garbles.** A wrong-form that is a real English word will over-replace, because the applier runs case-insensitively across the whole transcript:
- ✅ Safe (not real words): `glabbagel → Glabbagool`, `Ragum → Grygum`, `Hulkrist → Alkrist`, `Demonor('s) → Deneir('s)`, `Fembrance → Fembris`, `graffled → grappled`, `stinge → singe`, `abald → Avowed`.
- ❌ Do **not** add: `teeth → tea`, `high → ki`, `fake → point`, `snake → sneak`, `allowed → Avowed` — these are real words; a global replacement corrupts legitimate uses. They are inherently this pass's (context-aware) job, not the scanner's.

Append the safe pairs to the appropriate section of `notes/vtt_transcription_corrections.md`. This closes the loop: what this pass confirms once, `vtt-spell-pass` applies automatically next session.

## Conventions

- **Bracket notation for preserved artifacts**: when the VTT text is kept for reference but a correction is applied alongside it, use `[Corrected form; VTT: "original garbled text"]`.
- **Inaudible tag format**: `[inaudible]` for total loss; `[inaudible — probable "X"]` when context suggests a likely word but confirmation would require audio review.
- **Unclear tag**: `[unclear — possibly "X" or "Y"]` when two interpretations are equally plausible and the distinction matters.
- The scene summary is ground truth for the *meaning* of a quote, not for the *wording*. A quote can be garbled while the summary's paraphrase is accurate — fix the quote to match the intent, not to copy the summary's wording.
- Do not change speaker attributions. If a quote appears under the wrong speaker, flag it as a note but do not re-attribute without user confirmation.
- This skill does not update the session-summary or gm-assist docs — those are upstream of the scene extractions. Flag any summary-level errors you notice as out-of-scope observations; the user can address them separately.
