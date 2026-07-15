---
name: entity-triage
description: >
  Walk the UNKNOWN-surface-form queue emitted by CampaignGenerator's
  `registry.py triage-candidates` — proper nouns that appear in session outputs
  but aren't in the entity registry yet. For each candidate the GM decides:
  new entity, alias of an existing entity, not-an-entity, or defer. Positive
  rulings are written to docs/entity_registry.yaml through validated CLI verbs;
  not-an-entity/defer rulings live in a resumable skill-side state file so they
  don't re-surface. Invoke as /entity-triage [campaign-dir].
tools: Read, Write, Bash, AskUserQuestion, ToolSearch
---

# Entity Triage

Reconcile the campaign entity registry with the proper nouns that actually show
up in play. `registry.py triage-candidates` diffs the proper nouns in a
campaign's session outputs (summaries, scene extractions, merged facts, and
optionally a bible) against `docs/entity_registry.yaml` and emits a queue of
**UNKNOWN surface forms** — names/spellings the registry has never seen. This
skill walks that queue with the GM and records each decision.

## Why this exists

`triage-candidates` deliberately does **not** decide who is who — identity is a
scope decision, not a rendering decision (the repo's LLM Pipeline rule). It only
*surfaces* candidates and, for each, a `near_miss` hint (the closest existing
registry name, by string similarity). This skill is the human checkpoint: it
gathers evidence (a 5etools lookup, campaign-context lookups, the near-miss
hint), **recommends**, and then renders the GM's confirmed decision into a
deterministic, validated registry write. The hint and the 5etools verdict are
evidence for the GM — they are never auto-applied.

## The four rulings (and their write-backs)

Every candidate resolves to exactly one of:

| Ruling | Meaning | Write-back |
|---|---|---|
| **New entity** | A real entity the registry is missing | `registry.py add <dir> --name S --type T --yes` |
| **Alias of N** | A variant/typo/honorific of an existing entity N (the `near_miss` case) | `registry.py alias <dir> --to "N" "S"` |
| **Not an entity** | A generic noun, monster/spell/item type, scene role, or VTT artifact | skill-side state (`ignored`) — **no registry write** |
| **Defer** | GM isn't sure yet | skill-side state (`deferred`) — no registry write |

Special sub-case — **distinct-but-similar** (S looks like near-miss N but is a
*different* character, e.g. `Khalessa` vs `Khelessa Draga`): rule it **New
entity**, AND run `registry.py mark-distinct <dir> "S" "N"` so the near-miss
stops re-suggesting the pair on future runs.

Special sub-case — **do NOT register a bare race/collective as a global entity**: when
a candidate is a *people/race or generic collective* (`Derro`, `Myconid`, `Duergar`,
`Drow`, `Kuo-toa`, "the guards", "the cultists"), registering the bare name is the
**wrong** move — it makes the name a *global* known bundle, so `facts_to_state`
collapses every occurrence across the whole campaign into one place-blind dossier. What
you almost always want is the opposite: the same race is a *distinct faction in each
place*, and `facts_to_state` produces that for free — any subject that is **not** a
registry known-name is **location-scoped** into per-place bundles (`Derro (Gracklstugh)`,
`Myconid (Neverlight Grove)`, `Drow (Velkynvelve)`). So rule these **Not an entity**
(registry-wise) — leave them unregistered so location-scoping handles them — and if a
race name *is* already registered (or would otherwise read as known), add it to the
campaign's `--exclude-names` file (e.g. `docs/ensemble/location_scoped_races.md`) to
force location-scoping. You **cannot** register `Derro of Gracklstugh` and have it catch
Gracklstugh-derro facts: known-name matching is by *bare subject*, and the location split
is derived from where each fact occurs, not from a registry name. Register a race
globally only if you truly want one campaign-wide monolith (rare). *(GM ruling, OOTA
2026-07-13 — adding bare `Derro`/`Myconid` globalized them and collapsed the built-in
location-scoping; reverted. Corrects an earlier draft of this note that wrongly said
"add it location-qualified.")*

**Never put a not-an-entity into the registry.** `rejected_aliases` means "these
≥2 names are not aliases of *each other*" — a different claim from "this surface
form isn't an entity at all." Non-entities belong in this skill's state file, so
`triage-candidates` keeps surfacing them but this skill filters them out.

## Required information

1. **Campaign dir** — from the invocation arg, else the CWD if it contains
   `docs/entity_registry.yaml`, else ask. Resolve to an absolute path.
2. The registry must exist. If `docs/entity_registry.yaml` is absent, tell the
   GM to run `registry.py init <dir>` (and the importers) first — this skill
   triages against an existing registry; it does not bootstrap one.

If `AskUserQuestion` is not loaded, run `ToolSearch` with
`query: "select:AskUserQuestion"` first. Validation gotcha: every question needs
≥2 options. Always include a **"not an entity / scene-scoped"** and a **"defer"**
escape hatch — the GM must never be forced to classify something as a real
entity.

## Workflow

### Phase 0 — Pre-flight

1. Resolve the campaign dir; confirm `docs/entity_registry.yaml` exists.
2. **Load or create the state file** at `<campaign-dir>/docs/.entity_triage_state.json`:
   ```json
   {
     "started_at": "ISO-8601",
     "updated_at": "ISO-8601",
     "ignored":   [{"surface": "Narrator", "norm": "narrator", "reason": "VTT artifact", "at": "ISO-8601"}],
     "deferred":  [{"surface": "the Pale Cloak", "norm": "thepalecloak", "note": "maybe a title?", "at": "ISO-8601"}],
     "resolved":  [{"surface": "Ilvarra", "ruling": "alias", "target": "Ilvara Mizzrym", "at": "ISO-8601"}]
   }
   ```
   `ignored` and `deferred` are the "don't re-ask me" lists. `resolved` is an
   audit log of registry writes made through this skill (handy on resume; the
   registry itself is the source of truth). Use `date -u +%Y-%m-%dT%H:%M:%SZ`
   for timestamps.
3. **Generate a fresh queue** (do not reuse a stale one — the registry may have
   changed since last run):
   ```bash
   python registry.py triage-candidates <campaign-dir> --out <campaign-dir>/docs/.triage_queue.json [--bible path/to/bible.md] [--min-count 2]
   ```
   Run from the campaign workspace (config auto-detects). `--min-count 2` is a
   good default to drop one-off mentions; confirm with the GM if the queue is
   huge or tiny. Both `.triage_queue.json` and `.entity_triage_state.json` are
   transient/local — suggest gitignoring them.

### Phase 1 — Load and subtract

Read `.triage_queue.json`. Its shape:
```json
{ "campaign": "...", "generated_from": ["summaries/..."],
  "candidates": [
    { "surface": "Ilvarra", "norm": "ilvarra", "count": 7,
      "sources": ["summaries/s03/session-summary.md"],
      "near_miss": { "name": "Ilvara Mizzrym", "ratio": 0.91 } } ] }
```
Subtract by `norm` every candidate already in the state file's `ignored` or
`deferred` lists. (PCs are already excluded upstream — `triage-candidates` unions
party.yaml names into "known" — so you should not see PC names here. If you do,
that's a bug worth reporting, not an entity to add.)

Report a one-line summary: `N candidates (M with near-miss hints); K suppressed
by prior rulings.` Then begin — do not dump the full list.

### Phase 2 — Auto-classify with 5etools (evidence, not decision)

For each remaining candidate, check whether the surface form matches a
**published generic entry** — a monster/creature type, spell, item, or condition
name — in the 5etools data. A match is strong evidence the form is *generic*
(e.g. `orc`, `fireball`, `longsword`) rather than a campaign-specific proper
noun (e.g. `Grazzt`, `Ilvara`).

- **Backbone (always available, deterministic):**
  ```bash
  python fivetools_catalog.py search "<surface>" --limit 5
  ```
  from the CampaignGenerator dir. It emits JSONL hits, each with a `type`
  (`monster`, `spell`, `item`, `condition`, …), `name`, and `score`. A
  high-score hit whose `name` matches the surface form and whose `type` is a
  generic category is strong evidence the form is generic. This is the local,
  deterministic answer to the GM's "is `orc` a monster or a name?" question,
  over the same 5etools data the MCP serves.
- **Optional accelerator:** the per-campaign 5etools MCP (`launch_5etools_mcp.py`)
  may also be connected — discover its tools via `ToolSearch query: "mcp__5etools"`.
  Its confirmed surface is source/TOC/section (`list_sources` / `get_toc` /
  `get_section`), which is **not** a name lookup; only use the MCP for this check
  if it exposes a name/bestiary search tool. If it doesn't, don't force it — the
  catalog backbone already answers the question.
- Record a per-candidate `generic?` verdict: `yes` (matches a published type),
  `no` (no match), or `unknown` (couldn't check). **Never block on tooling** —
  if the catalog can't be built (no 5etools data resolved) and the MCP has no
  lookup, mark `unknown` and let the GM decide from count/sources alone.

This is evidence-gathering. A `generic?: yes` verdict *suggests* "not an entity"
but does not decide it — a campaign can name an NPC "Orc" ironically. The GM
rules.

**Partition the queue into two lanes:**

- **Batch lane (shallow):** candidates with **no `near_miss`** — either
  `generic?: yes` (likely not-an-entity) or clearly a fresh proper noun (likely
  new entity). These are low-ambiguity; batch them.
- **Converse lane (stakes):** candidates **with a `near_miss` hint** (alias vs
  distinct-but-similar is a precision call), or `generic?: unknown` on a
  high-`count` form, or anything spanning many sources. These get one-at-a-time
  reasoning.

### Phase 3a — Batch lane

Present 3–5 candidates per `AskUserQuestion`, one question per candidate, each
annotated with the evidence:

```
Candidate: "Narrator"  (count 12, in 4 sources; 5etools: no; near-miss: none)
Options:
  [ Not an entity ]  VTT/scene artifact — ignore, don't re-ask
  [ New entity ]     real entity the registry is missing (you'll pick a type)
  [ Defer ]          decide later
```
For a `generic?: yes` form, lead with **Not an entity**; for a fresh proper noun,
lead with **New entity**. Always include **Defer**. When the GM picks **New
entity**, ask its type in a follow-up (see Phase 3c).

### Phase 3b — Converse lane (near-miss / high-stakes)

One candidate at a time, like `ensemble-alias-review`:

1. **Gather context.** Look up both the candidate `S` and its `near_miss` name
   `N` in campaign docs (use the `mcp__campaign__*` tools if connected —
   `grounded_search`, `quick_search`, `search_document` — else read
   `docs/world_state.md`, `docs/planning.md`, dossiers). Note the 5etools verdict.
2. **Recommend**, with reasoning and a confidence level:
   ```
   ## "Ilvarra" vs registry "Ilvara Mizzrym"  (near-miss ratio 0.91)
   count 7 · sources: summaries/s03 · 5etools: no match

   Verdict: Alias of "Ilvara Mizzrym"  (high confidence — one-char VTT typo,
   same scenes ch. 3)
   ```
   Confidence bands: **high** (typo/VTT variant, same role/scenes) → recommend
   alias; **medium** (plausible variant, thin context) → recommend but flag;
   **low** (similar string, different role — retcon/namesake risk) → recommend
   distinct-but-similar, flag explicitly.
3. **Decide** via `AskUserQuestion` (≥2 options):
   - `Alias of N` → `registry.py alias <dir> --to "N" "S"`
   - `Distinct entity (looks like N, isn't)` → `add` as new **+**
     `mark-distinct <dir> "S" "N"`
   - `New unrelated entity` → `add` as new
   - `Not an entity` / `Defer`
   Offer "look up more context" as a natural-language path before deciding.

### Phase 3c — Executing a decision

Immediately run the matching CLI write (from the campaign workspace so config
auto-detects), then update the state file:

- **Alias of N:**
  ```bash
  python registry.py alias <dir> --to "Ilvara Mizzrym" "Ilvarra"
  ```
- **New entity** (ask type first — one of `npc location faction item deity event
  concept`; offer `--provenance module|supplement|on_the_fly` if known):
  ```bash
  python registry.py add <dir> --name "Sirac" --type npc --yes
  ```
- **Distinct-but-similar:** the `add` above, then:
  ```bash
  python registry.py mark-distinct <dir> "Sirac" "Sarith Kzekarit"
  ```
- **Not an entity:** append to state `ignored` (surface + norm + short reason).
  No registry write.
- **Defer:** append to state `deferred` (surface + norm + optional note). No
  registry write.

Each CLI verb validates before writing (they route through
`campaignlib.registry.validate`); if one errors (e.g. a collision the GM didn't
expect), surface the message and re-ask rather than forcing it. After each
decision (or each batch), **write the state file immediately** — the session is
resumable at any point. Confirm in one line, e.g. `✓ Ilvarra → alias of Ilvara
Mizzrym`.

### Phase 4 — Finish

When the queue is exhausted (or the GM says stop):

1. Report a tally: entities added, aliases attached, distinct pairs recorded,
   ignored, deferred.
2. Suggest re-running `registry.py check <dir>` — the two-pronged drift scan —
   to confirm the new writes didn't introduce grouping drift or a fuzzy
   near-dup, and `registry.py project <dir>` to regenerate the downstream
   projections (`aliases.json`, `entity_inventory.md`) if consumers need them.
3. Leftover `deferred` entries persist for the next run; `ignored` entries keep
   those surface forms out of future queues.

## Do not

- **Auto-decide a near-miss.** Alias-vs-distinct is a precision call — always
  present reasoning and let the GM rule. `near_miss` is a hint, not a verdict.
- **Write a non-entity into the registry.** Generic nouns / scene roles / VTT
  artifacts go to the state file's `ignored` list, never `add` or
  `rejected_aliases`.
- **Skip the generic-noun check for a plausibly-generic form** just because
  it's quick to guess — run `fivetools_catalog.py search`; but mark `unknown`
  and move on if no 5etools data resolves. Never block on tooling.
- **Reuse a stale queue.** Regenerate `triage-candidates` at the start of each
  run so it reflects the current registry.
- **Re-add a PC.** PCs come from `party.yaml` and are excluded upstream; if one
  appears in the queue, report it — don't register it.
- **Edit `entity_registry.yaml` by hand.** All writes go through the `registry.py`
  verbs so every change passes validation.
