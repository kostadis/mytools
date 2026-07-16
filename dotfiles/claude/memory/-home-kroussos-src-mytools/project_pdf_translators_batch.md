---
name: project_pdf_translators_batch
description: pdf-translators batch pipeline reworked into memory-cheap multi-pass (extract/Marker/split/encode) in June 2026
metadata: 
  node_type: memory
  type: project
  originSessionId: e41318a0-8e8b-4419-94f1-e9098416459a
---

`pdf-translators/batch_convert.py` was reworked (June 2026) from "spawn a
`pdf_to_5etools_v2.py` subprocess per doc" into a multi-pass pipeline, because
driver-machine RAM (the WSL box; the Spark endpoints do inference) capped
concurrency: each converter subprocess re-paid a ~53 MB PyMuPDF+modules import,
N× for N workers, and extraction re-ran on every retry.

**The pipeline now:**
- `batch_convert.py --phase extract` — fast PyMuPDF structural extraction (RAM-
  bound process pool) → `<stem>-extract.json` (granular: TocNode tree + per-page
  text). Docs that route to Marker are deferred as `needs_marker`, not failed.
- `batch_marker.py` — **standalone tool, run manually after the fast pass** (the
  user wanted Marker isolated; it loads ~5 GB GPU weights). Writes the same
  `<stem>-extract.json` (`kind="lines"`). Currently per-doc `marker_single`
  (reloads weights each doc — load-once via Marker's batch CLI is a TODO).
- `batch_convert.py --phase encode` — **in-process** (imports paid once, shared
  across worker threads; subprocess path fully removed) LLM conversion. Per doc:
  `chunk_cache.load_extract` → `split_to_chunks` at the **endpoint's** char
  budget → `encode_chunks`.

**Key design points (the non-obvious why):**
- `chunk_cache.py` stores the *granular* extract (tree + text units), not pre-
  split chunks. Splitting is a pure re-runnable function of (tree, units, cap),
  so re-chunking with a tighter cap is free (no PDF/Marker) and each doc can be
  chunked per-endpoint.
- `assemble_adventure` groups by `id(spec.root)` / walks by `id(node)`; that
  identity can't survive JSON, so chunk_cache assigns each TocNode a **stable
  key** and rebuilds the tree on load — split-after-load keeps identity
  consistent. This is the load-bearing correctness point (see `test_chunk_cache.py`).
- `convert()` is now a thin wrapper over `extract_structure` → `split_to_chunks`
  → `encode_chunks` in `pdf_to_5etools_v2.py`; CLI + all tests unchanged.

**Accepted tradeoffs:** no hard per-doc timeout kill (subprocess removed; bounded
by per-chunk HTTP read timeouts); a `fitz`/Marker crash now lives in the isolated
extract pool / Marker tool, not the encode driver.

CLAUDE.md was NOT updated to document this — offer to, if revisiting. Related:
[[project_mytools_repo]].
