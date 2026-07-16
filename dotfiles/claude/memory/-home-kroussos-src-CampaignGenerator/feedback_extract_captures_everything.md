---
name: Extract phase captures everything, synthesis decides scope
description: In the extract → synthesize pipeline, extract prompts must preserve all named NPCs/factions (including deceased and referenced-but-absent); scope and consolidation decisions only happen in synthesis.
type: feedback
originSessionId: cc0e0a63-3e43-4f7c-a877-0265b2e8263a
---
The extract phase is exhaustive capture. The synthesis phase decides what matters, what to fold, and what to drop.

**Why:** The user corrected an earlier iteration where the roster-seeded extract prompt was omitting deceased NPCs (Cryovain — corpse in play, folded into another NPC's section) and referenced-but-absent NPCs (Meril — mentioned in dialogue as a mentor but not physically present). The LLM was making scope decisions at extract time that belong at synthesis time. Extract drops are invisible; synthesis drops are reviewable because the source extracts still exist.

**How to apply:** When writing or editing any extract system prompt in this pipeline (`EXTRACT_SYSTEM`, `BUILD_EXTRACT_SYSTEM`, and the equivalents in distill.py / campaign_state.py / party.py / vtt_summary.py), include explicit rules that:
1. Every named NPC/faction mentioned gets captured — no scope calls about who is "important enough."
2. Deceased NPCs still count if corpses, remains, or postmortem discussion are in play.
3. Referenced-but-absent NPCs still count when meaningfully discussed (mentors named, leaders debated, owners of items in play). Physical presence is not required.
4. Do not fold one NPC's activity into another NPC's section (only applies to per-NPC-section prompts like `BUILD_EXTRACT_SYSTEM`).

Synthesis prompts should NOT inherit these rules — synthesis's job is consolidation, and preserve-everything rules would fight its purpose.
