---
name: session-summary-consistency
description: Quote-level consistency check on scene_extractions_new/ — flags VTT transcription errors, garbled phrases, and clarity issues in verbatim quote blocks, then proposes corrections for user approval. Invoke as /session-summary-consistency [session-dir].
tools: Read, Bash, Edit, Artifact, AskUserQuestion
---

# Session Summary Quote Consistency Check

Check the verbatim quote blocks in `scene_extractions_new/` for VTT transcription errors, garbled phrases, proper-noun misspellings, and pronoun/clarity issues. Propose all fixes before touching anything; apply only on user approval.

This skill is **quote-level only** — it does not check scene summaries, canon facts, or mechanical accuracy. It restores *what was said* (fixes the transcriber's errors); it does **not** smooth grammar or voice. For higher-level consistency (facts against campaign state), use `/consistency-check`. For VTT cleanup before extraction, use `/vtt-spell-pass`. Voice-aware sentence smoothing belongs to the **narration** layer (`session_doc` + `/voice-critic`), not here.

## Inputs

- **session-dir** — the `summaries/YYYYMMDD/` directory to check. Default: CWD — but CWD is often the campaign root, not a session dir. If so, ask which session (or use the most recent `summaries/*/` that has a scene-extraction dir).
- Scene files are in `<session-dir>/scene_extractions_new/` **or** `<session-dir>/scene_extractions/` — the suffix varies by pipeline version. Detect whichever exists and call it `<scene-dir>`.
- Corrections glossary is at `<campaign-root>/notes/vtt_transcription_corrections.md`.

## Workflow

### 0. Choose the review mode

Before locating anything, one `AskUserQuestion`:

> **Review the proposed quote fixes in an artifact, or here in the shell?**
> - **Artifact** — one page for the whole run, mark the rulings at your own pace, save once.
> - **Shell** — the grouped proposal report and "apply all / selective", the way this skill has always worked.

Ask this every run; do not remember a default. In artifact mode the per-scene
counts and the summary table are still printed in the shell — they are the
at-a-glance summary — but the *rulings* move to the page. See **Artifact mode**
below.

### 1. Locate files

```bash
ls <session-dir>/scene_extractions_new/ 2>/dev/null || ls <session-dir>/scene_extractions/
```

Use whichever of `scene_extractions_new/` / `scene_extractions/` exists (the suffix varies by pipeline version) and treat it as `<scene-dir>` throughout. If neither exists, tell the user and stop. Scene files are expected to be named `NN_<slug>.md` and must contain `## Verbatim moments` sections.

Walk up from `session-dir` to find the campaign root (the directory containing `notes/vtt_transcription_corrections.md`). Read the glossary — it defines canonical forms for all known proper nouns and is the primary reference for this check.

Also check for `docs/entity_registry.yaml` (or `docs/entity_inventory.md`) at the campaign root. The glossary documents *mishearing patterns*; the registry is the *identity* authority — canonical spelling, aliases, and who's a registered entity at all. Use it alongside the glossary when a name-like garble's referent is uncertain (e.g. confirming a name is a real registered NPC and not a hallucination).

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
- **Watch for glossary-substitution artifacts.** A prior `wrong → right` mapping can leave doubled/redundant reads downstream — e.g. `Semenor`/`Fembidor → Fembris Lancer` produced "one of **Fembris Lancer** or, **Fembris Lancer**" and "**Fembris Lancer**, sorry, **Fembris Lancer**." Reconstruct these to a single clean form. The same duplication can disguise itself as a false two-option choice rather than a stutter — e.g. "if we have to prioritize the man or the bowl cut" and "we gotta save him and his bowl cut" both read as a person weighing two things, but "the bowl cut" was a mishearing of the *same* person's name (Tadric), not a second referent. Don't assume an "X and/or Y" construction is meaningful until you've checked whether Y is just X garbled.
- **Don't assume a suspicious name variant is an authentic nickname without checking.** A short, single-letter-swap variant of a PC's name can look enough like an established table nickname to wave through as color — compare "Grygumite," which *is* a real, recurring GM nickname for Grygum. "Gaz" for Daz and "Dad" for Daz looked the same way and weren't; they were plain mishearings, caught only after the GM corrected them post-hoc. Check the variant against the entity registry and the glossary's existing nickname entries before deciding it's intentional; if neither corroborates it, surface it as an open question rather than defaulting to "authentic quirk."
- **A garbled name can hide behind several different spellings of the same underlying mishearing, discovered one at a time across multiple passes.** `Bolkut` / `Boldcut` / `bald cat` / `bowl cut` / `bolt cut` were all the same ASR mishearing of **Tadric**, surfaced and corrected in separate rounds because each pass only searched for the specific spelling already flagged. Once a garble is confirmed, grep the *whole* scene set (not just the flagged file) for phonetically-similar variants before calling the fix done — the same underlying error rarely has just one spelling.
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

## Artifact mode (batch review)

Replaces the "apply all / selective" adjudication in step 5. Steps 1-4, the
apply step, the verification grep and the step-7 glossary loop are unchanged.
Full contract: `~/.claude/skills/_shared/review-artifact/CONTRACT.md`.

### One page for the run

Sequence: read every scene -> classify -> apply what needs no ruling -> print the
per-scene counts and summary table in the shell -> build -> publish -> **stop** ->
the save comes back -> read back -> apply -> verification grep -> offer the
glossary loop.

```bash
python ~/.claude/skills/_shared/review-artifact/build_review.py \
    --in  $SCRATCH/review_items.json --out $SCRATCH/review.html
```

The plain `review_items.json` is correct here: this skill publishes **one** page
per run, so there is no second build to overwrite it. `/staged-consistency`
publishes one per stage over the same URL and must suffix the name
(`review_items_stage<N>.json`) or it loses the earlier stages' card text — see
**File names** in the contract.

Publish with **`capabilities: {"artifact": {}}`**. Set the `eyebrow` to
`<campaign> · <chapter> · scene quotes`. Never poll for the save — the
`artifact-changed` notification or the GM's word, whichever arrives first.

### What is auto-applied, footer only

A quote fix needs no ruling only when **two independent transcripts agree on the
correction**, or the glossary/registry already settles it AND the surrounding
dialogue confirms the referent:

- Glossary/registry proper nouns whose corrected form is confirmed in a second
  transcript (`Helspergaster` -> House Margaster; `Brewerdin` -> Vukradin).
- Plain homophones with one possible reading (`and no true power` -> `and know
  true power`; `Constitution safe` -> `Constitution save`).
- Player-name scrubs in **speaker labels and scene summaries** (never inside
  quote content — that is a card).

Name the count and the files in the `footer`.

### What is always a card

- **Reconstructions.** Any fix where you are splicing two transcripts, or where
  both transcripts are garbled and you are proposing the intended words. Say in
  `ev` which transcript said what.
- **Identity calls.** A name-garble whose referent is uncertain, or that could
  map to more than one entity.
- **Possible authentic coinages.** A variant that might be a real table nickname
  or in-character malapropism rather than a mishearing — this campaign's
  DO-NOT-CORRECT list exists because that call was got wrong before
  (`find-us fee`, `Big Al`, `Orcanese`). Check the glossary's garble lists and the
  DO-NOT-CORRECT table first, and **say in `ev` that the check found no
  corroboration** rather than asserting it is an error.
- **Unrecoverable lines** where the choice is between `[inaudible]` and a
  bracketed guess.
- **Player names inside quote content** — step 3 says these may stand; whether
  they do is the GM's call, not yours.

### Card shape

Use `sNN-MM` as the id — scene number, then the finding's number within that
scene — so the shell counts and the page line up, and the apply step knows which
file to edit.

```json
{ "id":  "s03-04",
  "t":   "“Brube’s world” — mishearing, or Brewbarry’s own shortening?",
  "y":   "Correct to “Brewbarry’s world” in <code>03_....md</code>. The Zoom .txt renders the same line that way.",
  "n":   "Keep “Brube”. It is Brewbarry shortening his own name, and the glossary gains a nickname row.",
  "ev":  "The .txt has “that’s how it works in Brewbarry’s world” (1797). But <b>“Brube” is not in the glossary’s 50-variant Brewbarry garble list and not in DO-NOT-CORRECT</b>, so nothing corroborates it either way." }
```

### Verdict mapping

| verdict | action |
|---|---|
| **approve** | Apply with `Edit`, then run the step-6 verification grep |
| **reject** | Leave the quote as transcribed; log it |
| **discuss** + note | Follow the note. A note confirming a coinage is a **DO-NOT-CORRECT** row, not a garble row |
| **discuss**, no note | Back to the shell, grouped |
| **unmarked** | Undecided — leave the quote alone and say so in the summary |

After applying, run step 7 as usual — but only feed the glossary the **safe
non-word** garbles the GM approved, and route any confirmed coinage to the
DO-NOT-CORRECT table instead.

## Conventions

- **Bracket notation for preserved artifacts**: when the VTT text is kept for reference but a correction is applied alongside it, use `[Corrected form; VTT: "original garbled text"]`.
- **Inaudible tag format**: `[inaudible]` for total loss; `[inaudible — probable "X"]` when context suggests a likely word but confirmation would require audio review.
- **Unclear tag**: `[unclear — possibly "X" or "Y"]` when two interpretations are equally plausible and the distinction matters.
- The scene summary is ground truth for the *meaning* of a quote, not for the *wording*. A quote can be garbled while the summary's paraphrase is accurate — fix the quote to match the intent, not to copy the summary's wording.
- Do not change speaker attributions. If a quote appears under the wrong speaker, flag it as a note but do not re-attribute without user confirmation.
- This skill does not update the session-summary or gm-assist docs — those are upstream of the scene extractions. Flag any summary-level errors you notice as out-of-scope observations; the user can address them separately.
