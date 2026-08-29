---
name: codebase-memory-adr-wipe
description: "codebase-memory-mcp destroys the stored ADR on ANY re-index, in-place included — save manage_adr(mode='get') output before indexing"
metadata:
  node_type: memory
  type: reference
  originSessionId: 5be5a889-170b-47e0-b4fb-2245e6c6182c
  modified: 2026-08-07T14:24:47.826Z
---

`mcp__codebase-memory-mcp__index_repository` **destroys the project's stored ADR**, even run in place with no `delete_project`. Confirmed 2026-08-07 on `home-kroussos-src-CampaignGenerator`: a plain in-place `index_repository(mode="full")` returned `adr_present: false` and a follow-up `manage_adr(mode="sections")` came back empty. `delete_project` wipes it too.

An earlier version of this memory claimed in-place re-index *preserved* the ADR. That was wrong — do not trust it.

**Always do this before re-indexing:**

1. `manage_adr(mode='get')` and keep the full content (not just `mode='sections'` — sections alone are useless for restore).
2. `index_repository(...)`.
3. `manage_adr(mode='update', content=<saved>)`.

There is no on-disk backup to recover from: the ADR lives inside `~/.cache/codebase-memory-mcp/<project>.db`, which the re-index rewrites. No `*.bak`, and the `-wal` is empty afterward.

If it is already lost, rebuild from the repo's hand-written sources rather than from the graph — for CampaignGenerator that is `CLAUDE.md` plus `docs/core/architecture.md`, which together cover all six sections (PURPOSE, STACK, ARCHITECTURE, PATTERNS, TRADEOFFS, PHILOSOPHY).

Caveat also observed 2026-07-23: `detect_changes` returned 0 changed files even though the working tree had diverged from the indexed snapshot, so it is unreliable for a post-merge refresh — prefer a full `index_repository` (with the save/restore dance above). See [[project_entity_registry_rollout]] for the surrounding session context.
