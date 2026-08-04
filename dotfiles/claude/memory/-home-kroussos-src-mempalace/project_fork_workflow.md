---
name: Fork workflow (kostadis/mempalace)
description: origin (kostadis/mempalace) is NOT a GitHub fork; upstream PRs must come from the real fork kostadis/mempalace-fork. kostadis-dev is the user's personal main.
type: project
originSessionId: bff24776-cb3b-45ae-b057-71bed7b02234
modified: 2026-07-26T01:44:00.451Z
---
`origin` = `github.com/kostadis/mempalace` — the user's day-to-day repo, but **NOT a GitHub fork** of MemPalace (`isFork:false`, `parent:null`; it shares history because it was clone-and-pushed, not forked). `upstream` = `github.com/MemPalace/mempalace` (canonical repo); the user has **READ-only** access.

**Opening a PR to upstream requires a real fork.** Because `origin` isn't in MemPalace's fork network, `gh pr create --head kostadis:<branch>` against it fails ("Head repository can't be blank / no commits between"). On 2026-07-03 we created a genuine fork **`kostadis/mempalace-fork`** (`gh repo fork MemPalace/mempalace --fork-name mempalace-fork`) for exactly this. Push PR branches to that fork (remote `fork`) and open from it. First successful upstream PR this way: #1922 (`.mempalaceignore`, §6 divergence) against `develop`.

**`kostadis-dev` is the user's personal main** — the stable integration branch on the fork. Feature/PR branches are cut *off* `kostadis-dev`, not off `upstream/main`. New work flows: branch-off-kostadis-dev → commits → push to origin → (optionally) open PR against upstream.

**Why:** The user has no write access to `upstream/main` (see `feedback_no_push_upstream_main.md`) and `upstream/develop` is off-limits for direct commits. Treating `kostadis-dev` as their personal main keeps their fork clean and gives a stable base for feature branches.

**`origin` has no `main` branch at all** (confirmed 2026-07-25 via `git ls-remote --heads origin`) — its default branch is `develop` (mirrors upstream's `develop`). The `main` branch that release syncs talk about ("fast-forward the fork's main to vX.Y.Z") lives on **`fork`** (`kostadis/mempalace-fork`), tracking `upstream/main` 1:1. "Sync the fork" = fast-forward `fork:main` to the new release tag (`git push fork vX.Y.Z:main`), not anything on `origin`.

**How to apply:**
- "push" / "merge into kostadis-dev" → target `origin/kostadis-dev`.
- "create a branch" / "PR branch" → `git checkout -b <name> kostadis-dev` (base is `kostadis-dev`, not `main`).
- Opening a PR to upstream → branch off the target upstream base, push to remote `fork` (`kostadis/mempalace-fork`), then `gh pr create -R MemPalace/mempalace --head kostadis:<branch> --base <upstream-branch>`. The `--head kostadis:` now resolves to the real fork. Ask which upstream branch; never assume `main`.
- "fast-forward the fork's main" / "sync the fork" → `git push fork <tag-or-commit>:main` on `kostadis/mempalace-fork`, never `origin` (which has no `main`). See `[[feedback_main_branch_push_needs_user_permission]]` — this class of push is blocked by the harness's own auto-mode classifier, not just a standing preference; expect to hand it to the user.
