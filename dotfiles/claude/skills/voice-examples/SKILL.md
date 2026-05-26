---
name: voice-examples
description: Create per-character style example files for session_doc.py narration. Use when the user asks for per-character examples, voice examples, or wants to make narrators sound distinct. Invoke as /voice-examples <name1>, <name2>, ...
tools: Read, Glob, Grep, Bash, Agent, Write
---

# Per-Character Voice Examples Generator

Create `examples/<firstname>.md` files for `session_doc.py` Phase 1 per-character example routing. Each file contains verbatim passages from the campaign's existing prose where **that specific character** carries the POV, dialogue, or emotional weight.

## What This Is For

The original `style-examples` skill produces a global pool of passages that every narrator sees. That causes regression toward an average voice — every character ends up sounding the same.

`session_doc.py`'s Phase 1 routes files in the `--examples` directory by character first-name match. A file named `thistl.md` or `thistl_examples.md` is appended to **only** Thistl's narration system prompt, framed as the authoritative voice target for that character specifically. This skill produces those files.

For the routing to fire, you also need `--characters "Thistl, Orsik, ..."` on the `session_doc.py` command line. The file's stem (lowercased, with optional `_examples` suffix stripped) must match a character's first name.

## Required Information

Before starting, ask for or detect:

1. **Character roster** — names to generate examples for (from `/voice-examples <names>` arg, or ask). Multi-name is common: `Thistl, Orsik, Vardis, Unla Key`.
2. **Campaign directory** — detect from CWD or ask. Output goes to `<campaign>/examples/`.
3. **Source material** — where the campaign's existing prose lives. Common locations:
   - `<campaign>/docs/chapters/` — a multi-chapter campaign bible (one file per chapter)
   - `<campaign>/summaries/` — per-session narrative summaries
   - A single large `summaries.md`
   Glob the campaign root for `chapter_*.md`, `summary_*.md`, or ask.

## Workflow

### Phase 1: Survey the source per character

For each character in the roster, use a Grep + Read pass to locate passages where they are central:

- **POV markers**: `### {Name}` or `#### {Name}` headings (some campaigns use sub-headings per POV)
- **First-person attribution**: `I {verb}` lines clearly belonging to this character — usually adjacent to their heading
- **Dialogue attribution**: `"..." {Name} said`, `"..." {Name} replied`, or speaker labels like `**{Name}:**`
- **Direct address**: passages where the prose names the character repeatedly (3+ times in a paragraph) — usually signals they're the scene's focus

For long source trees (e.g. 80+ chapter files), spawn parallel Explore agents — one per character — to keep context lean. Hand each agent a short brief: the character name, the chapters dir path, what to look for, what *not* to do (don't summarise, don't rewrite, just locate and return passage boundaries).

### Phase 2: Select 3–5 passages per character that span their range

For each character, pick passages that together teach the model:

- **Introspection** — the character alone with their thoughts (italicised inner monologue, what they notice, what they fear)
- **Dialogue with subtext** — a conversation where their voice cuts through, with internal commentary running underneath
- **Action / decision under pressure** — a moment that shows how they think when stakes are high
- **A signature emotional beat** — a scene that captures who they are at their core (grief, fury, joy, betrayal)

Don't pick five introspection passages. The point of having multiple is to teach the model how the character sounds across all the modes narration will need.

Length: each passage 300–1500 words. A passage too short doesn't establish rhythm; too long crowds the prompt. Trim at natural paragraph boundaries — never mid-paragraph.

### Phase 3: Write the per-character files

For each character, write to `<campaign>/examples/<firstname_lower>.md`.

- **First name only** — `unla.md`, not `unla_key.md`. The router matches on `narrator.lower().split()[0]`.
- **Lowercased** — `thistl.md`, not `Thistl.md`. The router lowercases keys at load time, but be consistent.
- **No `_examples` suffix needed** — both `thistl.md` and `thistl_examples.md` route to Thistl. Pick `<firstname>.md` for clarity.

File format:

```markdown
# {Character} — Voice Reference Passages
*Verbatim excerpts from {campaign} source material. Read these before narrating {Character}.*

---

## From {chapter or session reference}: {brief scene label}

{verbatim passage — exact text, including all formatting, italics, blockquotes, line breaks, typos}

---

## From {chapter or session reference}: {brief scene label}

{verbatim passage}

---

(3–5 passages total)
```

### Hard rules

- **Verbatim only.** Copy the passage exactly. Preserve italics, bold, blockquotes, sound effects, em-dashes, the writer's idiosyncrasies. A cleaned-up version teaches the model a cleaned-up voice — that's exactly the regression we're fixing.
- **No commentary, no analysis.** Don't write "this passage shows how Thistl uses dry humor to deflect emotion." The model reads these as prose to emulate, not as prose to study. The brief scene label in the heading is the only allowed framing.
- **Preserve the original character headings** if the source uses `### {Name}` per-POV sub-headings — they're part of the structural pattern the model needs to learn.
- **Different passage per character.** Don't reuse the same chapter excerpt across multiple files. If a scene has both Thistl and Orsik POVs, split it: Thistl gets her sections, Orsik gets his.
- **If a character has no clear POV in the source**, write the file anyway with passages where they're heavily dialogued or repeatedly named. Note this in the subtitle: `*This character has no first-person POV in the source — passages below show how they appear in third person.*` Don't invent prose.

## Output

For each character, report:
- File path written
- Source chapter(s) the passages came from
- A one-line note on what range the passages cover (e.g. "introspection, dialogue, combat" or "limited source — third-person only")

Then remind the user:

1. To pass `--examples <campaign>/examples/` on the next `session_doc.py` run.
2. That `--characters "Thistl, Orsik, ..."` must include every name whose file should route — otherwise the file falls into the global pool.
3. To skim each file and prune passages that misrepresent the character. The skill produces a starting point, not a final answer.
