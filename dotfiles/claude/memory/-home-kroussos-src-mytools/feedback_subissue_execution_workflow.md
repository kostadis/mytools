---
name: feedback-subissue-execution-workflow
description: "How Kostadis wants a multi-part implementation plan executed — GitHub sub-issues, Sonnet per issue, confirm-gate, single tracking PR"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 48319722-bc61-4e28-a699-e0142da4f4bb
---

For a substantial multi-part implementation, Kostadis wants this execution shape:
decompose the parent GitHub issue into **sub-issues** (native parent/child link via
`gh api repos/OWNER/REPO/issues/PARENT/sub_issues -F sub_issue_id=<child id>`); have
**Sonnet execute each sub-issue** while Opus orchestrates and independently verifies
(Opus does not write the implementation); a **human confirm-gate after every sub-issue**;
and a **single tracking PR** on one branch, updated (checklist + summary) with the
sub-issue closed as each one lands. Land any pre-existing WIP to main first so the branch
starts from a clean base.

**Why:** keeps each step small and reviewable, separates the implementer model (Sonnet)
from the planner/orchestrator (Opus/me), and yields one coherent PR per parent issue.

**How to apply:** parent issue → `gh issue create` per chunk + link as native sub-issues →
per chunk: `Agent(model: sonnet, scope = one sub-issue, "do NOT commit — coordinator handles git")`
→ independently re-run the tests / re-check scope myself → `AskUserQuestion` confirm-gate →
on approval commit + push + update the PR body + close the sub-issue. Open the PR as **draft**
after the first sub-issue's first commit (a PR needs a diff to exist); flip to **ready** after
the last. Leave the final merge-to-main to Kostadis. When he's away at a confirm-gate, HOLD —
the gate is an explicit checkpoint, not a "proceed on best judgment" case. He may say
"go, and auto-approve the rest" to collapse the remaining gates.

**Subagent-type gotcha (found 2026-07-04):** when asked to "have Opus create a plan" for
this workflow, the `Plan` subagent type is right for producing the planning document (no
Edit/Write, so it can't accidentally write code) but it has **no Agent tool** — it returns
once and cannot itself spawn Sonnet or drive the confirm-gate loop across turns, even via
SendMessage. Producing the plan and actually running the orchestration are two different
calls: real "Opus orchestrates, Sonnet implements" execution needs either a
`general-purpose` agent with `model: opus` (which does have Agent-tool access) spawned
fresh for the execution phase, or the user switching the main-loop session model to Opus.
Don't let "the plan is done" silently imply "the orchestrator is wired up" — say so
explicitly before the first "go."

Related: [[feedback-branch-pr-workflow]], [[project-mytools-repo]].
