---
name: Prompts surface candidates, never commit state
description: When designing LLM prompts for this codebase, any output that names a current value, running total, or committed state is out of scope — LLMs list candidate events with cited triggers for GM review
type: feedback
originSessionId: cc0e0a63-3e43-4f7c-a877-0265b2e8263a
---
When designing prompts for party.md, planning.md, campaign_state.md, or
any other synthesis step, the LLM must never produce output that
commits to a state value on behalf of the human. Examples of forbidden
output shapes:

- "Current arc score: 4" / "Hope is at +2"
- "Net change this session: +3"
- "Threshold crossed — next ability unlocked"
- "This puts them at X"
- Any compact summary table with a "current value" column

Correct shape: surface **candidates** — individual events with their
cited trigger text from the mechanic file, the session reference, and
the proposed direction (+/-). The GM reads the list and decides which
candidates actually fire.

**Why:** per the global CLAUDE.md rule, LLMs are renderers not
architects. Picking which events count toward a score and computing
totals is a precision/scope/attribution decision. When the LLM commits
to "Brewbarry is at 4 Hope," the next LLM call (session prep, planning
synthesis) inherits that as truth and the error compounds silently.
The human checkpoint has to land *before* any downstream call sees a
committed value.

**How to apply:**
- If a prompt asks for "current X" — rewrite to ask for "candidate X
  events with triggers cited."
- If a prompt produces a summary table with "Value" / "Total" /
  "Status" columns — drop the column or drop the table.
- Explicitly forbid running totals, deltas since last session, and
  threshold claims in the rules section of the system prompt.
- Trigger text must be quoted verbatim from the mechanic file so the
  GM can verify the match rather than trusting the LLM's paraphrase.
- Trackless PCs get no candidate list — consistent with their
  "intentionally no track" status (not a warning, not an empty table).
