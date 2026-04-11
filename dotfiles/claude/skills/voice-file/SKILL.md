---
name: voice-file
description: Create a per-character voice file for session_doc.py narration. Reads session summaries and VTT transcripts to extract a character's personality, speech patterns, and player table behavior. Use when user asks to create a voice file, character voice notes, or narration guide. Invoke as /voice-file <character_name>.
tools: Read, Glob, Grep, Bash, Agent, Write
---

# Voice File Generator

Create a `{character}_voice.md` file for session_doc.py narration by deeply reading source material.

## Required Information

Before starting, you need:
1. **Character name** (from args or ask)
2. **Player name** (ask if not provided)
3. **Campaign directory** (detect from CWD or ui_config.yaml, or ask)
4. **Session summaries file** — the large summaries.md or equivalent
5. **VTT transcript(s)** — at least one .vtt file where the player speaks

Ask the user for anything you can't detect automatically.

## Workflow

### Phase 1: Read the summaries

Read the session summaries file. Focus on sections written from or about the target character. Extract:

- **How the character thinks** — internal monologue style, what they notice, what they miss
- **How the character speaks** — sentence structure, vocabulary, verbal tics, tone
- **What the character cares about** — goals, values, blind spots, contradictions
- **How the character relates to others** — who they trust, who frustrates them, their role in the group
- **Signature moments** — the scenes that define who this character is
- **The character's specific blindness** — what they consistently fail to see or understand
- **Dark humor, irony, emotional range** — how they handle stress, fear, joy

Read at least the first 10 chapters/sessions. Use Explore agents in parallel to cover more material if the file is large.

### Phase 2: Read the VTT transcript(s)

Find VTT files in the campaign's summaries/ directories. Read them and extract every line spoken by the player. Analyze:

- **How the player speaks at the table** — terse vs. verbose, questions vs. declarations
- **Mechanical engagement** — do they ask about AC, movement, spell slots? Or do they narrate?
- **Humor style** — jokes, sarcasm, silence as humor
- **Relative volume** — are they the loudest voice or the quietest? How does this shape their character?
- **How they describe actions** — first person narration? Third person? Just state the mechanic?
- **Verbal tics** — repeated words, filler phrases, characteristic expressions

### Phase 3: Synthesize the voice file

Write the voice file to `<campaign>/voice/{character_lower}_voice.md`.

The file MUST follow this structure (based on the established format in this campaign system):

```markdown
# {Character} — Voice Notes
*Drafted from {source description}. Edit freely — you know {pronoun} better than the document does.*

---

## The Core Thing
One paragraph capturing the single most important thing about how this character sees the world. This is the key the narration model needs to get everything else right.

## {Defining Trait 1}
A section exploring a major character trait with specific examples from the summaries.

## {Defining Trait 2}
Another major trait. Use as many sections as needed (typically 3-6).

## Speech Patterns — {Player} at the Table
How the PLAYER behaves during sessions. Terse? Verbose? Mechanical? Narrative? This section is about the human, not the character.

## Speech Patterns — {Character} in Narration
How the character sounds in the written summaries. Internal monologue style, sentence structure, vocabulary.

## Things They'd Say
5-10 characteristic quotes (verbatim from summaries or representative invented examples), each as a blockquote with italics and brief context in parentheses.

## Things They'd Never Say
4-6 bullet points of things that would break character.
```

### Key Principles

- **Two voices**: The voice file captures BOTH the player's table behavior AND the character's narrative voice. These are different and both matter for narration.
- **Show, don't tell**: Use specific examples from the summaries, not generic descriptions. "He thinks in predator-prey metaphors" is better than "He's calculating."
- **Find the contradiction**: The best voice notes identify what the character thinks they are vs. what they actually are. The gap is where the interesting narration lives.
- **Be opinionated**: The voice file should make strong claims about who this character is. Hedged, generic descriptions produce hedged, generic narration.
- **Invite editing**: The subtitle always says "Edit freely" — this is a starting point the player should customize.

## Output

Write the file and tell the user where it was saved. Remind them to review and edit it — they know their character better than any document does.
