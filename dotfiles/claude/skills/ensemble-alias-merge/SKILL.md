---
name: ensemble-alias-merge
description: >
  Merge ensemble state_dossier files based on approved alias decisions in .alias_decisions.json.
  Deterministic — no LLM re-synthesis. Reads alias decisions as source of truth, classifies
  each merge (rename / subset / overlap), confirms overlaps with user, then executes.
  Invoke as /ensemble-alias-merge [campaign-dir].
tools: Read, Edit, Write, Bash
---

# Ensemble Alias Merge

Merge `state_dossiers/*.md` files based on alias decisions already approved in `.alias_decisions.json`.
No clustering, no re-confirmation of "same entity?" — those decisions are done. This skill executes them.

## Why this exists

The alias review pass (`/ensemble-alias-review`) populated `.alias_decisions.json` with approved merges.
The dossier `.md` files on disk were NOT updated — variant dossiers still exist alongside canonicals.
This skill closes that gap deterministically: rename, append aliases to frontmatter, delete variants.

## Locating files

**Ensemble dir:** `docs/ensemble/` relative to campaign root (default: Phandalin).

Key files:
- `docs/ensemble/.alias_decisions.json` — source of truth; only `status: "approved"` entries are processed
- `docs/ensemble/state_dossiers/*.md` — files to merge; pattern `<type>_<slug>.md`
- Types: `npc`, `location`, `monster`, `object`, `faction`

## Dossier format

**Frontmatter** (YAML block between `---`):
```yaml
name: Falcon
type: npc
n_facts: 95
chapters: 17-45
```

**After merge**, canonical gains:
```yaml
name: Falcon the Hunter
type: npc
n_facts: 95
chapters: 17-45
aliases:
  - Falcon
  - The Falcon
```

**Body sections:** `## Identity`, `## Personality & Motivations`, `## History with the Party`,
`## Current Status`, `## Relationships`, `## Uncertainty`.

Add "Also known as: Falcon, The Falcon" parenthetical to the `## Identity` section (first line after header).
If `## Identity` is missing, add it before the first `##` section.

## Slugify rule

Canonical name → filename slug: lowercase, replace any non-alphanumeric run with `_`, strip leading/trailing `_`.

Examples:
- "Falcon the Hunter" → `falcon_the_hunter`
- "Meril's Staff" → `meril_s_staff`
- "Elara 'Seasong' Meliamne" → `elara_seasong_meliamne`
- "Dragonbarrow Will-o'-wisps" → `dragonbarrow_will_o_wisps`

To find a dossier file for a name, try all type prefixes: `npc_<slug>.md`, `location_<slug>.md`,
`monster_<slug>.md`, `object_<slug>.md`, `faction_<slug>.md`.

## Phase 0: Backup + load

```bash
cd docs/ensemble
tar czf state_dossiers.backup-$(date +%Y%m%d-%H%M%S).tar.gz state_dossiers/
```

Load `.alias_decisions.json`, filter to `status: "approved"`. Report count.

## Phase 1: Inventory

For each approved decision:
- `canonical` — the target name
- `candidates` — all names including canonical; variants = candidates minus canonical

For each variant name, find matching dossier files (all type prefixes).
For the canonical name, find matching dossier files.

Build a work list. Skip decisions where no variant dossier files exist (nothing to do).

**Edge case — multiple canonical files** (e.g., `npc_harbin_wester.md` + `npc_townmaster_harbin_wester.md`
both match "Harbin Wester"): pick the one with highest `n_facts` as the primary canonical file;
the other becomes a variant to merge first, then proceed.

**Edge case — variant file IS canonical file** (same path): skip (noop).

## Phase 2: Classify

For each merge, classify based on n_facts ratio:

**`rename`** — canonical has NO matching dossier file; variant has one.
Action: rename variant file to `<type>_<canonical_slug>.md`, update `name:` in frontmatter.
Example: "Dragonbarrow Will-o'-wisps" ← monster_will_o_wisp.md

**`subset`** — canonical dossier exists; variant n_facts < 30% of canonical n_facts.
Action: auto-merge (no body content needed from variant). Add alias to frontmatter + "Also known as" note.
Example: Valphine (512 facts) ← Valphine Sortorra (21 facts, 4% ratio → subset)

**`overlap`** — canonical dossier exists; variant n_facts ≥ 30% of canonical n_facts.
Action: show user both bodies before deciding.
Example: npc_cryovain.md (N facts) ← monster_white_dragon.md (M facts, if M ≥ 30% of N)

Show the user a classified summary before proceeding:
```
## Merge plan (N decisions)

Renames (N):
  "Dragonbarrow Will-o'-wisps" ← Will-o'-wisp, will-o'-wisps

Subset auto-merges (N):
  Valphine (512) ← Valphine Sortorra (21)
  Falcon the Hunter (11) ← Falcon (95)   ← NOTE: canonical is thinner; use richer file as base

Overlaps requiring review (N):
  Cryovain (X facts) ← white dragon (Y facts)
  ...

Proceed with renames and subsets? (yes / review-first / stop)
```

**Special subset case — canonical is THINNER than a variant**: when the canonical-named file
has fewer facts than a variant-named file (e.g., `npc_falcon_the_hunter.md` has 11 facts but
`npc_falcon.md` has 95 facts), treat the richer variant as the content base. Rename the richer
file to the canonical slug, merge the thinner canonical's unique content in, delete the thinner file.
Still classified as `subset` if ratio applies; note to user which file "wins" on content.

## Phase 3: Confirm overlaps

For each `overlap` group, show:

```
## [Canonical] ← [Variant]
Canonical: <N> facts, ch <range>
Variant:   <M> facts, ch <range>

### Canonical body:
<first 20 lines of body>

### Variant body:
<first 20 lines of body>

keep-canonical  — discard variant body, keep canonical + add alias
keep-variant    — use variant body as base + add alias  
keep-both       — append variant's ## Uncertainty block to canonical (safe concat)
manual          — skip for now
```

## Phase 4: Execute

For each merge (rename / subset / confirmed overlap):

1. **Determine winner file** — the file whose body content is kept
2. **Update winner frontmatter:**
   - `name:` → canonical name
   - Add `aliases:` list with all variant names
   - `chapters:` → union range (min of all mins, max of all maxes)
   - `n_facts:` → winner's value (do not sum — facts weren't re-counted)
3. **Update winner body:**
   - Add/update `## Identity` section: first line → "Also known as: [variant1], [variant2]"
4. **Rename winner file** if its path ≠ `<type>_<canonical_slug>.md`
5. **Delete variant files** — safety check: never delete a file whose resolved path equals the winner path

Persist after each merge so the session is resumable if interrupted.

## Phase 5: Report

```
## Ensemble alias merge complete

Renames:           N
Subset merges:     N
Overlap merges:    N (confirmed) / N (deferred to manual)
Files deleted:     N
Nothing to do:     N (no dossier files found for these decisions)

Backup: state_dossiers.backup-<timestamp>.tar.gz
```

List any deferred/manual items so the user knows what's left.

## Do not

- Re-run LLM synthesis on any dossier. Body content is kept verbatim from the winner file.
- Delete a variant file before confirming its path ≠ the winner path.
- Modify `.alias_decisions.json` — it is read-only input to this skill.
- Merge rejected decisions (status ≠ "approved").
- Sum `n_facts` across merged files — the count reflects facts used to generate that dossier, not a running total.
