---
name: ensemble-alias-review
description: >
  Review undecided alias groups in docs/ensemble/ with campaign-context reasoning — one group at a time,
  conversationally. Claude looks up each candidate in campaign docs, gives a recommendation with reasoning,
  and the user confirms or overrides. Decisions persist to .alias_decisions.json after each group.
  Invoke as /ensemble-alias-review [campaign-dir].
tools: Read, Bash, Write, mcp__campaign__grounded_search, mcp__campaign__query_lore, mcp__campaign__search_document, mcp__campaign__quick_search, mcp__campaign__read_document
---

# Ensemble Alias Review

Walk through undecided entity-name alias groups in `docs/ensemble/state_dossiers/`, one at a time.
For each group, surface campaign lore and give a recommendation before the user decides.
Persist decisions to `.alias_decisions.json` after each group so the session is resumable.

## Why this exists

`review_aliases.py --review` finds near-duplicate entity names via string similarity and asks `[1/2/n/q]`.
It has no access to campaign lore, so it cannot tell "Sister Kaella" from "Sister Kayla" (VTT transcription
variants of the same NPC) vs "Lyra" from "Ilvara" (completely different characters sharing a phoneme).
This skill replaces that prompt loop with a conversational pass where Claude reasons from campaign context.

## Locating files

**Ensemble dir:** `docs/ensemble/` relative to the campaign root. If not in a Phandalin session, ask.

Key files:
- `docs/ensemble/.alias_decisions.json` — persisted decisions (read at start, write after each decision)
- `docs/ensemble/state_dossiers/*.md` — entity dossiers with frontmatter (`name`, `type`, `n_facts`, `chapters`)
- `docs/ensemble/aliases.json` — output (regenerated at the end via `python review_aliases.py --rebuild`)

## Opening move

Run: `python docs/ensemble/review_aliases.py --list`

Parse the output to identify undecided groups. Show the user a count:

> **X undecided groups** (Y already decided). Working through them one at a time.
> Say `skip` to defer a group, `stop` to save progress and quit, or `all done` when finished.

Then begin the first group immediately — do not present the full list upfront.

## Per-group workflow

### Step 1: Gather raw facts

Read both/all dossier files from `state_dossiers/`. Show the entity names, types, fact counts, and
chapter ranges in a compact table. Read the dossier body (not just frontmatter) to understand what each
entity actually does in the campaign.

### Step 2: Campaign context lookup

Search campaign docs to resolve the ambiguity. Use these tools as needed:

- `mcp__campaign__grounded_search` — "Who is [name]?" or "What is [name]?"  
- `mcp__campaign__query_lore` — deeper lore questions if quick_search is thin  
- `mcp__campaign__search_document` — look for mentions by chapter range  
- `mcp__campaign__quick_search` — fast name lookup  

Run as many queries as needed; don't present a recommendation based only on dossier content when
campaign docs can settle it.

### Step 3: Recommendation

Present a structured recommendation:

```
## [EntityA] vs [EntityB] (± others)

| Candidate | Type | Facts | Chapters |
|-----------|------|-------|----------|
| EntityA   | npc  | 930   | 2–45     |
| EntityB   | npc  | 38    | 1–2      |

**Verdict:** Same entity / Different entities / Uncertain

**Reasoning:** <one paragraph explaining why, citing chapter numbers or campaign facts>

**If same entity — canonical name:** <which one, and why>
```

Confidence levels to use:
- **High confidence** — chapter ranges overlap, facts describe same role, one is clearly a typo/VTT error
- **Medium confidence** — one is a possible transcription variant but context is thin
- **Low confidence / uncertain** — names are similar but facts point to different roles; flag explicitly

### Step 4: User decision

Ask: `Merge as [canonical]? (yes / no / pick different canonical / skip / more context)`

Accept natural-language answers — "yeah that's right", "no these are different", "use the long form".
`more context` → run additional campaign queries, then re-present the recommendation.
`skip` → defer this group (do not write a decision), move to the next.

### Step 5: Persist the decision

After the user confirms, **immediately** update `.alias_decisions.json`:

```python
# Decision format (matches review_aliases.py)
{
  "candidates": ["EntityA", "EntityB"],     # all names in the group, sorted by n_facts desc
  "canonical": "EntityA",                    # null if rejected
  "status": "approved"                       # or "rejected"
}
```

Read the file, append the new entry (do not clobber existing decisions), write it back.
Confirm in one line: `✓ Saved: EntityA (canonical) ← EntityB`

Then move to the next group.

## Special cases to watch for

**VTT transcription clusters** (high confidence to merge, canonical = most-facts):
- `Sister Kaella` / `Sister Kayla` / `Sister Kella` — almost certainly same NPC, pick the form with the
  most facts. Cross-check `notes/vtt_transcription_corrections.md` and `notes/vtt_known_additions.md`.
- `Valphine` / `Valphine Sortorra` — player character; canonical is the party doc spelling.
- Party PCs always win on canonical name: check `docs/party.md` for the authoritative spelling.

**Generic labels that cluster with real entities** (almost always reject):
- `Narrator` / `The narrator` — these are VTT artifacts; reject (not a real entity to alias).
- `woman` / `woman in windmill` / `the woman in green` — describe scene roles, not a named character.
  Check whether they're actually the same unnamed NPC before rejecting.
- `Bard` / `staff` / `orcs` — generic labels; reject unless the dossier body makes a clear referent.

**Cluster decomposition** (some groups need splitting):
- A group may contain 3+ names where some merge but others don't. For example, if `Harbin`,
  `Harbin Wester`, and `Townmaster` are all the same NPC, but `Corbin` and `Corrin` are a different
  character, say so and offer two decisions: one approve (Harbin cluster), one reject (Corbin ≠ Harbin).
  Write both decisions to the file.

**High-stakes entities** (flag explicitly, don't rush):
- Any entity where the facts span widely separated chapters (ch 2 vs ch 44) may reflect a retcon or
  a genuinely different person who shares a name. Call this out before recommending merge.
- Party PCs: `Vukradin`, `Soma`, `Valphine`, `Brewbarry`. Near-duplicates are almost always VTT typos.

## Finishing up

When all groups are processed (or user says `stop`), run:

```bash
python docs/ensemble/review_aliases.py --rebuild
```

This regenerates `aliases.json` from the full decisions file. Report the count of canonical entries and
total variants written.

## Do not

- Auto-approve any group without presenting reasoning first.
- Present the full 49-group list upfront — work one at a time.
- Write to `aliases.json` directly — always go through `--rebuild` so the Python script controls the format.
- Forget to read the dossier body, not just frontmatter — the body often has the deciding fact.
- Skip the campaign context lookup just because the string similarity is strong. "Ilvara" and "Lyra" have
  edit distance 3 and are completely different characters.
