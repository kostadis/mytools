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
tools: Read, Glob, Bash, Write, Edit, AskUserQuestion, TaskCreate, TaskUpdate, ToolSearch, Artifact, WebFetch
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

**First, ask how the GM wants to review.** Before anything else, one
`AskUserQuestion`:

> **Review the candidates in an artifact, or here in the shell?**
> - **Artifact** — one page, all candidates, mark them at your own pace, save once.
> - **Shell** — one candidate at a time, the way this skill has always worked.

Ask this every run; do not remember a default. If they choose the artifact,
run Phase 1 as written and then jump to **Artifact mode** below instead of
Phase 2. Everything from Phase 3 onward is shared.

Use `TaskCreate` to enumerate the target files. For each, run Phase 1–4
below. Process one file at a time so the GM isn't asked about 8 scenes'
worth of candidates in one breath.

Check `state.py show` first — skip any file already listed under
`processed` unless the GM explicitly asks to redo it.

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

## Artifact mode (batch review)

Replaces Phase 2 only. Phases 1 and 3–5 are unchanged, and the shell path
stays exactly as documented above. Full contract:
`~/.claude/skills/_shared/review-artifact/CONTRACT.md`.

**What is auto-applied, and it is deliberately almost nothing.** Only the
durable `state.rules` matches that Phase 1's `apply_known_rules.py` pre-pass
already collapses, plus `state.ignored` suppressions. **Every remaining
candidate becomes a card.** This skill's hard invariant is that nothing else
is rewritten without a per-candidate decision, and moving to a batch UI does
not relax it — it only stops the questions arriving one at a time.

**Build the items.** One card per `find_residue.py` candidate, keeping its
own `id` (`c1`, `c2`…) so Phase 3 can map decisions back to `line`/`match`.
Draft the proposed rewrite exactly as you would have in Phase 2 — the card
has to carry it, or the GM is approving a blank cheque. Keep the Phase 2
review ORDER as the card order: `roll_result_dialogue` / `roll_callout`
first, then the numeric categories, then `foot_count` / `round_count` /
`initiative` / `advantage_with_number` / `dice_verb`, then `table_speak` /
`player_name`.

```json
{ "id":  "c1",
  "t":   "Roll result spoken as a number — scene 01, line 21",
  "y":   "Rewrite <code>\"I have twenty-two.\"</code> → <code>\"Let me look.\"</code>",
  "n":   "Not residue — protect this exact phrase, never ask again (state.py ignore)",
  "ev":  "Context: <em>So I stepped up. \"I have twenty-two.\"</em> · category <code>roll_result_dialogue</code>" }
```

Put the `hint` tier in `ev` for the numeric categories — it is the register
the rewrite should land in.

**One page per file.** Phase 0's "process one file at a time" still holds:
eight scenes' worth of candidates in one artifact is the same breath problem
in a different shape.

**Publish**, hand over the link, and **stop — do not poll**. When the GM says
they are done, `WebFetch` the URL and run `read_decisions.py`.

**Map the verdicts back into the Phase 3 decisions array:**

| verdict | action |
|---|---|
| **approve** | `{"line": <candidate line>, "old": <candidate match>, "new": <the drafted rewrite>}` |
| **reject** | `state.py ignore "<match>"` — no entry in the decisions array |
| **discuss** + note | the note text becomes `new`; if the note says the phrase should *always* translate this way, use `state.py rule --match --replacement --category` instead of a one-off |
| **discuss**, no note | bring back to the shell, grouped with the other discussed cards |
| **unmarked** | undecided — say so, and leave the candidate for the next run |

`old` must still appear exactly once on that line — take it from the
candidate's `context`, never retype it. Then continue at Phase 3.

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
