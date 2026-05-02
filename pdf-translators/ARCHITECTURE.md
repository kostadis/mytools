# pdf-translators — Architecture Reference (for Tool Builders)

This document is for someone who wants to **build new tools on top of this
codebase without reading 17 kLOC of Python first**. It maps the public
surface area: what each module does, the precise functions/constants you
reuse vs. wrap, file:line references, the data-shape contracts between
stages, and the safe extension points.

The existing `architecture.md` is a v1-era diagram tour and is stale on
some routing details (the six v1 converters are gone — see `v1.0` tag).
This file supersedes it for planning purposes.

---

## 1. Mental model: three layers, one data shape

Everything in this repo is one of:

1. **Producers** — turn a PDF into 5etools adventure JSON
   (`pdf_to_5etools_v2.py`, `extract_monsters.py`, `merge_patch.py`,
   `patch_5e_chapters.py`, `convert_1e_to_5e.py`).
2. **Editors / fixers** — Flask UIs that load that JSON, mutate it,
   write it back (`adventure_editor.py:5104`, `toc_editor.py:5101`,
   `toc_fixer.py:5102`, `monster_editor.py:5103`, `app.py:5100`).
3. **Validators** — pure functions that read the JSON and report problems
   (`validate_adventure.py`, `validate_tags.py`, and the
   `adventure_model.py` parser used by both producers and validators).

The single boundary object is the **5etools homebrew adventure JSON**
(see §3). Every tool reads or writes that file. New tools should
likewise produce/consume that shape rather than introduce a new format.

```
PDF ──► pdf_to_5etools_v2 ──┐
                            │
               merge_patch ─┼──► adventure.json ──► editors / validators
              patch_5e_ch ──┤        ▲   │
            extract_mon ────┘        │   ▼
                                     └── bestiary.json (sibling)
```

---

## 2. Shared library surface — what to reuse vs. what to wrap

Anything in the **Reuse** column is a stable public API. Anything in
**Wrap** is module-internal logic; copy or call but don't expect
stability.

### `claude_api.py` — Anthropic API + retries + validation

| Use it for | Function | Signature contract |
|---|---|---|
| Single sync call with full retry/validation | `call_claude` (`claude_api.py:186`) | `(client, chunk_text, model, system_prompt, verbose, debug_dir, chunk_id, validate=True) -> list[Any]` |
| Batched async (50% cheaper) | `call_claude_batch` (`claude_api.py:456`) | `(client, chunks, model, system_prompt, verbose, debug_dir, validate=True) -> list[list[Any]]` |
| Recover an already-completed batch by ID | `fetch_claude_batch_results` (`claude_api.py:401`) | `(client, batch_id, num_chunks, ...) -> list[list[Any]]` |
| Cost / token estimate, no inference | `dry_run` (`claude_api.py:566`) | `(client, chunk_texts, chunks, model, system_prompt, use_batch, verbose) -> None` |
| Validate a parsed entries list | `validate_entries` (`claude_api.py:61`) | `(entries, chunk_id="") -> list[str]` errors |

Constants you may need to read but should **not redefine**:

- `MAX_OUTPUT_TOKENS = 50_000` (`claude_api.py:25`)
- `MAX_VALIDATION_RETRIES = 1` (`claude_api.py:54`)
- `COMMON_TAG_RULES`, `COMMON_NESTING_RULES` (`claude_api.py:29`,
  `claude_api.py:39`) — inject these into your converter's `SYSTEM_PROMPT`
  via f-string.
- `_PRICE` (`claude_api.py:382`) — haiku/sonnet/opus per-million-token
  prices used by `dry_run`.

**Important contract** — `call_claude(..., validate=False)` is
mandatory for non-adventure payloads (e.g. monster objects whose `type`
is a dict like `{"type":"humanoid","tags":[...]}`); the default
`validate=True` runs `adventure_model.parse_entry` which would crash on
that shape. See `claude_api.py:204-209`.

**Retry rules to know about** (`claude_api.py:227-315`):
- `stop_reason == max_tokens` with parseable output → re-process the
  *tail* of the input (not a fresh call).
- `max_tokens` or `end_turn` with malformed JSON → split input in half,
  recurse on each half.
- Validation errors are split into tag-fix errors (auto-retry, single
  attempt) and structural errors (logged, never auto-retried — see
  `_partition_errors` at `claude_api.py:72`). The structural-error policy
  enforces the global CLAUDE.md rule that scope/structure decisions
  require a human checkpoint.

### `pdf_utils.py` — PDF inspection & TOC

| Use it for | Function | Returns |
|---|---|---|
| Get a PDF's bookmark tree as data structures | `get_toc_tree` (`pdf_utils.py:214`) | `list[TocNode]` |
| Parse `doc.get_toc(simple=True)` output you already have | `parse_toc_tree` (`pdf_utils.py:140`) | `list[TocNode]` |
| Inject the bookmark outline into a Claude prompt as a hint | `extract_pdf_toc` (`pdf_utils.py:52`) | `str | None` |
| Detect a printed table-of-contents page in bookmark-less PDFs | `detect_printed_toc` (`pdf_utils.py:421`) | `(entries, pages)` |
| Build a synthetic TocNode tree from a printed ToC | `build_toc_from_printed` (`pdf_utils.py:586`) | `list[TocNode]` |
| Decode mojibake from PyMuPDF bookmarks | `_decode_pdf_string` (`pdf_utils.py:41`) | `str` |
| Skip Word/Adobe internal anchors (`_GoBack`, `_Toc…`) | `is_anchor_bookmark` (`pdf_utils.py:128`) | `bool` |

`TocNode` (`pdf_utils.py:103`) is the workhorse — a dataclass with
`level, title, start_page, end_page, children`, a `page_count` property,
and a `walk()` pre-order traversal. Every chunking strategy in v2
operates on `list[TocNode]`.

### `adventure_model.py` — typed model for the JSON

The whole 5etools homebrew schema is reified as dataclasses, so you
build a document programmatically and call `.to_json()` instead of
hand-assembling dicts.

Key constructors (top-down):

- `HomebrewAdventure.build(name, source, sections, *, ctx, is_book, authors, convertedBy)` (`adventure_model.py:1051`) — convenience: assigns IDs via `assign_ids()` (`adventure_model.py:1022`) and rebuilds the TOC via `build_toc()` (`adventure_model.py:1028`). **Use this.** Don't roll your own.
- `HomebrewAdventure.from_dict(raw, ctx)` (`adventure_model.py:1074`) — load existing JSON for in-place editing.
- `parse_document(raw, ctx)` (`adventure_model.py:1179`) — auto-detects homebrew vs. official (`OfficialAdventureData`).
- `parse_entry(raw, ctx, path)` (`adventure_model.py:682`) — single-entry deserialiser; this is what `validate_entries` walks.

Entry types you'll touch most: `SectionEntry`, `EntriesEntry`,
`InsetEntry`, `InsetReadaloudEntry`, `QuoteEntry`, `ListEntry`,
`TableEntry`, `ImageEntry`, `ItemEntry`, `HrEntry`, `StatblockEntry`,
`SpellcastingEntry`, `GenericEntry` (catch-all). All defined in
`adventure_model.py:138-625`.

`BuildContext` (`adventure_model.py:82`) threads validation mode
(`WARN` vs. `STRICT`) and accumulates errors. Pass the same `ctx` into
every `parse_entry`/`build` call in one operation so duplicate-ID
detection and error attribution work.

### `validate_adventure.py` — structural validator

Public API:

```python
from validate_adventure import validate
result = validate(json_data, filename="...")
result.errors   # list[str] — must fix
result.warnings # list[str] — should review
result.ok       # bool
```

Defined at `validate_adventure.py:111`. Constants used by the model:

- `VALID_ENTRY_TYPES` (`validate_adventure.py:34`) — 25 entry-type names.
- `KNOWN_TAGS` (`validate_adventure.py:52`) — 80+ valid `{@tag}` names.
  An unknown tag in shipped JSON causes 5etools to render a blank page,
  so any tool that **emits** entries must check tags against this set
  (or rely on `validate_entries`).
- `TAG_RE` (`validate_adventure.py:74`) — `{@(\w+)([^}]*)}` regex.

### `validate_tags.py` — tag-only checker / autofix

Standalone CLI; usable as a library too:

- `scan(obj, path="")` (`validate_tags.py:47`) — returns
  `list[(path, tag_name, full_match)]` of unknown tags.
- `fix_unknown(text)` (`validate_tags.py:62`) — does the canonical
  substitutions: `{@scroll X}` → `{@item scroll of X}`, `{@npc X}` →
  plain text, etc.

### `fix_adventure_json.py` — TOC/ID rebuild library

Used by every editor that saves:

- `reset_ids()` + `assign_ids(entries)` (`fix_adventure_json.py:72`,
  `fix_adventure_json.py:77`) — sequentially numbers `section`,
  `entries`, `inset` nodes (`000`, `001`, …) preorder. **Mutates in
  place**, uses module-global counter — call `reset_ids()` first.
- `build_toc(chapters)` (`fix_adventure_json.py:91`) — walks `data[]`
  and emits the matching `contents[]` array (with `headers[]` derived
  from each section's named children, skipping the section's own name).
- `normalize_chapters(entries, default_name)` (`fix_adventure_json.py:44`) —
  folds non-section top-level entries into the preceding section so
  `data[]` stays aligned with `contents[]` by index.

### `cli_args.py` — shared argparse

- `add_common_args(parser, *, default_chunk, default_model)` (`cli_args.py:22`)
- `add_ocr_args(parser, *, default_dpi)` (`cli_args.py:139`) — legacy.

Edit **only here** when adding a flag. v2 adds exactly one of its own:
`--force-marker` (`pdf_to_5etools_v2.py:1047`).

---

## 3. The data-shape contract

Every adventure file is one of two top-level shapes (auto-detected by
`parse_document`):

### Homebrew shape — what every producer writes
```jsonc
{
  "_meta": {
    "sources": [
      { "json": "MYMOD", "abbreviation": "MYMOD", "full": "My Module",
        "authors": [...], "convertedBy": [...] }
    ],
    "dateAdded": ..., "dateLastModified": ...
  },
  "adventure":     [ { "name": "...", "id": "MYMOD", "source": "MYMOD",
                       "contents": [ { "name": "...", "headers": [...] }, ... ] } ],
  "adventureData": [ { "id": "MYMOD", "source": "MYMOD",
                       "data": [ <SectionEntry>, <SectionEntry>, ... ] } ]
}
```

(For books, `adventure`→`book` and `adventureData`→`bookData`.)

### Hard invariants — break these and 5etools breaks
1. `adventure[0].contents[i].name` **must** equal
   `adventureData[0].data[i].name` for all `i`. Any mismatch breaks
   sidebar navigation. Enforced by `HomebrewAdventure._validate_alignment`
   (`adventure_model.py:1010`).
2. Every `data[i]` **must** have `type == "section"`. Non-section
   top-level entries break index alignment because `contents[]` only
   indexes sections. The save path in `adventure_editor.py:69-79`
   auto-promotes them with a warning rather than silently corrupting
   the file.
3. Section/entries/inset nodes must have unique IDs. `assign_ids`
   guarantees this if you use it (it's the **only** ID source — don't
   hand-write IDs).
4. Every `{@tag}` reference must be in `KNOWN_TAGS`. Unknown tag →
   blank page in 5etools renderer.
5. Bestiary JSON (when paired with an adventure) **must** use a
   different `_meta.sources[].json` ID, by convention `{SOURCE}b`.
   Individual monster `source` fields keep pointing at the adventure's
   source so `{@creature}` cross-links resolve. See
   `extract_monsters.make_bestiary_source_meta` (`extract_monsters.py:515`).

### Bestiary shape — what monster passes write
```jsonc
{
  "_meta": { "sources": [ {"json":"MYMODb", ...} ], ... },
  "monster": [ <Monster>, <Monster>, ... ]
}
```
Built by `extract_monsters.build_bestiary` (`extract_monsters.py:433`).
Always loaded **alongside** the adventure file in 5etools; the `b`
suffix is what keeps them from colliding.

### Entry inheritance / typing rules at a glance
- Use `{"type":"section"}` only for top-level chapters / named locations.
- Sub-rooms (A1, A2, …) go inside a section as `{"type":"entries"}`.
- In `contents[].headers[]`, sub-room titles must be
  `{"header":"name","depth":1}` objects (not flat strings).
- A section's `headers[]` must NOT include: the section's own name,
  generic sub-headings ("Creatures", "Treasure", "Development", "Trap"),
  or stat-block / NPC / encounter-group names.

These are the rules `COMMON_NESTING_RULES` (`claude_api.py:39`) injects
into every Claude prompt.

---

## 4. The v2 conversion pipeline (`pdf_to_5etools_v2.py`)

End-to-end in one call: `convert(...)` (`pdf_to_5etools_v2.py:840`).
The CLI in `main` (`pdf_to_5etools_v2.py:1042`) is just an arg-parsing
shell.

Stages (numbered comments in the source match these):

1. **Profile the PDF** — `profile_pdf` (`pdf_to_5etools_v2.py:153`)
   returns an `InputProfile` (`pdf_to_5etools_v2.py:128`) with
   `has_bookmarks`, `has_selectable_text`, `printed_toc_entries`. Two
   computed properties pick the route:
   - `use_fast_path` (`pdf_to_5etools_v2.py:142`) — bookmarks + text.
   - `use_printed_toc_path` (`pdf_to_5etools_v2.py:146`) — no bookmarks,
     selectable text, ≥5 detected printed-ToC entries.
   - Otherwise → Marker.
2. **Build chunks** — three branches in `convert` at
   `pdf_to_5etools_v2.py:912-943`:
   - Fast path: `get_toc_tree` → `build_chunks_from_toc` (`pdf_to_5etools_v2.py:322`).
   - Printed-ToC path: `build_toc_from_printed` → same `build_chunks_from_toc`.
   - Marker path: `run_marker` (`pdf_to_5etools_v2.py:338`) →
     `parse_markdown_headings` (`:382`) →
     `normalise_numbered_rooms` (`:397`) →
     `build_synthetic_toc` (`:503`) →
     `build_chunks_from_markdown` (`:518`).
   All three end with one `ChunkSpec` (`pdf_to_5etools_v2.py:226`) per
   leaf chunk. `split_oversized` (`:258`) handles oversized nodes by
   chunking children + emitting prose stubs.
3. **Dry run** (optional) — `_api.dry_run`.
4. **Claude pass** — three branches at `pdf_to_5etools_v2.py:967-992`:
   `--resume-batch` (recover an already-completed batch),
   `--batch` (`call_claude_batch`), or sync (`call_claude_for_chunk`
   per chunk; defined at `:549`).
5. **Assemble** — `assemble_adventure` (`pdf_to_5etools_v2.py:638`)
   groups chunks by `id(spec.root)`, parses each chunk's entries
   through `parse_entry`, and emits one `SectionEntry` per top-level
   `TocNode`. Then `HomebrewAdventure.build` finalises IDs + TOC.
6. **Write** — `doc.to_json()` to disk
   (`pdf_to_5etools_v2.py:1008`). Raw Claude responses are saved to a
   sibling `<stem>-responses/` dir (`pdf_to_5etools_v2.py:871-879`)
   unless `--debug-dir` is set.
7. **Optional bestiary pass** (`--extract-monsters`) — calls
   `extract_monsters.extract_italic_statblocks`, then
   `write_bestiary` (`pdf_to_5etools_v2.py:743`) →
   `extract_monsters.build_bestiary`.

The system prompt is `SYSTEM_PROMPT` at `pdf_to_5etools_v2.py:84`. It
declares Marker headings authoritative and injects the two shared
prompt fragments via f-string.

### The `--monsters-only` fast path
Bypasses adventure assembly entirely:
`convert_monsters_only` (`pdf_to_5etools_v2.py:781`) → Marker →
`extract_markdown_statblocks` (`extract_monsters.py:360`) →
`build_bestiary`. Use this when you only want stat blocks; it's ~2-3×
cheaper than a full conversion.

### Resume after a crash
`--resume-batch BATCH_ID` (`pdf_to_5etools_v2.py:967`) re-fetches an
already-completed Anthropic batch via `fetch_claude_batch_results`. This
relies on chunking being **deterministic**, so don't change chunking
behaviour mid-flight. Anthropic retains batch results ~29 days.

---

## 5. Editor / fixer surface

All four are single-file Flask apps with inline HTML/JS, run over a
JSON file. They share the same save contract: rebuild IDs + TOC via
`fix_adventure_json`, write `.bak` backup, overwrite original.

| Tool | Port | What it does | Entry point |
|---|---|---|---|
| `app.py` | 5100 | Browser front-end for `pdf_to_5etools_v2`. Spawns it as a subprocess, streams stdout via SSE, exposes a download link when `Job.status == "done"`. | `app.py:1138` (`/`), `app.py:1143` (`/convert`), `app.py:1264` (`/stream/<job_id>`), `app.py:1297` (`/download/<job_id>`). Job model: `app.py:44`. |
| `toc_editor.py` | 5101 | Three-level (section / header / sub-header) TOC reorder UI. Highlights name mismatches between `contents[]` and `data[]`. Logs corrections to `toc_corrections.jsonl`. | `toc_editor.py:104` (`/`), `:140` (`/api/demote`), `:180` (`/api/save`). |
| `toc_fixer.py` | 5102 | Heuristic rebuild of the **nesting tree** in `data[]` using PDF bookmarks + keyed-room patterns. Three-panel UI. | Heuristics: `apply_pdf_anchor` (`toc_fixer.py:229`), `apply_keyed_room` (`:336`), `_promote_interrupted_series` (`:434`). Rebuild: `rebuild_tree` (`:524`). API: `:607-789`. |
| `adventure_editor.py` | 5104 | Block-tree editor with live preview, undo log persisted to `<file>.undolog.json`, multi-select, flag system, smart paste for tables/stat blocks. | `load_adventure` (`adventure_editor.py:38`), `save_adventure` (`:62`, calls `_fix.reset_ids/assign_ids/build_toc`). Routes `:142-330`. |
| `monster_editor.py` | 5103 | Discovers stat blocks in an adventure JSON, sends selected ones to Claude, writes/merges a bestiary file. | `discover_statblocks` (`monster_editor.py:85`), `_extraction_worker` (`:124`), routes `:212-355`. |

Hard UI rules from `CLAUDE.md` (apply if you build a new editor in the
same vein):
- No confirmation dialogs for undoable actions — separate buttons + undo.
- Never put `pk` (path keys with embedded `"`) in HTML strings or
  `onclick` attributes — use `addEventListener` with closures.

### Patch tools (re-enter the pipeline mid-stream)

- `merge_patch.py` — splice another converter's output into an
  existing adventure at a given index. `list_sections`
  (`merge_patch.py:48`) for inspection, `merge` (`:62`) to do it.
  Re-runs `assign_ids` after merging.
- `patch_5e_chapters.py` — re-convert specific chapters from a 1e
  source JSON (the `patch` function at `patch_5e_chapters.py:54`).
- `convert_1e_to_5e.py` — bulk mechanical rewrite (1e stats → 5e).
  Per-zone driver at `convert_chapter` (`convert_1e_to_5e.py:421`).
  Contains a hardcoded `ZONES` dict — adapt this for non-T1-4 modules.

---

## 6. Building a new tool — recipes

These cover the four common shapes a new tool will take. Pick the
recipe that matches your need and follow it exactly; deviating from
these patterns is what causes the 5etools renderer to throw.

### A. New "PDF → adventure JSON" producer
Stand on `pdf_to_5etools_v2.py` rather than reinventing the pipeline.
Minimum viable add-on:

```python
import anthropic
import claude_api as _api
from adventure_model import (HomebrewAdventure, SectionEntry, BuildContext,
                             parse_entry)
from pdf_utils import get_toc_tree, TocNode

SYSTEM_PROMPT = f"""... your prompt ...
{_api.COMMON_TAG_RULES}
{_api.COMMON_NESTING_RULES}
""".strip()

def convert(pdf_path, source, name, model="claude-haiku-4-5-20251001"):
    client = anthropic.Anthropic()
    toc = get_toc_tree(pdf_path)
    ctx = BuildContext()
    sections = []
    for root in toc:
        body = _extract_body(root, pdf_path)
        entries = _api.call_claude(client, body, model, SYSTEM_PROMPT,
                                   verbose=False, chunk_id=root.title)
        parsed = [parse_entry(e, ctx, f"section[{root.title}].entries[{i}]")
                  for i, e in enumerate(entries)]
        sections.append(SectionEntry(name=root.title, entries=parsed, _ctx=ctx))
    doc = HomebrewAdventure.build(name=name, source=source, sections=sections,
                                  ctx=ctx)
    return doc.to_json()
```

Reuse `cli_args.add_common_args` for the CLI surface. Don't reimplement
retry/parsing/validation — that's `claude_api.call_claude`'s job. Don't
emit your own IDs — `HomebrewAdventure.build` does that.

### B. New post-processing pass on existing JSON
Load → mutate → save. **Always** rebuild IDs and TOC at the end:

```python
import json
from pathlib import Path
import fix_adventure_json as _fix

def transform(in_path: Path, out_path: Path):
    raw = json.loads(in_path.read_text())
    idx_key  = "adventure" if "adventure" in raw else "book"
    data_key = "adventureData" if idx_key == "adventure" else "bookData"
    sections = raw[data_key][0]["data"]

    # ... mutate sections in place ...

    _fix.reset_ids()
    _fix.assign_ids(sections)
    raw[idx_key][0]["contents"] = _fix.build_toc(sections)
    out_path.write_text(json.dumps(raw, indent="\t", ensure_ascii=False))
```

If you need typed access (rather than raw dicts), use
`HomebrewAdventure.from_dict` / `.to_json` instead. For validation,
call `validate(raw)` from `validate_adventure` and bail on
`result.errors`.

### C. New Flask editor (yet-another panel)
Pattern is consistent across `toc_editor.py`, `toc_fixer.py`,
`adventure_editor.py`, `monster_editor.py`. Reuse:

- `toc_editor.list_json_files` (`toc_editor.py:34`) for the file picker.
- `fix_adventure_json.{reset_ids, assign_ids, build_toc}` on save.
- Pick a port from the unused range 5105+.
- Pre-load a file from `argv[1]` (see how each editor reads
  `_preload_file`).
- Inline HTML/JS. No build step. Bootstrap 5.3.3 from CDN is the
  established style.

### D. Tool that "asks Claude something" about an adventure
Always go through `claude_api.call_claude` (or `call_claude_batch`) so
you inherit retry, validation, debug-dir logging, and structured-error
handling. If your output isn't an adventure entry list (e.g. it's
monster JSON, summary text, classification), pass `validate=False`.

### E. Anti-recipe — don't do these
- Don't hand-assemble `contents[]`. Use `build_toc` or
  `HomebrewAdventure.build_toc`.
- Don't hand-assign IDs. Use `assign_ids` (mind the module-global
  counter — call `reset_ids` first).
- Don't bypass `claude_api`. Anthropic SDK calls live in **one** module
  for a reason: token budget, retry policy, batch handling, and the
  validation-retry split-policy all need to stay in lockstep.
- Don't introduce a new `{@tag}` without adding it to
  `validate_adventure.KNOWN_TAGS` — it'll render as an empty page.
- Don't emit non-section top-level entries in `data[]`. Wrap everything
  in `SectionEntry`.

---

## 7. Test infrastructure

Three test files, all run via plain `pytest`:

- `test_adventure_model.py` (~90 tests) — model constructors,
  validation modes, round-trips, `parse_document` on official
  adventures.
- `test_adventure_editor.py` (81 tests) — Flask routes, undo,
  move/promote/demote, multi-select, flag system. Asserts the
  no-`pk`-in-onclick rule.
- `test_validate_adventure.py` (44 tests) — runs the validator against
  all 98 official 5etools adventure files; integration anchor for the
  schema.
- `test_pdf_to_5etools_v2.py` — chunking, profile routing,
  prompt building.

All tests mock external dependencies (Anthropic, PyMuPDF) — no API key
or system packages required to run them.

---

## 8. Quick reference: module map by responsibility

| If you need to… | Look at | Don't reinvent |
|---|---|---|
| Call Claude with retries | `claude_api.call_claude` | Retry/parse/validation logic |
| Submit a Claude batch | `claude_api.call_claude_batch` | Batch polling/result mapping |
| Estimate cost before running | `claude_api.dry_run` | Tier→price mapping |
| Read a PDF's TOC | `pdf_utils.get_toc_tree` | Bookmark decoding, anchor filtering |
| Detect a printed ToC page | `pdf_utils.detect_printed_toc` | OCR-style TOC parsing |
| Build a homebrew JSON document | `HomebrewAdventure.build` | ID assignment, TOC alignment |
| Validate an adventure file | `validate_adventure.validate` | Tag-name checking, alignment checking |
| Auto-fix unknown tags | `validate_tags.fix_unknown` | Manual tag substitutions |
| Discover stat blocks in JSON | `monster_editor.discover_statblocks` or `extract_monsters.extract_italic_statblocks` | Stat-block heuristics |
| Reassign IDs / rebuild TOC after editing | `fix_adventure_json.{reset_ids, assign_ids, build_toc}` | Anything ID-related |
| Add a CLI flag for converters | `cli_args.add_common_args` | Per-script argparse |

---

## 9. Where the bodies are buried

- **Module-global ID counter** in `fix_adventure_json.py:70` — call
  `reset_ids()` before `assign_ids()` or you'll continue numbering from
  whatever the last call left.
- **`SECTIONS` and `ZONES` constants in `convert_1e_to_5e.py`** are
  hardcoded for T1-4 (Temple of Elemental Evil 1e). Other modules need
  their own mapping.
- **Marker venv** (`marker-env/`) is required for the Marker route and
  is gitignored. A CUDA GPU is strongly recommended; CPU is 6-30× slower.
- **Anthropic batch results** are retained ~29 days — `--resume-batch`
  works inside that window only.
- **`HomebrewAdventure._validate_alignment`** logs warnings, not
  errors, when `contents[]` and `data[]` lengths/names disagree
  (`adventure_model.py:1010`). The CLI can succeed with misaligned
  output; the editors will warn loudly on load.
- **The two `architecture.md` files**: the older `architecture.md`
  describes the v1 six-converter layout (preserved at git tag `v1.0`)
  and is misleading for v2 work. Use this file for v2.
