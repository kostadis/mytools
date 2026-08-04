---
name: project-speckit-claude-gitignored
description: "CampaignGenerator .gitignore ignores .claude/, so spec-kit's skills are untracked and absent from every fresh clone/worktree; .specify/ survives because it is tracked."
metadata: 
  node_type: memory
  type: project
  originSessionId: f640abb2-a2c0-4003-8688-bbd0c5ea3c56
  modified: 2026-07-25T19:44:48.550Z
---

`.gitignore` line 15 is `.claude/`. Spec-kit installs its whole command surface as
skills under `.claude/skills/speckit-*/SKILL.md`, so **those ten files are untracked
and unrecoverable from git**. The `.specify/` half (scripts, templates,
`memory/constitution.md`) is tracked and survives.

**Why:** it has already bitten once — all ten skills were wiped and `/speckit-*`
silently did not exist. `specify integration status` diagnoses it exactly:
"10 managed files missing, 0 modified". It recurs in every new worktree, since a
worktree checkout has no `.claude/` at all.

**How to apply:** after any fresh clone or `git worktree add`, either run
`specify integration upgrade claude` in the new tree, or copy `.claude/` across
from the main checkout. Note the CLI's upgrade also refreshes tracked `.specify/`
scripts+templates to the CLI's version (0.11.10.dev0 → 0.14.2 on 2026-07-25),
which shows up as a real diff — the "shared infrastructure ... not updated"
warning it prints is wrong, check `git diff`.

Reverting `.specify/` in a tree whose `.claude/skills` are newer leaves a version
skew (new skills calling old scripts). Keep the two halves at the same version.

Related: [[reference-worktree-editable-install-shadowing]] — the other worktree
trap, where imports resolve to the main checkout.
