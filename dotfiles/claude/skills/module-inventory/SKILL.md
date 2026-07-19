---
name: module-inventory
description: >
  Extract a descriptive proper-noun inventory (NPCs, deities, locations,
  creatures, items, factions, events) from a module's SOURCE material — a
  prose bible (.md/.txt) or a 5etools-style adventure JSON — before or
  alongside running a campaign in it. Produces
  docs/background/<slug>-inventory.md (**bold**-name bullets grouped by
  category) plus a flat .txt companion. A deterministic regex pass surfaces
  raw candidates, parallel LLM passes group/describe them per chunk, a
  deterministic merge flags contradictions and near-duplicate names, and the
  GM rules on every flagged case before anything is written. Invoke as
  /module-inventory [campaign-dir] [source-file].
tools: Read, Write, Bash, Agent, AskUserQuestion, ToolSearch, Grep, TaskCreate, TaskUpdate
---

# Module Inventory

Build the descriptive "what's in this module" reference doc — the artifact
that `out-of-the-abyss-inventory.md`, `candlekeep_murders_module_inventory.md`,
`proper_nouns_adventure.md`, and Obelisk's `name_glossary.md` all independently
turned out to be, each built ad hoc in a one-off session. This skill is the
reusable version of that method.

## What this is NOT

- **Not the entity registry.** `registry.py triage-candidates` +
  `entity-triage` reconcile proper nouns seen in **session play** (summaries,
  scene extractions) against `docs/entity_registry.yaml` — a different, later
  concern that needs a registry to already exist. This skill runs against the
  **module's own source text**, before or independent of any registry, and
  needs nothing but the source file.
- **Not canon.** The output is a **staging/review artifact** — "Notes are
  staging, not canon" applies here too. Nothing gets promoted into
  `world_state.md`, `campaign_state.md`, or an NPC dossier without a human
  reading it first. Say this explicitly in the file's own header (see Phase 5).
- **Not a rewrite of an existing hand-curated file.** If the campaign already
  has one of these (Obelisk's `name_glossary.md` has a whole "Rulings decided
  by Kostadis" section — that is not idly regenerable), Phase 0 must catch
  that and ask before doing anything, never silently overwrite it.

## Why the pipeline is shaped this way

Per the project's LLM Pipeline Design Rule: grouping raw tokens into a full
name, picking a category, and writing a description is a **draft/render**
task — an LLM doing that first pass is fine, because nothing downstream
auto-applies it. But **merging the same entity's sightings across chunks**,
and **deciding which of two conflicting facts about a name is true**, are
**scope and attribution decisions** — exactly the case the rule says needs a
human checkpoint, not another LLM guess. So:

1. `raw_candidates.py` (deterministic, no LLM) — cheap, precision-favoured
   phrase extraction. This is the "verified structure" the next step renders
   on top of, not something an LLM invents from scratch.
2. Parallel LLM chunk passes (draft) — group tokens into names, categorize,
   describe, cite lines. Each chunk is blind to the others, same as
   `k-parallel`'s isolation principle — no chunk's output should bias another.
3. `merge_candidates.py` (deterministic, no LLM) — merges clean agreement,
   **flags** (never resolves) category mismatches, attribute conflicts
   (species/status/gender), and near-duplicate names.
4. GM ruling (human checkpoint) — every flagged case, one at a time, with
   grep-verified citations, exactly like Obelisk's own
   "✓ verified in source... ruling decided by Kostadis" precedent.
5. Render (draft) — safe now; everything contested has already been decided
   by a human.

## Required information

1. **Campaign dir** — from the invocation arg, else CWD if it has
   `config.yaml`, else ask. Resolve to an absolute path.
2. **Source file** — from the invocation arg, else look for one obvious
   candidate under `<campaign-dir>/docs/background/` (a large `.md`/`.txt`
   bible, or a 5etools-style `.json`). If more than one plausible file exists,
   list them and ask. If none exists, ask for a path (it need not be under the
   campaign dir — e.g. a pdf-translated JSON living elsewhere, as with toee's
   `~/toee-stuff/adventure-t14-5e.json`).
3. **Output slug** — derive from the source filename (kebab-case, strip
   extension) unless the GM names one. Output paths:
   - `<campaign-dir>/docs/background/<slug>-inventory.md`
   - `<campaign-dir>/docs/background/<slug>-inventory.txt`

If `AskUserQuestion` is not loaded, run `ToolSearch` with
`query: "select:AskUserQuestion"` first.

## Workflow

### Phase 0 — Preflight

1. Resolve campaign dir + source file per above.
2. Check for an existing output at the target path, **and** glob
   `docs/background/*glossary*.md` / `docs/background/*inventory*.md` for
   near-miss existing artifacts under a different name (Obelisk's
   `name_glossary.md` would not match `<slug>-inventory.md` and must not be
   silently duplicated or ignored). If anything turns up, tell the GM what you
   found and ask: regenerate from scratch, treat this as a fresh incremental
   run reading the existing file's already-ruled entries as pre-seeded
   "clean" (skip re-asking about names already resolved there), or abort.
3. Create the working dir `<campaign-dir>/docs/background/.module_inventory/<slug>/`
   (transient — gitignore it: `docs/background/.module_inventory/` in the
   campaign's `.gitignore` if not already covered) with subdirs `chunks/` and
   `chunk_outputs/`. This makes the whole run resumable — re-invoking the
   skill on the same slug skips any chunk whose output file already exists,
   same as `ensemble_batch.py`.
4. Detect source format from the extension: `.json` → json mode, `.md`/`.txt`
   → prose mode.

### Phase 1 — Deterministic raw candidates

```bash
python3 ~/.claude/skills/module-inventory/raw_candidates.py <source-file> \
  --out <workdir>/candidates.json
```

This needs no LLM call and costs nothing to re-run. Report the counts
(`section_titles` / `tagged_refs` (json mode only) / `candidates`) to the GM
in one line — do not dump the list.

### Phase 2 — Chunk + parallel LLM grouping passes

**Chunking** (skip entirely for a small source — under ~800 lines of prose or
a single JSON section — and just run one Agent over the whole thing):

- **Prose, with markdown headers present:** split on `^#` / `^##` boundaries,
  merging small adjacent sections so each chunk lands around 600–800 lines
  (the ratio Obelisk's own ad hoc pass used: 6,078 lines → 9 chunks ≈ 675
  lines/chunk). Never split a header's section across two chunks.
- **Prose, no clear header structure:** fixed-size ~700-line chunks with a
  ~50-line overlap at each boundary, so an entity's introduction isn't cut in
  half and lost.
- **JSON:** chunk by top-level structural section (e.g. a 5etools book's
  top-level `data` array entries) — one chunk per section, grouping tiny
  sections together and splitting a huge one further if needed.

Write each chunk's raw text (or JSON slice) to `<workdir>/chunks/chunk_NN.md`
(or `.json`) with a human-readable label (e.g. `ch3_the_spiders_web`).

**For each chunk** whose `<workdir>/chunk_outputs/chunk_NN.json` does not
already exist, spawn an `Agent` (multiple in one message for real
parallelism — these must be independent, no chunk sees another chunk's
output, matching `k-parallel`'s isolation rule). Each agent's prompt:

> Read `<chunk file>`. Here is a list of raw capitalized-phrase candidates
> already found in this text by a deterministic scan, with line numbers:
> `<the subset of Phase-1 candidates whose lines/paths fall in this chunk's
> range>`. Use this list as a checklist — account for every candidate that is
> a real proper noun (merge adjacent single-word candidates into full names
> where the text shows they're one entity, e.g. "Temple" + "Elemental Evil"
> → "Temple of Elemental Evil"; drop candidates that are false positives:
> generic words, ability/skill names, sentence-initial capitalization
> noise). You may also add a genuine proper noun the scan missed. For each
> surviving entity, write ONE entry:
> `{"name": ..., "aliases": [...], "category": "npc|deity|location|creature|item|faction|event|other", "description": "≤25 words, grounded ONLY in this chunk's text — do not invent or infer beyond what's written here", "lines": [...], "attributes": {"species": ..., "status": "alive|dead", "gender": ...}}`
> (`attributes` only where the text states it explicitly — this feeds
> automated contradiction detection against other chunks, so a wrong guess
> here causes a false-positive flag, not a silent error — still don't guess.)
> Write the result to `<workdir>/chunk_outputs/chunk_NN.json` as
> `{"chunk_label": "...", "entries": [...]}`. Return a one-line summary of how
> many entries you wrote.

Cap concurrent agents reasonably (a handful at a time) rather than firing
dozens in one message if the module is very large — batch if there are more
than ~10 chunks.

### Phase 3 — Deterministic merge

```bash
python3 ~/.claude/skills/module-inventory/merge_candidates.py \
  --chunks-dir <workdir>/chunk_outputs --out <workdir>/merged.json
```

Report the `stats` line to the GM: clean / contested / possible_duplicates
counts. If `contested` and `possible_duplicates` are both empty, skip straight
to Phase 5.

### Phase 4 — GM ruling (human checkpoint)

Walk `contested` and `possible_duplicates` one at a time — **TaskCreate** one
task per flagged item so progress is visible and the run is resumable if
interrupted.

For each **contested** entry: `grep -n` the source file around each cited
line (a few lines of context) so the GM sees the actual text, not just the
chunk-agent's paraphrase — same as Obelisk's "✓ verified in source" standard.
Present via `AskUserQuestion`:

```
"Grista" — attribute conflict: species [dwarf, orc]
  ch2 (line 761): "...a surly orc named Greska..."   [if the source itself
  ch5 (line 2438): "...a surly dwarf named Grista..."  says two different things,
                                                          that's the module
                                                          contradicting itself]
Options:
  [ Keep sighting A as canon, drop B ]
  [ Keep sighting B as canon, drop A ]
  [ Both are real — keep as two distinct entities ]
  [ Defer — flag in the doc, don't resolve now ]
```
Always include a defer/distinct escape hatch — never force a resolution the
GM isn't ready to make. Record the ruling; the chosen description(s) go into
the final render.

For each **possible_duplicate** pair (similar spelling, not already merged):
show both full entries side by side and ask: same entity (pick canonical
spelling, merge) / different entities (keep both, note the near-miss so a
future run doesn't re-ask) / defer. This mirrors `entity-triage`'s
distinct-but-similar handling and the project's own "filename similarity ≠
same NPC" lesson — never auto-merge on string similarity alone.

Persist rulings to `<workdir>/rulings.json` as you go (resumable).

### Phase 5 — Render

Write `<slug>-inventory.md`:

```markdown
# <Module Title> — module proper-noun inventory

**Source:** `<source file path>` (<N> lines/entries scanned).
**Provenance:** deterministic regex pass + <N>-way parallel LLM extraction,
merged and deduplicated (module-inventory skill, <date>). Contested
attributions were grep-verified against the source and ruled by <GM name> on
<date> (see Rulings below, if any).

This is the **source-material list**, not the campaign's homebrew — for the
campaign's adapted state see `<point at world_state.md / campaign_state.md /
docs/npcs/ as applicable>`.

---

## Rulings & contested attributions   <!-- omit this section if none -->

| Issue | Detail | Ruling |
|---|---|---|
| ... | ... | ... |

---

## <Category, e.g. NPCs>

### <Sub-group, when a category is large — by species/faction/location cluster>

- **Canonical Name** / **Alias** — one-line description [chapter/location tag if useful]
```

Formatting rules that matter (these feed real downstream tooling, not just
readability):

- **Names MUST be `**bold**`, aliases separated by `/`.** `spell_canon.py
  propose --inventory <this file>` parses names with the regex `\*\*(.+?)\*\*`
  and splits on `/`/`,` for alias groups — a table format (no bold markers)
  is invisible to it. Bullet-list-with-bold, not a table (this is the one
  place this skill diverges from Obelisk's own `name_glossary.md`, which
  predates this convention being load-bearing — don't "fix" that file to
  match; it's a separate, already-reviewed artifact).
- Group by category (`## NPCs`, `## Deities`, `## Locations`, `## Creatures`,
  `## Items`, `## Factions`, `## Events / concepts`); sub-group large
  categories by species/faction/location cluster, matching
  `out-of-the-abyss-inventory.md`'s structure.
- Skip empty categories.

Then write the flat companion:

```
<slug>-inventory.txt
```
One canonical name + one line per alias, sorted, no headers, no bullets —
the exact shape `find_unknowns.py --extra-known` and `vtt-spell-pass` expect.

### Phase 6 — Wrap-up

1. Report a tally: entries by category, contested resolved, duplicates
   resolved/deferred.
2. Suggest next steps:
   - `python spell_canon.py propose <bible> --inventory <slug>-inventory.md
     --out <map>.json` — canonicalise the bible's own spelling drift against
     this inventory now that it exists.
   - Point `vtt-spell-pass` at `<slug>-inventory.txt` via `--extra-known` for
     future session VTT passes.
   - If the campaign has (or wants) an entity registry for session-play
     reconciliation, that's a separate step — `registry.py init` +
     `triage-candidates` + `entity-triage`, not this skill.
3. Leave the working dir in place (gitignored) — it makes a future re-run
   (after the bible grows) resumable and incremental rather than a full redo.

## Do not

- **Do not auto-merge a contested entry or a possible-duplicate pair.**
  `merge_candidates.py` flags, it never resolves — that's Phase 4's job, not
  a script's and not an unchecked LLM's.
- **Do not silently overwrite an existing hand-curated inventory/glossary
  file**, especially one with its own Rulings section (Obelisk's
  `name_glossary.md`). Phase 0 must surface it and ask.
- **Do not let a chunk agent describe something beyond what its own chunk
  text says.** A description grounded in chunk N's text but describing facts
  actually established in chunk M is how contradictions get silently
  laundered instead of caught.
- **Do not treat the finished doc as canon.** It's a staging/review artifact;
  say so in its own header. Promotion into grounding docs or NPC dossiers is
  a separate, later, human-reviewed step.
- **Do not use a table format for the final render.** Bold-bullet format is
  required for `spell_canon.py --inventory` compatibility (see Phase 5).
- **Do not skip the GM ruling checkpoint because the contested list is long.**
  Batch the low-stakes ones (e.g. `AskUserQuestion` can only take one
  question per call, but you can ask about several straightforward duplicates
  in one multi-question call) — but never resolve a real contradiction
  without asking.
