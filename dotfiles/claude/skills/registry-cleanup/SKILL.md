---
name: registry-cleanup
description: Audit and repair a campaign entity registry that has transcription garblings recorded as aliases, garbled canonical names, or duplicate entities. Enforces the rule that an alias is an APPROVED CANONICAL ALTERNATE NAME, never a misspelling. Every removal, merge and rename is confirmed by the GM first. Invoke as /registry-cleanup [campaign-dir].
tools: Read, Glob, Grep, Bash, Edit, Write, AskUserQuestion, TaskCreate, TaskUpdate, ToolSearch
---

# Registry Cleanup

## The rule this skill enforces

> **An alias is an approved canonical alternate name. It is never a garbling.**

Legitimate aliases: plurals (`bridesmaids of Zuggtmoy`), short forms
(`Gromph's grimoire` for `Gromph Baenre's grimoire`), titles (`Gatewarden`),
diacritic-free renderings (`Faerun` for `Faerûn`), real-name variants
(`Christopher Perkins` for `Chris Perkins`).

Not aliases: `Thermbechaud`, `Glabagool`, `Zuggtomy`, `Blinddenstone`. Those are
ASR errors. They belong in the VTT corrections glossary, which exists precisely
to map them back to the canonical form.

**Why this matters operationally.** Downstream consumers treat every registry
name *and alias* as a known, correctly-spelled name. `vtt-spell-pass` builds its
known-names set that way. So a garbling parked in the alias list marks that
garbling "known" and **silently suppresses the correction the glossary would
otherwise have made**. The failure is invisible: nothing errors, the transcript
just quietly keeps the wrong spelling. One real instance: 22 of 434 aliases in
the Out of the Abyss registry were glossary wrong-forms, including `Zentarim` on
*The Zhentarim* — added to the glossary the same day it was found suppressing
itself.

## Before you start: the tooling is missing verbs

`registry.py` (CampaignGenerator) offers `add`, `alias`, `merge`,
`mark-distinct`, `mark-rejected`, `check`, `triage-candidates`, `project`,
and the `import-*` family. It has:

- **no `unalias`** — you cannot remove a bad alias through the CLI or the MCP
- **no `rename`** — you cannot fix a garbled canonical in place

So removal and renaming mean editing `docs/entity_registry.yaml` directly. Use
`strip_aliases.py` (this directory) rather than hand-editing: it keys on
(entity, alias) pairs, preserves YAML formatting, validates by re-parsing, and
refuses to write if the entity count moved.

### `registry merge` has two behaviours you must correct for

Both were observed live, both are silent:

1. **Merge re-adds the folded entity's name as an alias of the target.**
   Merging `House Turan` into `House T'sarran` leaves `House Turan` sitting in
   T'sarran's alias list — recreating exactly the bad data you are removing.
   **After every merge, strip the folded name.**
2. **Merge drops the folded entity's `note`.** Folding `Plinky` into `Plinki`
   discarded *"Author of Plinky's Journal, a demonological text from the
   Whorlstone Caverns"* — real information with no other home.
   **Read both notes before merging and hand-carry anything unique into the
   survivor's note.**

Neither is reported. Verify the merged entity yourself every time.

## Workflow

### Phase 1 — audit (deterministic, read-only)

```bash
python ~/.claude/skills/registry-cleanup/audit_aliases.py \
  --registry <campaign>/docs/entity_registry.yaml \
  --glossary <campaign>/notes/vtt_transcription_corrections.md
```

Three buckets:

| Bucket | What | Confidence |
|---|---|---|
| **A** definitive | alias is a wrong-form in the glossary | The GM already ruled. Propose stripping as a batch. |
| **B** probable | alias is a near-miss (≥0.80) of its *own* canonical | **Mixed.** Garblings and legitimate variants both land here. Adjudicate. |
| **C** inverted | the *canonical* is a garbling, or duplicates another entity | Needs merge or rename, not an alias edit. |

Also run the built-in drift report — it catches grouping problems the audit
does not:

```bash
# via MCP: registry_check   (or)
python -m entity_registry.registry check    # from the CampaignGenerator dir
```

### Phase 2 — classify bucket B before asking

Bucket B is the only part needing real judgment. Sort each entry into:

- **Garbling** — one fantasy name mangled into a near-homophone.
  `Thermbechaud`/`Thermbechaude`/`Thermbachaud` on *Themberchaud*;
  `Blinddenstone` on *Blingdenstone*; `Suushar` on *Shuushar*.
- **Legitimate variant** — plural, short form, diacritic-free, title, or
  real-world full-vs-short name. Keep.
- **Possibly a different entity** — the two names differ by a *word*, not by
  spelling. `Halls of Sacred Stones` vs `Halls of Sacred Spells`;
  `Circle of Sowers` vs `Circle of Sporers`; `Ilian` vs `Elian` vs `Elin`.
  Never rule on these yourself.

### Phase 2.5 — check the source before proposing (MANDATORY for anything ambiguous)

String similarity cannot tell a garbling from a real second name. The source
text can. Check, in this order:

1. **The campaign bible** (`docs/TheUnderdark.md` or equivalent) — what the GM
   actually wrote.
2. **The published module** (`docs/background/*.md`, or 5etools MCP).
3. **Module inventories** (`docs/background/*-inventory.md`).

Two live examples of why this is not optional:

- `Lolthism` was an *alias* of canonical `Lothheism`. The bible reads
  *"converted to Lolthism"* — the alias was correct and **the canonical was the
  garbling**. The fix was a rename, not a strip.
- `Circle of Sowers` was an *alias* of canonical `Circle of Sporers`. The
  published module names the seven Neverlight Grove circles explicitly and
  **Sowers is among them**; Sporers appears once. Same inversion.

A zero-hit count is strong evidence too: `Ilian` appears 0 times in the bible
(`Elian` 11, `Elin` 7), which settled it as a garbling with no source support.

**Watch for real-world collisions.** `Myrtul` looked like a garbling of the
death god *Myrkul* — but **Mirtul** is a Forgotten Realms calendar month. Ask;
don't assume the nearest fantasy name wins.

### Phase 3 — GM confirmation (hard gate)

Identity is a precision decision. The registry MCP says so itself: *"only call
these once the GM has explicitly confirmed the specific mapping in this
conversation — do not infer a match from string similarity."*

- Batch **A** into one question, **listing every member** so the GM sees each
  mapping. A batch confirmation where all items are visible is explicit; a
  batch where they aren't is not.
- Group **B** by the Phase-2 classification — garblings, legitimate variants,
  possibly-distinct — and confirm each group with all members shown.
- Ask about every **C** entry individually. These delete or rename entities.
- Anything that turns out to be a *different entity*: use
  `registry_mark_distinct` so no future pass re-merges it.

Never fill in a default because a question went unanswered. A timeout is not a
checkpoint.

### Phase 4 — apply

Order matters. Do the strips first, then the merges, then re-strip.

```bash
# 1. remove confirmed garbling aliases
python ~/.claude/skills/registry-cleanup/strip_aliases.py \
  --registry <campaign>/docs/entity_registry.yaml \
  --backup <campaign>/docs/entity_registry.yaml.bak-$(date +%Y%m%d) \
  --pair "Glabbagool::Glabagool" --pair "Themberchaud::Thermbechaud" ...
```

Use `--dry-run` first on any large batch. A `NOT FOUND` line means a typo or a
wrong entity — fix it rather than ignoring it.

```bash
# 2. merges (MCP registry_merge, or the CLI) — one at a time, notes read first
# 3. re-strip the names merge re-introduced as aliases  <-- ALWAYS
# 4. hand-carry any note the merge dropped
```

For a **rename** (garbled canonical, no duplicate to merge into), edit the
`- name:` line directly with Edit and record why in the entity's `note`:

```yaml
- name: Lolthism
  note: >-
    ... Spelling confirmed against docs/TheUnderdark.md ("converted to
    Lolthism"); the former canonical "Lothheism" was a garbling, dropped
    2026-08-03.
```

### Phase 5 — project and verify

```bash
# MCP: registry_project   (or)  python -m entity_registry.registry project
```

Then re-run the audit. Bucket A should be **0**. Bucket B should contain only
the entries the GM confirmed as legitimate variants — enumerate them in the
final report so the next run knows they were adjudicated, not missed.

Sanity-check the diff: it should be dominated by deletions. A cleanup that adds
lines to `entity_registry.yaml` is doing something you did not intend.

## Conventions

- **`entity_inventory.md` and `aliases.json` are generated.** Never hand-edit;
  always regenerate with `project`.
- **Back up before the first write.** `entity_registry.yaml` is ~4000 lines of
  hand-curated identity data with no other copy.
- **Preserve YAML formatting.** Line-oriented edits only — a `safe_load`/`dump`
  round-trip reformats everything and makes review impossible.
- **The glossary and the registry own different things.** Glossary: wrong → right
  for transcription. Registry: canonical identity plus approved alternates. When
  they disagree about whether a string is a misspelling, **the glossary wins** —
  it is the record of what the GM ruled at the table.
- **Report scale honestly.** The count that matters is not "aliases that look
  odd" but "aliases that are demonstrably garblings." Separate the two.

## Why this design

The audit is deterministic extraction. The GM adjudicates. The strip/merge/
rename steps are deterministic application. No step lets a model decide, from
string similarity alone, that two names are the same thing — that is exactly the
inference that produced the mess this skill cleans up.
