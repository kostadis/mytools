---
name: project-v360-sync-done
description: "kostadis-dev synced to upstream v3.6.0 (PR #37, merged); fork/main fast-forwarded to v3.6.0. Coverage sits under CI's gate, root-caused to upstream's new milvus.py, not this fork."
metadata: 
  node_type: memory
  type: project
  originSessionId: 878d805f-66eb-4037-b1d5-eded37fb23b0
  modified: 2026-07-26T01:44:36.772Z
---

**Status: DONE (2026-07-26).** `kostadis-dev` merged up to upstream **v3.6.0** via PR [kostadis/mempalace#37](https://github.com/kostadis/mempalace/pull/37) (tracking issue #35, single direct merge — no intermediate tags between v3.5.0 and v3.6.0). `kostadis/mempalace-fork:main` fast-forwarded to v3.6.0 to match. See [[project_fork_workflow]] for the corrected understanding that `origin` has no `main` branch at all — only `fork` (`kostadis/mempalace-fork`) does.

**Divergence.md is the durable record** — §1–§13, refreshed end-to-end for this cycle. §4 (lock reentrance) is now marked CONVERGED (adopted upstream's fork-safety rework wholesale). §1 (closet/primary split) diverged *further* this cycle — local fully removed the `candidate_strategy="union"` dispatch machinery that used to sit dormant.

**Known-accepted gap, not a regression:** full-suite coverage measures ~79.4%, under the CI `--cov-fail-under=80` gate. Root cause is upstream's own new `mempalace/backends/milvus.py` (800 stmts, only 22% covered under a `dev`-only install — CI's own install matrix, `pip install -e ".[dev]"`, never adds `.[milvus]`/`.[pgvector]`/`.[turbovec]`). Installing the `milvus` extra to verify hit an unrelated native-library conflict (`faiss-cpu` vs numpy, "cannot load module more than once per process") in the throwaway merge-worktree venv. Likely already true on pure upstream v3.6.0, independent of this fork — worth raising with upstream separately rather than writing new tests here for a file this fork doesn't own. Full writeup in `divergence.md`'s Test-impact section.

**Also found and fixed during this merge** (not deferred): a stale-cached-chromadb-client-not-closed bug in `mcp_server.py`'s per-palace cache dict — same class of bug as upstream's #1128 (Windows handle leak), just against local's dict-cache shape instead of upstream's scalar globals.

**Leftover from this cycle, not yet cleaned up:** worktree `~/src/mempalace-v3.6.0` and backup branch `kostadis-dev-backup-pre-3.6.0-merge` — both safe to remove once the merge is confirmed stable, ask before deleting.
