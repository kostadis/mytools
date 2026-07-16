---
name: Campaign prep query patterns
description: User's two dominant query types when working on campaign prep, and which tool fits each
type: project
originSessionId: 1162a388-0a05-46b9-9763-73c3bc0bf49f
---
The user's campaign-prep work produces two distinct query types:

1. **"Connect A to B"** — plot construction. Given two entities (NPC/faction/location/plot), what's the chain of relationships between them? This is a **graph path-finding** query. Deterministic traversal, no LLM needed for the lookup. LLM only renders plot ideas *after* the verified chain is in hand.

2. **"Is this behavior correct for person B given what happened to them"** — narrative consistency. This is NOT a graph query — it's semantic retrieval over prose (dossiers + summaries). MemPalace or `query.py` are the right tools.

**Why:** The user has tried MemPalace for connection-style queries and reports it works poorly for them — semantic search returns text similar to the query but can't traverse entity relationships. Graph (connections.py) fills that gap; MemPalace handles the prose-consistency gap. Do not try to unify the two into one tool.

**How to apply:** When designing or extending campaign tools, route connection/path queries through the graph (connections.py / future /paths endpoint) and route consistency/"what happened" queries through MemPalace or query.py. Don't overload the graph with narrative state; don't expect MemPalace to find multi-hop connections.
