---
name: feedback-codebase-search-policy
description: codebase-memory-mcp should be MCP-first for structural queries but never a hard ban on grep/find; keep the policy in one place
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 7883de04-8a71-45a1-ae17-b915b6b58b49
---

Don't accept "completely prohibited from using grep" style wording for codebase-memory-mcp policy, even when the user proposes it themselves — soften to: MCP-first for structural/relational queries (definitions, call chains, cross-file/class relationships), but Grep/Glob/Bash grep stay free for non-code files, configs, exact string/regex matches, and sanity-checking a result that looks stale.

**Why:** `codebase-memory-mcp`'s own installed `SessionStart` hook (`cbm-session-reminder`) already says "Use Grep/Glob/Read freely for text, configs, non-code files" — a hard ban contradicts the tool's own default guidance. Also, `auto_index` is off by default (checked via `codebase-memory-mcp config list`), so the graph can silently drift from the code after edits; banning grep as a fallback removes the only way to catch a stale/wrong graph answer. The `PreToolUse` gate hook on Grep|Glob (`cbm-code-discovery-gate`) is a no-op by design (never blocks, silent failure) — enforcement here is 100% instruction-following, not a technical gate, so the wording matters a lot.

**How to apply:** Canonical wording lives in global `~/.claude/CLAUDE.md` ("Codebase Semantic Search (codebase-memory-mcp)" section) — don't let per-repo CLAUDE.md files carry their own copy that could drift out of sync or contradict it (this happened once: `CampaignGenerator/CLAUDE.md` had a hard-ban version added 2026-07-15, reconciled the same day to point at the global section instead). Before vetting or propagating any cross-repo agent-behavior rule, check `~/.claude/settings.json` hooks and any tool-installed reminders first — the tool may already have shipped its own (more sensible) default that the proposed rule would override.
