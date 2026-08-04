---
name: project-local-grounding-docs
description: "how the OOTA grounding docs (world_state/campaign_state/party/npcs/threads) were built from the local ensemble pipeline, not distill.py"
metadata: 
  node_type: memory
  type: project
  originSessionId: 374c07c8-3825-4bfe-9ecf-1596ac85bef3
---

The four grounding docs were rebuilt for Out of the Abyss (2026-06-01) from the **local ensemble extraction**, not the per-tool Claude path. Method (extract once locally, small synthesis per doc): `ensemble_extract.py` → `gen-chNN/merged.json` (56 ch, 22,240 facts) → `facts_to_state.py` → per-entity current-state dossiers (`scratch_output/oota-state/`, 703) + threads track (`--types thread --render-only oota-threads.md`) → synthesis on **Opus 4.8**.

- **world_state**: `synthesise_world_state.py --dossiers 'oota-state/*.md' --dossier-min-facts 20 --threads oota-threads.md --party … --inventory … --backstories …` (89 entities ≥20 facts). The `--dossiers`/`--threads` inputs were ADDED to that script (PR #72).
- **npcs**: `scratch_output/to_planning_npcs.py` (deterministic converter, 0 API) → `oota-planning/npcs/` (221, planning.py format).
- **campaign_state / party**: those tools never got a `--dossiers` flag. The trick = copy our artifacts into an extract-dir as `extract_*.md` and run the tool's `--synthesize-only` path (skips its own Claude extraction). campaign_state fed world_state+threads; party fed the 4 PC dossiers + backstories.

**Outputs all in gitignored `scratch_output/` (`*_local.md`) — NOT promoted to `~/campaigns/out-of-the-abyss/docs/`.** Diff + copy by hand when satisfied.

**Full commands + caveats: `docs/cli/local_grounding_docs.md` (PR #73).** Key caveats: campaign_state is a derivation-of-a-derivation (only as rich as world_state); party lacks character sheets/arc-scores (class/level/player blank); **planning.md** built via `planning.py --npc <cut>` over an importance CUT of the npcs (≥10 facts AND (≥5 chapters OR seen since ch47) = 65 npcs, dropping the "I" pronoun-leak) — no real arc-scores, and a first-person "narrator/I" leak conflated a few entries (Narrator/Librarian/Yvenne). Token cost: ~9M local (free) + ~193K API total vs old ~3M API per full doc-set (~15× less opex; gap widens per extra doc). Relates to [[project-local-extraction-pipeline]], [[project-ensemble-replaces-claude-extraction]]; rationale in dgx-fun `local-compute-as-experiment-capital.md`.
