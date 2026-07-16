---
name: Never commit to develop branch
description: Hard rule — never commit directly to the develop branch (which is the main branch) in mempalace
type: feedback
originSessionId: 2f840be5-05e3-46e5-aca2-bef005677d53
---
NEVER commit to the `develop` branch in this repo. It is the main/upstream branch.

**Why:** The user maintains a private fork (kostadis/mempalace). The `develop` branch must stay clean to mirror upstream (MemPalace/mempalace). All work goes on `kostadis-dev` or other feature branches.

**How to apply:** Before any commit, verify the current branch is NOT `develop`. If on `develop`, switch to `kostadis-dev` first. Never `git push origin develop` with local changes. Only update `develop` by pulling from upstream. When creating PRs, the base branch must be `kostadis-dev` — all PRs merge into `kostadis-dev`, never into `develop`.
