---
name: project-ensemble-replaces-claude-extraction
description: "Validated — the local-LLM ensemble matches Claude's distill extraction coverage on untuned chapters; Claude can be dropped from the EXTRACTION role (kept for synthesis)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 374c07c8-3825-4bfe-9ecf-1596ac85bef3
---

**Update (2026-05-30): the synthesis stage is now built and merged to `main`** — `synthesise_world_state.py` (PR #68) is `distill.py`'s synthesis pass with the ensemble `merged.json` corpus swapped in for Claude's `distill_extractions`. End-to-end local pipeline complete: `session.md → ensemble_extract.py → merged.json → synthesise_world_state.py → world_state.md`. Validated on chapters 50–55 (~5000 facts, opus-4-7): coherent late-campaign canon, correct current-state focus. Sessions are ordered by the `chapter_NN` index parsed from the filename, NOT by in-world date — late chapters have unsortable date facts ("current day", "12 days of Christmas"), so the filename index is the reliable chronological signal. `--quotes` defaults on but had to be OFF for the 50–55 run (quotes-on ~259K tok > 200K context). Open tail-straggler perf issue: [[project-ensemble-tail-straggler]].

**Decision (2026-05-29): drop Claude from the fact-EXTRACTION role; keep it for synthesis.** The local 5-lens ensemble ([[project-local-extraction-pipeline]], now with self-consistency samples + [[project-fact-atomicity]] fixes + [[project-embedding-merge]]) matches the coverage of `distill.py`'s Claude pass-1 (the `docs/distill_extractions/extract_NNN.md` files).

**Evidence — coverage vs the Claude reference, including two UNTUNED chapters** (prompts were tuned only on chapter_03):
- chapter_03 (tuned) vs extract_004: NPC 15/15, faction 3/3, location 7/7, thread 7/8.
- chapter_02 (untuned) vs extract_003: every entity/faction/thread present on inspection.
- chapter_05 (untuned) vs extract_006: NPC 15/15, thread 12/13; all location "misses" present (Trillimac 21 facts, Ormu 13, Lost Tomb 7×).

So chapter_03 was NOT train-on-test — coverage holds on unseen, structurally-different chapters (combat / escape / exploration).

**Reference-to-chapter mapping is off-by-one: `chapter_NN ↔ extract_(NN+1)`** (verified by proper-noun overlap; chapter_03↔extract_004 is the known anchor). The distill extracts derive from session summaries, so they can be RICHER than the bible chapter file the ensemble reads — coverage parity is therefore a conservative (hard) test.

**Boundaries on the claim:** (1) coverage-level, not claim-by-claim — the references are bundled prose, never atomized; deemed not worth it because Claude reasons correctly over present+true facts (the operative risk is a wrong fact with no corrective companion fact, mitigated by feeding `source_quote` into synthesis). (2) n=3 of 55 chapters. (3) Parity at higher compute (15 calls + merge vs Claude's 1) — fine given the local-hardware exploration goal; "runs on metal you own," not "cheaper."

**Methodology caveat:** the coverage harness `scratch_output/coverage_check.py` uses SUBSTRING matching for entities, which UNDER-counts — every apparent "miss" across all three chapters was a label/type mismatch (e.g. ref "Two unnamed Drow guards" vs ensemble guards-as-events; ref "Narrow passageway with Ormu fungus" vs ensemble "Ormu fungus"), not a real gap. To promote it to a standing eval tool, make entity matching embedding-based too.
