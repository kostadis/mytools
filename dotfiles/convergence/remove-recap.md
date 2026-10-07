# Convergence report: remove-recap

Compared: `codex/skills/remove-recap/` vs `claude/skills/remove-recap/` (paths relative to `/home/kostadis/src/mytools/dotfiles/`).

## 1. Summary

The two sides are **near-identical**. The body text ("When to run it" → "Why this design") matches byte for byte except for two `~/.codex` vs `~/.claude` script paths. Both scripts are byte-identical (`cmp`).

**Lineage: Claude → Codex.** The skill was created in `8897d5f` (2026-09-04) on the Claude side. It was copied to Codex in `8bfd959` (2026-09-18) with a rewritten frontmatter and an 18-line "Codex Compatibility" block. `git log --follow` on the Codex path traces back to `8897d5f`. The Claude side has not changed since creation.

Codex's additions are mostly platform notes. Two of its bullets add small gates the Claude text lacks: explicit rulings for rebuilds, and confirmation before paid re-narration.

## 2. File inventory

| file | codex | claude | status |
|---|---|---|---|
| `SKILL.md` | 256 lines | 237 lines | differs (frontmatter + compat block + 2 paths) |
| `find_recap.py` | 164 lines | 164 lines | identical |
| `recap_unique.py` | 112 lines | 112 lines | identical |
| `agents/openai.yaml` | absent | absent | n/a |
| `__pycache__/` | present | — | ignored |

## 3. Only in Codex

Every changed line cluster, in file order:

1. **Frontmatter** (`codex/.../SKILL.md:3-5`): a shorter description plus `metadata.short-description: Remove an opening previous-chapter recap`. Codex's description drops two points Claude's makes: "Scoped to the FIRST scene" and "Cheapest before scene_extract". Both still appear in the body (`## Scope: the first scene`; the cost table), so nothing is lost.
2. **Port note** (`:18-19`): "This is the Codex port of the Claude skill. Do not edit `~/src/mytools/dotfiles/claude/skills/remove-recap/` when changing this skill." This is housekeeping.
3. **Codex Compatibility block** (`:21-34`), bullet by bullet, each checked against the Claude body:
   - `:23` "Ask the GM questions in chat; do not refer to Claude `AskUserQuestion`." This is platform-only.
   - `:24-26` "Detection and rescue analysis may run without approval. Any recap boundary, rescued-content destination, file deletion, or downstream rebuild requires the GM's explicit ruling first." This is **mostly covered** in Claude. Phase 3 (`:144-165`) covers boundary and destination ("Where rescued content goes is its own decision"). Claude's Phase 4 (`:167-177`) does not say that the *rebuild* (`sd_plan` + re-narrate all) needs its own ruling. It presents the cost in Phase 3 (`:152`) and then proceeds. The explicit "detection may run without approval" permission is new in Codex, but it only makes Claude's implicit behaviour explicit.
   - `:27-29` "Use `apply_patch` for approved Markdown edits. When trimming only a prefix … use the `no-mech` deterministic applier so its path and stale-line guards remain active." `apply_patch` is platform-only. Reusing `apply_cut.py` is **already in Claude** (`:179-180`).
   - `:30-32` "Deleting an approved derived scene is allowed only after resolving the exact path and restating the renumbering consequence. Never delete the verbatim counterpart." This is **partly covered**. Claude has "`scene_extractions/` stays" (`:219`) and presents renumbering in Phase 3 (`:152`). "Resolve the exact path" before `git rm <…>/01_*.md` is new. It matters because the Claude command uses a glob.
   - `:33-34` "Re-narration may invoke a paid or remote backend. Explain its scope and obtain confirmation before running it." This is **substantive and absent in Claude**. Claude Phase 4 lists `sd_narrate … # ALL scenes` with no confirmation step.
4. **Script paths** (`:115`, `:135`): `~/.codex/skills/remove-recap/…` in place of `~/.claude/…`. This is platform-only.

## 4. Only in Claude

- **Frontmatter** (`claude/.../SKILL.md:3-4`): a longer description and `tools: Read, Bash, Write, Edit, Glob, AskUserQuestion`. This is platform-only.
- **No substantive rule is present only in Claude.**

## 5. Conflicts

None between the two sides.

Two issues are **shared by both sides**: identical text, so not a convergence conflict, but worth fixing when you converge.

1. **Run point vs input layer.** "When to run it" says to run **before `/scene-extract`** (Claude `:19-20`, `:26`, and the cost table `:83`: "Drop the recap scene from `session-summary.md`'s `## Scenes`"). But Phase 1 and Phase 2 operate on `<session>/scene_extractions_smoothed` (Claude `:96-97`, `:117`), a directory that exists only *after* extraction and `/voice-smooth`. At the recommended run point there is nothing for `find_recap.py` / `recap_unique.py` to read. I did not check whether the scripts accept a `session-summary.md` or VTT input instead.
2. **Stale-narration deletion order.** Phase 4 (Claude `:172-176`) lists `rm <session>/narration/session_doc_scene_*.md   # stale numbering, before re-narrating` *after* the `sd_narrate` line. Read top to bottom, that would delete the fresh narration. The Landmines section (`:212-214`) states the correct order: "delete the stale narration files before re-narrating".

## 6. Platform-only differences

- Frontmatter: `metadata.short-description` (Codex) vs `tools:` allowlist (Claude).
- The port note and "Ask in chat, not `AskUserQuestion`" (Codex `:18-23`).
- `apply_patch` (Codex `:27`) vs `Edit`/`Write` (Claude).
- Script install root: `~/.codex/skills/remove-recap/` vs `~/.claude/skills/remove-recap/` (Codex `:115, :135`; Claude `:96, :116`).
- Both sides reference the sibling skill's applier (`/no-mech`'s `apply_cut.py`) by name only, not by path, so the cross-skill reference is harness-neutral.

## 7. Script diffs

- `find_recap.py`: none. Identical (`cmp` clean).
- `recap_unique.py`: none. Identical. Neither script embeds a harness-specific path.

## 8. Open questions for the GM

1. **Should the shared body gain Codex's two gates?** These are "downstream rebuild requires the GM's explicit ruling" and "confirm before paid re-narration" (Codex `:24-26`, `:33-34`). Suggestion: yes. Both are harness-neutral, and re-narrating *all* scenes is the most expensive path in the skill's own cost table.
2. **Should "resolve the exact path before deleting" (Codex `:30-32`) replace the bare `git rm <session>/scene_extractions_smoothed/01_*.md` glob in the shared Phase 4?**
3. **Pre-extraction mode.** How is the recommended "before `scene_extract`" run meant to work, when both detection scripts read `scene_extractions_smoothed/`? Should the skill document a pre-extraction mode (operating on `session-summary.md` `## Scenes` + the VTT), or should the recommended run point move to after `/voice-smooth`?
4. **Fix the Phase 4 command order** so the `rm` of stale narration comes before `sd_narrate`, on both sides.
5. **Keep the scripts duplicated, or share them?** Same question as for `no-mech`.
