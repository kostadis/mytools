---
name: no-mech
description: Strip table mechanics — die rolls, DCs, virtual-tabletop and quest-log operation, rules Q&A, session scheduling — out of a session's voice-smoothed scene extractions, then re-narrate the affected scenes. Propose→review→apply with a GM checkpoint on every scene, because which quotes are roleplay is a scope decision. Edits ONLY scene_extractions_smoothed/; the verbatim scene_extractions/ and the VTT are never touched. Run before sd_narrate. Sibling of /scrub, which fixes residue that already reached the narration. Invoke as /no-mech [session-dir].
tools: Read, Bash, Write, Edit, Glob, AskUserQuestion
---

# no-mech — strip table mechanics out of scene extractions

Remove the quotes that are **the table operating the game** from a session's
voice-smoothed scene extractions, so `sd_narrate` never has to convert a die
roll into prose — and then re-narrate the affected scenes.

Sibling of `/scrub`. Same three honest phases (deterministic scan, human
checkpoint, deterministic apply) and the same core lesson: **the pattern scan
is a floor, the reading pass is the load-bearing one.**

## Where this sits

```
VTT (verbatim — IMMUTABLE)
  → scene_extractions/            (verbatim; NEVER edited by this skill)
  → voice-smooth                  (readable, in-voice)
      → scene_extractions_smoothed/
          → [THIS SKILL] no-mech  (cut the mechanics; re-narrate)
  → sd_narrate → narration/
      → /scrub                    (residue that still reached the prose)
```

The full pipeline order is in `~/src/CampaignGenerator/docs/design/SkillPipelineOrder.md`; the diagram above shows only the data layers this skill touches.

**Run it BEFORE `sd_narrate`.** Running it after means re-narrating, which is
fine but wasteful — and re-narrating has a real cost, see Phase 4.

## Why this exists, and what it actually buys

`/scrub` catches mechanical residue that reached the *narration*. This skill
removes it from the *input*. Those sound like the same job. They are not, and
the difference is the whole reason to have this skill:

**On obelisk ch10, `/scrub` finished with zero mechanical residue in any of the
eight narrated scenes.** By its own standard the session was clean. Two scenes
were nonetheless built from extractions that were almost entirely the table
working the virtual tabletop, and `sd_narrate` had quietly done a good job of
converting that to prose.

Removing the mechanics upstream and re-narrating those two scenes produced
**visibly better prose** — not more correct, *better*. With die rolls gone from
its input the narrator stopped spending its budget on conversion and spent it on
character. Scene 06 surfaced the party's darkvision split in narration for the
first time in the campaign ("Leadership is sometimes a grand word for deciding
where everyone sleeps"). Scene 08 recovered a being-lost comic sequence that the
roll-by-roll input had flattened.

**So the argument for this skill is not correctness. It is room.** Do not
measure success by whether the narration was broken before.

There is also a failure case this prevents outright. When a scene is *entirely*
mechanical and `sd_narrate` writes no reclassification hatch, the tooling reaches
the page as in-fiction dialogue: obelisk ch10 scene 02 narrated `"Quest log."`,
`"I cannot see your pointer."` and `"do we directly teleport to the quest
location?"` as things Zenvon said aloud.

## The hard invariant

**`scene_extractions/` is never edited by this skill.** It is the pipeline's
verbatim record of what was said. Only the derived `*_smoothed/` layer is
touched, and `apply_cut.py` refuses to write to any path not inside a
`*_smoothed/` directory. This is enforced in code, not by instruction.

The VTT is likewise untouched, always.

## The classifier — four categories, and only three have a default

The mistake is asking "is this quote mechanical?" That framing produces
endless per-line argument. Ask instead **who is being spoken to**:

| | Example | Ruling |
|---|---|---|
| **In-character speech** | Hamun: *"if I wanted my secrets to be safe, I would kill you"* | **KEEP** |
| **GM read-aloud / scene description** | *"the faint smell of smoke hangs in the air as you ascend a rugged ridge"* | **KEEP** — this is boxed text, and the narrator uses it |
| **GM-to-player-as-player** | *"roll a Perception"*, *"I'll move you back here"*, *"we'll continue next week"* | **CUT** |
| **Player-to-table reaction** | *"HOLY DICE!"*, *"WHAT THE F!"*, *"Average of bloody two, bro!"* | **ASK** |

The third category is the target, and it is wider than dice. It includes
virtual-tabletop operation (pointers, tokens, map highlighting), quest-log
mechanics, rules Q&A, session scheduling and wall-clock time, and out-of-character
exposition delivered as a lecture to the player rather than to the character.

**The fourth row has no default, and do not invent one.** A player swearing at
their own dice is table speech by the classifier — they are talking to the room,
not in character. It is also, sometimes, the best texture in the session. On toee
ch34 Sequoia's twenty-line meltdown over rolling 36 on twelve dice runs straight
into *"Sequoia curses at Frostbrand. You had one job."* — his intelligent sword.
The GM ruled KEEP. Bring these as their own question with the run quoted in full;
never fold them into a larger cut, and never keep them silently either.

**Cutting category-2 exposition is sometimes right too.** On ch10 scene 06 the
GM's world-building about Neverwinter's frontier was cut along with everything
else, and the narration came back *better* — because the scene-summary bullets
already carried those facts, and the narrator re-rendered them in Zenvon's voice
instead of quoting a lecture. That is a GM decision, not a default.

## Inputs

1. **session dir** — `summaries/<date>/`. Needs `scene_extractions_smoothed/`.
   If only `scene_extractions/` exists, run `/voice-smooth` first; do not edit
   the verbatim layer to compensate.
2. **`config/party.yaml`** — required for the triage signal. See Phase 1.
3. **`plan.md`** — needed for Phase 4's re-narration.
4. **`notes/scrub_register_policy.md`** — shared with `/scrub`. Read it first;
   it carries the campaign's standing rulings, and re-asking a settled question
   puts a settled ruling back at risk. It is also where a **dead triage signal**
   is recorded (see Phase 1) — that is per-campaign structure, discoverable only
   by having been bitten once, and nothing else on disk states it.

## Phase 1 — scan (deterministic, no LLM)

```bash
python ~/.claude/skills/no-mech/scan_quotes.py \
  <session>/scene_extractions_smoothed \
  --party-config config/party.yaml
```

Per scene it reports the quote count, the speaker-label distribution, how many
quotes trip a mechanical pattern, how many are in-character by stage direction,
who is voiced in those directions, a triage line, and any warnings.

**`--party-config` is close to mandatory.** The triage asks whether any speaker
label names someone *outside the party*. A PC label is worthless as evidence —
the player speaks under their character's name, so `Zenvon Forepot` sits on both
`"I'll do a Perception"` and a line of real dialogue. Without the party list,
every scene triages as roleplay and the signal is dead.

**The triage is one-directional and both scripts say so.** An NPC label is strong
evidence of roleplay. Its absence is *not* evidence of the reverse: ch10 scene 03
is a full two-hander in which all 55 of Daran Edermath's lines are labelled `GM`,
because the extractor never broke the NPC out.

**And the label signal can be dead for an entire campaign, by convention.** ch10
scene 03 was one scene; some extractors do it *always*, keeping `GM` on every NPC
line and naming who is being voiced in the italic stage direction instead:

```
**GM** — *as Varek Solain, asking why they came*
> "What's the problem?"
```

On toee ch34 that convention made **all six scenes** — three of them substantially
roleplay — triage as `REVIEW CLOSELY — no NPC speaker labels`. The signal was not
weak, it was structurally absent, and it will be absent on every future run of that
campaign.

So `scan_quotes.py` reports a **second signal**: `voiced:` counts the `*as <name>,*`
directions and triages on them when the labels give nothing. Read both lines. When
the second signal is the one carrying the campaign, **record that in
`notes/scrub_register_policy.md`** so the next run does not rediscover it.

**A party character in the `voiced:` line is a red alert, not a curiosity.** It means
the GM is also a player, and the script says so:

```
WARNING: Calmer is a PARTY character voiced under a non-PC label (5 quotes)
         — the GM is also a player. NEVER cut on the 'GM' label alone.
```

toee's GM plays Calmer. Since `config/players.yaml` gained `gm: true`, every one of
his lines carries a `**GM**` label — so a cut keyed on that label would have deleted
a PC's entire performance from the session. Exclude every `*as <PC>,*` block from
the cut by construction.

**The pattern flags are a floor, and a low one.** On ch10 scene 06 they matched
**3 of 47** quotes in a scene where all 47 were mechanical — 6% recall. Never
rule from the flag count.

## Phase 1b — read every scene. This is the phase that classifies.

Run with `--quotes` and read the whole census for each scene. You are deciding,
per scene, which of three shapes it has:

- **All-mechanical** — no in-character speech anywhere. Candidate for a whole-
  section cut. (ch10 scenes 02, 06.)
- **Mostly mechanical, with real beats inside** — needs selective span cuts.
  (ch10 scene 08: ~20 of 28 mechanical, but Veyra's two lines and the read-aloud
  are the scene's whole point.)
- **Roleplay** — leave it, or cut the handful of stray `roll a check` lines.
  (ch10 scenes 03, 04, 05, 07.)

**For the middle shape, build the cut by exclusion, not by keyword.** This is the
difference between a cut that works and one that leaves a mess. The instinct is to
list the mechanical lines and cut those; on toee ch34 scene 03 that produced a
129-line span list that was still wrong in both directions at once — it left
behind every table line carrying no keyword:

> `"Me?"` · `"Yes, you are up."` · `"Pistol?"` · `"Did you?"` · `"How much?"` ·
> `"14."` · `"17."` · `"Called—"`

while *keeping* a full Stunning Strike rules lecture, because the words "focus
point" and "stunned condition" read as in-world vocabulary to a pattern.

What worked was the inverse. **Find the block's boundaries, read it once, and list
what SURVIVES**; cut everything else in the range:

```
combat block = lines 227-966   (initiative call -> last creature retreats)
KEEP inside it = 37 hand-read beats
cut = every quote in 227-966 not in KEEP
```

232 of 317 quotes went, and what came back reads as a scene rather than a
transcript. The keep-list is also the thing you show the GM in Phase 2 — it is far
easier to rule on "here are the 37 beats I propose saving" than on a wall of line
numbers.

Two shapes that look mechanical and are not:

- **GM recap prose** at the top of a session's first scene. It is narration
  source, not table talk. ch10 scene 01 is 41 GM quotes of recap and only one is
  mechanical.
- **A GM prompt that sets up a character beat** — *"Do you want to tell her
  anything, or just look at her knowingly?"* is mechanically shaped and produced
  the best moment in ch10 scene 08.

## Phase 2 — the GM rules, per scene

**Never batch a whole session into one approval, and never decide the shape
yourself.** Which quotes are roleplay is a scope decision.

Present each scene with its count, its triage, the evidence, and the three
options:

- **Cut the whole section** — for all-mechanical scenes. State plainly that the
  scene will then be narrated from its summary bullets alone.
- **Cut listed spans** — give the line numbers and the text, grouped, with what
  survives.
- **Leave it.**

Quote real lines as evidence. `"Quest log."` and `"my pointer's nowhere"` make
the case in a way a percentage cannot.

## Phase 3 — apply (deterministic)

```bash
# all-mechanical scene
python ~/.claude/skills/no-mech/apply_cut.py \
  --file <session>/scene_extractions_smoothed/06_*.md --mode all \
  --note "*Cut in full by GM ruling (DATE): none of this scene's N quotes is
roleplay — all GM map operation and out-of-character exposition. Narrate from
the summary bullets. Verbatim record untouched in ../scene_extractions/.*"

# selective
python ~/.claude/skills/no-mech/apply_cut.py \
  --file <session>/scene_extractions_smoothed/08_*.md --mode spans \
  --cut 31 34 37 40 43 --note "*...*" --dry-run
```

The applier refuses any line number that is not a quote line (the file drifted
since the scan), drops speaker labels left introducing nothing, and **warns on
orphaned acknowledgements** — a bare `"Yes."` whose question you just cut. That
last one is real: it happened on ch10 scene 08 and the label between the two
lines initially hid it.

**An orphan is a NEW proposal, not a free fix.** Take it back to the GM as its
own decision rather than folding it in silently.

**Pass the path with its `*_smoothed/` segment intact.** The guard reads the path
string, so `cd`-ing into the directory and passing a bare filename gets you
`REFUSED: ... is not inside a *_smoothed/ directory` on a file that plainly is.
Run from the session dir and pass `scene_extractions_smoothed/NN_*.md`.

Always `--dry-run` first.

### Two residue classes the applier cannot see

`apply_cut.py` catches the orphaned *acknowledgement* — a bare `"Yes."` whose
question you cut. It cannot catch either of these, and only reading finds them:

**Orphan rubble.** Table lines that carry no keyword and were never in your cut
list, now sitting with nothing around them. This is the failure mode that argues
for the exclusion-built cut above; if you built the cut by keyword, sweep the
survivors for it before you write.

**Residue inside a KEPT line.** toee ch34 scene 03 survives with
`"24? You immediately recognize this as the equipment of the Greater Temple."` —
read-aloud text that still opens with a roll result. **This is not yours to fix
here.** Trimming it edits a quote you are keeping, which is a word change, and
word changes belong to `/voice-smooth`'s ruled-card process, not to a cut skill.
Report it and carry it forward.

Both are **new proposals**, exactly like orphaned acknowledgements: take them back
to the GM rather than folding them in. A line that is obviously in a class the GM
already ruled on is still a line they did not see — and generalising a ruling past
its stated scope is itself a judgment call.

## Phase 4 — re-narrate, then check the seams

**If you ran this at the recommended point, this whole phase is a no-op — and that
is the success case, not a gap.** No `plan.md` and no `narration/` means nothing has
been narrated yet, so there is nothing to regenerate and no seams to walk. Say so
plainly in the manifest rather than leaving a reader to wonder whether the phase was
skipped. toee ch34 ran this way: six scenes cut, zero re-narration, zero seam risk.

**Re-narration is a separate, potentially costly step — confirm it first.** When
narration already exists, name the affected plan indices and the backend that
will run (and whether it bills: a metered API or a remote endpoint), and wait for
the GM's explicit yes before invoking `sd_narrate`. An approved cut authorizes
the smoothed-layer edit only, never the re-narration.

Everything below applies only when narration already exists.

```bash
sd_narrate <recap>.md --plan <session>/plan.md \
  --scene-extractions <session>/scene_extractions_smoothed \
  --per-scene-output <session>/narration \
  --scene <N> [<M> ...] \
  --party docs/party.md --party-config config/party.yaml \
  --players-config config/players.yaml \
  --voice-dir voice --examples examples \
  --prose-mode --reflections --narrate-tokens 3200 \
  <backend flags>
```

**Either backend works; the GM picks per run.** Use one of:

```bash
--backend claude-code                                                    # the subscription
--backend codex-cli --model gpt-5.6-sol --codex-reasoning-effort medium  # Codex
```

If the GM hasn't said which, ask — and mention which one narrated the
neighbouring scenes, since a re-narrated scene sits between them. On
`claude-code`, extended thinking eats the output budget and runs several times
slower; `MAX_THINKING_TOKENS=0` closes most of the gap.

`--scene N` takes **plan section indices**, not filename numbers. Read `plan.md`.

**Re-narrating one scene changes the seams around it, and this is the skill's
sharpest edge.** The narrator sometimes opens a scene by echoing the previous
scene's closing sentence. Regenerating a scene therefore:

1. **Silently drops an echo** the neighbouring scene was relying on, and
2. **Can render the echo as quoted dialogue** — on the ch10 test run, scene 08
   opened with `"So we kept going."`, so Veyra appeared to speak Zenvon's closing
   narration aloud.

So after every re-narration, walk the seams: last non-blank line of scene N
against the first of scene N+1. A repeated sentence assembles as the same line
twice in a row; a quoted echo is a defect that must be fixed before shipping.

Then confirm what you actually bought:

```bash
# no mechanical language reached the prose (hatch comments stripped first)
# and the quote count moved the way you expected
```

**Expect the reclassification hatch to disappear.** With the mechanics gone
upstream there is nothing left for `sd_narrate` to reclassify, so a scene that
had a `<!-- table-speech reclassified: … -->` comment may now have none. That is
correct, and it means the audit trail has moved from the pipeline's own record
into your cut note — which is why the note is mandatory and must say what went.

**Never hand-write a hatch.** It fabricates a record of a decision the pipeline
never made.

## Phase 5 — record it

Two files, both shared with `/scrub`:

- **`<narration-dir>/no_mech_manifest_<session>.md`** — per scene: quotes before
  and after, the mode, the GM's ruling, and the exact note written. Plus any
  orphan decisions and any seam damage from Phase 4.
- **`notes/scrub_register_policy.md`** — append the durable rulings. Whether this
  campaign cuts category-2 GM exposition, whether wall-clock/session-scheduling
  talk is always cut, any scene shape ruled in-canon. **None of it is scannable**,
  so nothing else stops the next run re-proposing it.

## Landmines

- **The pattern scan has ~6% recall on an all-mechanical scene.** It exists to
  mark obvious hits, not to find them all. Read.
- **PC speaker labels prove nothing.** Always pass `--party-config`.
- **A missing NPC label does not mean a scene is mechanical** (ch10 scene 03).
- **In some campaigns the label signal is dead by convention, permanently.** Read
  the `voiced:` line, and write the finding into `scrub_register_policy.md`.
- **The GM may also be a player.** Then their PC's every line wears a `**GM**`
  label, and a label-keyed cut deletes a character. Heed the script's WARNING.
- **A keyword-built cut list leaves orphan rubble** the applier's orphan check
  cannot see. Build the middle shape by exclusion and read the survivors.
- **A roll result can survive inside a line you are keeping.** That is a word
  change and belongs to `/voice-smooth`, not here.
- **Pass the path with `*_smoothed/` in it**, or the guard refuses a valid file.
- **Cutting a question orphans its answer**, and a speaker label in between hides
  the adjacency.
- **`--scene` is plan indices, not file numbers.**
- **Re-narrating breaks seams**, sometimes as quoted dialogue.
- **Do not run this on `scene_extractions/`.** The script refuses, but the
  intent is what matters: that layer is the record.
- **This is not `/scrub`.** If the residue is already in the narration, that is
  `/scrub`'s job. This skill fixes the input; that one fixes the output.

## Why this design

Per the global rule: *LLMs are renderers, not architects.* Which quotes are
roleplay and which are the table talking is a **scope** decision, so no LLM makes
one here. `scan_quotes.py` is regex over text on disk. Phase 1b is an LLM reading
and **proposing**. Phase 2 is the GM ruling. `apply_cut.py` renders exactly what
was confirmed, verifying every span before it writes.

The bad pattern would be a model reading the extractions and deciding for itself
what counts as roleplay — which is precisely how a scene loses a joke, an NPC
loses a line, or a campaign quietly loses the one moment a sidekick spoke.
