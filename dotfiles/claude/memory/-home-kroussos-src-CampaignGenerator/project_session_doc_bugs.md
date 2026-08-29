---
name: session_doc.py known bugs and fixes
description: Running log of bugs found and fixed in session_doc.py --by-scene pipeline
type: project
---

# session_doc.py — Bug Log

All bugs below were found during live testing of the `--by-scene` pipeline on the Phandalin campaign (session-mar, 2026-03-21).

---

## Bug 1: Wrong model hard cap caused consistent cutoffs
**Symptom**: Narration cut off mid-sentence at roughly the same place every run regardless of `max_tokens`.
**Root cause**: Default model `claude-sonnet-4-20250514` has an 8192 output token hard cap. Setting `max_tokens=12000` was silently clamped to 8192, which the model filled exactly.
**Fix**: Changed default model to `claude-sonnet-4-6` (64K output).

---

## Bug 2: parse_plan only handled `## Section N`, not `## Scene N`
**Symptom**: `--by-scene` only generated one character (last narrator in the plan).
**Root cause**: `re.split(r"(?m)^## Section \d+", ...)` didn't match `## Scene 1` headings from `PLAN_SCENE_SYSTEM`. Entire plan parsed as one block; only the last narrator/chunks/focus lines survived.
**Fix**: Changed regex to `(?:Section|Scene)`.

---

## Bug 3: Plan assigned NPC as narrator (Xanth)
**Symptom**: Plan contained `narrator: Xanth` even though he's not in `--characters`.
**Root cause**: Prompt said "every character must appear at least once" but didn't say "only use characters from the roster."
**Fix**: Added explicit instruction "Use ONLY characters from the Available narrators list. Never assign a scene to an NPC."
**Runtime check**: Added warning if any narrator in the parsed plan is not in `--characters`.

---

## Bug 4: Plan dropped final scene (Carving a Path)
**Symptom**: The last scene in the session was consistently absent from the plan.
**Root cause**: Scene checklist was extracted from `structured_sections` (pass 2 output), which sometimes produced only Memorable Moments and Consistency Notes with no `### ` scene headings.
**Fix**: Extract checklist from `## Scenes` section of the original recap, which always has `### Scene Name` headings. Pass this as "Session Scenes (every scene must appear in your plan)" to pass 3.

---

## Bug 5: Overlap warning fired on normal 2+2 distribution
**Symptom**: Warning fired for every run with 4 characters and 2 chunks (e.g. Brewbarry chunk 1, Soma chunk 1).
**Root cause**: Warning condition `len(overlap) > 1 or (overlap and a_range == b_range)` triggered when two characters shared a single chunk.
**Fix**: Changed to `overlap and (len(a_range) > 1 or len(b_range) > 1)` — only warn when at least one range spans multiple chunks.

---

## Bug 6: Characters covered entire session instead of their chunk (chunk mode)
**Symptom**: All four characters narrated the full session instead of their assigned portion.
**Root cause**: PLAN_SYSTEM was too permissive about overlap. Valphine got chunks 1-2 AND Vukradin got chunk 2, so both narrated the full mountain journey.
**Fix**: Rewrote overlap rule: "A character may span two chunks ONLY when their single most important moment straddles the boundary. Two characters with overlapping ranges will both narrate all events in the overlap — avoid it."

---

## Bug 7: Scenes 6-9 all over-narrated the full mountain journey (scene mode)
**Symptom**: Each of scenes 6-9 (Stone Giants, Glacier, Carver's Path, Drake) narrated all of chunk 2 instead of just their scene.
**Root cause 1**: `parse_plan` bug (Bug 2) — only one section was parsed, so all chunk 2 content went to Vukradin.
**Root cause 2**: Even after fix, extraction prompt received the full chunk (all scenes visible). "Extract ONLY from scene X" instruction was ignored because the model could see all scenes.
**Fix**: In scene mode, `build_char_extract_prompt` sends only the named scene's text from the recap as the scope boundary, plus the full roleplay extractions for dialogue. The model can see the scene's exact content but not adjacent scenes.

---

## Bug 8: No dialogue in scene-mode narration
**Symptom**: After Bug 7 fix, narration had no verbatim dialogue quotes.
**Root cause**: Extraction was sending ONLY the recap scene text. The recap has structured summaries ("Vukradin uses intimidation") but no verbatim quotes. The VTT roleplay extractions were no longer included.
**Fix**: Send both: recap scene text as scope boundary (labelled "Scene scope: defines what belongs here") AND full chunk roleplay extractions (labelled "Roleplay Extractions: verbatim dialogue — primary source for quotes").

---

## Bug 9: Narrator omitted other characters' actions (witness problem)
**Symptom**: Brewbarry's narration of "Carving a Path" omitted Soma's druid action to reshape the mountain.
**Root cause**: Extraction system prompt said "pull out every moment from {narrator}'s perspective" — interpreted as "only Brewbarry's own actions", not what he witnessed.
**Fix**: Added to extraction system prompt: "Capture everything {narrator} witnessed — their own actions AND what other characters did."

---

## Bug 10: Over-narration / bleeding into adjacent scenes (narration pass)
**Symptom**: Narration described events from adjacent scenes even after extraction was scoped correctly.
**Root cause**: Narration system prompt constraint was too soft ("do not extend into adjacent scenes"). Model treated it as advisory.
**Fix**: Replaced with three explicit stop rules: "STOP when this scene ends. Do not continue into what happened next. Do not summarise what came before. Do not foreshadow what comes after." Plus a concrete test: "If you find yourself describing a new location or the next event, you have gone too far — stop."
Also reduced `max_tokens` from 3000 → 1500 for scene narration (2-3 paragraphs needs ~600-800 tokens, not 3000).

---

## Current status (2026-03-21)
- `--by-scene` pipeline produces correctly scoped per-scene narration
- Scenes are correctly taken from the recap's `## Scenes` checklist
- All characters appear in both chunks
- Verbatim dialogue is present
- `--dry-run` available to inspect pass 4 prompts before spending tokens
- `--verbose` available to print all prompts at runtime
- `--plan-file` available to supply a hand-edited plan and skip pass 3
- `--narrator NAME` available for single-character voice tweaking

## Still to test / watch for
- Whether the two-source extraction (recap scope + VTT dialogue) correctly scopes dialogue to the right scene when the same dialogue appears in multiple scene extractions
- Whether 1500 token limit for narration is enough for dialogue-heavy scenes (may need 2000)
