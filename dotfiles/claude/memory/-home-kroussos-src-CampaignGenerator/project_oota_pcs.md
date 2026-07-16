---
name: Out of the Abyss player characters
description: PC names for the Out of the Abyss campaign — these should never appear as NPC dossiers; the LLM extraction occasionally leaks them in despite the prompt instruction
type: project
originSessionId: 044d56ee-a230-4e04-88b4-7060e060202a
---
The Out of the Abyss campaign (~/campaigns/out-of-the-abyss/) has these player characters:

- **Daz** — drow magic user
- **Grygum** — orc, has The Platinum Chronicle: Discourses on the Abyssal Blight
- **Thorin** — has carried Stool the myconid sprout
- **Zalthir** — drow

**Why:** `planning.py --build-dossiers` is supposed to skip PCs (per the BUILD_EXTRACT_SYSTEM prompt: "Only include named NPCs — not player characters"), but the LLM occasionally extracts them anyway. After 2026-04-18 build run all four appeared as NPC dossiers (`daz.md`, `grygum.md`, `thorin.md`, `zalthir.md`) and had to be deleted manually. They were also auto-clustered with similar-named NPCs (Zalthir↔Sarith, Daz↔Dasco Pickshine), which would have caused incorrect merges if not caught.

**How to apply:** When running `/dossier-merge` on `~/campaigns/out-of-the-abyss/docs/npcs/`, scan for these four filenames before clustering. If found, delete them outright (user has confirmed delete-not-move is the preferred handling). Then re-evaluate any clusters that included a PC — the remaining members are usually a real NPC group whose merge becomes obvious once the PC is removed (e.g., Sarith family with Zalthir removed = clean Sarith spelling-drift cluster).

There may be more PCs — check `docs/party.md` or `partyfile.md` if encountering other suspect filenames.
