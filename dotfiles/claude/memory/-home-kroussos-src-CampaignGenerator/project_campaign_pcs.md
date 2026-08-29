---
name: project-campaign-pcs
description: "PC rosters for Phandalin and Storm King's Thunder campaigns — pre-filter from NPC dossier pools"
metadata: 
  node_type: memory
  type: project
  originSessionId: c525383c-2dcc-432a-a02c-9483830bfed4
  modified: 2026-08-15T04:45:26.445Z
---

PC rosters (same rule as [[project-oota-pcs]]: PCs are party.py's domain — pre-filter them from any NPC dossier set feeding world_state/planning synthesis):

- **Phandalin**: Brewbarry, Vukradin (alias: **Vucravinios**), **Valphine Sotorra**, Soma. party.yaml at `~/src/campaigns/Phandalin/config/party.yaml` (see [[reference_campaigns_repo_is_under_src]]).
  - **Widened 2026-08-15 by GM ruling** from "Valphine" to the sheet's own title, `Valphine Sotorra` (campaigns commit `6fb8f5e0`). Sweep for **both** forms. Note `docs/entity_registry.yaml` still has it the other way round — canonical `Valphine`, with `Valphine Sotorra`/`Valphine Sortorra` as aliases — and that divergence is deliberate-for-now, not an error to auto-fix.
- **Storm King's Thunder** (the "3HPP"): Orsik (aliases seen: Orsik Thornacious / Prince Thornacious, Orsik Zymorven), Thistle (Thistle Wendrod), Unla Kee (variants: Unla, Unla Key), Vardis. party.yaml at `~/stormgiants/stormgiants/docs/party/party.yaml`.

**Why:** ensemble extraction types everyone as `npc`; facts_to_state then builds PC dossiers (often the densest in the corpus, with alias-split fragments) that don't belong in the NPC pool.

**How to apply:** after any facts_to_state aggregation for these campaigns, delete `npc_<pc>*.md` including alias variants before synthesis. Caution: storm-giant has a separate real NPC `npc_lord_zymorven` — do NOT delete it when sweeping Orsik's Zymorven variants.
