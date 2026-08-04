---
name: reference-oota-inventory
description: Canonical Out of the Abyss name and entity inventory used as grounding for Claude synthesis
metadata: 
  node_type: memory
  type: reference
  originSessionId: 1428518a-c522-44e4-a9f5-48555ab07280
---

The Out of the Abyss campaign has a complete proper-noun inventory at:

`~/campaigns/out-of-the-abyss/notes/sessions/out_of_the_abyss_module_inventory.md`

~700 lines covering NPCs (organised by chapter), demon lords, deities, locations, items, factions, and concepts. Compiled by the user from the module bible (`docs/background/Out of the Abyss.md`).

**How to apply:** Pass this file to `synthesise_polish.py` (and any future Claude-synthesis step) via `--inventory`. It dramatically improves output quality — Claude uses it to:
- Normalize phonetic spelling drift (Velkenyvelve → Velkynvelve, Sloopdopblop → Sloobludop)
- Resolve same-character variants (Sarith / Sathir / Serith)
- Enrich character profiles with canonical race/role/background details that session extracts don't capture
- Distinguish PCs from NPCs from creature-types

Source-of-truth doc; pipeline reads it, never writes to it.
