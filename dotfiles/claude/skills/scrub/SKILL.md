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

Clean game-mechanical residue out of `session_doc` narration prose — without
ever letting an LLM decide, unsupervised, what counts as "mechanical" and what
counts as "the campaign's magic system."

## What the output is for

`.scrubbed.md` is **not a terminal artifact**. It assembles into the session
doc, and it is also handed back into `sd_narrate` as reference material for
the next narration pass — in this workspace, fable's input. Read the whole
skill with that loop in mind, because it changes what "good enough" means.

Residue that merely looks untidy in a finished document is not the real cost.
The real cost is that **whatever survives here teaches the next pass what this
campaign sounds like.** A stray die roll is inert on that trip — the narrator
drops it. Voice-level residue is not: an out-of-fiction aside, a modern idiom,
a register that does not belong to any narrator reads as *established style*,
and the model extends it confidently. That asymmetry is why
[Phase 1b](#phase-1b--read-the-scene-the-scan-is-a-floor-not-a-ceiling) treats
the reading pass as the load-bearing one and the regex scan as the cheap
floor, and why anachronisms get their own section there despite being
structurally unscannable.

It also raises the stakes on the human checkpoint rather than lowering them.
An unreviewed rewrite here is not one bad sentence in one document; it is a
premise the next generation inherits.

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

**The invariant binds the Phase 1b reading pass too.** That pass is a real
LLM reading real prose, so unlike the scanner it *could* propose a spell name
— and must not. It looks for the mechanical shapes the regexes miss (rolls,
skill numbers, levels, table talk) and nothing else. In-world magic, spell
names, item names, and creature names are never candidates, whoever noticed
them. A manual candidate is still only a proposal into Phase 2, so the GM
checkpoint remains the thing that actually holds — but do not make the GM the
first line of defence for the one failure this skill was built to prevent.

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
5. **Register policy** — `<campaign>/notes/scrub_register_policy.md`. The
   campaign's accumulated rulings on what is **not** residue. **Read it before
   walking candidates in Phase 2**, and append to it in Phase 6. If it does not
   exist, say so, and create it at the end of the run from whatever the GM ruled.

   This file is load-bearing, and it is the only durable home these rulings
   have. None of its content is scannable — `find_residue.py` matches numbers,
   fixed table-speak phrases and player names, and cannot match vocabulary at
   all by design — so nothing else stops the next run re-proposing every ruling
   in it, one instance at a time. It is campaign-scoped (resolved relative to
   the campaign dir, not the CWD) and version-controlled, which is exactly what
   project memory is not: see Phase 6.

   It is a cleanup-pass reference, not campaign canon. Like the rest of
   `notes/`, do not mine it into the mempalace.
6. **Protect files (optional)** — flat one-per-line files of terms that
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

**Read `<campaign>/notes/scrub_register_policy.md` before anything else.** It
carries the campaign's standing rulings on what is not residue, and every one of
them is invisible to the scanner. Reading it first is what stops you re-asking a
question the GM has already answered — and re-asking is not a harmless cost: the
GM has to re-adjudicate a settled call, and a tired yes on a ruling they
previously said no to silently reverses campaign policy.

**When the target is a directory, read every scene and take a cross-scene
census BEFORE entering the per-file loop.** Running gags and imported
vocabulary span scenes, and a per-file loop meets them one fragment at a time
— you cannot rule on a span in scene 01 without knowing it recurs eleven more
times in scenes 03 and 06. After the Phase 1b reading pass, grep each
distinctive token across the whole directory:

```bash
for t in <distinctive tokens from the reading pass>; do
  printf '\n### %s\n' "$t"; grep -nHi -- "$t" <dir>/session_doc_scene_*.md
done
```

Resolve every cross-file cluster as its own decision first. In ch50 this
surfaced `Bimbo` at 12 spans across 3 scenes, `fair trade` at 7 across 3, and
`cosplay` at 3 across 2 — and scene 01 could not have been settled without the
`Bimbo` ruling. The per-file loop then handles only what is genuinely local to
one scene.

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

Frontmatter and `<!-- ... -->` comments are both excluded from matching.
Comment spans are masked to spaces (offsets and line numbers preserved), so
the reclassification hatch `sd_narrate` writes cannot generate candidates —
see "the hatch is an audit record" under Important conventions.

**Expect false positives, especially on `foot_count`.** A pattern like
`\d+ feet` matches both genuine movement-mechanic residue ("moved forty feet")
and ordinary physical description ("a two-foot box of metal"). The regex
can't tell those apart and isn't trying to — that's Phase 2's job. Don't
pre-filter these out of the candidate list; surface them and let the GM
reject the non-residue ones (and optionally `state.py ignore` the exact
phrase so it never resurfaces).

### Phase 1b — read the scene; the scan is a floor, not a ceiling

**A zero-candidate scan is not a clean scene.** The patterns cover the shapes
someone thought to write down, and real transcripts keep producing shapes
they don't cover. Measured on Phandalin ch02: the scanner returned **6**
candidates across 8 scenes — one genuine, two `foot_count` false positives on
mundane description, three the same passive-perception cluster — while the
reading pass found **11 more** accepted changes. Two whole classes were
invisible to it (anachronism, and character-level / sheet talk), as was a
literal `[inaudible]` transcript artifact sitting in finished narration. Read every target scene yourself before reporting a result,
and surface what you find as manual candidates that go through Phase 2 like
any other. Say plainly which findings came from the scanner and which from
reading — "0 candidates" and "no residue" are different statements.

Confirmed blind spots, all observed live while the scanner reported zero — the
first five in Phandalin ch48 scene 06, the last four across ch50, where eight
scenes yielded exactly one scanner candidate and it was a false positive:

| Shape | Example that slipped | Why |
|---|---|---|
| second-person roll result | `"You got a 9 perception?"` | `roll_result_dialogue` is anchored to first-person `I` |
| `had` as the roll verb | `"Looks like I had a 9 perception."` | pattern covers `got\|have\|rolled` only |
| bare *number + skill* | `"13 investigations"`, `"20 insights"`, `"27 persuasion"` | no pattern pairs a number with a skill name |
| character level | `"we're level 7?"` | no level pattern exists |
| skill-as-noun roll | `"the Insight roll"`, `"double rolls"` | `dice_verb` needs a pronoun immediately before the verb |
| numberless roll instruction | `"Roll for initiative."` | every `initiative` pattern requires a digit; the bare imperative matches nothing |
| bare skill-as-noun | `"That's not an intimidation."` | no pattern treats a skill name as a countable noun |
| metagame tooling | `"Let's add it to the quest tracker!"` | a game-log tool is neither a number nor a fixed table-speak phrase |
| clock-notation drift | `"at 3 AM"` in a doc that says `the third hour after midnight` four other times | not residue at all — an internal-consistency defect that only reading catches |

Do **not** silently widen `find_residue.py` to cover these mid-run. Adding
patterns creates new false positives and is a scope decision — propose it to
the GM as its own change, the same way the hard invariant requires for any
vocabulary-based category.

#### Anachronisms — the highest-value reading-pass class, and structurally unscannable

Real-world references reach the narration constantly, because the table
speaks in modern idiom and the GM ad-libs: brand names, cities, tech, pop
culture, corporate jargon. Phandalin ch48 carried nine into finished
narration — `Oral B. Vance` as an NPC's name, `Houston, Texas`, `Mandalore`,
`Zoomer`, `SystemD`, `meth lab`, `dollars`, `Sherlock`, `Chinese wall`.

**The scanner cannot ever find these**, and not by oversight: every pattern
matches a number, a fixed table-speak phrase, or a real player name, and an
anachronism is none of the three. Detecting one would require a vocabulary
category, which [the hard invariant](#the-hard-invariant) forbids adding
without the GM's explicit sign-off. So this class is *only* ever found by
reading, and finding it is on you.

**Why it matters more than ordinary residue: the scrubbed file is fable's
input.** `.scrubbed.md` is not a terminal artifact — it is handed back into
`sd_narrate` as reference material. A leftover number is inert there; the
narrator drops it. An anachronism is *not* inert, because it reads as
established voice, and fable will extend a register it believes the campaign
has already adopted. One `SystemD` in the input licenses a whole scene of
sysadmin metaphor in the output. This is the one residue class that
**compounds across passes**.

**It is still a GM scope decision, and the checkpoint is unchanged.** Many
campaigns license absurdist comedy in the genre rulebook, and the jokes are
often the players' own and genuinely loved. Surface every instance through
Phase 2 with its tape line; never strip one on your own judgement. Note also
that these sit inside verbatim dialogue almost by definition, so removing one
is an **authorial rewrite of what a player said**, not a correction — say so
when you propose it, and record it that way.

**Settle the campaign's register policy ONCE, before you walk the candidates.**
The anachronism class is where a campaign's genre licence actually lives, and
it is usually a *single policy* rather than N independent rulings. Make it your
first anachronism question, cite the specific spans you found as evidence, and
let the answer collapse the rest of the queue.

Phandalin ch50 is the cautionary case. Eight scenes carried ~20 modern-idiom
spans; several rounds went by proposing `fair trade`, `supply chain`,
`marketing`, `revenue share` and `image and likeness` as residue before the GM
explained that **Vukradin importing real-world economics into Faerûn is the
campaign's central conceit** — KP's planar-efficiency project being the same
premise from the other side. Every one of those was canon by design. The
questions were not wrong to ask; asking them one at a time was.

The line that emerged there is a good default to *propose* — never to assume:

| Class | Example | Usual ruling |
|---|---|---|
| **named real-world entity** | `Bud Light`, `Hollywood`, `Kickstarter`, `Blue Oyster Cult`, `Houston` | scrub — a brand, place, platform, band or person has no in-world referent |
| **imported concept** | `fair trade`, `supply chain`, `revenue share`, `perpetuity` | ask — this may be the campaign's premise rather than its residue |
| **self-covering reference** | `Yoko`, answered two lines later by `I do not know who Yoko is.` | usually keep — the narration has already absorbed it in-voice |

A campaign may also rule a specific word in-canon outright (ch50: *"cosplaying
is an in canon word"*), or rule an entire class in — Phandalin ch02 settled that
metagame *adventuring* vocabulary (quest, quest marker, alignment, action
economy, a caster naming prepared spells) is canon, and that the class to police
is **modern technology**: "MMO" was scrubbed while "the quest marker" in the very
same line was kept.

**Write those down in `<campaign>/notes/scrub_register_policy.md`**, as well as
in the run manifest. They are invisible to every future scan, because the scanner
cannot match vocabulary at all, so nothing but that file stops the next run
re-proposing them.

**When the GM does say yes, replace rather than delete — the replacement is a
lore opportunity.** A neutralised line is a dead line; an in-world equivalent
is free canon, and it is what makes the input better for fable rather than
merely less wrong. From the ch48 pass:

| Anachronism | Replacement | What it bought |
|---|---|---|
| `Chinese wall` | the Menzoberranzan **cadet house** | a drow institution for laundered agency, and Valphine's read on the whole scene |
| `SystemD` | a **Mielikki** teaching on what holds a wood up | put the druid's faith into prose for the first time |
| `meth lab` | an alchemist cooking **dreamlily** | a named narcotic |
| `Zoomer` | "talks like a **shell-sprout**" | Soma's own idiom for the young |
| `Oral B. Vance` | **Aurum Bee Vance** | kept the mishearing joke, lost the toothbrush |

Two obligations follow, and both are easy to forget:

1. **Anything you invent is now canon.** Log new proper nouns
   (`dreamlily`, `cadet house`) with `provenance: on_the_fly` and a note
   saying they were authored in narration rather than played or prepped —
   otherwise the next consistency pass reads them as fabrications. A
   *mishearing* like `Aurum Bee Vance` is **not an alias** and must not be
   registered as one; it belongs in the canonical entity's note.
2. **The narration now diverges from the tape on purpose.** Every future
   fidelity check will flag these spans as errors. Record them in the run's
   manifest as GM-authored, or someone will dutifully "fix" them back.

And apply the blast-radius check from Phase 2 with particular care here: a
distinctive real-world noun is exactly the kind of thing a later line calls
back to. Removing `Houston, Texas` from one line stranded `Nobody asks him
what a Houston is.` two sentences on.

#### The third disposition: annotate — the sage's marginal note

Keep and replace are not the only rulings. When the anachronism sits inside
**verbatim player speech**, the joke is loved, and no in-world swap survives
inside the quote without rewriting what the player said, offer **annotate**:
leave the quote byte-exact and add an in-world scholarly gloss immediately
after the beat it explains, as an italic paragraph in this shape:

> *Marginal note in a later hand: "<term>" — <invented in-world explanation>.
> — <sage persona>*

Established precedent (Phandalin ch3 scene 07, GM-approved 2026-08-18):
`"He's dead, Jim,"` stayed verbatim, Brewbarry's `I do not know Jim. Dead is
dead.` stayed, and the note invented **Jimble the Unmoved** — a cleric of the
old coastal sagas who pronounced companions dead rather than spend the prayer
— which simultaneously explains why coastal Soma knows the phrase and mountain
Brewbarry does not.

Rules for the device:

- **The persona must be the campaign's established in-world scholar** —
  Phandalin: **Kostadinious the Sage** (the campaign's in-world biographer).
  Never mint a new sage per note; if a campaign has no such persona, that is
  a GM decision to make before the first note, not something to improvise.
- **The note is narration-layer apparatus**, not dialogue and not direct
  thought — the `Marginal note in a later hand:` preamble is what keeps the
  italics from reading as the genre's thought convention. `assemble.py`
  passes it through untouched.
- **Both obligations above apply in full**: whatever the note invents is
  canon (`provenance: on_the_fly`), and the note is a deliberate divergence
  from the tape — record it as GM-authored.
- **It is a spice, not a default.** Propose it per instance alongside keep
  and replace; one note per session doc is apparatus, a note per joke is
  clutter.
- **Place notes at the end of the beat, not inside it.** A scholarly note
  dropped mid-exchange kills comic pacing. ch50 put two notes in one scene and
  it read fine, because both glossed the same rapid naming sequence and both
  landed *after* it closed — capping the sequence rather than interrupting it,
  with the scene's own transition line (`Names are finished. Work starts.`)
  following them. Two notes explaining two different beats, scattered, would
  not have worked.

### Phase 2 — the GM reviews, one candidate at a time, ALWAYS

**Hard rule: nothing is rewritten without an explicit per-candidate
decision.** No cluster-wide auto-apply, no "these all look like the same
thing so I'll batch-approve them" — each candidate is either genuinely
identical repeated text (handle via a durable `rule`, Phase 2b) or gets its
own question.

**First, drop every candidate the campaign has already ruled in canon.**
`<campaign>/notes/scrub_register_policy.md` is the list. Filtering against it is
not an optimisation — a settled ruling re-asked is a settled ruling put back at
risk, and a distracted yes on the fifth re-ask quietly reverses campaign policy
without anyone deciding to. Nothing in that file reaches the GM as a proposal
again unless the GM reopens it.

The rulings still standing after that filter are the ones that get questions.

**Coupled candidates get one decision, labelled as such.** Two spans whose
rewrites must agree — a question and its answer (`"You got a 9 perception?"` /
`"Looks like I had a 9 perception."`) — are one decision presenting both
halves, because approving them separately invites an exchange that no longer
echoes. State in the question that it covers both lines. This is the only
exception to one-candidate-one-question, and it does not extend to spans that
merely *resemble* each other.

**A cluster that spans scenes is still one decision.** The coupling rule is
about meaning, not proximity: a running gag repeated across a directory
(ch50's `Bimbo`, 12 spans in 3 scenes) has to be ruled once and applied
consistently, or the assembled doc contradicts itself scene to scene. Give the
span count and the scenes it touches, and say plainly which single ruling you
are asking for. This still does not license batching *unlike* spans that
merely share a category.

**Check whether a candidate is another's setup or payoff before proposing.**
Scene 04 of ch48 had `"we're level 7?"` and, two lines later, the joke
`"We're about to be level dead"`. Rewriting the first strands the second.
Surface the dependency in the question so the GM is choosing with it in
view, and offer the dependent line its own decision rather than silently
adjusting it.

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

**Check the blast radius before you propose, not after you apply.** The span
you are replacing may be load-bearing for text you are not replacing, and
`apply_scrub.py` cannot see that: it verifies the span, swaps it, and reports
success. The prose is then broken and the tooling says it is clean.

Two shapes, both observed:

- **The neighbouring clause depends on the span's grammar.** An attribution
  verb, a pronoun, a conjunction. `"…yourself—" Soma starts.` parses only
  while the dash marks her as cut off; change the dash to a period and
  `starts` dangles with nothing to start.
- **A distinctive noun is called back later.** Removing a proper noun from
  one line orphans the joke built on it further down — dropping `Houston,
  Texas` from a line of dialogue left `Nobody asks him what a Houston is.`
  stranded in the next sentence.

So, for every candidate, before drafting:

```bash
sed -n "$((LINE-3)),$((LINE+3))p" <preview>      # read around it
grep -n "<distinctive token>" <preview>          # does anything call it back?
```

If the fix needs a second edit to stay grammatical, **propose both spans
together as one decision** and say so. A GM who approves "drop the number"
has not thereby approved "and also rewrite the following sentence" — that is
a separate change to prose, and it gets its own explicit yes.

**(C) "Not residue"** is persisted immediately — *when the matched text is
specific enough to be safe*:

```bash
python ~/.claude/skills/scrub/state.py --state <campaign>/notes/.scrub_state.json \
  ignore "<exact matched text>"
```

**`ignore` carries the same short-string hazard as a durable rule, and the
matched text is not always safe to persist.** The list is subtracted from
every future scan in the campaign, so ignoring a common fragment silently
disables a whole detector. `"seven feet"` (a goliath's height) is specific
enough to retire permanently; `"you roll"` is not — persisting it would have
suppressed every genuine `dice_verb` hit in the campaign from then on. When
the match is short or generic, take the rejection as a per-instance skip and
say why you are not writing it to state. If the false positive is structural
rather than incidental, fix the cause instead of suppressing the symptom —
the comment-masking behaviour in Phase 1 exists because of exactly one such
case.

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

**Build the file by slicing the source lines, not by transcribing them.**
Narration prose is full of characters that do not survive retyping — U+2026
ellipses, curly apostrophes, non-breaking spaces — and every one of them
turns into a silent Phase 4 skip. Read the preview, index the line, slice the
span, and let the JSON be written from the actual bytes:

```python
L = pathlib.Path(preview).read_text(encoding="utf-8").split("\n")
line = L[25 - 1]                                   # 1-indexed
old  = line[line.index('"You know,'):]             # slice, never retype
decisions.append({"line": 25, "old": old, "new": "…"})
```

Then print each `old → new` pair for the GM to eyeball before applying. If
Phase 4 reports any skip, the cause is almost always a character that differs
from what was typed by hand.

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

**Then read each changed line WITH ITS NEIGHBOURS — a clean re-scan is not a
clean paragraph.** Both tools are span-local: the applier checks the span it
replaced, and `find_residue.py` checks for mechanical residue. Neither can
tell you the sentence after your edit no longer parses. Every prose defect
introduced by a *correctly applied, GM-approved* edit in practice has come
from this gap, and each one shipped past a green re-scan.

```bash
diff <scene>.md <scene>.scrubbed.md            # what moved
awk 'NR>=L-2 && NR<=L+2' <scene>.scrubbed.md   # read around every changed line
```

You are reading for three things: a stranded attribution verb, a pronoun that
now points at the wrong person, and a callback to something you deleted. If
you find one, it is a **new** proposal — take it back to the GM as its own
decision rather than folding it in silently, because it changes prose rather
than stripping mechanics.

Once clean:

```bash
python ~/.claude/skills/scrub/state.py --state <campaign>/notes/.scrub_state.json \
  processed <scene.md-path>
```

**Never mark a file processed while a (D) skip is outstanding on it.**
`processed` makes Phase 0 skip the file entirely on the next run, so
recording it converts "ask again next run" into "never asked again" — it
quietly destroys the decision the GM actually made. A scene with one pending
skip stays out of the list, even when every other candidate in it is
resolved, and you say so rather than leaving the omission to be inferred.

**A scene with no accepted changes gets no `.scrubbed.md`, and that is
correct.** Don't write a pass-through copy to make the directory look
uniform. `collect_scene_files` in `assemble.py` prefers `.scrubbed.md` per
scene and falls back to the raw `.md`, so a mixed directory assembles
correctly; a scene is "processed" because it was reviewed, not because it
produced a file.

### Phase 6 — write the run manifest

The anachronism section tells you to record divergences "in the run's
manifest". This is that file. Write it once per run, next to the scenes, at
`<narration-dir>/scrub_manifest_<session>.md`. It exists because two kinds of
damage happen silently months later:

1. **A fidelity check flags your approved rewrites as transcription errors**
   and someone dutifully "fixes" them back to the tape.
2. **A consistency pass reads your invented nouns as fabrications** — or
   worse, a registry pass records a *mishearing* as an alias of the real
   entity, fusing an insult into an NPC's identity.

Four required sections:

- **GM-authored divergences** — a table of scene / line / tape text /
  scrubbed text / class, one row per accepted change. This is the whole point
  of the file; make it greppable.
- **New canon (`provenance: on_the_fly`)** — every proper noun, item, proverb
  or institution the run invented, marked as authored in narration rather than
  played or prepped. State explicitly where a coinage is **not** an alias
  (ch50: `"Bimbo"` is dockside slang, the entity is still **Bimble Nackle**).
- **GM rulings on what is NOT residue** — the register policy, any word ruled
  in-canon, and the kept references. Without this the next run re-proposes all
  of them, because none of it is scannable.
- **Notes** — scenes reviewed with no `.scrubbed.md` and why, any scanner
  false positive deliberately not persisted to `ignore`, and any tooling gap
  hit during the run (e.g. a roster line `--party-md` could not parse).

**Then append the durable, campaign-level rulings to
`<campaign>/notes/scrub_register_policy.md`.** Every class the GM ruled in
canon, every word ruled in-canon outright, every kept reference, and every
coinage authored during the run. The manifest serves the next consistency pass;
the policy file serves the next `/scrub`.

**Do NOT rely on project memory for this.** Claude Code's project memory is keyed
to the **working directory**, not to the campaign: a run started in
`<campaign>/summaries/20250514-chapter-02-new/` and a run started in
`<campaign>/` or in `<campaign>/summaries/20260901/` get three different memory
directories, and none of them can see the others. A ruling written to memory
during one chapter's scrub is therefore already unreachable from the next
chapter's scrub — not merely at risk of being lost. Earlier versions of this
skill claimed "memory serves the next `/scrub`"; that was wrong, and it is why
the policy file exists. Writing a *cross-campaign* lesson to memory as well is
fine; the campaign's rulings must land in the policy file regardless.

## Important conventions

- **Dialogue is never deleted, only rewritten.** Every decision's `old`/`new`
  pair is a targeted span or sentence replacement on one line, applied by
  exact literal match — there is no whole-line deletion path in
  `apply_scrub.py`. If a candidate genuinely warrants cutting a whole
  sentence (e.g. a stray table-speak aside), that's still an explicit
  per-instance decision with `"new": ""`, confirmed by the GM like any other.
- **Writing `.scrubbed.md` forks the scene, and every later editor inherits
  the fork.** Leaving the raw file untouched is right for *this* skill — it
  keeps an unmodified pipeline record and makes the scrub reversible. But the
  moment the pair exists, the two files disagree, and the next pass to touch
  that scene (a `/voice-critic` fix, a `/consistency-check` ruling, a typo
  repair) has to decide which one it is editing. Editing only the
  `.scrubbed.md` ships correctly today and leaves the defect live in the raw,
  where a re-run of `sd_narrate`, a re-scrub, or a scene that later loses its
  scrubbed variant will resurrect it. Editing only the raw fixes nothing that
  assembles.

  So when a *downstream* pass reports a fix on a scrubbed scene, say which
  copies it landed in, and default to both. Note the asymmetry that makes this
  easy to get wrong: scenes with no accepted scrub changes have **no**
  `.scrubbed.md` at all, so a single sweep across one narration directory is
  editing one file for some scenes and two for others. Resolve the effective
  set explicitly — the same `.scrubbed.md`-then-raw precedence `assemble.py`
  uses — before touching anything, and never assume it is uniform.
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
- **The `<!-- table-speech reclassified: … -->` hatch is an audit record —
  never scrub it, never forge one.** `sd_narrate` writes it to record spans it
  judged to be out-of-fiction table talk and dropped; `assemble.py` strips it
  at assembly. Its contents are already *out* of the narration, so a match
  inside it is always a false positive (which is why Phase 1 masks comments).
  And when a scene needs a hatch it never got, **do not hand-write one** —
  that fabricates a record of a decision the pipeline never made. Excise the
  lines by explicit per-instance decision with `"new": ""` instead, and tell
  the GM the hatch is absent.
- **Roll residue found in *dialogue* has two possible remedies, and the choice
  is the GM's.** Scrub can rewrite the line in the narrator's voice (keeping
  the beat, dropping the number), or the line can be cut as table speech that
  reclassification should have caught. Re-running `sd_narrate --scene N` is a
  third option that re-rolls the whole scene. Present them; don't assume the
  rewrite. `/voice-critic`'s "Reclassified table speech" section is the
  natural place this gets noticed first — the two skills are complementary,
  and a voice-critic pass immediately before a scrub run makes the reading
  pass in Phase 1b much cheaper.
- **`--party-md` only sees names written as `Player: X`.** `load_player_names`
  matches that literal prefix, so a roster line formatted any other way
  (Phandalin's `**Barbarian 7 | Goliath | Stéphane Bourdeaud**`) yields no
  name and that player is invisible to `player_name` detection. Check how many
  names actually loaded — `find_residue.py` reports them in
  `player_names_loaded` — against the campaign's real roster, and say so when
  they don't match.
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
- Phase 1b is LLM extraction, added because the regexes provably miss real
  residue. It widens what gets *proposed*; it decides nothing. Both kinds of
  candidate land in the same queue and neither can reach the narration
  without a GM decision, so the pipeline stays **extract → human → render**.
  The bad pattern would be an LLM reading the scene and rewriting what it
  found — that is the step this skill does not have.
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
