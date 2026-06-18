---
name: staged-consistency
description: Run consistency checks at every LLM-pipeline boundary (gm-assist → session-summary → scene extractions → narration) with a human-review gate between stages. Use when the user invokes /staged-consistency [session-dir] and wants the multi-stage check rather than a one-shot. Prevents fix-propagation drift where stale per-scene quotes silently re-inject errors into the next narration run.
tools: Bash, Read, Edit
---

# Staged Consistency

Run the multi-stage consistency check pattern documented in `~/campaigns/STAGED_CONSISTENCY_HOWTO.md`. The pattern: a `check_consistency.py` run gated by a human-review/fix cycle at each LLM extraction boundary in the session-doc pipeline — gm-assist, session-summary, scene extractions, and (optionally) the final narration.

The point of this skill is to **catch verbatim transcription errors before they reach the narrator**. A single late-stage check misses the per-scene-quote layer, which is the layer that silently re-injects errors into every subsequent narration run. See `STAGED_CONSISTENCY_HOWTO.md` for the rationale.

## When to use this skill vs. the others

- `/consistency-check <file>` — one-shot check on a single file. Use when you already know which document needs checking.
- `/gmassist-precheck [session-dir]` — covers stage 0 → stage 1 only (gm-assist enrichment + check). Use when you only want the cheap pre-extraction pass.
- `/staged-consistency [session-dir]` — **this skill**. The full pipeline with checks at every boundary. Use when you're preparing a session-doc you'll share with players, or when a prior narration run produced output that doesn't match prep.

## Workflow

### 0. Locate the session directory and prep

If the user passed a path argument, use it. Otherwise:
- Run `pwd` to confirm CWD is a campaign workspace (contains `docs/`, `summaries/`, `config.yaml`).
- List recent session directories: `ls -t summaries/ | head -10`
- Ask: "Which session — pass the path under `summaries/` (e.g. `summaries/20260512`)?"

Then locate the prep file(s) for this session — this is non-negotiable, the same as in `/consistency-check`:

1. Look in `notes/session_prep/`, `notes/prep/`, `notes/sessions/`, `notes/<date>/`.
2. List candidates: `ls notes/session_prep/ 2>/dev/null; ls notes/prep/ 2>/dev/null`
3. **Ask the user explicitly**: "Which session prep file(s) should I fact-check against? Found: [list]. Or pass `none` if there is no prep for this session."

If the user says `none`, run the skill anyway but explicitly note in the final summary that the run was prep-less and will have missed transcription errors. Do not silently proceed without asking.

Hold the prep path list in the conversation — every stage's check uses it.

### 1. Inventory the pipeline artifacts in this session

Determine which stages exist:

```bash
SESSION=<session-dir>
ls "$SESSION"/gm-assist.md 2>/dev/null
ls "$SESSION"/session-summary.md 2>/dev/null
ls "$SESSION"/scene_extractions_new/0*.md 2>/dev/null | grep -v ".prev\|.scaffold"
ls "$SESSION"/narration/enhanced_sections.md 2>/dev/null
ls "$SESSION"/narration/*.md 2>/dev/null   # final narration if generated
```

Tell the user which stages were found and what will be checked. Some sessions may be partial — e.g. gm-assist + session-summary done but scene extractions not yet generated. Run the check on whatever exists; don't try to generate missing artifacts (that's the pipeline's job, not this skill's).

## Report format (mandatory at every stage)

After each stage's check, **always** present findings as a severity-ranked table before asking about fixes:

```
● Stage N complete — M issues in <filename>. Going 1x1?

  Quick preview:

  ┌─────┬──────────┬──────────────────────────────────────────────────────┐
  │  #  │ Severity │                        Issue                         │
  ├─────┼──────────┼──────────────────────────────────────────────────────┤
  │ 1   │ Critical │ <one-line description>                               │
  │ 2   │ Moderate │ <one-line description>                               │
  │ 3   │ Minor    │ <one-line description>                               │
  │ 4   │ Trivial  │ <one-line description>                               │
  └─────┴──────────┴──────────────────────────────────────────────────────┘
```

**Severity rubric:**

| Level | Meaning |
|---|---|
| **Critical** | Contradicts established canon (NPC fates, event timing, faction state, established mechanics); would cause player confusion or DM embarrassment if it reaches narration. Must fix before narrating. |
| **Moderate** | Framing drift — what happened is right but characterised wrongly; wrong kill attribution; characterisation that conflicts with the voice file; missing context that changes meaning. Should fix before narrating. |
| **Minor** | Misspelling of a proper noun, wrong pronoun, single-word transcription error, inconsistency within the same document. Easy to fix; fix before narrating. |
| **Trivial** | Stylistic quirk, table-chatter artifact, item you flagged as "leave as-is" in a prior stage, or flavour call that is defensible either way. Surface but do not push. |

Sort the table by severity (Critical first, then Moderate, Minor, Trivial). Number issues sequentially across the whole table. If there are zero issues, say so in one line and advance automatically to the next stage.

### 2. Stage 0 — gm-assist check

Delegate to `/consistency-check`:

> Stage 0 — running `/consistency-check $SESSION/gm-assist.md` with prep as context.

Invoke the consistency-check skill workflow against `$SESSION/gm-assist.md`, passing `docs/party.md` and all prep files via `--context`. After it returns:

- Present the severity table (format above).
- Ask: "Apply any of these fixes to `gm-assist.md` before moving to stage 1?"
- If yes, edit `gm-assist.md` directly. If no, log what was deferred so it can be revisited.

**Important caveat about gm-assist.md**: this file may be the user's preserved-original artifact (paired with a `gm-assist-update.md` next to it). If a `gm-assist-update.md` exists, ask the user whether to check that file instead and treat it as the canonical first-pass artifact. The convention is "original preserved, corrected version alongside" — apply fixes to the `-update.md` if present, otherwise the original.

### 3. Stage 1 — session-summary check

Delegate to `/consistency-check`:

> Stage 1 — running `/consistency-check $SESSION/session-summary.md` with prep as context.

Same flow: invoke `/consistency-check`, present the severity table (format above), ask about applying fixes, edit if approved.

Pay particular attention at this stage to:
- **Cross-section contradictions** (Summary prose vs. bulleted scene log)
- **Pronoun drift** on player characters
- **NPC affiliation fabrications** (the canonical Phandalin example: Prutha "committed to the Order of the Gauntlet" — party.md says Lathander convert)
- **Killing-blow attribution** in combat scenes (LLM extractors often credit the wrong character)

### 4. Stage 2 — scene extractions check (the load-bearing one)

For each scene extraction `$SESSION/scene_extractions_new/0N_*.md` (excluding `.prev` and `.scaffold` files), delegate to `/consistency-check`. Run them in numbered order so the user sees them in scene order. Present a severity table (format above) per scene.

This stage exists because **the scene extractions contain the verbatim quotes the narrator reads literally**. Fixes applied only at the session-summary layer get silently undone the next time the narrator runs.

When applying fixes to verbatim quotes:
- **Preserve the speaker attribution and tone** of the original quote when correcting transcription drift — the players' table voice is the whole point of these quotes.
- **Add an italic editorial note** in the speaker attribution explaining the discrepancy between raw Otter/Zoom capture and prep canon. Future readers (and the next narrator pass) get a transparent audit trail.
  - Example: `**GM** — *voicing Prutha (transcript per session-prep canon; raw Otter capture said "my uncle Seidan comes for everyone" — a mishearing of "great-uncle said dawn")*`
- **Do not strip table chatter, jokes, or player improvisations** that the table values. Some "errors" the check flags are intentional flavor. The Phandalin "blacklist" / "blood money list" terminology is real OOC table vocabulary — preserve those.

After each scene's fixes, ask: "Continue to next scene, or revisit this one?" Don't auto-advance through all scenes silently.

### 5. Stage 3 — narration check (optional)

If a final narration file exists (typically `$SESSION/narration/<something>.md` or the session_doc output), delegate to `/consistency-check` on it. Present a severity table (format above).

At this stage the check is mostly catching narrator-layer voice drift and prose fabrications. Findings here are usually candidates for a narrator re-run (after fixing upstream) rather than direct edits, since editing final prose tends to fight the narrator's voice.

### 6. Fix-propagation pass

After all stages have been checked and fixed, do a quick propagation sweep — fixes applied to a deep stage may need to propagate upward, and fixes at a shallow stage may need to propagate downward. Use grep to verify:

```bash
# Grep all touched files for residual bad patterns
grep -n "<bad pattern>" $SESSION/gm-assist.md $SESSION/gm-assist-update.md \
  $SESSION/session-summary.md $SESSION/narration/enhanced_sections.md \
  $SESSION/scene_extractions_new/0*.md 2>/dev/null | grep -v ".prev\|.scaffold"
```

Where "<bad pattern>" is the specific text that was wrong (e.g. `"bear comes"`, `"Order of the Gauntlet"`, `"Elemental Cleaver"`). Run this for every fix that was applied.

If grep finds the bad pattern in a file that wasn't checked or fixed, surface it to the user and ask whether to apply the corresponding fix there. **This propagation step is what catches the scenario where session-summary was fixed but the scene extractions still carry the original error.**

### 7. Final summary

End with a tight summary:

- Stages run, issue counts per stage
- Fixes applied per stage
- Anything deferred (with the location)
- Whether prep was available (or whether the run was prep-less and possibly blind to transcription errors)
- Recommendation on next action — usually one of:
  - "Re-run `session_doc.py` to produce a clean narration from the corrected scene extractions"
  - "Ready to share session-doc with players"
  - "Stage X still has unresolved issues — revisit those before narrating"

## Notes

- This skill is intentionally heavy. It exists for sessions that matter — chapter releases, sessions you're sharing externally, sessions where you've already produced a bad narration and need to root out why. For a quick sanity check on a single document, use `/consistency-check` directly.
- Skipping the prep step (step 0) collapses the value of this skill the same way it collapses `/consistency-check`. The whole reason this pattern beats a one-shot check is that prep is wired into every stage's check. Do not skip.
- The Phandalin Ch 41 run (2026-05-17) was the discovery case — 11 prep-canonical issues survived a late-stage one-shot check that returned "no major issues." The same issues were trivially catchable at stage 0 with prep wired in. That's the failure mode this skill exists to prevent.
- See `~/campaigns/STAGED_CONSISTENCY_HOWTO.md` for the methodology rationale, the pipeline diagram, and the per-stage table of what each check catches that the others miss.
