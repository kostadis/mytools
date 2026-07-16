---
name: Never push to any main (including user's own fork)
description: Hard rule — never `git push` to main on origin or upstream, even for fork-sync operations
type: feedback
originSessionId: a3a83436-8023-4551-95fb-dc63d8f762d9
---
Never `git push` to `main` on any remote, including the user's own fork (`origin/main` on github.com/kostadis/mempalace). This extends the existing "never target main" rule to also cover sync/update operations, not just PRs and commits.

**Why:** The user treats `main` as strictly upstream-tracking — it exists only to mirror the upstream project's released state. Any local creation, reset, or sync of `main` must stay local (or be done by the user via GitHub's "Sync fork" UI, which is the normal mechanism). Pushing `main` from Claude would bypass that boundary.

**How to apply:**
- Never run `git push origin main` or `git push upstream main`.
- Never run `git push -u origin main` even to create the branch for the first time.
- Fork-sync operations are the user's job via GitHub UI or manual commands — offer the commands, don't execute the push.
- Local `main` branch creation (`git branch main upstream/main`) and local fast-forward are fine; publishing it is not.
- If a workflow requires an updated `origin/main`, stop and ask the user to sync their fork first, then continue.
