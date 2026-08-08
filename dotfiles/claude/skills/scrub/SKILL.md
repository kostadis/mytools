---
name: scrub
description: >
  Propose→review→apply mechanical-residue scrub for session_doc narration
  prose. A deterministic regex pass surfaces candidate residue (raw numbers
  on DC/AC/HP/damage/healing/feet/rounds/initiative, out-of-fiction
  table-speak, real player names as speakers) — never spell names or magic
  vocabulary, which are not a candidate category at all. The GM confirms
  every candidate one at a time before anything is rewritten; a deterministic
  apply step then writes `.scrubbed.md`. Replaces the autonomous
  `scrub_mechanics.py` LLM pass per CampaignGenerator issue #151 (the
  spell-stripping incident). Invoke as /scrub [narration-dir-or-file].
tools: Read, Glob, Bash, Write, Edit, AskUserQuestion, TaskCreate, TaskUpdate, ToolSearch
---

# Scrub

Clean game-mechanical residue out of finished `session_doc` narration prose —
without ever letting an LLM decide, unsupervised, what counts as "mechanical"
and what counts as "the campaign's magic system."

## Why this exists

`scrub_mechanics.py` (the CampaignGenerator CLI wired to the **Scrub** button
in the Session Doc Editor) reads a finished narration scene, runs it through
one LLM call with a strict-sounding filter prompt, and writes
`<scene>.scrubbed.md` — no review step. That is the bad pattern from the
global LLM Pipeline Design Rule: **LLM extracts → LLM decides scope → LLM
renders**, all in one autonomous pass with no human checkpoint before the
output becomes the working narration.

**It already went wrong once.** The bundled default prompt treated in-world
magic as mechanical residue and silently rewrote spell names into vague
euphemisms: *Speak with Dead* → "question the dead", *Locate Object* → "a
working to find the chip", *Identify* → "the least of the seeing-arts",
*Drawmij's Instant Summons* → "an old summoning working", *Lesser
Restoration* → "the healing that draws a poison clean out of the blood",
*Magic Missile* → "a lance of unerring force light" in one scene and "darts
of pure force" in another. Diffing real `.scrubbed.md` output against its
source narration (Out of the Abyss, sessions 20260601–20260618) also shows
the pass rewriting dialogue, idiom, and voice well past "strip a number" —
scope creep with nobody reviewing the boundary before it shipped as canon
narration. See CampaignGenerator issue #151.

The stopgap fix (a per-campaign override prompt that hand-encodes "magic is
in-world, keep it") just moves the same precision decision into a differently
worded prompt an LLM still applies autonomously every run. A new spell name,
a new phrasing, a new campaign — the hole reopens. **Only a human checkpoint
closes it**, which is what this skill is.

This is modeled directly on `~/.claude/skills/vtt-spell-pass/` — same three
honest phases: deterministic extraction, human checkpoint, deterministic
apply.

## The hard invariant

**Spell names and magic vocabulary are never a candidate category.** Every
regex in `find_residue.py` matches a *number* (DC/AC/HP/damage/healing/feet/
rounds/initiative) or a *fixed out-of-fiction phrase* ("the DM", "we
rolled", …) or a *real player name*. None of them match on spell-name
vocabulary, so the scanner is structurally incapable of flagging "Fireball"
or "Speak with Dead" — this isn't a prompt instruction an LLM could
misjudge, it's a category of pattern that doesn't exist in the tool. If a
future edit to `find_residue.py` ever adds a vocabulary-based category,
that edit needs the same scrutiny as any other scope decision — flag it to
the GM rather than shipping it silently.

## Required inputs

Detect or ask:

1. **Campaign dir** — CWD if it contains `docs/party.md`, else walk up, else
   ask. All state lives under `<campaign>/notes/`.
2. **Narration target** — from the invocation arg, else default to
   `summaries/<most-recent-date>/narration/` in the campaign. Accepts a
   single `session_doc_scene_*.md` file or a directory (every
   `session_doc_scene_*.md` in it, excluding `.scrubbed.md` and
   `.knobs.json`). List candidates if ambiguous.
3. **`docs/party.md`** — sourced for real player names (the "Player: X"
   line per character). Pass as `--party-md` to `find_residue.py`. If
   missing, proceed without player-name detection and say so.
4. **State file** — `<campaign>/notes/.scrub_state.json`. Created on first
   run via `state.py`.
5. **Protect files (optional)** — flat one-per-line files of terms that
   should never be flagged even if a pattern would otherwise match (e.g. a
   mundane phrase that happens to contain a number-and-feet pattern, like "a
   two-foot box"). Pass every confirmed path via `--protect` (repeatable).
   Not required to start — the hard invariant above already protects magic
   vocabulary structurally; this is for campaign-specific false positives
   the GM wants suppressed permanently.

If `AskUserQuestion` is not loaded, run `ToolSearch` with
`query: "select:AskUserQuestion"` first.

## Workflow

### Phase 0 — pre-flight

Use `TaskCreate` to enumerate the target files. For each, run Phase 1–4
below. Process one file at a time so the GM isn't asked about 8 scenes'
worth of candidates in one breath.

Check `state.py show` first — skip any file already listed under
`processed` unless the GM explicitly asks to redo it.

**`processed` does not track content.** It records a path, not a hash or
mtime, so a scene that has been re-rendered since its last scrub still looks
done. Before skipping a `processed` file, compare it against its
`.scrubbed.md`: if the raw `.md` is newer, or the `.scrubbed.md` is missing
entirely, the recorded state is stale and the scene needs a fresh pass. Say
so rather than silently skipping.

### Phase 1 — collapse known rules, then scan (deterministic, no LLM)

Apply any durable rules the GM has already approved in a prior run, so the
same recurring call isn't re-asked:

```bash
python ~/.claude/skills/scrub/apply_known_rules.py \
  --file <scene.md> --state <campaign>/notes/.scrub_state.json \
  --output /tmp/scrub_preview.md
```

Then scan the *preview* (not the original) for the true residual:

```bash
python ~/.claude/skills/scrub/find_residue.py \
  --file /tmp/scrub_preview.md \
  --party-md <campaign>/docs/party.md \
  --state <campaign>/notes/.scrub_state.json \
  [--protect <campaign>/notes/scrub_protect.txt] \
  > /tmp/scrub_candidates.json
```

`find_residue.py` emits categorized candidates: `dc_number`, `ac_number`,
`hp_number`, `damage_number`, `heal_number`, `foot_count`, `round_count`,
`initiative`, `roll_callout`, `roll_result_dialogue`, `dice_verb`,
`advantage_with_number`, `table_speak`, `player_name`. Numeric categories
with a matched value carry a `hint` — a difficulty/impact tier straight from
the existing translation-scale tables (ported verbatim from
`scrub_mechanics_prompt.md`), not an invented rewrite.

**Expect false positives, especially on `foot_count`.** A pattern like
`\d+ feet` matches both genuine movement-mechanic residue ("moved forty feet")
and ordinary physical description ("a two-foot box of metal"). The regex
can't tell those apart and isn't trying to — that's Phase 2's job. Don't
pre-filter these out of the candidate list; surface them and let the GM
reject the non-residue ones (and optionally `state.py ignore` the exact
phrase so it never resurfaces).

### Phase 1b — supplementary read pass (REQUIRED)

**The scanner reliably misses about half the real residue.** Measured over
several sessions on the Phandalin ch46 narration: of 11 items in one pass, 6
came from reading rather than scanning; of 4 in another, 1; of 3 in another,
1. The misses are systematic, not random, and they fall into known shapes:

| What was missed | Why the pattern can't fire |
|---|---|
| `I **only** got a ten` | an adverb between `I` and `got` breaks `roll_result_dialogue` |
| `**The roll** came up short` / `The roll — I felt it go` | no pronoun, so `dice_verb` can't fire |
| `those are some amazing **rolls**` | noun, not pronoun-plus-verb |
| `Insight. **Natural One** Insight.` | bare skill name + spelled die result; no number token |
| `A **17** where a flat roll would have been a **1**` | bare numerals, no result construction |
| `"17. 17."` | bare numerals in dialogue |
| `quest tracker` | table vocabulary, matches nothing |
| `*Inaudible.*` promoted out of a quote into prose | transcription marker, not a residue category |

So after Phase 1, **read the file** and grep for the shapes the categories
cannot express. A serviceable starting sweep:

```bash
grep -nEi "\bthe roll\b|\brolls?\b|\bDM\b|\bGM\b|natural (one|1|20)|\bnat [0-9]\b|\badvantage\b|initiative|saving throw|\bmodifier\b|\bDC\b|hit point|\bcheck\b|, guys|quest tracker|sidebar|\bI (only |just )?(got|have|rolled)\b|\[inaudible\]|\bInaudible\b|\b(insight|perception|arcana|persuasion|intimidation|investigation|deception|athletics|stealth|medicine|religion|survival)\b" <scene.md>
```

**This does not weaken the hard invariant.** The grep is a reading aid for
*you*, not a new category in `find_residue.py` — nothing it turns up is
auto-applied, and every hit goes to the GM in Phase 2 like any other
candidate. Label them explicitly as **supplementary (found by reading, not
by the scanner)** so the GM knows which findings carry deterministic backing
and which carry your judgement. Expect false positives from this sweep
(`check in on`, `pressed his advantage`, `and I have a plan` are idioms, not
residue); reject them yourself before presenting rather than padding the
queue.

Never silently add a vocabulary-matching category to `find_residue.py` to
close these gaps — that is a scope decision and it goes to the GM (see **The
hard invariant**).

### Phase 1c — debris that belongs to no category

Two things recur that are neither numbers nor fixed phrases nor player
names, and both are worth surfacing:

- **Transcription markers relocated into prose.** In one case the narration
  pass lifted `[inaudible]` *out of* a quoted line and re-sited it as a
  standalone italic thought (`*Inaudible.*`), leaving the quote itself
  ungrammatical (`"…Has heard about that?"`). Fixing this has two halves —
  delete the promoted marker *and* restore it inside the quote — and the
  second half is easy to forget.
- **Out-of-fiction vocabulary inside locked dialogue**, e.g. `"I'm gonna
  write that down on the quest tracker."` The immutable-quote rule means no
  pass will touch it. Report it as an upstream note for
  `notes/vtt_transcription_corrections.md` rather than editing it.

**Known limit of the immutable-quote rule:** it protects the *contents* of a
quote, but nothing stops an upstream pass from moving material out of a
quote into narration. When a quote reads as ungrammatical, suspect that
something was lifted out of it.

### Phase 2 — the GM reviews, one candidate at a time, ALWAYS

**Hard rule: nothing is rewritten without an explicit per-candidate
decision.** No cluster-wide auto-apply, no "these all look like the same
thing so I'll batch-approve them" — each candidate is either genuinely
identical repeated text (handle via a durable `rule`, Phase 2b) or gets its
own question.

Use `TaskCreate` per candidate (or per small batch) and `AskUserQuestion` to
walk them in this order — highest-yield / highest-risk first:

1. `roll_result_dialogue` and `roll_callout` — these are almost always real
   residue and usually need a genuine prose rewrite (a die roll spoken as a
   number, like `"I have twenty-two."`), not a word swap.
2. `dc_number`, `hp_number`, `damage_number`, `heal_number` — numeric, use
   the `hint` tier as a starting register.
3. `foot_count`, `round_count`, `initiative`, `advantage_with_number`,
   `dice_verb` — expect a meaningful false-positive rate; review skeptically.
4. `table_speak`, `player_name` — usually a full removal or a rename to the
   speaking character; player names in particular should almost never
   survive into narration prose.

For each candidate, draft a **specific proposed rewrite** for that exact
line (do this yourself, in the moment — you have the scene's voice in
context) and present it for confirmation:

```
Candidate (roll_result_dialogue), line 21, session_doc_scene_01...md
Context: So I stepped up. "I have twenty-two."
Matched: "I have twenty-two"

Proposed: "I have twenty-two." → "Let me look."

A) Accept proposed rewrite
B) I'll type the replacement
C) Not residue — protect this exact phrase (never ask again)
D) Skip for now (ask again next run)
```

For numeric categories with a `hint`, lead the proposal with the tier
language (e.g. a `damage_number` hint of "real impact — a hit that costs
something" becomes the register for your drafted sentence), but still draft
the actual sentence — don't hand the GM a bare tier label and call it done.

**(C) "Not residue"** must be persisted immediately:

```bash
python ~/.claude/skills/scrub/state.py --state <campaign>/notes/.scrub_state.json \
  ignore "<exact matched text>"
```

If the GM says a phrase should *always* translate the same way everywhere
(genuinely repeated boilerplate, e.g. "the DM said" appearing verbatim
across scenes) — not just this one instance — record it as a durable rule
instead of (or in addition to) the per-instance decision:

```bash
python ~/.claude/skills/scrub/state.py --state <campaign>/notes/.scrub_state.json \
  rule --match "<exact text>" --replacement "<exact replacement>" --category table_speak
```

Durable rules are literal, case-sensitive, whole-phrase matches — no regex,
no case-insensitive matching. A short rule text that's also an ordinary word
or phrase will over-replace on a future scene; before adding one, sanity
check it isn't a common substring. When in doubt, keep it a per-instance
decision instead of a durable rule.

Mark the corresponding `TaskUpdate` completed after each decision.

### Phase 3 — build the decisions file

Collect every (A)/(B) decision from Phase 2 into a JSON array:

```json
[
  {"line": 21, "old": "I have twenty-two.", "new": "Let me look."},
  {"line": 17, "old": "\"Now roll an investigation check,\" came the call. ",
   "new": ""}
]
```

`old` must appear **exactly once** on that line — copy it verbatim from the
candidate's `context`, don't retype it from memory. Write this to a
scratchpad file, e.g. `/tmp/scrub_decisions.json`.

Three things that bite here:

- **`line` is the absolute file line number**, counting the YAML
  frontmatter. `apply_scrub.py` computes `line - body_start_line` itself.
  Use the numbers `find_residue.py` reports and the numbers Read shows —
  don't subtract the frontmatter yourself.
- **Build the decisions file programmatically, don't retype.** Read the
  target line out of the file and slice it, then assert the slice matches
  before writing anything. Retyped strings fail on curly vs. straight
  quotes, em-dash vs. hyphen, and doubled spaces. Do not attempt to
  construct an em-dash via escape tricks (`"—".encode().decode(...)`
  mangles it) — paste the literal character.
- **Assert before you write.** Build the whole edit list, verify every
  `old` matches exactly once, and only then write the file. A failed
  assertion mid-loop must leave the file untouched.

### Phase 4 — apply (deterministic)

```bash
python ~/.claude/skills/scrub/apply_scrub.py \
  --file /tmp/scrub_preview.md \
  --decisions /tmp/scrub_decisions.json \
  --output <scene>.scrubbed.md
```

The applier verifies each `old` still matches exactly once before replacing
— if the file drifted since Phase 1/2 (e.g. you scanned then hand-edited the
preview), it reports the mismatch and skips that decision rather than
guessing. Re-run Phase 1's scan on any skipped-decision lines and re-ask.

The original `session_doc_scene_*.md` is never modified. Frontmatter
(the `---` YAML block) passes through untouched.

**Whitespace after deletions.** `apply_scrub.py` replaces a span on a line;
a decision with `"new": ""` blanks the line rather than removing it, so
deleting a contiguous block leaves a run of blank lines. Most of that is
cosmetic — Markdown renders three blank lines the same as one — but one case
is a real structural defect: a blank line left between a speaker tag and its
quote (`**[GM]**` / blank / `> "…"`) orphans the tag against the file's own
convention. After applying deletions, check for both, and if you clean them
up do it as an explicit whitespace-only pass that **verifies no non-blank
line changed**:

```python
a=[x for x in original if x.strip()]; b=[x for x in cleaned if x.strip()]
assert a==b, "whitespace pass altered content"
```

Report the cleanup to the GM; do not silently hand-edit the applier's output
in ways that alter text, or the deterministic guarantee is gone.

### Phase 5 — re-scan to confirm, record processed

Re-run `find_residue.py` against the freshly written `.scrubbed.md`. Any
remaining candidates mean either a Phase 2 decision was skipped in Phase 4,
or a new false-positive category needs a `state.py ignore`. Show the GM the
diff (`diff <scene>.md <scene>.scrubbed.md`) and confirm before moving on.

Once clean:

```bash
python ~/.claude/skills/scrub/state.py --state <campaign>/notes/.scrub_state.json \
  processed <scene.md-path>
```

## Important conventions

- **Dialogue is never deleted, only rewritten.** Every decision's `old`/`new`
  pair is a targeted span or sentence replacement on one line, applied by
  exact literal match — there is no whole-line deletion path in
  `apply_scrub.py`. If a candidate genuinely warrants cutting a whole
  sentence (e.g. a stray table-speak aside), that's still an explicit
  per-instance decision with `"new": ""`, confirmed by the GM like any other.
- **Numeric tier hints are a starting register, not a rewrite.** The `hint`
  field in `find_residue.py` output comes from lookup tables ported from
  the existing `scrub_mechanics_prompt.md`; it tells you roughly how hard a
  hit should read, not what sentence to write. Draft the actual sentence
  yourself in Phase 2, in the scene's voice.
- **`foot_count` will over-fire on mundane description.** This is expected
  and not a bug to fix by tightening the regex — see Phase 1. Surface, let
  the GM reject.
- **Durable rules are dangerous if too short.** Before adding one via
  `state.py rule`, grep the target file(s) for the match text in contexts
  where it *shouldn't* translate. Prefer a per-instance decision unless the
  phrase is genuinely unique boilerplate.
- **Promote a decision to a rule the second time you re-ask it.** If a scene
  is re-rendered and the same line comes back, that is the signal: the
  per-instance decision will keep costing a question every render. A long,
  distinctive match (`you can ask the GM, whether it helps`) is safe; grep
  first to confirm every occurrence is the same call, then
  `state.py rule`. This works — a rule added mid-session self-applied on the
  next run and removed the line without a question.
- **Scrubbing an upstream layer propagates, but only if it is complete.**
  When a scrubbed extraction file is promoted to be the narration pipeline's
  source, its deletions carry through: eight mechanical items removed
  upstream stayed out of the re-narration. But partial scrubbing backfires —
  a bare `> "17. 17."` left in place because it was out of scope was
  **expanded** by the next render into a full paragraph with a roll total
  and a flat 1. If you scrub an upstream layer, scrub it completely, or tell
  the GM plainly which residue you are leaving for the renderer to inflate.
- **Scrub sits downstream of narration** (`extraction → narration → scrub →
  assemble`). That means a re-narration is re-scrubbed anyway, so "scrub the
  upstream layer to stop regressions" is a weaker argument than it sounds.
  The real reason to scrub upstream is to stop the renderer *elaborating*
  mechanics into prose, which is a different and worse failure than passing
  them through.
- **This skill does not touch `scrub_mechanics.py` or the Session Doc
  Editor's Scrub button.** Those remain as-is (the OOTA per-campaign
  override prompt stays in place as the existing stopgap). Wiring the
  editor's UI to this propose→review→apply flow instead of the autonomous
  pass is a CampaignGenerator-side change, not something this
  Claude-Code-side skill does — flag it back to issue #151 as a follow-up if
  the GM wants that.
- **State lives in `notes/`**, which is excluded from the mempalace — it's a
  cleanup-pass reference, not campaign canon. Don't try to mine it.

## Why this design

Per the global rule (`~/.claude/CLAUDE.md`): *LLMs are renderers, not
architects.* Good pattern: **LLM extracts → human reviews and imposes
structure → LLM renders inside that structure.** Bad pattern (what
`scrub_mechanics.py` does today): **LLM extracts → LLM decides scope → LLM
renders**, with the error compounding silently into the narration that
becomes canon.

Here:
- Phase 1 (`find_residue.py`) is deterministic extraction — regex only, no
  LLM, and structurally incapable of touching magic vocabulary because no
  pattern references it.
- Phase 2 is the human checkpoint — every rewrite, even a well-drafted one,
  is a proposal until the GM picks (A)/(B)/(C)/(D). Nothing reaches (D) in
  the CampaignGenerator prompt's failure mode: silently deciding scope and
  shipping it.
- Phase 4 (`apply_scrub.py`) is deterministic rendering of exactly what was
  confirmed — literal span replacement, verified before write, no
  reinterpretation at apply time.

The spell-stripping incident is structurally impossible under this design:
removing a spell name would require it to first match a numeric or
table-speak pattern (it can't), and even a false-positive match would still
require the GM to affirmatively pick "accept" on a proposal that visibly
touches the spell name — which they wouldn't.
