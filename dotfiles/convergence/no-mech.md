# Convergence report: no-mech

Compared: `codex/skills/no-mech/` vs `claude/skills/no-mech/` (paths relative to `/home/kostadis/src/mytools/dotfiles/`).

## 1. Summary

The two sides are **near-identical**. The body text (Where this sits → Why this design) matches byte for byte except for three `~/.codex` vs `~/.claude` script paths. Both scripts are byte-identical (`cmp`).

**Lineage: Claude → Codex.**
- The skill was created on the Claude side in `8897d5f` (2026-09-04), then updated on both sides in the same commit `32a1262` (2026-09-05, "classify on the stage direction, not just the speaker label").
- The Codex copy was then re-landed in `8bfd959` (2026-09-18) with a front-matter rewrite and a "Codex Compatibility" block. `git log --follow` on the Codex path traces back through the Claude-side commits, which confirms the copy.

Codex is the more recently touched side. Its only additions are platform notes, plus one arguably substantive gate: confirm before a paid re-narration.

## 2. File inventory

| file | codex | claude | status |
|---|---|---|---|
| `SKILL.md` | 409 lines | 391 lines | differs (frontmatter + 17-line compat block + 3 paths) |
| `scan_quotes.py` | 194 lines | 194 lines | identical |
| `apply_cut.py` | 123 lines | 123 lines | identical |
| `agents/openai.yaml` | absent | absent | n/a |
| `__pycache__/` | present | — | ignored |

## 3. Only in Codex

Every changed line cluster, in file order:

1. **Frontmatter** (`codex/.../SKILL.md:3-5`): a shorter description, plus `metadata.short-description: Remove table mechanics before narration`. This is platform-only; see section 6. Codex's description drops two points Claude's makes: "Sibling of /scrub" and "Run before sd_narrate". Both still appear in the body (`:14`, `:47`), so nothing is lost.
2. **Port note** (`:18-19`): "This is the Codex port of the Claude skill. Do not edit `~/src/mytools/dotfiles/claude/skills/no-mech/` when changing this skill." This is housekeeping.
3. **Codex Compatibility block** (`:21-33`), bullet by bullet, each checked against the Claude body:
   - `:23` "Ask the GM questions in chat; do not refer to Claude `AskUserQuestion`." This is platform-only.
   - `:24-25` "present one scene at a time and wait for the GM's ruling before applying that scene's cut." **Already present in Claude** in substance: Claude `:223-224` reads "**Never batch a whole session into one approval, and never decide the shape yourself.**" Codex is slightly stricter. It says *apply* per scene after each ruling, where Claude requires rulings per scene but does not order the apply step.
   - `:26-28` "Use `apply_patch` for manual changes … Prefer the bundled deterministic applier … because it enforces the smoothed-layer invariant and detects stale line numbers." `apply_patch` is platform-only. The applier's guards are already described in Claude (`:254`, `:263-266`).
   - `:29-30` "An approved cut authorizes only the stated derived-layer edit. It never authorizes changes to the VTT or `scene_extractions/`." **Already covered** by Claude's "The hard invariant" (`:61-68`).
   - `:31-33` "If narration already exists, re-narration is a separate, potentially costly follow-up. Explain the affected scene indices and obtain confirmation before invoking a paid or remote backend." **This is the one substantive addition.** Claude Phase 4 (`:292-312`) discusses re-narration cost ("re-narrating has a real cost", `:30`) but never requires confirmation before running `sd_narrate`.
4. **Script paths** (`:135`, `:260`, `:267`): `~/.codex/skills/no-mech/…` in place of `~/.claude/…`. This is platform-only.

## 4. Only in Claude

- **Frontmatter** (`claude/.../SKILL.md:3-4`): a longer, trigger-rich description and `tools: Read, Bash, Write, Edit, Glob, AskUserQuestion`. The description adds "then re-narrate the affected scenes", "Sibling of /scrub" and "Run before sd_narrate". All three are also in both bodies. This is platform-only.
- **No substantive rule is present only in Claude.** The Codex copy carries the whole Claude body.

## 5. Conflicts

None between the two sides.

There is one point of note that is **shared by both sides**, not a conflict: the Phase 4 re-narration example hard-codes a Codex backend on the Claude side too, `--backend codex-cli --model gpt-5.6-sol --codex-reasoning-effort medium` (Claude `:311`, Codex `:329`). On Claude this contradicts the backend convention used elsewhere (`claude/skills/enhance-summary/SKILL.md:63` defaults to `claude-code`). See Open questions.

## 6. Platform-only differences

- Frontmatter: `metadata.short-description` (Codex) vs `tools:` allowlist (Claude).
- The port note and "Ask in chat, not `AskUserQuestion`" (Codex `:18-23`).
- `apply_patch` (Codex `:26`) vs the `Edit`/`Write` tools (Claude, implied by `tools:`).
- Script install root: `~/.codex/skills/no-mech/` vs `~/.claude/skills/no-mech/` (Codex `:135, :260, :267`; Claude `:117, :242, :249`).

## 7. Script diffs

- `scan_quotes.py`: none. Identical (`cmp` clean).
- `apply_cut.py`: none. Identical. Neither script embeds a `~/.claude` or `~/.codex` path. The only self-references are the `/no-mech` name in a docstring and the refusal message (`apply_cut.py:2`, `:24`), so both copies are harness-neutral.

## 8. Open questions for the GM

1. **Should the "confirm before paid re-narration" gate (Codex `:31-33`) become part of the shared body, so Claude gets it too?** Suggestion: yes. It is harness-neutral and consistent with the skill's own "re-narrating has a real cost" (`:30`).
2. **Should "apply per scene, after that scene's ruling" (Codex `:24-25`) be stated in the shared Phase 2/3 text?** Claude currently requires per-scene rulings but does not order the apply step.
3. **Which backend should the Phase 4 `sd_narrate` example show?** Both sides show `codex-cli` / `gpt-5.6-sol`. Suggestion: make the example backend-neutral (for example `--backend <configured>`), or give each side its own harness's backend.
4. **Keep the scripts as two copies, or have one side reference the other / `_shared/`?** They are identical today, and nothing enforces that.
