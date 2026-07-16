---
name: MemPalace wings — two use cases with different semantics
description: Campaign wings are a structured content DB (not conventional MemPalace); tools/project wings are the conventional agent-memory pattern; never consolidate
type: feedback
originSessionId: 5dd816fa-12b1-4df6-a38a-469a555f9886
---

The user's MemPalace hosts two fundamentally different use cases. They share the substrate but are queried and grown differently. Do not consolidate wings across them, and do not consolidate wings *within* either group.

**Use case 1 — D&D campaign content DB (NOT conventional MemPalace):**
Wings: `narrative` (9288 drawers — chapters), `phandalin`, `chronicle`, `abyss`
Semantics: a structured knowledge store for campaign material — NPCs, world lore, arcs, chapters. Queried as a content database for the campaign-generation pipeline. NOT agent autobiographical memory. Drawers here are source material, not session records.

**Use case 2 — Tools/project agent memory (conventional MemPalace):**
Wings: `-home-kroussos-src-mytools`, `mytools`, `wing_claude-code`
Semantics: conventional MemPalace — agent diary, decisions, code snippets, session records for work done in /home/kroussos/src/mytools. The auto-save Stop hook (mempal-stop-hook.sh) targets this use case.

**Why:** User pushed back on 2026-04-18 when I suggested merging the two tools wings, and followed up to clarify that the campaign wings are an entirely different use case from conventional MemPalace. The distinction matters because the "query before responding" protocol and AAAK diary conventions apply to use case 2, not use case 1.

**How to apply:**
- Describe wings as-is; never recommend merging, renaming, or migrating drawers unless explicitly asked.
- For questions about work/tooling/decisions, query the tools wings (`mytools`, `-home-kroussos-src-mytools`, `wing_claude-code`) or diaries.
- For questions about D&D campaigns, NPCs, world, treat the campaign wings as a content DB — search/traverse them as a knowledge source, not as "things I remember doing."
- Auto-save hook writes target the tools use case — don't dump session meta into campaign wings.
