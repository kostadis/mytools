---
name: campaign-chapter-review
description: Use when reviewing or editing D&D campaign narrative chapter markdown generated from session transcripts, especially when the user provides a campaign root path and a current summary/chapter file. Loads per-campaign canon docs, party state, planning pressure, character voice files, and examples; edits to a new sibling file unless explicitly told otherwise.
---

# Campaign Chapter Review

## Overview

Review campaign narrative chapters as canon-bearing fiction, not generic prose. The goal is a clean edited copy that preserves session truth, character voice, campaign continuity, and the user's established chapter style.

The user normally provides:
- a campaign root path, such as `/home/kroussos/campaigns/Phandalin` or a WSL UNC path to it
- a current summary/chapter markdown file, usually under `summaries/YYYYMMDD/`

## Expected Campaign Layout

Given `CAMPAIGN_ROOT`, assume these files and folders unless the user says otherwise:

- `CAMPAIGN_ROOT/docs/campaign_state.md` — completed-content canon; do not contradict or replay
- `CAMPAIGN_ROOT/docs/world_state.md` — current setting/state truth
- `CAMPAIGN_ROOT/docs/party.md` — character state, bonds, items, active tensions
- `CAMPAIGN_ROOT/docs/planning.md` — forward pressure and GM intent; not necessarily revealed truth
- `CAMPAIGN_ROOT/voice/` — narrator voice guides, typically `{character}_voice.md`
- `CAMPAIGN_ROOT/examples/` — sample prose used to calibrate narrator/style

If a path is a Windows WSL UNC path like `\\wsl.localhost\Ubuntu-24.04\home\...`, read it directly or convert it to the matching WSL path for shell commands. Do not copy campaign files into the workspace unless the user asks.

## Workflow

1. Read the current chapter structure first:
   - line count
   - headings
   - first section
   - remaining sections as needed

2. Load the canon bundle:
   - `campaign_state.md`
   - `world_state.md`
   - `party.md`
   - `planning.md`

3. Load only the voice/example files needed for narrators present in the chapter. Prefer headings and filenames to identify narrators.

4. Review in four passes:
   - **Canon continuity:** names, locations, timeline, item ownership, resolved/open threads
   - **Narrator voice:** each POV should match its voice file and examples, not generic polished prose
   - **Transcript artifacts:** garbled phrases, accidental player/table wording, malformed quotes, repeated generated motifs
   - **Chapter clarity:** scene transitions, causality, spatial orientation, whether facts/inferences/beliefs are distinguished

5. Write an edited copy as a sibling of the original file unless the user specifies a destination. Use a conservative suffix such as:
   - `*-edited.md`
   - `*-reviewed.md`
   - `*-canon-edit.md`

6. Verify with a diff and a small targeted scan for known risk strings.

## Editing Rules

- Preserve the original file.
- Preserve event order unless a passage is clearly out of order and the session/chapter context proves the correction.
- Prefer small repairs over rewriting whole scenes.
- Do not invent session events, dialogue, or discoveries.
- Treat `planning.md` as hidden GM pressure unless the chapter text or canon docs show the party knows it.
- Keep character interiority character-specific:
  - factual uncertainty is fine in narration
  - revealed canon should not become stronger than the session supports
  - GM-only causes should remain implications unless already revealed
- Keep Markdown structure intact.

## Review Lens

Use these labels mentally while editing:

- **clarity:** confusing wording, unclear referents, scene geometry, missing setup
- **canon:** contradiction with campaign/world/party state
- **voice:** narrator does not sound like their guide/example
- **timeline:** location/order drift, premature references to later events
- **overclaim:** text asserts something as fact that should remain belief or inference
- **artifact:** transcript cleanup issue, malformed phrase, duplicated model pattern

## Preflight Script

For cheap mechanical checks, run:

```bash
python scripts/preflight_chapter.py CHAPTER.md
```

The script flags likely transcript artifacts and high-risk continuity words. It is not authoritative; use it as a checklist before and after editing.

## Output

When finished, report:
- edited file path
- original file left untouched
- the highest-signal categories of edits made
- any residual concerns that need GM judgment