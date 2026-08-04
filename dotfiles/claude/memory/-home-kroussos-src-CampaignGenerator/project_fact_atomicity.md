---
name: project-fact-atomicity
description: "In the fact-extraction ensemble, one fact MUST = one state-change; bundled facts silently break dedup, agreement counting, verification, and attribution"
metadata: 
  node_type: memory
  type: project
  originSessionId: 374c07c8-3825-4bfe-9ecf-1596ac85bef3
---

The atomic fact is the unit of the entire extraction pipeline — the unit of dedup, self-consistency agreement counting, verification, and attribution. The moment one record bundles multiple claims ("Buppido warns of spiders, suggests burning the tower, makes a wager"), all four break at once: bundle A never matches bundle B in dedup, each unique bundle scores as a `1×` singleton so reproduced claims masquerade as noise, "is it real?" has no clean verdict for a 3-in-1, and one source span can't back three actions.

**Diagnostic tell:** a `source_quote` containing `...` (stitched non-contiguous spans) means the model bundled. Measure bundling rate by counting facts whose quote has `...` or whose `fact` text has ≥2 finite verbs.

**Measured 2026-05-28 on chapter_03 (Qwen3-Next 80B, 3-sample run):** bundling rate by lens — sweep **41%** (77 of 88 ellipsis-quotes), interiority 14%, large 10%, small 2%, temporal 0%. Sweep was worst because its "breadth/exhaustive per entity" mandate nudged the model into one summary fact per entity. Tightening the sweep prompt (prominent "one fact = one state-change" rule + the real Buppido bundle as a WRONG→RIGHT worked example + "the ellipsis is the tell") dropped sweep bundling **41%→4%**, ellipsis quotes 77→2. Proof it fixed agreement: the "points out very large spiders" claim went from a buried `1×` bundle-fragment to the top-confidence `[3×]` fact across samples.

Lens→prompt map: `small` and `large` both use `config/agents/extract_facts.md` (generalist, larger chunks bundle more); `sweep`/`temporal`/`interiority` have their own `extract_facts_*.md`.

This is the local concrete instance of the global "extraction is selection, not interpretation / do not abstract" rule — a bundled fact IS abstraction (summarizing a scene into one sentence). Atomicity is **upstream** of dedup, embedding-merge, and self-consistency; none of them work on bundled facts, so fix atomicity before calibrating `n_samples` against a gold set. Relates to [[project-local-extraction-pipeline]] and [[reference-two-spark-ensemble-perf]].
