---
name: UI redesign direction
description: The three core workflows the app should guide users through, and the origin of the current UX confusion
type: project
---

The app.py and session_doc_ui.py UIs evolved from debugging scripts. They present a flat list of tools with no workflow guidance — confusing even to the author.

**Three core workflows:**

1. **Initial campaign setup** (one-time): take old campaign notes → create world_state.md, campaign_state.md, adventure state. Uses `new_workspace.py`, then `distill.py`, `campaign_state.py`, `make_tracking.py`.

2. **Periodic maintenance**: update character sheets from D&D Beyond (`dnd_sheet.py`), refresh `party.md` (`party.py`), refresh `planning.md` (`planning.py`), re-run `campaign_state.py` after new sessions.

3. **Regular session workflow** (the main flow):
   - VTT extraction (`vtt_summary.py`) + gmassisstant recap + saga20 summary
   - Scene extraction (`session_doc.py --extract-only`)
   - Editor fine-tuning (`session_doc_ui.py`) — edit extractions + roleplay context per scene → narrate → assemble

**Directory convention:** workspace created via setup script, session data stored in `summaries/<date>`.

**Why:** The app needs to guide users through these workflows, not present a flat toolbox. Experimental one-step tools exist but aren't ready for heavy use.

**How to apply:** When reorganizing the UI, group pages by workflow, highlight the main session flow, and de-emphasize experimental tools.
