---
name: Working contexts — D&D vs mempalace dev
description: User's two main Claude Code contexts and how directory maps to activity
type: user
originSessionId: a3a83436-8023-4551-95fb-dc63d8f762d9
---
User operates in two primary contexts, distinguished by working directory:

- **Campaign directory** → D&D session work (planning, worldbuilding, NPC prep, session docs, campaign generator pipelines).
- **mempalace repo** (`~/src/mempalace`) → MemPalace development (feature work, PRs, architecture).

Implications:
- When in the campaign dir, frame suggestions around D&D workflows, session_doc.py, voice files, dossier merging, campaign generator tooling.
- When in the mempalace repo, frame around Python dev, tests, MCP tools, palace internals.
- Global tooling (like chat-palace hooks) is fine in both — palace isolation guarantees hooks only write to the chat palace, never to a curated campaign palace.
