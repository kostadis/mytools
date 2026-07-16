---
name: Never target main — work lands on kostadis-dev
description: All commits, pushes, and PRs land on the user's kostadis-dev branch. Never propose targeting main (origin or upstream) for anything.
type: feedback
originSessionId: bff24776-cb3b-45ae-b057-71bed7b02234
---
Never push to, merge into, open a PR against, or otherwise propose changes to any `main` branch — neither `origin/main` (the user's fork) nor `upstream/main` (`MemPalace/mempalace` main). All work lands on `kostadis-dev` or feature branches based on it.

**Why:** The user has explicitly said: "I never want to check to main, only my dev branch." This applies to both their fork's main and upstream/main. They have no write rights on `upstream/main` regardless, and they treat `kostadis-dev` as their personal main on the fork (see `project_fork_workflow.md`). Suggesting a PR to `main` after wrapping a feature wastes a round-trip and contradicts their workflow.

**How to apply:**
- After completing a feature on a branch (e.g. `feat/palace-isolation`), do not suggest "ready for a PR to main." Either offer to merge back into `kostadis-dev`, or stop and let the user decide what's next.
- When opening any PR, the base must not be `main`. Default base is `kostadis-dev` (or another user-named branch). For upstream PRs, ask which non-main branch to target (e.g. `develop`); never assume `main`.
- "Push the branch" → push to `origin/<branch>`, never to `origin/main` or `upstream/main`.
