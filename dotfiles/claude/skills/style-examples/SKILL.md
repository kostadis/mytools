---
name: style-examples
description: Create style example files for session_doc.py narration by extracting representative passages from the user's campaign summaries. Use when user asks to create examples, style references, or writing samples for a campaign.
tools: Read, Glob, Grep, Bash, Agent, Write
---

# Style Examples Generator

Create `examples/*.md` files for session_doc.py narration by extracting representative passages from the user's own writing.

## What These Files Are For

session_doc.py Pass 5 (narration) loads all `*.md` files from the `--examples` directory as style references. The model reads them before writing narration to match the user's tone, sentence structure, POV handling, humor, and pacing. These must be **verbatim excerpts** from the user's writing — not rewritten, not summarized, not improved.

## Required Information

Before starting, you need:
1. **Campaign directory** (detect from CWD or ui_config.yaml, or ask)
2. **Session summaries file** — the source of the user's writing
3. **How many chapters/sessions to read** (default: first 10)

Ask the user for anything you can't detect automatically.

## Workflow

### Phase 1: Read the source material

Read the summaries file thoroughly (at least the first 10 chapters/sessions). Use Explore agents in parallel for large files. As you read, identify passages that showcase distinct writing qualities:

**Look for these style dimensions:**
- **Character introspection**: Internal monologue, italicized thoughts, how characters observe and assess
- **Dialogue and political maneuvering**: Conversations where characters lie, negotiate, manipulate — with internal commentary running underneath
- **Combat and consequences**: How violence is described (terse? elaborate?), aftermath and emotional cost
- **Ensemble comedy**: Multi-character scenes with humor, rapid NPC introductions, escalating absurdity
- **Suspense and action**: Chases, stakeouts, infiltration — pacing and tension techniques
- **POV switching**: How the writer moves between character perspectives within a chapter
- **NPC voice**: How the writer gives distinct personalities to NPCs through dialogue and description

**Also identify the writer's signature patterns:**
- Sentence rhythm (staccato fragments? flowing prose? both depending on mood?)
- How they handle the gap between internal monologue and spoken dialogue
- Humor style (dry? dark? absurdist? observational?)
- Use of sound effects, italics, formatting
- First person vs. close third person and when they switch
- How they describe physical spaces and people

### Phase 2: Select and extract passages

Choose 4-6 passages that together cover the full range of the writer's style. Each passage should be:
- **Self-contained**: Makes sense without context (or with minimal context)
- **Verbatim**: Copied exactly from the source, not rewritten or edited
- **Substantial**: Long enough to demonstrate a pattern (typically 500-2000 words each)
- **Distinct**: Each example showcases a different facet of the writing

**Good example categories** (pick 4-6 that fit this writer's strengths):
1. Introspection and observation — a character alone with their thoughts
2. Political maneuvering — dialogue with subtext and internal commentary
3. Ensemble comedy — multiple characters bouncing off each other
4. Combat and consequences — violence and its emotional aftermath
5. Suspense/action — a chase, infiltration, or stakeout
6. World-building — how the writer describes places and introduces new settings
7. Emotional weight — a death, a betrayal, a moment of genuine feeling

### Phase 3: Write the example files

Write each example to `<campaign>/examples/<descriptive_name>.md`.

Each file should:
- Start with `# Style Example: <category>` as a title
- Use `---` separators between non-contiguous passages
- Preserve the original character headings (### Zephyr, #### Sequoia, etc.)
- Preserve all formatting: italics, bold, blockquotes, line breaks
- Include NO commentary, NO annotations, NO "this shows the writer's tendency to..."
- Be **pure source material** — the model reads these as writing to emulate, not writing to analyze

### Key Principles

- **Never rewrite**: These are the user's words. Copy them exactly. Typos, unconventional formatting, and all. The model needs to learn the ACTUAL voice, not a cleaned-up version.
- **Variety over quality**: A single brilliant passage teaches one thing. Five good passages covering different modes teach the model to match the writer across all situations.
- **Show the range**: If the writer does staccato combat AND flowing political dialogue AND dark humor, the examples need all three. Don't just pick the "best" writing — pick the most representative.
- **Include the weird stuff**: If the writer uses sound effects (*Crack*, *Twang*), animated vegetables, six repetitions of "Shit" — include those. The unusual choices ARE the voice.
- **Multi-POV is a feature**: If the writer switches between character perspectives within scenes, the examples should show this. It's a deliberate technique the model needs to learn.

## Output

List the files created with a brief note on what each one teaches the model. Remind the user they can add more examples over time — the model reads all `*.md` files in the directory.
