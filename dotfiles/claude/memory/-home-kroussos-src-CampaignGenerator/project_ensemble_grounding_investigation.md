---
name: project-ensemble-grounding-investigation
description: Ensemble grounding-doc investigation (2026-07-27/28) — read docs/design/EnsembleGroundingInvestigation.md before touching the ensemble fact pipeline
metadata: 
  node_type: memory
  type: project
  originSessionId: 430c4b5b-c271-4407-a7fb-569385db518c
  modified: 2026-07-28T15:45:43.446Z
---

An investigation on 2026-07-27/28 into "OOTA grounding docs stamped ch62, contain
ch61" found four defects sharing one pattern and produced a full write-up at
**`docs/design/EnsembleGroundingInvestigation.md`**. Read it before working on
`ensemble_merge`, `facts_to_state`, `synthesise_world_state`, or the extraction
lenses.

**The pattern:** the pipeline computes a signal, serialises it, then ignores it —
forcing a later stage to guess what it was already told. Second-order form:
atomization strips the syntax that carries attribution, so no downstream
clustering recovers it.

**Shipped:** #194 (recency-scoped dossier floor), #197 (embed merge reachable +
fallback legible), #200 (quote offsets → within-chapter event order).

**Open:** #195 (the attribution defect itself), #199 (session-summary.md already
holds the structure, 16/62 chapters), #201 (coverage report for hearsay-only
dossiers), #202 (narrative pass + scene-boundary chunking).

**Do not re-try these — tested and killed, with numbers in the doc:** agreement
as a filter (98% of facts are `n_samples: 1`), embed-merge rescuing the
attribution (facts stay singletons; correct-vs-inverted cosine 0.8465), a
contradiction detector (15 candidates campaign-wide, 14 benign).

**Live hazard:** OOTA's `npc_moziqodo.md` says "Current status: Alive" for a
dead antagonist, and #194's recency window now *admits* it into the world_state
payload (the old floor was hiding it by accident). Hand-correct it or accept the
error on the next regeneration.

Related: [[project_local_extraction_pipeline]],
[[project_ensemble_replaces_claude_extraction]], [[project_embedding_merge]],
[[feedback_llm_surfaces_candidates_not_decisions]].
