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
> Working through them densest groups first.

Use TaskCreate to enumerate progress — one task per group for small sets, one per *batch* for large ones.
Then begin immediately — don't dump the full list upfront.

**Scale / batching.** One-group-one-confirmation is the safe default but it does not scale: the OOTA run had
**91 groups**, and 91 round-trips is a multi-hour slog. When the set is large (roughly >15), offer to
**batch** and let the user choose the cadence — don't impose it. A batch that worked well was 10 groups:
read every member body in the batch, present a compact **verdict table** (one row per group: files, the
recommended `primary` in bold, and any judgment-call flag spelled out), then take a **single bulk
confirmation** with an escape hatch — "approve all N" / "approve except the ones I name" / "go one-by-one".
AskUserQuestion allows up to 4 questions per call, so put each genuine judgment call in the batch (a
keep-separate candidate, a primary-type choice, a re-subject question) in its own question and make the last
question the bulk "approve the rest". This still gives the human a veto on *every* identity decision — they
see each verdict — it just spends one turn per batch instead of one per group. **Persist each batch before
starting the next** so a stop mid-run loses nothing, and treat an ambiguous or mis-clicked batch answer as
*no decision* (re-ask) rather than assuming approval.

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
- **A humanoid *race/people* name typed as `monster` (duergar, drow, kuo-toa, myconid, derro, …):** the
  `monster` typing of a humanoid people is almost always the alignment-monolith stereotype trap, not a real
  bestiary facet — humanoids vary in religion and alignment, so "the duergar" as a hostile monolith is a
  mis-frame. Unless the `monster` body is genuinely about **physiology/anatomy/statblock** (innate
  invisibility mechanics, spore biology, etc.), it is describing *a specific society doing things* and
  should merge into the **faction** dossier, with the **faction file as `primary`** (so the merged output
  stays framed as a people, not a creature). In play this is usually "the <race> of <place>" — e.g. the
  `duergar` group resolved to *"the Duergar of Gracklstugh"* (faction), not duergar-in-general. Only keep a
  `monster` race-facet separate when it is purely physiological reference material. **Keep the race
  location-scoped — don't globalize it at the registry level:** this merge only concerns the *dossier*
  (folding the `monster` facet into the `faction` facet). Separately, the same race is a distinct faction per
  place, and `facts_to_state` emits `Derro (Gracklstugh)`, `Myconid (Neverlight Grove)` for free *as long as
  the bare name is not a registry known-name*. So **do not register the bare race name** — leave it
  unregistered, or add it to the `--exclude-names` file; registering it makes one global bundle that
  collapses every location. You can't register `Derro of Gracklstugh` to catch those facts either — matching
  is by bare subject; the location split is derived from where facts occur. *(GM ruling, OOTA 2026-07-13 —
  corrects an earlier draft that said "register it location-qualified.")*

The OOTA run surfaced a handful of recurring *shapes*. These merge almost every time:

- **A place across `location` + `faction` (+ sometimes a 1-fact `npc`):** almost always one settlement —
  `location` is its geography/state, `faction` its governance/polity, `npc` the place personified as a
  negotiating agent ("Blingdenstone is making weapons deals"). Merge all, **`location` primary**.
  (Blingdenstone, Gracklstugh, Candlekeep, Menzoberranzan, Velkynvelve, Sloobludop all resolved this way.)
- **A deity or demon lord across `monster` / `faction` / `npc`:** the entity itself, its cult/dominion, and
  its invoked-voice-through-a-mortal. Merge all; **primary is usually `monster`** for demon lords, `npc`
  for gods. (Zuggtmoy, Juiblex, Demogorgon, Lolth, Yeenoghu.)
- **A sentient item or creature across `object` / `npc` / `monster`:** a talking sword, an ooze companion, a
  captive dragon legitimately spans all three — magic-item facet, person facet, combat-creature facet.
  Merge all. (Glabbagool = npc+monster+object; Dawnbringer = object+npc+monster; Themberchaud =
  npc+monster+faction+object, where the odd facets were "the sacred flame the Keepers tend" and "his
  political captivity".)
- **The party's own reputation or tactic as a pseudo-entity:** an invented group name or combat combo gets
  scattered across faction/npc/monster/object as different scenes name it. Merge all into **`faction`**. (The
  Ember Vanguard; the Ember Grapple — but keep those two *distinct from each other*.)

And two shapes that mean **keep separate** — the minority this skill exists to catch:

- **A low-fact secondary that is a *different* entity mis-subjected onto this name (not mere noise):** the
  sharpest case is `faction_daz` (1 fact) — the *unknown-patron* plot thread ("someone pays Menzoberranzan
  rates to keep the drow evoker alive") mislabeled with subject "Daz", when Daz is the *protected*, not the
  payer. Merging would inject an inverted fact into the PC's dossier and synthesis would amplify it. Keep
  separate **and** record a re-subject note pointing the stray content at its real subject. Same shape as
  `ilvara`'s 1-fact `faction` ("goods she carried at her death" confusion) — kept out of her merge.
- **A generic common noun with facets in different chapters/contexts:** `spores` (Ilvara's infection vector
  vs Voosbur's dreamscape spores) and `spider` (a wild prison spider vs Daz's Lolth familiar) share a word
  by coincidence, not identity. Keep separate; re-subject each with a qualifier. Contrast a *specific* named
  thing whose files are the same event — `poison` (ch60) had `monster`+`object` that were both the one
  Janussi murder poison, so it merged.

**Calibration (OOTA, 91 groups): ~95% merged, ~5% kept separate.** The large majority of same-name
type-collisions really are one entity — but the keep-separate minority clusters exactly where you'd expect
(1–3-fact secondaries and generic common nouns), and it's the whole reason a blind script is wrong. Default
to reading carefully, not to either merge or keep-separate.

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
- Optional `"note"` (string) on a group records reasoning worth keeping — a mis-extraction diagnosis, a
  kept-separate rationale, or a **re-subject flag** (see below). The apply script ignores it; it's for the
  human record.

**Re-subject flags for generic subject names.** When a merged group's subject is a *generic* name — a
common item, structure, role, or org label that could collide with other instances downstream (`bag of
holding`, `inner circle`, `high tower`, `miners guild`, `temple of oghma`, `poison`, `spider`, …) — the
merge is still correct if the members are the same specific thing, but the *name* needs qualifying by its
owner or parent context so synthesis doesn't conflate it with a different one. **Do not rename in place**
(this skill is verbatim concatenation only). Instead record a `"note"` flagging it as a RE-SUBJECT CANDIDATE
for the entity-triage/alias tooling, with the suggested qualified name — `owner's <item>` or
`<place>_<structure>`. Documented GM rulings: `bag of holding` → "Glabbagool's Bag of Holding"; `inner
circle` → "neverlight_grove_inner_circle". Surface the suggestion to the user when a generic name comes up;
they may want a specific qualifier. *(GM ruling, OOTA 2026-07-13.)* Recurring qualifier shapes from the run:
`<place>_<structure>` (`neverlight_grove_circle_of_masters`, `candlekeep_high_tower`,
`blingdenstone_miners_guild`), `<owner>'s_<item>` ("Glabbagool's Bag of Holding", `daz_familiar_spider`),
and `<thing>_<event>` (`midnight_tears_poison_used_to_kill_janussi`, `sylviras_abyssal_plague`).

**Alias flags (cross-name sameness).** Type-merge only collapses *one* subject name across types; a
*different* subject name for the same thing is the alias tool's job — but you will spot such aliases here, so
leave a breadcrumb. Record a `"note"` marking the alias; don't merge across names yourself. OOTA: the
`poison` group (ch60 murder poison) is the same substance as the separate `midnight tears` group, flagged as
an ALIAS for entity-triage/alias tooling.

**Primary-type accuracy.** The `primary` file's *type* becomes the merged dossier's lead frontmatter, so the
densest-default is wrong when the densest member is typed inaptly. When densest ≠ apt, surface the choice to
the user instead of taking densest silently: `faerzress` (an ambient phenomenon) took `location` as primary
over the denser `monster`; `deepking` (an individual ruler) kept `faction` as primary (densest) but with a
note flagging the office-vs-person mismatch. Races always take `faction` primary (see Step 2), regardless of
which file is densest.

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
  don't act on it — that's the other skill's job. You *may* leave an alias/re-subject `"note"` as a
  breadcrumb (see Step 4); just never merge across two *different* subject names yourself.
- Treat an ambiguous, mis-clicked, or timed-out batch answer as **approval**. It is a non-decision — re-ask
  the exact groups it left unresolved. Only an explicit "approve" (of all, or of the named remainder) is a
  decision; an answer that only refines one group in a batch does not silently ratify the rest.

## Why this design

Mirrors the project's LLM-pipeline design rule: the scanner is deterministic extraction (Phase 1), the
per-group conversation is the human checkpoint on a genuine identity/scope decision (Phase 2-3), and the
apply step is deterministic rendering (Phase 4) — no LLM call anywhere in this skill, only Claude-as-reader
making a judgment call that a script can't, then a human confirming it.
