---
name: vtt-spell-pass
description: Clean up Otter/Zoom VTT transcripts for a D&D campaign — applies the known-misspellings glossary and prompts the user about unrecognised proper nouns. Invoke as /vtt-spell-pass [vtt-path].
tools: Read, Glob, Grep, Bash, Edit, Write, AskUserQuestion, TaskCreate, TaskUpdate, ToolSearch
---

# VTT Spell Pass

Clean up a campaign session's VTT transcript with two complementary passes:

1. **Known-misspellings pass** — apply every wrong→right replacement already
   recorded in the campaign's corrections glossary.
2. **Unknown-proper-noun pass** — flag every Capitalised token (or run) in
   the transcript that is **not** in the campaign's known-names set
   (glossary canonicals + NPC dossiers + extras). Treat each unknown as a
   suspect new misspelling. Ask the user, one at a time, what each one
   should map to (or whether it's a real new name to add to the known set,
   or table-chatter to ignore).

The user's stated invariant: *"I know all the NPCs. If a proper name appears
in a transcript that isn't in our notes, it's a misspelling."* The skill
operationalises that: the unknown set IS the candidate-misspelling set.

## Required inputs

Detect or ask:

1. **VTT path** — from args, or default to the most recent
   `summaries/*/[Gg][Mm][Tt]*.vtt`. List candidates if ambiguous.
2. **Campaign root** — CWD if it contains `notes/vtt_transcription_corrections.md`,
   otherwise walk up.
3. **Glossary path** — `<campaign>/notes/vtt_transcription_corrections.md`.
   If missing, abort and tell the user to seed it (this skill assumes a
   glossary already exists in the documented format — see Out of the Abyss
   for the canonical example).
4. **NPC dossier dir** — `<campaign>/docs/npcs/` if present.

## Workflow

### Phase 1 — gather candidates (deterministic, no LLM)

Run `find_unknowns.py`, piping into `cluster_unknowns.py`:

```bash
python ~/.claude/skills/vtt-spell-pass/find_unknowns.py \
  --vtt <vtt> \
  --glossary <campaign>/notes/vtt_transcription_corrections.md \
  --npcs-dir <campaign>/docs/npcs \
  --min-count 1 \
| python ~/.claude/skills/vtt-spell-pass/cluster_unknowns.py \
  --glossary <campaign>/notes/vtt_transcription_corrections.md \
  --npcs-dir <campaign>/docs/npcs \
  > /tmp/spell_pass_clusters.json
```

`find_unknowns.py` emits the raw unknown-token list with counts and
contexts. `cluster_unknowns.py` then:

- **Bound clusters** — every token within edit distance ≤ 1/2/3 (length-
  scaled) OR matching phonetic key of a known canonical or wrong-form
  is grouped under that canonical. *One question per canonical replaces
  N questions per variant.*
- **Cross-unknown clusters** — remaining tokens that look like each
  other (ed ≤ 2 with first-letter match, or matching phonetic key) get
  grouped together. The user names the canonical once and all members
  get glossed.
- **Singletons** — leftovers each get a one-member cluster.

Each cluster carries a confidence (high/medium/low) and a reason
(`exact` / `substring` / `edit_distance` / `phonetic` / `cross-unknown`
/ `singleton`).

Also run the state filter:

```bash
python ~/.claude/skills/vtt-spell-pass/state.py \
  --state <campaign>/notes/.vtt_spell_pass_state.json show
```

Drop any cluster whose only member is in `ignored_tokens` — the user
already said "not a name, ignore" in a prior run.

**Sanity check before continuing:** `find_unknowns.py`'s
`known_names_count` should be in the hundreds for a mature campaign. If
it's <50 the glossary or `docs/npcs/` isn't being read correctly —
investigate before bothering the user with hundreds of false positives.

### Phase 2 — pre-classify candidates (LLM judgment, MINIMAL filtering)

Read the unknown list. Before asking the user, **only filter what is
unambiguously not a campaign name**. When in doubt, surface — the user
explicitly prefers being asked over silent dismissal.

Drop ONLY:

- **Confirmed real-world places** the user has previously talked about
  (e.g. "Greece", "Europe" in conversational context — but if a token
  doubles as a campaign location, surface it).
- **Pure stopwords** that snuck past the helper's list ("Sounds",
  "Mr" — pronouns and articles).
- **Capitalised mechanics** that are clearly D&D rules text ("Wisdom"
  in "Wisdom save", spell names like "Misty Step", "Tremor Sense").
- **Obvious garbage** — single letters, all-caps acronyms with no context.

DO NOT drop:

- **Anything that looks like a personal name**, even if you suspect it's
  a player name. (User invariant: there are very few players, the user
  knows them all by name, and if you guess wrong about whether something
  is a player vs an NPC misspelling, you will silently lose a real
  correction. Always ask.)
- **Anything that could be a place, faction, item, or deity** the user
  hasn't dossiered yet.
- **Multi-word capitalised phrases** — these are almost always real.

For everything that survives, you have your **candidate list**.

### Phase 3 — ask the user, one CLUSTER at a time, ALWAYS

Per the user's stated preferences (memories: `feedback_question_style`,
`feedback_scope_discipline`, `feedback_vtt_spell_pass_confirm`), use
TaskCreate to enumerate clusters and AskUserQuestion to walk them one at
a time as multiple choice.

**Hard rule: every new wrong→right mapping requires explicit user
confirmation before being written to the glossary.** The cluster
proposal is exactly that — a *proposal*. The user always picks.

**Cluster ordering:** present in this order so the user makes the
highest-yield decisions first:

1. High-confidence bound clusters (proposed canonical, ≥2 members)
2. Medium-confidence bound clusters
3. Cross-unknown clusters (≥2 members, no canonical)
4. High-count singletons (count ≥ 3)
5. Low-count singletons (final bulk dismissal batch — acceptable to
   ask "any of these N tokens look like real names you want to address?"
   with a multi-select)

For each multi-member cluster, your AskUserQuestion shows the proposal:

```
Cluster #2  (3 members, 5 occurrences total)
Proposed canonical: "Glabbagool"
Members:
  - "And Glabbagool"   1x   "And Glabbagool, of course, is really happy to..."
  - "Does Glabbagool"  1x   "Does Glabbagool have anything that he wants to..."
  - "Globagool"        1x   "How many eyes you can have, Globagool?"

A) Confirm — all members → Glabbagool
B) Different canonical — I'll type it
C) Split — not all the same; ask me one at a time
D) All ignore (table chatter)
```

For singleton clusters (one member), use the per-token form:

```
Token: "Vulking Valve"  (3 occurrences)
Context: "...we returned to Vulking Valve and..."

A) Misspelling of <closest known suggestion>      ← if cluster has a proposed canonical
B) Misspelling — I'll type the right form
C) New canon — add to known set
D) Not a name (ignore — saved to state)
```

**(D) "Ignore" decisions** must be persisted via `state.py` so the same
token doesn't resurface next session:

```bash
python ~/.claude/skills/vtt-spell-pass/state.py \
  --state <campaign>/notes/.vtt_spell_pass_state.json \
  ignore "Joe" "Gabe" "Christmas" ...
```

**No assumed table chatter.** If a token looks like a personal name and
you don't know whether it's a player or an NPC, ask. Mistakes here cost
real corrections. Clustering already cuts the question count — don't
compound that with silent dismissals.

### Phase 4 — record decisions

For each "misspelling" decision (A or B), call:

```bash
python ~/.claude/skills/vtt-spell-pass/add_to_glossary.py \
  --glossary <campaign>/notes/vtt_transcription_corrections.md \
  --section <pcs|npcs|items|factions|locations|table> \
  --wrong "<wrong-form>" \
  --right "<canonical>"
```

The script appends to the existing canonical's row if one exists, or
creates a new row, or creates a new section. You decide which section
based on what the canonical refers to (ask the user if unclear).

For "New canon" decisions: don't write to the glossary. Instead append a
line to a new file `<campaign>/notes/vtt_known_additions.md` listing
`<canonical>  — <context excerpt>  — <date>`. The user can promote that
into a real NPC dossier or world note later. This avoids polluting the
glossary with non-misspellings.

For "Ignore" decisions: take no action.

Mark the corresponding TaskUpdate as completed after each decision.

### Phase 5 — apply replacements

Once all candidates have been classified, apply the now-updated glossary
to the transcript:

```bash
python ~/.claude/skills/vtt-spell-pass/apply_replacements.py \
  --vtt <vtt> \
  --glossary <campaign>/notes/vtt_transcription_corrections.md \
  --output <vtt-stem>.cleaned.vtt
```

(Default output: `<vtt-stem>.cleaned.vtt` next to the original. Pass
`--in-place` only if the user explicitly asks to overwrite.)

Report the per-pair replacement count back to the user.

### Phase 6 — re-scan to confirm + record processed VTT

Re-run `find_unknowns.py` against the cleaned VTT. Any remaining
unknowns mean either (a) a candidate slipped through pre-classification
or (b) a new word the user didn't get to. Show the user the diff and ask
whether to do another pass.

After confirming, record the VTT as processed so future runs against the
same path are no-ops:

```bash
python ~/.claude/skills/vtt-spell-pass/state.py \
  --state <campaign>/notes/.vtt_spell_pass_state.json \
  processed <vtt-path>
```

## Important conventions

- **Speaker labels are stable.** `Thorin (Joe):` does not contain
  misspellings of "Thorin" worth catching — the helper strips speaker
  labels before scanning. If you suspect a label is wrong, that's a
  separate manual fix.
- **Possessive `'s` is auto-handled.** The applier extends each wrong-form
  to also catch its possessive (`Lavagul'` → `Lavagul's` → `Glabbagool's`).
- **Don't silently expand the user's variant lists.** If the user says
  "add X as a misspelling of Y", add exactly X — not your guesses about
  related forms. (See memory: `feedback_scope_discipline`.)
- **Don't replace inside speaker labels or VTT cue metadata.** The
  applier uses word-boundary regex on the full text — generally safe, but
  if a wrong-form is also a real word ("May" the month vs "May" the
  surname), prefer skipping rather than replacing. Flag to the user.
- **The glossary lives in `notes/`, which is excluded from the mempalace.**
  This is intentional — the glossary is a cleanup-pass reference, not
  campaign canon. Don't try to mine it.

## Why this design

The glossary is a hand-curated **boundary** between sloppy transcription
and canon. The user reviews every addition. The skill never invents
canonical forms — it only:

- applies what the user has already approved (Phase 1, Phase 5), and
- surfaces unknowns and asks (Phase 3).

This matches the global rule: *LLMs are renderers, not architects. Good
pattern: LLM extracts → human reviews and imposes structure → LLM renders
inside that structure.* Phase 1 is deterministic extraction; Phase 3 is
the human checkpoint; Phase 5 is deterministic rendering.
