---
name: feedback-orchestrate-vs-code
description: "For non-trivial multi-file implementation work, stay as orchestrator and delegate actual coding to Agent-tool subagents rather than editing directly in the main thread."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f872fd21-15a5-431e-b122-e70d0c3e0207
---

"Opus orchestrates, sonnet codes" — the user's own phrase for how they want implementation work structured once a plan is approved.

For a non-trivial, multi-phase implementation (the kind that already warranted Plan mode — multiple files, an architectural decision, sequenced steps), don't just start editing directly in the main thread after the plan is approved. Instead: stay in the orchestrating role — sequence the phases, review each subagent's diff, run tests, decide when to move to the next phase — and delegate the actual file-editing/coding work to Agent-tool subagents, one per phase or logical unit.

**Why:** Said explicitly when I proposed exiting plan mode straight into direct sequential edits for a 3-script refactor (extending citation grounding from distill.py to planning.py/party.py). When asked to clarify the mechanism (delegate to subagents vs. just code it directly vs. hand off the plan entirely), the user chose subagent delegation.

**How to apply:** For small/simple tasks (a few lines, one obvious fix, something that wouldn't have warranted Plan mode in the first place), direct editing in the main thread is still fine — this preference is about *implementation-sized* work, not every edit. When a task is big enough to plan, it's big enough to delegate: use the Agent tool per phase, review the resulting diff and test output before proceeding to the next phase, keep the main thread as the coordination/review layer rather than the place where the actual edits happen.
