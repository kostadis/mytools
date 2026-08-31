---
name: voice-smooth
description: Render corrected scene-extraction quote blocks into readable, in-voice prose in a derived scene_extractions_smoothed/ layer. Use when the user asks for /voice-smooth [session-dir] or wants voice-aware smoothing after session-summary-consistency.
metadata:
  short-description: Smooth scene quotes in character voice
---

# Voice Smooth

Turn raw, transcriber-corrected verbatim quotes into readable prose that still
sounds like the character who said it. Write the result to a derived
`scene_extractions_smoothed/` layer for `session_doc` to consume.

This is the Codex port of the Claude skill. Do not edit
`~/src/mytools/dotfiles/claude/skills/voice-smooth/` when changing this skill.

## Inviolable Rule

Never mutate the verbatim record. This skill only writes
`scene_extractions_smoothed/`; it does not edit the VTT,
`scene_extractions_new/`, or `scene_extractions/`.

Pipeline context:

```text
VTT
  -> scene_extractions_new/ or scene_extractions/
  -> voice-smooth
  -> scene_extractions_smoothed/
  -> session_doc narration
```

## Codex Compatibility

- Ask user questions in chat.
- Use `update_plan` for multi-step progress when useful.
- Use `apply_patch` for manual edits to tracked documents.
- Codex does not have the Claude Artifact review callback flow. For batch
  review, either present the flagged pairs in chat or write a normal Markdown or
  JSON review queue file in the session directory, then ask the user to provide
  decisions in chat.
- Human approval is required before treating the smoothed layer as ready for
  `session_doc`.

## What This Does

- Improves readability while preserving meaning: collapse run-ons, remove
  filler-as-noise, repair genuinely unreadable fragments only when meaning is
  unambiguous, and add punctuation.
- Preserves each character's register, vocabulary, rhythm, and tics from their
  voice file. Deliberate style is voice, not an error.
- Keeps names, numbers, mechanics, speaker labels, attribution, and factual
  content unchanged.

This is not transcription correction. If the source still contains obvious VTT
mishears, garbled names, or likely proper-noun errors, stop and flag them for
`session-summary-consistency`; do not silently smooth them away.

This is not narration. Produce cleaner quote blocks, not scene prose.

## Inputs

- `session-dir`: a `summaries/YYYYMMDD/` directory. Default to CWD only when it
  is already a session directory. If CWD is the campaign root, ask which session
  to use or choose the most recent `summaries/*/` that has a scene extraction
  directory.
- Scene files: `<session-dir>/scene_extractions_new/` or
  `<session-dir>/scene_extractions/`; detect whichever exists and call it
  `<scene-dir>`.
- Voice files: `<campaign-root>/voice/<char>_voice.md` and
  `<campaign-root>/voice/_genre.md`. These are authoritative.
- Player-to-character map: the glossary section `## Player names -> characters`,
  needed if scene summaries or labels still contain real names.

## Workflow

### 1. Confirm Review Mode

Ask whether the user wants post-calibration review in chat or as a review queue
file in the session directory. Ask every run; do not remember a default.

The one-scene calibration always happens in chat. It is a conversation about
how aggressively to smooth, and must settle before batching the rest.

### 2. Locate Guardrails

Find the scene extraction directory. If neither candidate exists, report that
and stop.

Find the campaign root by walking upward from `session-dir` until campaign
directories such as `docs/`, `notes/`, `summaries/`, or `voice/` identify it.
Read every `voice/*_voice.md` plus `voice/_genre.md` before smoothing any
character lines. Build a speaker-to-voice-spec map.

For speakers with no voice file:

- GM narration, OOC, and rules talk: render as clean, plain prose. Do not invent
  a voice.
- `GM as <NPC>`: use characterization from `docs/npcs/`, `notes/session_prep/`,
  `notes/sessions/`, or other session prep if present. If no source gives a
  voice, use neutral readable rendering.

### 3. Smooth Quotes

For each quote block under `## Verbatim moments`:

1. Identify the speaker and the applicable voice source.
2. Produce a smoothed version that is readable, in-voice, and faithful.
3. Keep OOC and table chatter lightly smoothed and near-verbatim. Preserve any
   OOC marker.
4. For mixed-attribution blocks where another speaker's reply appears inside a
   quote block, render each line in the correct voice and tag the interloper
   inline, such as `[GM]`, `[Kalan]`, or `[Dawnbringer]`. Do not silently move
   the line to another speaker label; flag the attribution issue upstream.

If a line cannot be smoothed without changing meaning, leave it close to
verbatim or mark the uncertain piece as `[unclear]`.

### 4. Write the Derived Layer

Write `<session-dir>/scene_extractions_smoothed/NN_slug.md`, mirroring each
source file's structure so it is a drop-in replacement for `session_doc`.

Preserve:

- frontmatter structure, with added or updated `source: voice-smoothed` and
  `from: ../<scene-dir-name>/NN_slug.md`
- `## Scene summary`, except for player-name scrubs described below
- moment ordering
- speaker labels
- quote block placement

Replace each verbatim quote's text with its smoothed rendering under the same
speaker label.

When copying `## Scene summary`, scrub player real names via the
`## Player names -> characters` map, such as replacing the GM's real name with
`GM`. Do not otherwise reword or fact-correct the summary. Flag summary garble
as an upstream extraction issue.

### 5. Calibrate First

On a first run for a session or campaign, smooth one representative scene,
present verbatim-to-smoothed pairs in chat, and ask the user to approve the
voice fidelity and grammar-fix aggressiveness before rendering the rest.

After calibration, render the remaining files and present review material
grouped by scene.

Flag any pair that:

- risks changing meaning
- risks flattening or over-correcting the character's voice
- required repairing an ambiguous fragment

Ask the user whether to approve, edit specific pairs, or request a different
smoothing pass for any character. Apply edits only to
`scene_extractions_smoothed/`.

### 6. Batch Review Queue

If the user selected file-based batch review, write a review queue in the
session directory, preferably
`<session-dir>/voice_smooth_review_queue.md`.

Include only flagged pairs as review items. Unflagged pairs may be summarized by
count per scene because their draft renderings are already in the smoothed
layer.

Each flagged item should include:

- stable id, such as `s04-q07`
- scene and quote index
- speaker
- voice source used
- verbatim text
- smoothed text
- flag reason
- clear decision options: approve, revert to verbatim, or discuss with proposed
  wording

When the user provides decisions:

| Decision | Action |
|---|---|
| approve | Leave the smoothed rendering as written |
| revert | Replace that one quote with its verbatim text in `scene_extractions_smoothed/` only |
| discuss with wording | Apply the user's wording to that quote |
| discuss character pass | Re-smooth that character's quotes and bring the new pairs back for review |
| unmarked | Leave the draft smoothed rendering in place, but report which ids were undecided |

If the user's note says the source quote is wrong, treat it as a
`session-summary-consistency` item and do not smooth it away.

## Hand-Off

After review, state that `session_doc` should read from
`scene_extractions_smoothed/`. The verbatim scene extraction directory and VTT
remain the permanent record.

## Conventions

- Voice files are authoritative; preserve voice and never homogenize characters.
- Readability is allowed; meaning changes are not.
- Clear grammar repairs are fine when they preserve meaning. Ambiguous repairs
  should stay near-verbatim or be flagged.
- Residual transcription mistakes belong upstream in
  `session-summary-consistency`.
- Human review gates the hand-off to `session_doc`.
