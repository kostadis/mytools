---
name: campaign-prep
description: Load the four grounding documents for the current campaign before session prep. Use when the user says "campaign prep", "prep mode", or invokes $campaign-prep or /campaign-prep. This loads context; use gm-session-prep when the user requests a session prep document.
---

# Campaign Prep Mode

Load the campaign's four grounding documents before working on beats, encounters, NPC drafts, or session arcs. This is a read-only context-loading skill, not a grounding refresh or a written briefing.

## Locate the campaign

Confirm the working directory with `pwd` and follow applicable `AGENTS.md` instructions. Use the campaign directory named by the user or established in the conversation. The four documents live under its `docs/` directory.

If the working directory is nested inside a campaign, locate its enclosing campaign directory. If it is a campaigns root (typically `$CAMPAIGNS_ROOT`, default `~/src/campaigns/`) or another directory without a clear campaign, inspect the immediate layout for an unambiguous campaign. Ask which campaign to use only when it cannot be determined. Do not mix documents from different campaigns.

## Read all four grounding documents

Use shell reads through the available execution tool. Batch the four independent reads in one `functions.exec` call with `Promise.allSettled` when available, and inspect every result:

- `docs/campaign_state.md`: current party situation, ongoing arcs, recent sessions.
- `docs/world_state.md`: distilled NPC, faction, location, and thread facts.
- `docs/planning.md`: GM plans, upcoming beats, intended arcs.
- `docs/party.md`: composition, relationships, and mechanical state.

Read each document in full unless it exceeds 2,000 lines. For a larger document, read its first and last 500 lines and disclose the skipped range. Size tool output to avoid silent truncation; retrieve any unexpectedly truncated portion before claiming a full read. If a document is missing, note it and continue with the others. Do not regenerate missing documents as part of this skill.

## Acknowledge readiness

Give a brief status, normally 3–6 lines:

- Campaign name, from the documents.
- Where the party currently is.
- Most recent session or chapter played.
- Open threads or near-term beats flagged in planning.
- Any missing documents or skipped portions.

Do not summarize the documents in detail. If the user has only requested prep mode, end with “Ready for prep — what are we working on?” If they already supplied a prep task, continue with that task instead of asking them to repeat it.

## Keep the context in use

Treat these documents as working references for subsequent prep in this conversation. Ground factual claims in their contents and distinguish proposed inventions from established canon. If a needed fact is absent, say so and consult relevant chapter files, summaries, dossiers, or a memory search tool if available.

Follow the campaign's documented source hierarchy in `AGENTS.md` and, where applicable, `CLAUDE.md`. The grounding documents are CampaignGenerator outputs and can drift from summaries, VTT transcripts, voice files, and chapter sources. Voice files (`voice/`) and chapter splits (`docs/chapters/`) take precedence over grounding prose when they conflict; verify precision questions against the authoritative source.

This skill never writes to the grounding documents. Use the grounding-refresh workflow when the user requests their regeneration or correction.
