---
name: vtt-spell-pass
description: Clean up Otter/Zoom VTT transcripts for a D&D campaign — applies the known-misspellings glossary and prompts the user about unrecognised proper nouns. Invoke as /vtt-spell-pass [vtt-path].
tools: Read, Glob, Grep, Bash, Edit, Write, AskUserQuestion, TaskCreate, TaskUpdate, ToolSearch, Artifact, WebFetch
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

7. **A second, independent transcription (when one exists)** — the same
   session transcribed by a *different* tool, with no shared timestamps and
   different segmentation (e.g. a voice-detection markdown export alongside a
   D&D-tuned WebVTT). This is NOT the `.retranscribed` pairing in #6, which is
   filename- and cue-aligned; here nothing lines up, so matching is by text.
   Use `sibling_context.py` (Phase 3). Check the session directory for one
   before starting — if two transcripts of the same date exist, you have this.

## Workflow

### Phase -1 — choose the review mode

Before anything else, one `AskUserQuestion`:

> **Review the candidates in an artifact, or here in the shell?**
> - **Artifact** — one page, every pair that needs a ruling, mark them at your own pace, save once.
> - **Shell** — one cluster at a time, the way this skill has always worked.

Ask this every run; do not remember a default. If they choose the artifact,
Phases 0–2.5 run exactly as written and **Artifact mode** below replaces
Phase 3. Phases 4–6 are shared.

### Scratch files — one namespace per run, never a fixed path

Every intermediate below goes in a per-run scratch directory. Set it once and
use `$SCRATCH` everywhere:

```bash
SCRATCH="${CLAUDE_SCRATCH:-/tmp}/spell_pass_$(basename <session_dir>)_$$"
mkdir -p "$SCRATCH"
```

This matters because the intermediates are **read back**, not just written.
Phase 1's collapse step writes a preview, then re-scans that preview to compute
the true residual. With a fixed `/tmp/preview_current.vtt`, two runs in flight at
once — two chapters, two terminals, two agents — silently interleave: run A
writes its preview, run B overwrites it, run A scans B's chapter. Nothing
crashes and no output looks wrong; run A just reports a residual for a transcript
it never read. Same hazard for `/tmp/scan_src.txt` and the cluster JSON.

If you are processing more than one transcript, **assert before every re-scan**
that the file you are about to read is the one you just wrote — compare line
count or sha256 against your own input. A cheap check here is the difference
between a wrong answer and a caught mistake.

### Phase 0 — normalise the input (deterministic, no LLM)

Do not assume the input is a plain Otter/Zoom WebVTT. Run:

```bash
python ~/.claude/skills/vtt-spell-pass/prepare_input.py \
  --input <transcript> --scan-copy "$SCRATCH/scan_src.txt"
```

It reports three things that change the rest of the run:

- **`format`** — `webvtt`, `labelled_markdown`, `labelled_text` or `plain`.
  `find_unknowns.py` strips `Name:` / `Name (Player):` labels but NOT
  markdown-bold ones (`**dave:**`), so for `labelled_markdown` you MUST scan
  the `--scan-copy`, not the original. Apply replacements to the ORIGINAL in
  Phase 5 — the scan copy is only for candidate gathering.
- **`speakers`** — who is attributed and how often. A file reporting *no*
  speakers cannot support quote attribution at all; if the GM needs speakers
  (they usually do), that file cannot be the deliverable no matter how clean
  its text is. Say so before doing the work, not after.
- **people in the room who are not at the table.** A partner, a child, or a
  housemate wandering through gets transcribed like anyone else, and every
  proper noun in their speech becomes a candidate the GM must dismiss by hand
  (`Ben didn't find this funny` → `Ben`). If the speaker list contains a label
  you don't recognise as a player or the GM, **ask** who it is before Phase 1
  rather than scanning their lines. Then:

  ```bash
  # keep their lines in the file, just don't mine them for names
  prepare_input.py --input <t> --exclude-speaker natasha --scan-copy "$SCRATCH/scan.txt"
  # only if the GM says the lines should not ship at all
  prepare_input.py --input <t> --exclude-speaker natasha --filtered-output <t>.filtered.md
  ```

  `--scan-copy` filtering is always safe. `--filtered-output` deletes content
  from the deliverable, so it needs the GM to have said so explicitly — feed
  its output to `apply_replacements.py` in Phase 5 in place of the original.
- **`duplication`** — whether the body is recorded twice. This does not break
  replacement, but it **doubles every occurrence count**, so every "26x" you
  put in front of the GM is really 13. Detect it here, and pass
  `--dedup-output` to write a single-copy file. Do not eyeball this with a
  midpoint split: one split or merged utterance shifts everything after it and
  makes a 99.8%-identical duplicate look ~60% similar. The script anchors on
  the repeated first line and aligns with difflib.

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
  > "$SCRATCH/clusters.json"
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
  --vtt <vtt> --glossary <glossary> --output "$SCRATCH/preview_current.vtt"
python ~/.claude/skills/vtt-spell-pass/find_unknowns.py \
  --vtt "$SCRATCH/preview_current.vtt" --glossary <glossary> \
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

### Phase 2.5 — adjudicate against the second transcription (MANDATORY when one exists)

If Phase 0 / required-input #7 found a second transcription, check **every**
candidate against it BEFORE putting any of them to the GM:

```bash
python ~/.claude/skills/vtt-spell-pass/sibling_context.py \
  --sibling <other-transcript> --context "<excerpt from the candidate's contexts>"
```

This is not a spot-check and not an optional enrichment. It is the only
evidence available that distinguishes *a real name transcribed badly* from
*a word the ASR invented*, and fuzzy-match confidence cannot tell them apart —
a garbled token scores just as well against a known name whether or not the
underlying audio contained a name at all.

Read the result four ways:

- **Sibling spells the name correctly** → confirms the proposed canonical.
- **Sibling has ordinary words at that span** → there is no name here; the
  token is an ASR hallucination. Ignore it, do not "correct" it. Real examples:
  `You can just barely see the Grygum` vs `…see the game`; `Oh yeah, it's me.
  Summer, all right` vs `Oh, yeah, it's me. All right.`; `Orsick … he's not
  Orsick` vs `He's not late stage or sick.` — none of those names were spoken.
- **Both transcriptions produce the same odd string** → usually genuine audio.
  Route it to "new canon", not to a correction — but see the contamination
  warning below before trusting agreement on a *name*.
- **Sibling shows a DIFFERENT plausible name** → do not rule. See below.

A low score (<0.55) is inconclusive, not negative — the sibling may not cover
that span. Say so rather than ruling.

**Establish what kind of transcriber the sibling is before weighing it.**
An acoustic ASR fails phonetically: it turns a name into a similar-sounding
non-word. An LLM-based, domain-tuned transcriber fails *semantically*: it
substitutes a plausible name it already knows — including one from a
**different campaign** — for the name actually spoken. The second failure mode
produces confident, well-formed, entirely fictitious output that looks like
strong evidence.

Confirmed instance (Phandalin chapter 04): the D&D-tuned VTT rendered
**Valphine** as **"Bramgrim"** five times. Bramgrim is a cleric in another of
the GM's campaigns; Valphine is a cleric in this one. Nothing phonetic connects
them. Reasoning from the sibling's spelling produced a proposal to rewrite a PC
name to another campaign's NPC — caught only because the GM recognised the
name. Note this also poisons the "both agree" rule: agreement with an LLM
transcriber is not independent corroboration.

So weight the sibling's evidence **by kind, not by score**:

| Sibling shows | Trust | Why |
|---|---|---|
| ordinary words / plain prose | high | contamination swaps names for names; it does not invent coherent filler |
| a campaign-correct name | high | it is recovering real vocabulary |
| a *different* plausible name | **none** | possible cross-campaign substitution — GM rules, you do not |

When the two transcriptions disagree on *which character* was named, that is a
question for the GM with both readings shown, never a proposal.

**Why this is mandatory.** In the session this phase was written from, five
candidates (`Grygum`, `Grym`, `Gryumary`, `Gilly`, `Summer`) were proposed
from fuzzy matching, approved by the GM on that framing, applied, and only
then caught by the sibling check — every one was a hallucinated word, and one
more (`Thalne`) pointed at the wrong character. Confirmation by the GM does
not validate the evidence you gave them; it only validates their reading of
it. Get the evidence right first.

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

### Phase 5 — lint the glossary, then apply replacements

**Lint first.** The glossary is a standing rewrite rule applied to every
future transcript, so a bad row is not a one-off. Run:

```bash
python ~/.claude/skills/vtt-spell-pass/lint_glossary.py \
  --glossary <campaign>/notes/vtt_transcription_corrections.md \
  --corpus <vtt>
```

Exit 1 means ERRORs. Show them to the user before applying; each names the
offending row with a `<file>:<line>` location.

- `doubling` — the canonical contains the wrong-form as a word, so the rule
  fires on *already-correct* text (`Brin Bundlewine` →
  `Brin Bundlewine Bundlewine`). Note the trigger is a **correct** transcript,
  not a mangled one — the better the ASR, the more damage. `apply_replacements.py`
  now refuses these rules and prints what it skipped, so the row is inert until
  rewritten. Fix by dropping the row (a bare short name standing alone is fine)
  rather than by editing the canonical.
- `conflict` / `noop` — one wrong-form with two canonicals; or a row mapping
  a form to itself.
- `chained` (warn) — a canonical is also someone else's wrong-form, so output
  depends on rule order.
- `split_section` (warn) — same canonical with rows in two sections; the next
  `add_to_glossary.py --section` append will silently create a third.
- `common_word` / `corpus_lower` (warn) — the automated form of the
  case-insensitivity gate described in Phase 4. `common_word` consults a small
  built-in list; `--corpus` is the reliable one, flagging wrong-forms that
  genuinely occur lowercase in a real transcript. Warnings are for review, not
  automatic rejection: `Brewberry` and `Thunder Wave` both trip `corpus_lower`
  and both are correct rules.

Replacement is expected to be **idempotent** — running the pass twice must
equal running it once. After Phase 6, re-applying the glossary to the cleaned
file should produce a byte-identical result; if it doesn't, a row is corrupting
correct text and the lint will say which.

Then apply the now-updated glossary to the transcript:

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

## Artifact mode (batch review)

Replaces Phase 3 only. Phases 0–2.5 and 4–6 are unchanged, and the shell path
stays exactly as documented. Full contract:
`~/.claude/skills/_shared/review-artifact/CONTRACT.md`.

### The consent unit is the PAIR, never the cluster

**This is not negotiable and it is why this skill produces more cards than the
others.** `merge_proposals.py` states it directly:

> *"Consent granularity: the unit is the (wrong_form → canonical) PAIR.
> Questions are grouped by canonical for batching, but every member carries
> its own count and sibling verdict so the GM can accept some and reject
> others. **Collapsing a group into one yes/no would approve hallucinated
> members invisibly.**"*

So one card per `(token → canonical)` pair. Group them by canonical in card
order so the GM reads a canonical's members together, but never merge them
into a single card, and never let approving one member imply another.

### What is auto-applied, footer only

- `action ∈ {leave_alone, add_to_known_set}` — no ruling needed.
- `auto_dismissed[]` under the `AGENT_BRIEF.md` gate: **`count == 1` AND
  `kind == ordinary_words`**. Never on `inconclusive`, never on `count ≥ 2`.
- Glossary rows that already exist — Phase 0's known-misspellings pass.

Name the counts in the `footer` so the GM can see what ran without them.

### What becomes a card

`action ∈ {propose, propose_low_confidence, escalate, escalate_blocking}`.

```json
{ "id":  "vucherton__vukradin",
  "t":   "<code>Vucherton</code> → <b>Vukradin</b> · 3 occurrences, 2 chapters",
  "y":   "Add the row to <code>vtt_transcription_corrections.md</code>, lint, and rewrite 3 occurrences to <b>Vukradin</b>.",
  "n":   "Not a garbling of Vukradin. Saved to <code>.vtt_spell_pass_state.json</code> as ignored, and never asked again.",
  "ev":  "Verbatim: <em>…a no-skimming clause that Mr. Vucherton insisted…</em> · rule <code>edit_distance,metaphone</code> · confidence <code>medium</code> · sibling: <code>agent_corrected</code>" }
```

Card ids must round-trip to the pair. Use `<token>__<canonical>`, lowercased
and non-alphanumerics collapsed to `_`, and keep a sidecar map in `$SCRATCH`
from id → `{token, canonical, section, count}` — the page returns ids only.

**Always put the verbatim excerpt in `ev`.** A pair judged without its context
is the exact failure the pair-consent rule exists to prevent.

### Publish, then stop

Hand over the link and **do not poll**. When the GM says they are done,
`WebFetch` the URL and run `read_decisions.py`.

### Verdict mapping — feeds Phase 4 unchanged

| verdict | action |
|---|---|
| **approve** | `add_to_glossary.py --wrong <token> --right <canonical> --section <matching the canonical's EXISTING row>` |
| **reject** | `state.py ignore "<token>"`, unless the card's `n` says "real name" — then append to `notes/vtt_known_additions.md` instead |
| **discuss** + note naming a canonical | treat as approve with the GM's canonical, not the proposed one |
| **discuss**, no note | back to the shell, grouped with the other discussed pairs |
| **unmarked** | undecided — leave the pair for the next run and say so |

Then Phase 5 as written: **lint before applying.** `lint_glossary.py` exit 1
blocks the run — a batch of approvals is exactly when a `doubling` or
`conflict` row does the most damage.

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
  **`lint_glossary.py` does not catch this** — the row is fine in isolation and
  only doubles when the transcript already supplies the surname, so grep the
  *cleaned output* for repeated surnames every run. It recurs: this pass found
  `Toblin → Toblen Stonehill` turning "Toblin Stonehill" into
  "Toblen Stonehill **Stonehill**"; fixed by demoting it to `Toblin → Toblen`.
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
