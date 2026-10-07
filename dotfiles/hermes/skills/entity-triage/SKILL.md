---
name: entity-triage
description: "Use when triaging unknown proper nouns against a campaign entity registry. Walks the registry.py triage-candidates queue with the GM - new entity, alias, not-an-entity, or defer."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [dnd, campaign, registry, triage, human-checkpoint]
    related_skills: []
---

# Entity Triage

## Overview

Reconcile a campaign entity registry with the proper nouns that actually show
up in play. CampaignGenerator's `registry.py triage-candidates` diffs the
proper nouns in a campaign's session outputs against `docs/entity_registry.yaml`
and emits a queue of **UNKNOWN surface forms** — names/spellings the registry
has never seen. This skill walks that queue with the GM and records each
decision.

`triage-candidates` deliberately does **not** decide who is who — identity is a
scope decision, not a rendering decision. It only *surfaces* candidates and,
for each, a `near_miss` hint (closest registry name by string similarity).
This skill is the human checkpoint: it gathers evidence (5etools lookup,
campaign-context lookups, the near-miss hint), **recommends**, and renders the
GM's confirmed ruling into a deterministic, validated registry write. The hint
and the 5etools verdict are evidence for the GM — never auto-applied.

## When to Use

- GM asks to reconcile the entity registry, process unknown names, or run triage
  after a session pipeline (`enhance_summary` → `scene_extract` → facts).
- A fact-extraction run surfaced names the registry has never seen.
- **Not for:** repairing garblings already recorded as aliases or duplicate
  entities — that is `registry-cleanup` (sibling workflow, different queue).

## Required information

1. **Campaign dir** — from the request, else CWD if it contains
   `docs/entity_registry.yaml`, else ask. Resolve to an absolute path.
2. The registry must exist. If `docs/entity_registry.yaml` is absent, tell the
   GM to run `registry.py init <dir>` (and the importers) first — this skill
   triages against an existing registry; it does not bootstrap one.

Every ruling is presented via `clarify` with **≥2 options and always a "not an
entity" and a "defer" escape hatch** — the GM must never be forced to classify
something as a real entity. If a question comes back unanswered or ambiguous,
re-ask; a timeout is not a decision.

## The four rulings (and their write-backs)

Every candidate resolves to exactly one of:

| Ruling | Meaning | Write-back |
|---|---|---|
| **New entity** | A real entity the registry is missing | `registry.py add <dir> --name S --type T --yes` |
| **Alias of N** | Variant/typo/honorific of existing entity N (the `near_miss` case) | `registry.py alias <dir> --to "N" "S"` |
| **Not an entity** | Generic noun, monster/spell/item type, scene role, VTT artifact | skill-side state (`ignored`) — **no registry write** |
| **Defer** | GM isn't sure yet | skill-side state (`deferred`) — no registry write |

All writes go through `registry.py` verbs (they route through
`campaignlib.registry.validate`). **Never hand-edit `entity_registry.yaml`.**

### Sub-case — distinct-but-similar

S looks like near-miss N but is a *different* character (e.g. `Khalessa` vs
`Khelessa Draga`): rule **New entity**, AND
`registry.py mark-distinct <dir> "S" "N"` so the pair stops re-suggesting.

### Sub-case — never register a bare race/collective

When the candidate is a *people/race or generic collective* (`Derro`, `Myconid`,
`Duergar`, `Drow`, `Kuo-toa`, "the guards", "the cultists"), registering the
bare name is the **wrong** move — it makes the name a *global* known bundle, so
`facts_to_state` collapses every occurrence across the whole campaign into one
place-blind dossier. The opposite is wanted: the same race is a *distinct
faction in each place*, which `facts_to_state` produces for free — any subject
that is **not** a registry known-name is **location-scoped** into per-place
bundles (`Derro (Gracklstugh)`, `Drow (Velkynvelve)`). So rule these **Not an
entity** (registry-wise) and leave them unregistered. If a race name *is*
already registered, add it to the campaign's exclude-names file
(e.g. `docs/ensemble/location_scoped_races.md`) to force location-scoping.
You **cannot** register `Derro of Gracklstugh` and have it catch
Gracklstugh-derro facts: known-name matching is by *bare subject*; the
location split comes from where facts occur, not from registry names.
Register a race globally only if one campaign-wide monolith is truly wanted
(rare). *(GM ruling, OOTA 2026-07-13 — adding bare Derro/Myconid globalized
them and collapsed the built-in location-scoping; reverted.)*

### Sub-case — bare fragment of a registered multi-word name

(e.g. `Wester` when `Harbin Wester` is registered, `Coster` when `Lionshield
Coster` is registered): `near_miss` frequently **misses these entirely** — it
scores whole-normalized-string similarity (`SequenceMatcher` on `"wester"` vs
`"harbinwester"`), which short fragments of long names rarely clear. So
`near_miss: none` does **not** mean "unrelated." For any candidate with no
near_miss, also check by eye for substring / last-word / surname matches
(grep `entity_registry.yaml` for the candidate); route hits into the Converse
lane even without a hint.

Then **calibrate before recommending alias** — a bare-word match alone is not
enough:
- **Distinctive word (surname, uncommon term)** — `Wester`, `Hallwinter`,
  `Coster`, `Yimek`(→`Yeemik`) — high confidence, recommend alias.
- **Ordinary English tail-word** — `Exchange` (of "Phandalin Miner's
  Exchange"), `Alliance` (of "Lords' Alliance"), `Enclave`, `Gauntlet`,
  `Trail`, `Manor`, `Coast`, `Tavern`, `Orchard`, `Hideout` — **too risky to
  alias from the bare match alone**, even with matching session context. A
  session mentioning "the alliance" or "an orchard" is far more likely using
  the word ordinarily. Default recommendation: **not an entity**. This
  reverses the "substring match → probably same thing" instinct. *(GM
  correction, Obelisk 2026-07-18.)*

### Sub-case — fragment names a family/group, no single alias target

(e.g. `Dendar` — likely a mishearing of `Dendrar`, but four individually-
registered Dendars exist and none alone is "the" answer): don't force-alias to
one member. Rule **New entity**, type `faction`, name the collective, alias the
fragment to it:
```bash
python registry.py add <dir> --name "Dendrar family" --type faction \
  --aliases "Dendar" --provenance on_the_fly --yes
```

**Never put a not-an-entity into the registry.** `rejected_aliases` means
"these ≥2 names are not aliases of *each other*" — a different claim from
"this surface form isn't an entity." Non-entities belong in the state file.

## Workflow

### Phase 0 — Pre-flight

1. Resolve campaign dir; confirm `docs/entity_registry.yaml` exists.
2. **Check for `docs/party.yaml` (or `config/party.yaml`) — do not assume it
   exists.** `triage-candidates` only excludes PC/sidekick names if present. If
   missing, every PC name (first, full, title/surname fragments separately)
   surfaces on *every* run, forever. Before generating the queue:
   - Find campaign-original names: module-inventory glossary appendix,
     `docs/party.md`, or ask the GM.
   - Build `docs/party.yaml` as `characters: [{name: "..."}, ...]`. **List
     every surface form separately** — `Registry.known_names()` expands
     multi-word registry names but NOT party.yaml names, so `"Zenvon Foreput"`
     alone won't suppress bare `"Zenvon"`. List both (and any form seen in play).
   - Additive, not a blocker — GM may proceed without, but then PC names need
     per-run `ignored` rulings instead of a permanent fix.
3. **Load or create state file** `<campaign-dir>/docs/.entity_triage_state.json`:
   ```json
   {
     "started_at": "ISO-8601", "updated_at": "ISO-8601",
     "ignored":  [{"surface": "Narrator", "norm": "narrator", "reason": "VTT artifact", "at": "..."}],
     "deferred": [{"surface": "the Pale Cloak", "norm": "thepalecloak", "note": "maybe a title?", "at": "..."}],
     "resolved": [{"surface": "Ilvarra", "ruling": "alias", "target": "Ilvara Mizzrym", "at": "..."}]
   }
   ```
   `ignored`/`deferred` are the "don't re-ask me" lists; `resolved` is the
   audit log of writes made through this skill (registry remains truth).
   Timestamps: `date -u +%Y-%m-%dT%H:%M:%SZ`.
4. **Generate a fresh queue** (never reuse a stale one — the registry may have
   changed):
   ```bash
   python registry.py triage-candidates <campaign-dir> --out <campaign-dir>/docs/.triage_queue.json [--bible path/to/bible.md] [--min-count 2]
   ```
   Run from the CampaignGenerator install (e.g. `~/src/CampaignGenerator`;
   config auto-detects). `--min-count 2` drops one-off mentions. Both `.json`
   dotfiles are transient — suggest gitignoring them.

### Phase 1 — Load and subtract

Queue shape (`docs/.triage_queue.json`):
```json
{ "campaign": "...", "generated_from": ["docs/ensemble/merged.json"],
  "candidates": [
    { "surface": "Ilvarra", "norm": "ilvarra", "count": 7,
      "sources": ["docs/ensemble/per_chapter/03/merged.json"],
      "near_miss": { "name": "Ilvara Mizzrym", "ratio": 0.91 } } ] }
```
Subtract by `norm` everything in state `ignored`/`deferred`. PC names *should*
be excluded upstream — if they still appear, don't register them: report it
and fix `party.yaml` (permanent) or `ignore` them this run. Never add a PC as
a registry entity.

Watch for **real people's names** from VTT speaker-diarization bleed ("Nikhil",
"Kostadis") — not PCs, not party.yaml material; a `not an entity` case, same
bucket as "Narrator".

Report one line: `N candidates (M with near-miss hints); K suppressed by prior
rulings.` Then begin — do not dump the full list.

### Phase 2 — Genericness evidence (5etools), then two lanes

For each candidate, check whether the surface matches a **published generic
entry** (monster type, spell, item, condition) — evidence it's generic
(`orc`, `fireball`) not campaign-specific (`Grazzt`, `Ilvara`):

```bash
python pipelines/rlm/fivetools_catalog.py search "<surface>" --limit 5
```
from the CampaignGenerator dir. JSONL hits with `type`, `name`, `score`; a
high-score hit whose name matches and type is generic ⇒ likely not-an-entity.
Record `generic?: yes|no|unknown`. **Never block on tooling** — no 5etools
data resolved ⇒ mark `unknown` and let the GM decide from count/sources. A
`generic?: yes` verdict *suggests* not-an-entity but never decides it (a
campaign can name an NPC "Orc" ironically). The GM rules.

**Partition into two lanes:**
- **Batch lane (shallow):** no near_miss, no by-eye fragment match, and either
  `generic?: yes` or clearly a fresh proper noun. Low ambiguity; batch.
- **Converse lane (stakes):** any near_miss hint (alias-vs-distinct is a
  precision call), bare-fragment suspects even with `near_miss: none` (the
  algorithm's blind spot), `generic?: unknown` on high-count forms, or
  anything spanning many sources. One at a time.

### Phase 3a — Batch lane

Present 3–5 candidates per `clarify` call, each annotated with evidence:

```
Candidate: "Narrator"  (count 12, 4 sources; 5etools: no; near-miss: none)
choices: [Not an entity] [New entity] [Defer]
```
Lead with the recommended option given the evidence (`generic?: yes` →
"Not an entity" first; fresh proper noun → "New entity" first). Always include
Defer. For New entity, follow up with the type question (Phase 3c).

### Phase 3b — Converse lane (one at a time)

1. **Gather context** for candidate S and near-miss N from campaign docs
   (`docs/world_state.md`, `docs/planning.md`, dossiers; grep works).
2. **Recommend** with reasoning and confidence:
   ```
   ## "Ilvarra" vs registry "Ilvara Mizzrym"  (near-miss ratio 0.91)
   count 7 · sources: merged ch.3 · 5etools: no match
   Verdict: Alias of "Ilvara Mizzrym" (high — one-char VTT typo, same scenes)
   ```
   Bands: **high** (typo/VTT variant, same role/scenes) → recommend alias;
   **medium** (plausible, thin context) → recommend, flag; **low** (similar
   string, different role — retcon/namesake risk) → recommend
   distinct-but-similar, flag explicitly.
3. **Decide** via `clarify` (choices: Alias of N / Distinct entity / New
   unrelated entity / Not an entity / Defer). Offer "look up more context"
   as a path before deciding.

### Phase 3c — Execute immediately

Run the matching CLI write, then update the state file **before the next
candidate** (the session must stay resumable at any point):

- Alias: `python registry.py alias <dir> --to "Ilvara Mizzrym" "Ilvarra"`
- New entity (ask type first — `npc location faction item deity event concept`;
  offer `--provenance module|supplement|on_the_fly` if known):
  `python registry.py add <dir> --name "Sirac" --type npc --yes`
- Distinct-but-similar: the `add` above, then
  `python registry.py mark-distinct <dir> "Sirac" "Sarith Kzekarit"`
- Not an entity → append to state `ignored` (surface+norm+reason). No write.
- Defer → append to state `deferred` (surface+norm+note). No write.

If a verb errors (unexpected collision), surface the message and re-ask —
don't force. Confirm each in one line: `✓ Ilvarra → alias of Ilvara Mizzrym`.

### Phase 4 — Finish

1. Tally: entities added, aliases attached, distinct pairs, ignored, deferred.
2. Run `registry.py project <dir>` **before** `registry.py check <dir>`, not
   after — `project` regenerates `aliases.json`/`entity_inventory.md`, and
   `check` diffs against those projections; running `check` first reports this
   session's own edits as false-positive drift.
3. Leftover `deferred` persist for the next run; `ignored` stay suppressed.

**Done when:** queue exhausted (or GM says stop), every candidate has a
recorded ruling in state, tally reported, project→check run clean.

## Offline review artifact (HTML)

When the queue is too long for 1x1 `clarify` (roughly >12 candidates) or the GM
asks to review offline, publish ONE self-contained HTML page instead of a chat
marathon — a tired reviewer rubber-stamps; a page they can mark at their own
pace keeps the checkpoint real. Format follows the staged-consistency review
page: single file, no network, no build, decisions persist in localStorage,
Save/Copy exports one JSON.

**This artifact does not write anything.** It collects rulings; the agent
applies them afterwards through the `registry.py` verbs. Nothing reaches the
registry until the export is applied and confirmed.

### Pipeline

1. Build the queue as usual (Phase 0, `triage_queue.json`).
2. Run Phase 2 evidence-gathering for every candidate FIRST (5etools verdicts,
   near-miss merge, lane partition) — the page is built from settled evidence,
   not as a substitute for gathering it.
3. Author a **review plan** `docs/.triage_review_plan.json`:
   ```json
   {
     "campaign": "obelisk",
     "title": "Obelisk — entity triage review",
     "eyebrow": "obelisk / entity registry triage",
     "lede": "38 candidates after 12 suppressed by prior rulings.",
     "items": [
       { "surface": "Ilvarra", "lane": "converse", "generic": "no",
         "rec": "alias", "rec_conf": "high — one-char typo, same scenes ch.3",
         "rec_meta": {"target": "Ilvara Mizzrym"},
         "ev": "near-miss 0.91; both appear in the Velkynvelve escort facts." },
       { "surface": "Narrator", "lane": "batch", "generic": "unknown",
         "rec": "ignore", "ev": "VTT speaker label bleed; 12 mentions, 4 chapters." }
     ]
   }
   ```
   `rec` ∈ `add | alias | distinct | ignore | defer | discuss`. `rec_meta`
   carries what the write needs (`target` for alias/distinct, `type` for add —
   resolve the type per the four-rulings table before rendering; never let a
   silent default `npc` ride into the export). Candidates absent from the plan
   are not shown; plan items missing from the queue merge with blanks. Per-card
   `choices` override the default option set when a candidate needs it.
4. Render:
   ```bash
   python3 scripts/render_triage_review.py \
     --queue <campaign>/docs/.triage_queue.json \
     --plan  <campaign>/docs/.triage_review_plan.json \
     --out   <campaign>/docs/entity_triage_review.html
   ```
   Tell the GM the absolute path; they open it in any browser, offline.
5. The GM marks cards (the recommended option is outlined; the note field
   carries type / alias-target / discuss question) and clicks **Save output**
   (or Copy). The export `entity_triage_decisions_<date>.json` has
   `kind: "entity-triage-decisions"`, `decisions: {id: {k, meta}}`, `notes`,
   `unmarked`. GM hands the file (or pasted JSON) back.
6. Apply the export (Phase 3c mechanics per card, using `meta`/`note` for
   targets and types), updating the triage state file as you go. Cards with
   missing `meta` (alias without target, add without type) → ask per card;
   never guess. `unmarked` candidates go to state `deferred`.
7. Finish with Phase 4 (`project` then `check`). In the final report state
   explicitly which rulings came via the artifact export.

## Renaming an existing registry entity (adjacent, not a ruling)

A GM ruling elsewhere says a registered entity's canonical should change.
`registry.py` has **no rename verb**. The closest, `merge`, always keeps the
folded name as a **resolving alias**:
```bash
python registry.py add <dir> --name "Tuck Stonehill" --type npc --yes
python registry.py merge <dir> "Pip" --into "Tuck Stonehill"
```
Correct when the old name should keep resolving (usual case). **Wrong** when
the old name must stop resolving — e.g. "Pip" unqualified means a different,
intentionally-unregistered sidekick at this table, so aliasing Pip → the
renamed NPC would misattribute future facts. Confirm which with the GM; don't
assume "keep the alias" just because merge is the only rename-shaped verb.

If the alias must be dropped, no verb covers it either — use the same
validated API every verb uses (never a raw YAML edit that skips `validate()`):
```python
from pathlib import Path
from campaignlib.registry import load_registry, save_registry
path = Path("<dir>/docs/entity_registry.yaml")
reg = load_registry(path)
target = next(e for e in reg.entities if e.name == "Tuck Stonehill")
target.aliases = [a for a in target.aliases if a != "Pip"]
save_registry(reg, path)  # re-validates before writing
```

## Common Pitfalls

1. **Auto-deciding a near-miss.** Alias-vs-distinct is a precision call; the
   hint is evidence, never a verdict.
2. **Writing a non-entity into the registry** (via `add` or
   `rejected_aliases`) — state file `ignored` only.
3. **Skipping the genericness check** on a plausibly-generic form — run the
   catalog search; mark `unknown` and move on if data won't resolve.
4. **Reusing a stale queue** — always regenerate; the registry moves.
5. **Re-adding a PC** — PCs come from `party.yaml`; if one appears in the
   queue, fix party.yaml (or ignore this run), never register.
6. **Aliasing from a bare substring match** — distinctive word vs ordinary
   English vocabulary decides the default, not the match itself.
7. **Hand-editing entity_registry.yaml** — verbs, or the validated
   load/save API when no verb exists. Nothing else.
8. **Running `check` before `project`** — reports this session's edits as drift.
9. **`fivetools_catalog.py` path** — it lives at
   `pipelines/rlm/fivetools_catalog.py` under the CampaignGenerator install,
   not at the repo root (the original Claude skill said repo root — wrong).

## Verification Checklist

- [ ] Every candidate has exactly one ruling recorded (registry write or state entry)
- [ ] Each registry write confirmed with a one-line `✓` and succeeded (no swallowed errors)
- [ ] State file updated after every decision — resumable at any point
- [ ] No PC, race/collective, real-person, or VTT-artifact name was registered
- [ ] `project` ran before `check`; `check` output reviewed
- [ ] Tally reported; deferred list surfaced for next run
