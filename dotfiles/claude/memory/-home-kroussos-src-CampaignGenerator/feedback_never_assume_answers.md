---
name: never-assume-answers
description: "Never treat a defaulted/auto-selected/timed-out question response as the user's decision — wait for an explicit answer"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 7164eaa7-a5bc-412e-b2e2-226abc74ffe4
---

When a question to the user (AskUserQuestion or otherwise) comes back without a clear, explicit answer from Kostadis — e.g. a default/recommended option appears selected, the response is ambiguous, or he was simply taking time — do NOT proceed as if he decided. Re-ask and wait.

**Why:** On 2026-07-06 an AskUserQuestion result showed "A (Recommended)" selected for a design decision he never actually made; proceeding on it violated his explicit rule that the GM/user owns every decision. Decisions made "because the user was taking too long" are a rule violation, not a convenience. This is the same principle as his LLM Pipeline Design Rule: precision decisions require a real human checkpoint, and a timeout is not a checkpoint.

**How to apply:** Treat only an explicit, affirmative user response as a decision. If in doubt whether an answer was really given, ask again and say why. Never fill in a "recommended" choice on his behalf. Now a permanent rule in ~/.claude/CLAUDE.md ("An Unanswered Question Is Not a Decision", added 2026-07-06; the file is a symlink into mytools/dotfiles).
