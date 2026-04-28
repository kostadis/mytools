# How `adventure_model.py` Works and Why It Solves the Hierarchy Problem

## The core problem

5etools has an **index-alignment constraint**: `adventure[0].contents[N]` maps to `adventureData[0].data[N]` by direct array index. Every top-level `data[]` entry **must** be `type: "section"`. If Claude produces a non-section entry at the top level (an `entries`, `inset`, bare string, etc.), it shifts every subsequent chapter's sidebar navigation by 1. One misplaced entry breaks the entire document.

The original converters hit this in three ways:

1. **Claude decides the structure.** Each chunk prompt says "return a JSON array of 5etools entries." Claude creates `section` entries when it feels like it, sometimes wrapping rooms in a "Room Key" section, sometimes emitting bare `entries` blocks at the top level. The converter has no say in what becomes a chapter.

2. **Post-hoc repair is lossy.** The original pipeline tries to fix this with a hoist step (fold non-sections into the preceding section) and `fix_adventure_json.py` after the fact. But by that point the structure is already wrong — you're guessing which orphaned entries belong to which section.

3. **TOC is synthesized from Claude's output.** The `contents[]` TOC is built from whatever sections Claude produced, so if Claude got the section boundaries wrong, the TOC is also wrong.

## What `adventure_model.py` changes

The model inverts the control: **the script creates the structure, Claude fills the content.**

### 1. The TOC-driven converters create `SectionEntry` objects themselves

In `pdf_to_5etools_toc.py:332`:

```python
section = SectionEntry(
    name=node.title,      # from PDF bookmark, not Claude
    entries=parsed,        # Claude's content goes inside
    page=node.start_page,
    _ctx=ctx,
    _path=path,
)
```

The converter reads the PDF bookmarks via `TocNode`, and for each top-level bookmark it creates a `SectionEntry`. Claude is only asked to fill the `entries[]` array for that one chapter. Claude never creates top-level sections — it can't introduce the misalignment.

### 2. The TOC is built from bookmarks, not Claude output

`build_toc_from_tree()` builds `contents[]` directly from the `TocNode` tree. The `TocEntry` and `TocHeader` dataclasses mirror the exact 5etools TOC format. Since both `data[]` and `contents[]` come from the same bookmark tree, they're guaranteed to be aligned by construction.

### 3. Validation during construction, not after serialization

Every dataclass runs `__post_init__` validation:

- `SectionEntry` warns if name is missing, validates tags in the name, checks ID uniqueness, validates all child entries recursively
- `validate_tags()` catches `{@scroll}`, `{@npc}`, and other bad tags Claude invents
- `ImageEntry` errors if `href` is missing
- `ListEntry` validates its `items[]`
- `TableEntry` checks `colLabels`/`rows` consistency

This happens at construction time via the `BuildContext` that's threaded through every object. In WARN mode it collects all issues; in STRICT mode it raises immediately.

### 4. Validation retry in `claude_api.py`

The `validate_entries()` function in `claude_api.py` creates a `BuildContext`, runs `parse_entry()` on every item Claude returned, and collects errors. If errors are found, `call_claude()` retries with a correction prompt that includes the specific errors:

```
Your previous response had the following validation errors:
- chunk-0000[0].entries[3]: unknown tag '{@scroll fireball}'
- chunk-0000[0].entries[5]: image has no href

Please fix these errors and return the corrected JSON array.
```

This catches problems **before** they make it into the output file, rather than discovering them when the 5etools renderer throws a JS error.

## Where it's used

| Consumer | What it uses | Why |
|----------|-------------|-----|
| `claude_api.validate_entries()` | `BuildContext`, `parse_entry` | Validates every Claude response and triggers retry on errors |
| `pdf_to_5etools_toc.py` | `SectionEntry`, `EntriesEntry`, `HomebrewAdventure`, `TocEntry`, `TocHeader`, `parse_entry`, `BuildContext` | Builds the document structure from bookmarks, uses Claude only for content |
| `pdf_to_5etools_ocr_toc.py` | Same as above | OCR variant, reuses all assembly/TOC functions |
| `pdf_to_5etools_1e_toc.py` | Same as above | 1e variant, reuses all assembly/TOC functions |

## The key insight

The original converters treat Claude as the **architect** (it decides what's a section, what's nested where) and then try to repair the result. The model-based approach treats Claude as the **content writer** (it fills in entries for a pre-defined structure) and validates its output against typed constraints. The hierarchy is determined by the PDF's own bookmark tree — the one source of truth that was there all along.
