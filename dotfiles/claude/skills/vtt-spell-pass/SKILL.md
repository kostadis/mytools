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
5. **Verified-noun dictionaries** — flat, one-name-per-line files of
   confirmed proper nouns (module NPCs, creatures, spells, locations,
   deities) that should be treated as known and therefore never surfaced
   as candidate misspellings. These are *not* the glossary — they are
   pre-verified vocabulary that suppresses false positives and improves
   clustering (dictionary entries also become canonical replacement
   targets). **Auto-detect the conventional flat path
   `<campaign>/notes/proper_nouns_adventure.txt`. Also check whether the
   campaign keeps a generated entity inventory: `docs/entity_inventory.md`
   (produced from `docs/entity_registry.yaml` by `registry.py project`) is
   the current OOTA source. Surface what you found and ask the user to
   confirm or add more before running Phase 1.** Pass every confirmed flat
   file to both scripts via `--extra-known` (the flag accepts multiple
   paths).

   Format matters: `--extra-known` treats every non-`#` line as a name, so
   only feed flat one-per-line dumps. Do **not** pass a markdown file raw
   (tables, `- **Name** — description` bullets, prose) — it injects markup
   and prose fragments into the known set and can silently suppress real
   unknowns.

   **Flatten generated markdown sources first.** `entity_inventory.md` and
   `notes/vtt_known_additions.md` are valuable name sources but are
   markdown, not flat. Extract each into a throwaway `.txt` in your
   scratchpad, then pass the `.txt`:
   - pull every `**bold**` span from each `- ` bullet line;
   - split each span on ` / ` (multi-alias entries like
     `**Whistlerites / Miloites / Protanthians**` become three names);
   - unescape `\'` → `'` (e.g. `Drow\'s`);
   - dedupe case-insensitively, one name per line.

   **`vtt_known_additions.md` can hold stale entries.** It records
   "real name, not a misspelling" rulings from prior passes, but some may
   since have been reclassified — a name the glossary now treats as a
   *wrong-form*. This run, `Callan Strongbench` was listed here as canonical
   but the glossary maps it → `Kalan Strongbranch`; a stale "known" entry
   silently suppresses a real unknown. When you flatten it, flag any entry
   that also appears as a glossary wrong-form to the user — the glossary wins.

   If no dictionary exists, proceed without one — it is an enhancement, not
   a hard dependency.

6. **Retranscription context (when available)** — if `<vtt>`'s filename
   contains `.retranscribed` or `.retranscribed.cleaned` (i.e. it's an
   `audio-to-vtt` output, not a plain Otter/Zoom export), two extra
   sources exist and should be used:
   - **Zoom's original transcript**, the sibling file with those suffixes
     stripped (`<x>.transcript.retranscribed.cleaned.vtt` →
     `<x>.transcript.vtt`). `zoom_context.py` (this skill's directory)
     looks up Zoom's original cue for any context excerpt — see "Cross-
     referencing Zoom's original" under Phase 3.
   - **`<vtt-stem>.proper_nouns.md`**, if `retranscribe.py` already
     produced it — a report (from the sibling `audio-to-vtt` project)
     flagging cue groups where the campaign vocabulary is confidently
     present in the retranscription but doesn't appear in Zoom's original
     for that span. Skim it before Phase 3; it's the same underlying
     technique as `zoom_context.py` run in bulk ahead of time, and gives
     useful priors on which names this session's ASR struggled with most.
   Both are enhancements, not hard dependencies — a plain Otter/Zoom VTT
   with no `.retranscribed` sibling has neither, and the skill runs
   exactly as it always has.

## Workflow

### Phase 1 — gather candidates (deterministic, no LLM)

Run `find_unknowns.py`, piping into `cluster_unknowns.py`:

```bash
python ~/.claude/skills/vtt-spell-pass/find_unknowns.py \
  --vtt <vtt> \
  --glossary <campaign>/notes/vtt_transcription_corrections.md \
  --npcs-dir <campaign>/docs/npcs \
  --extra-known <campaign>/notes/proper_nouns_adventure.txt \
  --min-count 1 \
| python ~/.claude/skills/vtt-spell-pass/cluster_unknowns.py \
  --glossary <campaign>/notes/vtt_transcription_corrections.md \
  --npcs-dir <campaign>/docs/npcs \
  --extra-known <campaign>/notes/proper_nouns_adventure.txt \
  > /tmp/spell_pass_clusters.json
```

`--extra-known` accepts multiple paths — pass every dictionary the user
confirmed in required-input #5 (omit the flag if none exist).

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
(`exact` / `substring` / `edit_distance` / `metaphone` / `phonetic` /
`cross-unknown` / `singleton`). `metaphone` = a vendored Double Metaphone
code match (models pronunciation, links variants that cross the first
letter like Elvara↔Ilvara); `phonetic` = the crude devowel fallback key,
used when Double Metaphone finds nothing or its module is unavailable.

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

**Collapse the set first: apply the current glossary, then re-scan.**
Before surfacing anything, run `apply_replacements.py` with the *existing*
glossary to a throwaway copy, then re-run `find_unknowns.py` +
`cluster_unknowns.py` on that cleaned copy. This removes every token the
glossary already knows how to fix (e.g. `Bookworm`, `Alcrist`, `Gergam`)
and leaves the **true residual** — the tokens that actually need a decision.

```bash
python ~/.claude/skills/vtt-spell-pass/apply_replacements.py \
  --vtt <vtt> --glossary <glossary> --output /tmp/preview_current.vtt
python ~/.claude/skills/vtt-spell-pass/find_unknowns.py \
  --vtt /tmp/preview_current.vtt --glossary <glossary> \
  --npcs-dir <npcs> --extra-known <dicts> --min-count 1 \
| python ~/.claude/skills/vtt-spell-pass/cluster_unknowns.py \
  --glossary <glossary> --npcs-dir <npcs> --extra-known <dicts>
```

Many survivors are **false residuals**: multi-word capitalised runs whose
embedded name is *already correct* — `And Kalan`, `The Helmed Horror`,
`But Alkrist`, `How's Grygum`. The scanner flags them only because it can't
split the run. Don't ask about these; the name is right. Only surface a
residual when the embedded proper noun is actually wrong.

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

**Cross-referencing Zoom's original (when a `.retranscribed` sibling
exists — see Required input #6).** Before asking about a cluster, look up
Zoom's original text for one representative context excerpt:

```bash
python ~/.claude/skills/vtt-spell-pass/zoom_context.py \
  --vtt <vtt> --context "<a ~40-80 char excerpt containing the candidate>"
```

Prints `null` if there's no `.retranscribed` sibling, the pair doesn't
align (different `--max-group-seconds` than the original retranscribe.py
run — pass `--max-group-seconds` to match if known), or the excerpt isn't
found verbatim (try a shorter/exact substring from the candidate's own
`contexts` field). When it returns a hit, include Zoom's original line in
the question — it's often decisive, not just supporting color:

- It can **confirm a proposed canonical is right** even for a large,
  unusual mangle a fuzzy-match cluster would otherwise flag as
  low-confidence (obelisk session 6: "Zerabira" looked like a new
  character on its own, but Zoom's original for that exact cue was
  "...sorry, Vera is a 19" — clearly the existing PC "Veyra", not new).
- It can **overturn a high-confidence bound-cluster match**. Run this
  check even for clusters `cluster_unknowns.py` already scored high-
  confidence — a strong edit-distance/phonetic match to a known canonical
  says nothing about whether the underlying cue was intelligible speech at
  all (obelisk session 6: "Redbrand Exo" edit-distance-matched "Redbrand"
  at high confidence, got confirmed, and was only caught as wrong after
  the fact — Zoom's original for that exact cue turned out to be
  "Welcome Maxwell Press PS6 Short Short Short", equally unintelligible
  gibberish on both sides, not a real Redbrand mention either system
  missed).
- It can **rule out a mangle as a real name entirely** when Zoom's
  original is a plausible, coherent ordinary phrase at that span
  (obelisk session 6: retranscription's "...in the back of and Povit"
  vs. Zoom's cleaner "...back and forward" — "Povit" was a Whisper
  hallucination of "forward", not a name to fix).

This is a deterministic lookup (no LLM judgment), so it's cheap enough to
run for every cluster and singleton when the sibling exists — do not
skip it just because a cluster already looks high-confidence.

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

When `zoom_context.py` returns a hit for either template, add it as a
line under the context/members before the options, e.g.:

```
Token: "Povit"  (1 occurrence)
Context: "...what could be useful to us in the back of and Povit."
Zoom's original for this cue: "...what could be useful to us back and forward."

A) Misspelling — I'll type the right form
B) New canon — add to known set
C) Not a name (ignore — saved to state)
```

Let it inform your own recommended default (if the question format
supports one) as well as the user's decision — Zoom's original is often
the tie-breaker between "real garbled name" and "ASR noise on both sides."

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

**Match `--section` to the canonical's *existing* row.** `add_to_glossary.py`
only looks for an existing row *inside the named section*. If the canonical
already has a row in a different section, a wrong `--section` silently
creates a **duplicate** row (this run: `Talon, Talen → Kalan` landed in
`## PCs` while the real `Kalan` row lives in `## NPCs and creatures`). Grep
the glossary for the canonical first (`grep -n '\*\*Kalan\*\*' <glossary>`)
and use whatever section its row is already in.

For "New canon" decisions: don't write to the glossary. Instead append a
line to a new file `<campaign>/notes/vtt_known_additions.md` listing
`<canonical>  — <context excerpt>  — <date>`. The user can promote that
into a real NPC dossier or world note later. This avoids polluting the
glossary with non-misspellings.

For "Ignore" decisions: take no action.

Mark the corresponding TaskUpdate as completed after each decision.

**Glossary entry vs. targeted edit — the case-insensitivity gate.**
`apply_replacements.py` matches `\bwrong\b` with `re.IGNORECASE`, so a
wrong-form that is also a common English word will over-replace anywhere it
appears lowercase. Before writing a *new* wrong-form to the glossary, grep
the VTT for lowercase occurrences of it. If any exist — or the wrong-form is
a common word (`Embrace`, `Close`, `Home`), a generic phrase (`Call and`),
or a non-name transcription fix (`Izzy` → `he's`) — **do not add it to the
glossary.** Apply that one correction as a targeted `Edit` on the *cleaned*
output in Phase 5, touching only the specific line(s). This keeps the
glossary safe to auto-apply to every future transcript. Examples this run:
`Embrace → Fembris` (a blanket rule would corrupt "corrosive embrace"),
`Call and → Kalan`, `Izzy → he's`.

The glossary keeps its own running landmine list (a "Notes for future passes"
section flagging risky case-insensitive rows like `Char→Shar`, `Cal→Kalan`).
Re-read it and grep the VTT for those lowercase forms before every apply.

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

Expect **false residuals** to remain (see Phase 1) — multi-word capitalised
runs like `And Kalan`, `The Helmed Horror`, `Helmed Horror No` whose embedded
name is already correct. These are *not* a reason for another pass; only a
residual whose embedded proper noun is actually *wrong* is. Also grep the
cleaned output for accidental doubling from full-name wrong-forms (e.g.
`Strongbranch Strongbranch`) and fix any with a targeted edit.

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
- **Never map a bare first name to a full "First Last" canonical.** If the
  surname is independently corrected by another row, the two fire together
  and *double* the surname (this run: `Kellen → Kalan Strongbranch` plus
  `Strongbench → Strongbranch` turned "Kellen Strongbench" into
  "Kalan Strongbranch **Strongbranch**"). Map a bare first name to the bare
  first-name canonical (`Kellen → Kalan`) and let the surname row fix the
  surname independently; reserve full-name wrong-forms for inputs that
  actually contain a surname token (`Callan Strongfeld → Kalan Strongbranch`).
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
