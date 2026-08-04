---
name: codebase-memory-adr-wipe
description: "codebase-memory-mcp delete_project also wipes the project's stored ADR; incremental re-index preserves it"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 5be5a889-170b-47e0-b4fb-2245e6c6182c
  modified: 2026-07-24T06:06:26.701Z
---

`mcp__codebase-memory-mcp__delete_project` deletes the whole project **including any ADR** stored via `manage_adr`. A "clean full rebuild" (delete_project → index_repository) therefore drops the ADR — re-store it afterward, or avoid delete.

To refresh the graph after a small change WITHOUT losing the ADR, run `index_repository` in place (it re-indexes and preserves the ADR). Do NOT delete+reindex unless you specifically want to prune orphaned nodes.

Caveat observed 2026-07-23: `detect_changes` returned 0 changed files even though the working tree had diverged from the indexed snapshot (graph was pinned to a stale HEAD). So `detect_changes` is unreliable for a post-merge refresh — prefer `index_repository`. See [[project_entity_registry_rollout]] for the surrounding session context.
