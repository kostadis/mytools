---
name: project_drive_tagger_prompt_vs_consolidation
description: "drive-tagger compound regeneration needs BOTH the facet prompt AND consolidation — prompt alone can't stop neighbor imitation"
metadata: 
  node_type: memory
  type: project
  originSessionId: 8ea9a23f-0cdc-4d22-bb8f-33b6b523c1d2
---

The drive-tagger enrichment prompt was rewritten (2026-07-04, `JUDGE_PROMPT` +
`FACET_VOCABULARY` in `src/drive_tagger/prompts.py`) so the local Qwen judge emits
atomic facets on four axes (aesthetic / genre / content-type / subject) instead of
mashed compounds like `Cosmic Horror`. A/B probes against live Qwen proved two
distinct vectors, only one of which the prompt fixes:

- **Invention vector (prompt FIXES this):** with no compound-tagged neighbor
  anchoring it, the model stops inventing new compounds and decomposes into the
  curated facets (~30→8 compound assignments across 8 files). The taxonomy no
  longer grows NEW compounds.
- **Imitation vector (prompt does NOT fix this):** when a `find_similar` neighbor
  is already tagged with a compound that still exists in the taxonomy, "PREFER
  REUSING" makes the model imitate it verbatim (OLD 8 → NEW 7, unchanged). A
  positive-framing V2 moved it 0. **No prompt can make Qwen avoid a *fitting
  existing category* it sees on a neighbor without negation — which Qwen ignores
  (see [[feedback_qwen_negation_blindness]]).**

**Why:** the prompt and the human consolidation ([[project_drive_tagger_pass2_faceting]])
are complementary, not alternatives. Prompt stops NEW invention → makes
consolidation durable. Consolidation *deletes* existing compounds → a deleted
`Cosmic Horror` can't anchor a neighbor, so the prompt becomes effective. As the
corpus is consolidated, neighbors become atomic and the two reinforce.

**How to apply:** don't re-attempt to solve compound regeneration with prompting
alone — it's a known dead end for the imitation vector. Progress requires
consolidation to keep removing compound categories from the store. The prompt's job
is only to stop the bleeding (no new compounds), not to clean existing ones.
