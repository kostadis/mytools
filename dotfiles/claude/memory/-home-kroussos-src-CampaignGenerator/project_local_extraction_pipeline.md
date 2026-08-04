---
name: project-local-extraction-pipeline
description: Local-LLM fact extraction + Claude synthesis pipeline for converting D&D session text into atomic facts and downstream campaign documents
metadata: 
  node_type: memory
  type: project
  originSessionId: 1428518a-c522-44e4-a9f5-48555ab07280
---

A 5-pass local-LLM ensemble + Claude synthesis pipeline exists in CampaignGenerator for converting session source text into atomic facts and then into downstream campaign documents. Built on the DGX Spark for local extraction, Claude for synthesis.

**Why:** User wants to produce `world_state.md`, `party.md`, and `campaign_state.md` from session source. The existing `distill.py` does Claude-extract + Claude-synthesize; this pipeline replaces the extraction with local LLM (DGX Spark, "free" in $ terms) and uses Claude only for synthesis. Architecturally fits the LLM Pipeline Design Rule (extract → reviewable checkpoint → render).

**How to apply:** When the user asks about extraction, facts, or session-to-document workflows, this pipeline is the relevant context. Architecture: `session.md → ensemble_extract.py (5 passes) → merged.json → synthesise_*.py (Claude) → target_doc.md`.

**Key files** (verify against current state):
- `ensemble_extract.py` — 5-pass driver (small/large/sweep/temporal/interiority)
- `extract_facts.py` — single-pass extractor with `--agent NAME` and salvage parser
- `synthesise_polish.py` — Claude polish to extract_NNN.md shape (per-session)
- `synthesise_facts.py` — deterministic Layer-1 grouping (no LLM)
- `config/agents/extract_facts*.md` — 4 lens prompts (generalist, sweep, temporal, interiority)
- 8-type schema: npc, faction, event, location, object, monster, thread, date

**Strategic note:** `synthesise_polish.py` produces a per-session intermediate parallel to `distill.py`'s pass-1 output. The real goal is `world_state.md` (cumulative); the next planned script is `synthesise_world_state.py` that consumes merged.json across all sessions directly.

See [[reference-oota-inventory]] for the canonical OOTA name inventory.
