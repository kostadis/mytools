---
name: feat/palace-isolation feature goal
description: Branch feat/palace-isolation — support running mempalace as both campaign-state tracker AND chat-session tracker without the two palaces contaminating each other.
type: project
originSessionId: bff24776-cb3b-45ae-b057-71bed7b02234
---
Branch `feat/palace-isolation` (off `kostadis-dev`, pushed to `origin` 2026-04-18) exists to enable dual use of MemPalace: one palace tracking D&D campaign state, another palace tracking Claude Code chat session state, with strict isolation so chat content never lands in the campaign palace (or vice versa).

**Why:** User runs D&D campaigns (see `mempalace-campaign` skill) and also uses MemPalace for general chat memory. Today those appear to share scope in ways that cause cross-contamination. Campaign palaces are curated narrative/canon; chat palaces are raw conversation mining — mixing them pollutes both.

**How to apply:** When reasoning about this feature, treat isolation as the core invariant — not a nice-to-have. Mining routes (hooks, miner, convo_miner), palace paths, and MCP server scoping all need to respect which palace owns which content. Before proposing designs, ask the user which mechanism they prefer: per-directory palaces, explicit palace selection at call time, config-declared palace-per-workspace, or something else.
