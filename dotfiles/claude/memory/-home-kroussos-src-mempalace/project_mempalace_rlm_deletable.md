---
name: mempalace-rlm-deletable
description: /home/kroussos/src/mempalace-rlm is a temporary checkout slated for deletion — do not treat it as an active tree
metadata: 
  node_type: memory
  type: project
  originSessionId: d598fd5b-9beb-44ec-a5be-119f878cc5df
---

`/home/kroussos/src/mempalace-rlm` is a throwaway checkout (branch `rlm-phase1`, RLM phase-1 work). User confirmed 2026-05-13 it can be deleted.

**Why:** the RLM phase-1 experiment is paused. Keeping two checkouts of the same repo around caused a real bug — the `mempalace-rlm/venv` was the host of the `mempalace-mcp` entry point and its editable install pointed at `mempalace-rlm`, so the MCP server quietly ran stale rlm-phase1 code (missing `_resolve_embedding_function`, missing two-tier shape) while tests ran against the correct `/home/kroussos/src/mempalace` tree. Workaround was `PYTHONPATH=/home/kroussos/src/mempalace` in the MCP server's env; the real fix is to delete the rlm checkout and house the venv inside the active tree.

**How to apply:**
- Before relying on `/home/kroussos/src/mempalace-rlm` for anything, check whether it still exists.
- A dedicated venv now lives at `/home/kroussos/src/mempalace/venv` and the MCP server is registered against it (2026-05-13). The rlm venv is no longer referenced by any active toolchain.
- The `mempalace-rlm/` entry has been removed from `/home/kroussos/src/CLAUDE.md` (2026-05-13).
- Update [[project_fork_workflow]] mentally: workflow is now a single mempalace checkout at `/home/kroussos/src/mempalace`.
- The directory itself may or may not still exist on disk — verify before referencing.
