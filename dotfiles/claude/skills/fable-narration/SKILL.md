---
name: fable-narration
description: Write the full POV-rotating narrative session doc (session-summary-fable-doc.md) in a single pass, directly from scene_extractions_smoothed/ + the voice/ specs + examples/, with the recurring voice-critic findings (em-dash overuse, bookkeeping-noun caps, cross-narrator register bleed, banned portable tics) baked in as hard constraints up front rather than fixed after the fact. Invoke as /fable-narration [session-dir].
tools: Read, Bash, Write, Edit, Glob, AskUserQuestion
---

# Fable-Narration — one-pass, critic-constrained session narration

Write the assembled narrative session document **in one authored pass**, from the smoothed quote layer, with every recurring `/voice-critic` finding treated as a *writing constraint* instead of a post-hoc fix. The output is a sibling of the `session_doc.py` assembly (`session-summary-doc.md`), written to **`session-summary-fable-doc.md`** so the two can be compared side by side.

## Where this sits

```
VTT (raw verbatim — IMMUTABLE)
  → scene_extractions/            (/session-summary-consistency fixes transcription errors)
  → scene_extractions_smoothed/   (/voice-smooth renders quotes in-voice)
      → [THIS SKILL] fable-narration → session-summary-fable-doc.md
         (parallel path: session_doc.py per-scene narration → /voice-critic → hand-fix → assembly)
```

This is an **alternative render**, not a replacement for the pipeline: the smoothed layer and the VTT stay the record, and `/voice-critic` can still be run on the output as verification.

## Inputs

- **session-dir** — `summaries/YYYYMMDD/`. Default: CWD (if CWD is the campaign root, ask which session).
- **scene source** — `<session-dir>/scene_extractions_smoothed/` (fall back to `scene_extractions/` only if no smoothed layer exists — and say so, since unsmoothed quotes will read rougher).
- **structure/facts** — `<session-dir>/session-summary.md` (scene list, scene summaries, memorable moments) and, if present, an existing `session-summary-doc.md` (title, scene selection, narrator assignments — mirror them so the two docs are directly comparable).
- **voice guardrails** — `voice/_genre.md` (genre spec incl. banned tics + bookkeeping rules) and every `voice/<char>_voice.md`. **Authoritative. Read all of them before writing a single sentence.**
- **prose models** — `examples/<char>.md` per-character reference passages + verbatim VTT speech extracts.
- **prior critiques (optional but preferred)** — `<session-dir>/narration/voice_critique_*.md` and `voice_critique_summary.md`. If they exist, read them: they name the exact failure modes of the machine pass for *this* session, and the whole point of this skill is to not repeat them.

## Workflow

### 1. Load guardrails, then sources
Genre spec first, then each voice file + its examples file, then the critiques, then the smoothed scenes and session-summary. Do not start writing with only part of the voice set loaded — cross-narrator bleed comes from writing one voice while another is freshest in context.

### 2. Fix scene list and narrator assignments
- If `session-summary-doc.md` exists, mirror its scenes and `## <Character> — <Scene Name>` narrator assignments exactly.
- Otherwise: pick the story-bearing scenes (recaps and pure-logistics scenes usually drop), rotate POV so each PC narrates at least once and the narrator is the character with the most skin in that scene, and confirm the assignment with the user before writing.

### 3. Write each section
First-person past, one POV per section, `## <Character> — <Scene Name>` heading, `---` separators, loose paragraphing with single-line beats. Per section:
- **Dialogue fidelity:** spoken lines come from the smoothed quotes, near-verbatim. Don't invent dialogue; don't sanitize table profanity or signature phrases.
- **Table-level material** (map lag, dice talk, GM meta) is either rendered in-fiction from the POV's frame (the map stretching → running at magical speed; the whispering-gallery request → the narrator noticing the acoustics) or dropped — never narrated as table events.
- **Mechanics live inside reaction** (spell names, damage, saves, focus points), per the genre spec's procedural-combat convention.
- **Thought-source intrusions:** at most one per scene, per that character's spec. Zalthir's monastery names must be *freshly invented each time* — check both this doc and the prior narration/doc for names already used.
- **Spec-signature lines** (Thorin's "quiet knock inside the chest", Zalthir's "filed it", aphorisms): reuse is good — the critic has repeatedly praised earned reuse — but at most once per doc each, in the scene where it does real work.
- Sweep the memorable-moments section of `session-summary.md` for strong beats the machine pass dropped, and work the good ones in.

### 4. The baked-in critic constraints (the point of this skill)
These are the findings `/voice-critic` flags on essentially every machine pass. Write to them; don't fix to them.

- **Em-dashes: near-zero at narration level.** Connective asides get colons, commas, or periods. Allowed exceptions only: VTT trailing-off inside quotes/notes (`*He is using the beast to—*`), interrupted speech inside quoted dialogue, and at most 1–2 genuinely load-bearing narration dashes in the whole doc (enacted hesitation, emphatic repetition). Section headings don't count.
- **Bookkeeping/recording metaphors — hard caps per the genre spec:**
  | Narrator | Cap | Vocabulary |
  |---|---|---|
  | Thorin | uses *clocked / noted / kept it*; **never files** | "Thorin filed it" is the canonical wrong answer |
  | Grygum | ONE per section | *took notes, filed, the column marked X* (filing is his) |
  | Daz | TWO per section max, **different nouns**, paragraphs apart | rotate *audit / tally / account / column / balance*; debt/collection talk is his native Menzo register and doesn't count against the cap |
  | Zalthir | rarely; at most one *filed it* in the whole doc | he watches, he doesn't tally |
- **Register separation:** terrain/position/geometry is Thorin's only. Analytical-structural vocabulary ("architecture", "geometry", "system") never goes to Daz or Zalthir. Each POV keeps its own lexicon even when describing the same event.
- **Banned portable tics — target zero across the doc:** "the shape of X"; "with the particular [noun] of [someone who…]" relative-clause portraits; "the cusp of something" / "what could only be described as"; narrator editorializing; adverb-heavy combat; recap framing.

### 5. Mechanical self-scan before presenting
Run the critic's cheap checks yourself:
```bash
grep -n "—" <out>.md          # expect: headings + protected trailing-offs only
grep -inE "filed|ledger|column|account|audit|tall(y|ied)|inventory" <out>.md   # check against the caps table
grep -inE "the shape of|the particular|the cusp of|could only be described" <out>.md  # expect empty
```
Fix violations before showing the user anything.

### 6. Output + human review
Write `<session-dir>/session-summary-fable-doc.md` (same title as the machine doc). Present a short summary of what was written, which critic constraints were applied, and any beats added or dropped relative to the machine pass. The human reviews before anything downstream consumes it; suggest `/voice-critic session-summary-fable-doc.md` as independent verification if wanted.

## Conventions

- **Voice files are authoritative**; examples files are prose models; the smoothed quotes are the record of what was said. When they conflict, quotes win on content, voice files win on rendering.
- **Never modify** the VTT, `scene_extractions/`, `scene_extractions_smoothed/`, or the machine-pass `session-summary-doc.md`/`narration/` files. This skill's only output is `session-summary-fable-doc.md`.
- **Fresh prose, not a paraphrase.** When a machine doc exists, match its structure for comparability but write new sentences — the value of the parallel doc is a genuinely independent render, not a light edit.

## Why this design

The critic's findings are stable across sessions (em-dash tic, clerk-convergence, register bleed) — which means they are cheaper to obey at write time than to detect and patch afterward. The house pattern still holds: the structure is human-verified upstream (consistency-checked extractions, human-reviewed smoothing, human-authored voice specs), this skill only *renders* inside it, and a human reviews the render before it feeds anything else.
