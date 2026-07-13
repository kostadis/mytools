---
name: ensemble-type-merge
description: >
  Merge type-duplicate dossiers in docs/ensemble/state_dossiers/ — the same entity extracted under two or
  more different (type, subject) keys, e.g. npc_glabbagool.md + monster_glabbagool.md — into
  docs/ensemble/merged_dossiers/. A shared name across types is not always the same entity, so each
  candidate group is confirmed with the user one at a time before anything is merged. Deterministic
  concatenation only, no re-synthesis. Invoke as /ensemble-type-merge [campaign-dir].
tools: Read, Bash, Write, AskUserQuestion, TaskCreate, TaskUpdate
---

# Ensemble Type Merge

Merge `state_dossiers/*.md` files that are **type-duplicates** — the same subject name extracted under
more than one `(type, subject)` key by `facts_to_state.py` — into `merged_dossiers/`, the input Stage 3
synthesis reads. One group at a time, human-confirmed.

## Why this exists

`facts_to_state.py` groups facts by `(type, subject)`, not by subject alone (CampaignGenerator's
`docs/cli/ensemble_workflow.md`, "Known limitation — type duplicates"). The same entity extracted as both
`npc` and `monster` in different scenes — Glabbagool, Boney, Cryovain, Talos, Gorthok are documented
examples — produces two separate dossiers that need to become one before synthesis sees them.

**Alias review does not fix this.** Aliases collapse name *variants* ("Bupido" → "Buppido"); this is a name
*collision across types*, a different axis entirely.

**A blind merge-everything-with-the-same-name script is wrong**, and this skill exists specifically because
that's not a safe default. Two dossiers sharing a subject name are not always the same fictional entity — a
location can coincidentally share a name with an NPC, and low-fact secondary-type bundles are frequently
extraction noise rather than a real second facet. Concretely, in the Out of the Abyss campaign this skill
was built against, the very first two candidate groups were:

- `glabbagool`: `npc_glabbagool.md` (151 facts) + `monster_glabbagool.md` (41 facts) + `object_glabbagool.md`
  (4 facts) — genuinely the same entity (a sentient ooze companion), three real facets worth preserving.
- `daz`: `npc_daz.md` (539 facts, a PC) + `faction_daz.md` (1 fact) — almost certainly a mis-extraction
  ("Daz's crew" or similar getting tagged as a faction mention), not a real second facet.

A script cannot tell these apart from filenames and fact counts alone. This is an identity decision —
scope, not rendering — and per the project's LLM-pipeline design rule, it needs a human checkpoint. Same
principle as the sibling `ensemble-alias-review` skill, applied to the type axis instead of the name axis.

## Locating files

**Ensemble dir:** `docs/ensemble/` relative to the campaign root. Ask if ambiguous.

Key files:
- `docs/ensemble/state_dossiers/*.md` — source dossiers (frontmatter: `name`, `type`, `n_facts`, `chapters`)
- `docs/ensemble/merged_dossiers/*.md` — output; Stage 3 synthesis reads this, not `state_dossiers/`
- `docs/ensemble/.type_merge_decisions.json` — persisted decisions, read at start, written after each group
- `docs/entity_registry.yaml` — if present, worth a quick grep for the candidate's name when a group looks
  ambiguous (registry `distinct:` pairs are keyed on *different* names though, e.g. "Lyra" vs "Ilvara" — they
  won't directly cover a same-name type-collision candidate, so treat this as a secondary sanity check, not
  a hard gate)

Helper scripts (this skill directory):
- `find_type_duplicates.py` — deterministic scan; groups `state_dossiers/*.md` by normalised name, emits
  only groups spanning >1 `type`, excludes groups already fully covered by `.type_merge_decisions.json`
- `apply_type_merge.py` — deterministic apply; concatenates confirmed "merged" sub-groups, copies everything
  else (single-type, "kept separate", and undecided members) through unchanged so nothing silently drops
  out of the synthesis corpus

## Opening move

Run:

```bash
python3 ~/.claude/skills/ensemble-type-merge/find_type_duplicates.py \
  --dossier-dir docs/ensemble/state_dossiers \
  --decisions docs/ensemble/.type_merge_decisions.json
```

(First run: omit `--decisions` or point at a nonexistent path — it degrades gracefully to "nothing
decided yet".)

Report to the user:

> **X candidate groups** (Y single-type entities need no decision; Z groups already decided).
> Working through them one at a time, densest groups first.

Use TaskCreate to enumerate the candidate groups so progress is visible. Then begin the first group
immediately — don't dump the full list upfront.

## Per-group workflow

### Step 1: Show the group

```
## glabbagool  (3 files, 196 total facts)

| File                   | Type    | Facts | Chapters |
|-------------------------|---------|-------|----------|
| npc_glabbagool.md       | npc     | 151   | 34-61    |
| monster_glabbagool.md   | monster | 41    | 34-61    |
| object_glabbagool.md    | object  | 4     | 39-61    |
```

Read the body of every member file, not just frontmatter — the deciding signal is usually in the prose
(does the monster-typed file describe the *same* creature doing combat-flavored things the npc file already
narrates from a social angle, or does it read like an unrelated encounter that happens to share a name?).

### Step 2: Confidence heuristics

These are starting priors, not a substitute for reading the bodies:

- **npc + monster, chapter ranges overlap or adjoin, low file count (2):** high confidence merge — this is
  the documented common case (recurring NPCs who are also combat-capable creatures).
- **A secondary type with very few facts (1-3) relative to a dominant type (10x+ more facts):** treat as a
  noise/mis-extraction candidate first, not an automatic merge. Read it — a 1-fact `faction_daz.md` next to
  a 539-fact `npc_daz.md` is very unlikely to be a real faction-facet of the PC named Daz.
- **npc/monster + location, or npc + faction, or any combo without an obvious "same fictional thing, two
  facets" story:** low confidence — read both bodies fully before recommending anything. A place and a
  person sharing a name is a real, unremarkable coincidence in fiction.
- **3+ types in one group:** flag as higher-stakes. It's fine (and expected) for the resolution to be
  partial — e.g. merge two of the three, keep the third separate. `glabbagool` above is exactly this case if
  the object-typed file turns out to be about a different "Glabbagool" reference.

State your recommendation and confidence before asking, same as `ensemble-alias-review`:

```
**Verdict:** Same entity (merge all) / Same entity except <file> / Different entities / Uncertain
**Reasoning:** <cite what's in the bodies, not just the fact counts>
```

### Step 3: Ask the user

For a clean 2-member group, use AskUserQuestion:

```
Merge npc_glabbagool.md + monster_glabbagool.md?

A) Merge — same entity, different facets
B) Keep separate — different entities that happen to share a name
C) Skip for now — decide later
```

For 3+ member groups where the resolution might be partial, ask conversationally instead (rigid
multiple-choice doesn't fit "merge these two, keep that one separate") — state your read of the split and
let the user confirm, override, or describe a different split in their own words. Accept natural-language
answers.

**Skip** defers the group — do not write a decision, move on. It'll resurface next run.

### Step 4: Persist immediately

Read `docs/ensemble/.type_merge_decisions.json` (default to `{"groups": []}` if missing), append the new
group's decision, write it back — never clobber existing entries.

```json
{
  "key": "glabbagool",
  "resolution": [
    {"status": "merged", "members": ["npc_glabbagool.md", "monster_glabbagool.md"],
     "primary": "npc_glabbagool.md"},
    {"status": "kept_separate", "members": ["object_glabbagool.md"]}
  ]
}
```

- `status: "merged"` sub-groups need `"primary"` — the file whose name the merged output takes (default:
  the densest member; only worth overriding if the user has a reason).
- `status: "kept_separate"` sub-groups can hold one or more members — each stays a distinct file in
  `merged_dossiers/`, untouched.
- A group's `resolution` list must account for every member file in that group (every filename the scanner
  reported for that key appears in exactly one sub-group).

Confirm in one line: `✓ Saved: glabbagool — merged (npc+monster), kept object separate`

Mark the TaskUpdate for this group completed, then move to the next.

## Finishing up

Once all groups are resolved (merged/kept-separate) or explicitly skipped, run the deterministic apply:

```bash
python3 ~/.claude/skills/ensemble-type-merge/apply_type_merge.py \
  --dossier-dir docs/ensemble/state_dossiers \
  --out-dir docs/ensemble/merged_dossiers \
  --decisions docs/ensemble/.type_merge_decisions.json
```

Report its summary line back to the user (merged groups / kept-separate files / copied-unchanged count /
total). If anything is still "copied unchanged (no decision yet)" beyond the single-type entities, tell the
user how many groups remain undecided and that re-running this skill will pick up where it left off.

## Do not

- Auto-merge without confirmation, even for cases that look obviously safe (Glabbagool). The whole point of
  this skill over the plain Stage 2e concatenation script is the human checkpoint on identity — a script
  that "usually gets it right" is exactly the failure mode this replaces.
- Re-run LLM synthesis on any dossier body. Merging is verbatim concatenation — content is kept exactly as
  `facts_to_state.py` wrote it.
- Recommend a merge based on fact counts and chapter ranges alone without reading the body text of every
  member — the deciding signal about whether two type-facets describe one fictional thing is almost always
  in the prose.
- Silently drop a "skip"/undecided group from `merged_dossiers/` — `apply_type_merge.py` always copies
  every member through unmerged until a decision says otherwise, so nothing is missing from the synthesis
  corpus even mid-review.
- Confuse this with `ensemble-alias-review`/`ensemble-alias-merge` (name-variant merging, a different axis).
  If a group here turns out to actually be a spelling/name variant rather than a type-duplicate, say so but
  don't act on it — that's the other skill's job.

## Why this design

Mirrors the project's LLM-pipeline design rule: the scanner is deterministic extraction (Phase 1), the
per-group conversation is the human checkpoint on a genuine identity/scope decision (Phase 2-3), and the
apply step is deterministic rendering (Phase 4) — no LLM call anywhere in this skill, only Claude-as-reader
making a judgment call that a script can't, then a human confirming it.
