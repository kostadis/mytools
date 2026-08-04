---
name: project-embedding-merge
description: ensemble_extract.py embedding-cosine fact merge — catches cross-subject duplicates the subject-keyed merge misses; calibration + threshold
metadata: 
  node_type: memory
  type: project
  originSessionId: 374c07c8-3825-4bfe-9ecf-1596ac85bef3
---

`ensemble_extract.py` has two merge paths. **Default** = `merge_facts` (subject-keyed: groups by `(type, normalized-subject)`, SequenceMatcher within group). It cannot collapse duplicates whose `subject` strings differ — the killer case is `event`/`thread` facts, whose subject is a synthetic free-text label the model invents per sample ("prisoners flee to Darklake tunnel" vs "...flee toward Darklake"), and phonetic-variant entity spellings (Velkynvelve / Velkenyvelve). Different subject → never compared → survive as separate `1×` singletons, undercounting agreement.

**Opt-in** = `merge_facts_embed` (flag `--embed-endpoint`, e.g. vllm-embed `http://192.168.1.147:8000`; or `$EMBED_ENDPOINT`). Clusters on **embedding cosine of the FACT TEXT, partitioned by `type` only** (subject dropped from the key). nomic-embed-text-v1.5, 768-dim, L2-normalized → cosine = dot product. Greedy against a fixed longest-first anchor.

**Calibration (measured 2026-05-29, chapter_03 facts, nomic, no task prefix):** true duplicates cosine **0.97–0.98** (incl. the Velkynvelve phonetic pair at 0.970); distinct-but-related facts (same scene/actor, different action — "Daz flees vrock" vs "Daz dies under rocks") **0.75–0.78**; unrelated 0.4–0.6. There is an **empty gap between 0.78 and 0.97**, so the default threshold **0.93** merges real dups and provably does NOT touch distinct facts. Audit of all 23 multi-variant event/thread clusters at 0.93: **zero over-merges**; the only residual is safe *under*-merges (a few near-dups left separate) — correct bias per the LLM-pipeline rule (better the human sees two near-dups than a distinct fact silently eaten).

**Result vs subject-keyed (same data):** unique 369→298, singletons 226→149 (**−34%**), high-confidence mass grew (n=4 facts: 12→27). Finishes what the atomicity fix started ([[project-fact-atomicity]]).

Safeguards: every collapsed phrasing preserved in a `variants` field (+ `subjects`) on the survivor, so merges are auditable and reversible by the human. Default path stays SequenceMatcher → **CI green with no Spark needed**. Relates to [[project-local-extraction-pipeline]]; the cross-subject normalization this fixes was the gap the ensemble docstring deferred as "a deliberately separate step."
