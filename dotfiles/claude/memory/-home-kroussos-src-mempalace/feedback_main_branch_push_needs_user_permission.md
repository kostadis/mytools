---
name: feedback-main-branch-push-needs-user-permission
description: "gh pr merge and git push to any *:main ref get blocked by Claude Code's own auto-mode permission classifier, not just standing user preference — expect to hand these to the user, don't retry or work around."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 878d805f-66eb-4037-b1d5-eded37fb23b0
  modified: 2026-07-26T01:44:13.511Z
---

Discovered 2026-07-26 during the mempalace v3.6.0 fork-sync ([[project_fork_workflow]]): both `gh pr merge <n>` (merging PR #37 into `kostadis-dev`) and `git push fork v3.6.0:main` (fast-forwarding `kostadis/mempalace-fork:main`) were denied by "the Claude Code auto mode classifier" — a harness-level block, separate from and in addition to the standing user preferences already on file ([[feedback_never_push_main]], [[feedback_no_push_upstream_main]]).

**Why this matters beyond the existing preference memories:** those describe *my own* judgment call not to push to main. This is different — it's the harness refusing the tool call outright regardless of my judgment, and the denial message explicitly says not to route around it via other tools. Retrying the same class of action wastes a turn.

**How to apply:** When a task involves `gh pr merge` or any `git push <remote>:main` (or `master`), don't attempt it and then explain after a denial — anticipate the block, do the read-only/prep work (verify mergeable state, confirm fast-forward is safe, stage everything), then hand the actual merge/push command to the user with exact copy-pasteable syntax, same as any other action requiring their direct approval. If they explicitly ask me to do it anyway, still attempt it once (their instruction may unblock it via a session permission grant) but don't loop retries if it's denied again — report back and let them run it themselves.
