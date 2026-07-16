---
name: Never commit directly to main
description: All changes must go through a feature branch and PR, never committed directly to main
type: feedback
originSessionId: 100fd73a-f533-49eb-bf44-73ff24a4e120
---
Never commit directly to main. Always create a feature branch, push it, open a PR, and wait for the user's go-ahead before merging.

**Why:** User's explicit rule — learned after I committed directly to main and had to force-reset it to fix the workflow.

**How to apply:** For any code change, the sequence is: `git checkout -b <branch>` → commit → push branch → `gh pr create` → wait for "merge" → `gh pr merge`.
