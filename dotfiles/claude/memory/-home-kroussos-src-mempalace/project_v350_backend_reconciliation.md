---
name: project-v350-backend-reconciliation
description: "v3.5.0 merge — converge on upstream's pluggable-backend framework; re-home turbovec as an adapter"
metadata: 
  node_type: memory
  type: project
  originSessionId: e665df06-f005-411f-a04f-8bbf781f6e63
---

During the kostadis-dev → upstream **v3.5.0** sync (tracking issue kostadis/mempalace#23, worktree `../mempalace-v3.5.0`, branch `merge/v3.5.0-into-kostadis-dev`), a new divergence surfaced that is NOT in `divergence.md`: **both branches independently built a pluggable-backend layer** on `backends/{base,chroma,registry}.py`. Upstream added a full framework (registry + pgvector/qdrant/sqlite_exact/embedding_wrapper/_sidecar, RFC 001, lands in v3.4.0); the fork added `turbovec.py` + `MEMPALACE_BACKEND` routing.

**Decision (user, 2026-07-03):** adopt **upstream's** backend framework and re-home `turbovec` as an adapter onto upstream's evolved `BaseBackend`/`BaseCollection`, registering via upstream's `registry.register`. The upstream RFC 001 work was done with the user's input, so convergence is the intent — do NOT preserve the local turbovec-centric `backends/` layer.

**Why:** the standing "keep local design at the 7 divergence sites" rule is wrong for `backends/` — keeping local base/registry would discard and break upstream's new backends. This is a scope/architecture decision, so it took a human checkpoint (per the "LLMs are renderers, not architects" rule) rather than a Sonnet auto-merge.

**Status: DONE in sub-issue C (merge v3.4.0, commit be10b66, 2026-07-03).** Reality was easier than planned: local `turbovec.py` *already* subclassed upstream's RFC-001 `BaseBackend`/`BaseCollection` and registered via a pyproject **entry point**, so little re-homing was needed. Resolution: upstream's pgvector/qdrant/sqlite_exact registered eagerly (their heavy client deps import lazily), chroma kept **best-effort/lazy** (local #20) so turbovec-only deploys never import chromadb; entry points keep all backends. Adopted upstream's refined HNSW quarantine. This exception is scoped to `backends/` ONLY — the original 7 sites still keep local design.

**Turbovec verified (2026-07-04, with turbovecdb installed):** the merge did NOT regress turbovec. `test_turbovec_backend.py` 30/30 pass; the recall path (`palace.get_collection` → `TurboVecCollection` → `searcher.search_memories`) works end-to-end with verbatim preserved and a genuine `turbovec` store on disk (no chroma.sqlite3). **Known pre-existing limitation (NOT a merge regression — chroma-centric already on base 535242e):** `mcp_server._get_collection`/`_get_client` use `ChromaBackend` directly, so **direct MCP write tools (`tool_add_drawer`, `tool_status`) create/expect a chroma palace even under `MEMPALACE_BACKEND=turbovec`**. The turbovec chat palace works because hooks mine via CLI (`palace.get_collection`, backend-routed) and searches go through `searcher`→`palace.get_collection`; only the direct-MCP-write path is chroma-only. Note: the pinned lock has turbovecdb 0.1.0 while the canonical `~/.venvs/main` has 0.5.0. Full write-up in `docs/v3.5.0-merge-notes.md` §Sub-issue C. Relates to [[project_chat_palace_turbovec_switch]].
