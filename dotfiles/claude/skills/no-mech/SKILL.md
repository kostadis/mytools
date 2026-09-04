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

## The classifier — three categories, not two

The mistake is asking "is this quote mechanical?" That framing produces
endless per-line argument. Ask instead **who is being spoken to**:

| | Example | Ruling |
|---|---|---|
| **In-character speech** | Hamun: *"if I wanted my secrets to be safe, I would kill you"* | **KEEP** |
| **GM read-aloud / scene description** | *"the faint smell of smoke hangs in the air as you ascend a rugged ridge"* | **KEEP** — this is boxed text, and the narrator uses it |
| **GM-to-player-as-player** | *"roll a Perception"*, *"I'll move you back here"*, *"we'll continue next week"* | **CUT** |

The third category is the target, and it is wider than dice. It includes
virtual-tabletop operation (pointers, tokens, map highlighting), quest-log
mechanics, rules Q&A, session scheduling and wall-clock time, and out-of-character
exposition delivered as a lecture to the player rather than to the character.

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
   puts a settled ruling back at risk.

## Phase 1 — scan (deterministic, no LLM)

```bash
python ~/.claude/skills/no-mech/scan_quotes.py \
  <session>/scene_extractions_smoothed \
  --party-config config/party.yaml
```

Per scene it reports the quote count, the speaker-label distribution, how many
quotes trip a mechanical pattern, and a triage line.

**`--party-config` is close to mandatory.** The triage asks whether any speaker
label names someone *outside the party*. A PC label is worthless as evidence —
the player speaks under their character's name, so `Zenvon Forepot` sits on both
`"I'll do a Perception"` and a line of real dialogue. Without the party list,
every scene triages as roleplay and the signal is dead.

**The triage is one-directional and both scripts say so.** An NPC label is strong
evidence of roleplay. Its absence is *not* evidence of the reverse: ch10 scene 03
is a full two-hander in which all 55 of Daran Edermath's lines are labelled `GM`,
because the extractor never broke the NPC out.

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

Always `--dry-run` first.

## Phase 4 — re-narrate, then check the seams

```bash
sd_narrate <recap>.md --plan <session>/plan.md \
  --scene-extractions <session>/scene_extractions_smoothed \
  --per-scene-output <session>/narration \
  --scene <N> [<M> ...] \
  --party docs/party.md --party-config config/party.yaml \
  --players-config config/players.yaml \
  --voice-dir voice --examples examples \
  --prose-mode --reflections --narrate-tokens 3200 \
  --backend codex-cli --model gpt-5.6-sol --codex-reasoning-effort medium
```

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
