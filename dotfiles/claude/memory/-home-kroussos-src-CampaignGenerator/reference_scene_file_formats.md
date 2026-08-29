---
name: Session doc file formats
description: Exact on-disk format of scene output files and extraction files produced by session_doc.py
type: reference
---

## Scene output files (`sceneN.md`)

Written by `session_doc.py --by-scene` pass 5 (narration). One file per scene.

```
# {session-stem}


---

## {Narrator} — {Scene Name}

{narrative prose, multiple paragraphs}

---
```

Key details:
- Starts with `# session-stem` (e.g. `# session-mar`), then TWO blank lines, then `---`
- Ends with a trailing `---` (narrative beat closer — always present)
- `## Narrator — Scene Name` heading uses em-dash ` — `

Assembly must strip BOTH leading title/`---` block AND trailing `---` from every scene
before joining with `\n\n---\n\n`, otherwise trailing `---` + join separator = double `---`.

## Extraction files (`scene_extractions/NN_narrator_scene_slug.md`)

Written by `session_doc.py` pass 4 (extraction). One file per scene.

```
**{Beat Title}**
{description of what happened}
{Character}: "{verbatim quote}"

---

**{Beat Title}**
...
```

Optional first line: `tokens: N` (per-scene narration token override, stripped before use).

No title header — extraction files start directly with `**Beat Title**`.
