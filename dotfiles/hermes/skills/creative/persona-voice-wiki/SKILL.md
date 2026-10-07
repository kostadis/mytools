---
name: persona-voice-wiki
description: Write persona-voiced cited wikis from digests.
---

# Persona-Voice Wiki Synthesis

## When to use
- The user hands you one or more **source digests / reports / transcripts** and asks for a wiki, codex, chronology, gazetteer, or "LLM-style" reference in a **specific persona's voice** (dry scholar, acerbic critic, in-world chronicler, etc.).
- They want opinions/commentary **in character**, but also want sources **checkable** (citations preserved).
- Typically yields **multiple files** (chronology, events, NPCs/figures) rather than one blob.

This is the *authoring/output* counterpart to `note-taking: corpus-digest` (which digests raw sources INTO a digest). Use both together when the user gives raw material and wants both a digest and a voiced wiki.

## Core discipline (the part that matters)
1. **Read every source fully before writing.** Do not skim. The connecting threads (causes, consequences, who profited) only appear after you hold all sources in mind.
2. **Preserve each source's citation convention VERBATIM.** If the digest cites as `[ch: chapter_01_x.md]`, `(chapter_01_x.md)`, and `(ch01)`, keep all three exactly. Never "normalize" them — a normalized citation is an unverifiable one. Match the format the digest actually uses so a reader can grep the chapter file.
3. **Hard wall between FACT and OPINION.**
   - Factual summary: neutral, no interpretation, **every load-bearing claim carries its citation**.
   - Opinion: a clearly-marked block (e.g. `**Historian's Assessment**`) written in the persona's voice, and **signed** with the persona's name (e.g. `— The Historian of Candlekeep`).
   - Flag source unreliability inside the opinion block: self-interested witnesses, single-chapter claims, convenient transformations the digest doesn't explain.
4. **Voice consistency across all files.** The persona's cadence, favorite phrases, and biases must read the same in chronology, events, and NPC files. Pick 2–3 mannerisms and reuse them.

## Step-by-step
1. Read all sources. Sketch the connecting threads (causal chains, shared villains, a single fraying age, etc.).
2. Choose the output shape. Common, reusable:
   - **Chronology** — unified annotated timeline in the given order, with commentary on causes/consequences/threads.
   - **Events** — 15–25 most significant events; each = factual summary (cited) + marked Assessment.
   - **NPCs/Figures** — 15–25 most consequential personages; each = factual summary (cited) + marked Assessment of role/legacy.
3. **Write large files in `/tmp` chunks, then concatenate.** For outputs >~3k words, write each section to `/tmp/<name>_partN.md` and `cat` them into the final path. Avoid one giant `write_file` call (write stalls / truncation risk). See `references/technique.md`.
4. **Sign every opinion block** with the exact persona string the user specified.
5. **Verify before reporting done** (see Verification). Report paths + word counts.

## Pitfalls
- Do NOT let the persona's opinion leak into the factual summary. If it's interpretive, it goes in the marked/signed block.
- Do NOT "clean up" or reformat source citations. Verbatim or it's worthless.
- Do NOT write one enormous file in a single `write_file`. Chunk it.
- Do NOT inflate event/NPC counts to hit a number — pick by *consequentiality* (causal weight, forces commanded, questions raised), and say so.
- The persona is a narrator, not a license to invent. Every fact still needs its citation.

## Verification (run before declaring success)
From the terminal, confirm each deliverable:
- File exists and has sane size: `wc -w <file>` and `wc -l <file>`.
- Citations present: `grep -c 'ch: chapter_\|(chapter_\|(ch[0-9]' <file>` (adapt regex to the source's actual conventions).
- Assessments present: `grep -c "Historian's Assessment" <file>` (should equal event/NPC count).
- Signoffs present: `grep -c '— The Historian of Candlekeep' <file>` (should match assessments + closing statements).
Mismatches mean a section was dropped during concatenation — rebuild that chunk.

## Support files
- `templates/event_entry.md` — skeleton for one event (heading + cited factual summary + marked Assessment + signoff).
- `templates/npc_entry.md` — skeleton for one figure.
- `references/technique.md` — the /tmp-chunk + concatenate + verify workflow with exact commands.
- `references/campaign_conventions.md` — a worked example: the per-campaign citation formats and 21-event/22-NPC structure used for a three-campaign D&D chronicle project.
