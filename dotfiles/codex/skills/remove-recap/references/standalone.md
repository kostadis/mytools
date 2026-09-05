---
name: remove-recap
description: Detect and remove the previous-chapter recap that opens a recorded session, so it is not narrated a second time in this chapter's document. Scoped to the FIRST scene, where the recap always lives. Rescues GM asides, this chapter's bookkeeping, and anything the previous chapter's record missed, before anything is cut. Propose→review→apply with a GM checkpoint; edits only derived layers, never scene_extractions/ or the VTT. Cheapest before scene_extract. Invoke as /remove-recap [session-dir].
tools: Read, Bash, Write, Edit, Glob, AskUserQuestion
---

# remove-recap — the previous chapter does not belong in this one

Every recorded session opens with the GM catching the table up on last time.
That material belongs to the **previous** chapter's document, which already
exists. Narrated again here, the campaign gets the same events twice, told
twice, in two chapters.

Sibling of `/no-mech` and `/scrub`: deterministic detect → human checkpoint →
deterministic apply.

## When to run it

**After `enhance_summary` and its human-verified consistency pass (Stage 0/1),
and before `/scene-extract`.**

```
VTT -> /speaker-attribution
   -> enhance_summary -> gm-assist.md + session-summary.md
   -> /staged-consistency phase 0, phase 1      (scene structure now verified)
   -> [ /remove-recap ]   <-- HERE
   -> /scene-extract -> /staged-consistency phase 2 -> /voice-smooth
   -> [ /no-mech ]
   -> sd_plan -> sd_narrate -> /scrub -> assemble
```

**Not earlier:** removing a scene is a scope decision about the scene list, and
Stage 0/1 can still move scene boundaries. Settle the list first.

**Not later:** see the cost table below. Past `sd_plan`, deletion renumbers
every scene.

## THREE surfaces carry the recap — cutting scene 01 fixes only one

This is the mistake to avoid, and it is invisible if you only look at the scenes:

| # | Surface | Produced by | Effect if left |
|---|---|---|---|
| 1 | The recap **scene** in `## Scenes` | scene structure | narrated as a chapter opening |
| 2 | The **`## Summary` prose** in `session-summary.md` | `enhance_summary` | the chapter's own summary retells the previous chapter |
| 3 | The **enhanced-summary file** — same prose | `enhance_summary` | **worst of the three**: this file is `sd_narrate`'s positional *recap* argument, so it is framing context in EVERY scene's prompt and can bleed into any of them |

On obelisk ch10 all three were live. `session_summary.md`'s Summary opens with
three full paragraphs of chapter 8 — the Tresendar escape, the black stone,
Sildar/Garaele/Halia — and chapter 10 does not actually begin until *"With the
party still at the Miner's Exchange, Zenvon reviewed every open lead."*

**Handle all three in one pass**, at the single insertion point above. Surfaces 2
and 3 are prose, so they are trimmed by paragraph with the GM's ruling, not by
the scene-level tooling — and surface 3 is usually a copy of surface 2, so fix
them together and diff to confirm they still agree.

## Scope: the first scene

**Check the first scene. That is where the recap is**, because the recap is the
opening of the recording and the extractor cuts scenes in recording order.

`find_recap.py` defaults to the first scene for exactly this reason. `--all-scenes`
exists to *audit the assumption* once per campaign, not to hunt for a recap in
the middle of a session. On obelisk ch10 the audit gives 6/6 for scene 01 and
**0/6 for all seven others** — that separation is what licenses the scoping.

If a session genuinely resumes mid-scene after a break and the GM recaps again,
that is a `/no-mech`-shaped problem (out-of-character talk inside a live scene),
not this one.

## The hard invariant

**`scene_extractions/` and the VTT are never edited.** They are the record of
what was said, and a recap *was* said. Only derived layers change:
`scene_extractions_smoothed/`, `plan.md`, `narration/`, and — before extraction —
the scene list in `session-summary.md`.

## Cost of running it late

| When | Cost |
|---|---|
| **Before `scene_extract`** (recommended) | Drop the recap scene from `session-summary.md`'s `## Scenes` and trim surfaces 2 and 3. Nothing downstream ever sees it. Numbering is clean from the start. |
| After extraction, before narration | Delete the recap scene file, re-run `sd_plan`. Everything renumbers. |
| After narration | As above, plus **every scene must be re-narrated**, because the plan indices all shift. Most expensive. |

**Renumbering is the operational hazard, and it is not optional.** `sd_plan`
numbers sections by directory order, so removing `01_*` makes the old `02_*`
become section 1. Old `plan.md`, every `--scene N` invocation, and every
`session_doc_scene_NN_*.md` filename in `narration/` are then wrong. Regenerate
the plan and re-narrate; do not hand-renumber.

## Phase 1 — detect (deterministic, no LLM)

```bash
python ~/.claude/skills/remove-recap/find_recap.py \
  <session>/scene_extractions_smoothed
```

Scores the first scene 0–6 on independent evidence: explicit opening markers
(*"let me read you what happened"*, *"last time"*), real-world scheduling talk
(*"after, like, three weeks"*), a closing sting (*"Bum, bum, bum!"*), the word
recap in the filename or heading, and an overwhelming GM share.

It also reports **boundary candidates** — the last closing sting, and the first
line that reads like live play (*"you see"*, *"roll a"*). Those are proposals.

`--all-scenes` runs the audit. `--json` for machine output.

**A high score is evidence, not a verdict, and the boundary is never the
script's to set.**

## Phase 2 — rescue BEFORE you cut. Never skip this.

```bash
python ~/.claude/skills/remove-recap/recap_unique.py \
  --recap <session>/scene_extractions_smoothed/01_*.md \
  --against <previous-session-dir>
```

A recap is *supposed* to be redundant. It is not reliably redundant, and three
kinds of content die if you cut it blind:

**1. GM asides delivered while recapping.** The GM corrects, clarifies, or
reveals something the party did not know at the time. On obelisk ch10 the recap
is where the party finally learns the magic sword is named **Talon** — the
extraction annotates *"the GM notes the party has now learned the name."* That
is new canon, spoken during a recap, and the previous chapter's document cannot
possibly contain it. The script prints every `*(…)*` annotation; **read all of
them.**

**2. This chapter's bookkeeping, announced at the top.** Level-ups, subclasses,
spells gained, rests taken. ch10's recap scene opens with Zenvon reaching 3rd
level and taking Arcane Trickster — chapter 10 state, stated during a chapter 8
retelling. Rescue it into this chapter; never cut it.

**3. Beats the previous chapter genuinely missed.** Then the recap is the only
record, and the finding is a **gap upstream**, not a cut here. Report it and let
the GM decide whether the previous chapter's document gets fixed.

The coverage check is crude proper-noun and numeric matching against the previous
chapter's text. Low coverage means *look*, never *keep* or *cut*.

## Phase 3 — the GM rules

Present, with evidence quoted:

- the detector's score and the specific markers that fired
- **every** GM aside, verbatim
- the bookkeeping that must be rescued, and where you propose moving it
- anything poorly covered upstream
- the true cost: which scenes renumber, and what must be re-narrated

Then the options:

- **Cut the whole first scene** — when it is recap end to end (ch10: 45 quotes,
  zero live-play markers).
- **Trim the recap prefix** — when live play begins partway through. Use the
  boundary candidates, and cut at a beat, never mid-exchange.
- **Leave it** — some campaigns want the recap in the document.

**Where rescued content goes is its own decision.** Bookkeeping usually belongs
in this chapter's session summary; a GM aside that reveals canon usually belongs
in the entity's own record or the grounding docs, not smuggled into a scene it
did not happen in.

## Phase 4 — apply, then rebuild

Cutting a whole scene:

```bash
git rm <session>/scene_extractions_smoothed/01_*.md     # derived layer only
sd_plan --scene-extractions <session>/scene_extractions_smoothed ... --out <session>/plan.md
sd_narrate ... --plan <session>/plan.md --scene-extractions <session>/scene_extractions_smoothed \
  --per-scene-output <session>/narration        # ALL scenes; indices have shifted
rm <session>/narration/session_doc_scene_*.md   # stale numbering, before re-narrating
```

Trimming a prefix instead: reuse `/no-mech`'s `apply_cut.py --mode spans`, which
already refuses to write outside a `*_smoothed/` directory and warns on orphans.

**Then check the seams.** The narrator sometimes opens a scene by echoing the
previous scene's closing line. Deleting scene 01 orphans that echo in the scene
that followed it — on obelisk ch10, scene 02 opened on scene 01's last line,
*"Nothing about it felt polite."* Removing the recap leaves that dangling as an
opening with no referent. Walk every seam after re-narrating.

Also confirm the new first scene actually **opens** the chapter. A scene written
to continue from a recap may begin mid-thought.

## Phase 5 — record it

`<session>/remove_recap_manifest.md`, with:

- the detector score and the markers that fired
- **every rescued item, where it came from, and where it went** — this is the
  part a future reader needs, because the recap scene will no longer exist to
  check against
- what was cut, and the previous chapter it duplicated
- any upstream gap found in Phase 2, as an explicit open item against the
  previous chapter
- which scenes renumbered

If the campaign keeps `notes/scrub_register_policy.md`, append the standing
ruling: does this campaign cut recaps by default, and does it keep or drop the
scheduling chatter that precedes them.

## Landmines

- **Never cut before running the rescue check.** The one thing in ch10's recap
  worth keeping was invisible in the bullets and lived in an editorial aside.
- **Removing scene 01 renumbers everything.** Regenerate `plan.md` and delete the
  stale narration files before re-narrating, or you get a directory with both
  numberings in it.
- **The recap is not the only thing in the first scene.** Level-ups and rests get
  announced there.
- **A recap can be the only record of a beat.** That is a gap in the previous
  chapter, and it is a finding, not licence to keep the recap.
- **`scene_extractions/` stays.** The recap was really said.
- **Do not delete the previous chapter's document to "resolve" the duplication.**
  The recap is the copy; the chapter is the original.
- **Cutting scene 01 and stopping is the most likely way to half-fix this.** The
  summary prose and the enhanced-summary file carry the same recap, and the
  latter is framing context for every scene's narration prompt.
- **Trimming the summary prose is a judgement call about where the chapter
  starts.** Get it ruled; do not infer it from the first scene's boundary.

## Why this design

Which sentence ends the recap, and which of its contents are new, are **scope and
attribution decisions** — the two things the global rule says an LLM must not
make unsupervised. `find_recap.py` and `recap_unique.py` are regex and set
arithmetic over text on disk. The reading and the proposal are the model's; the
ruling is the GM's; the apply renders exactly what was confirmed.

The failure this prevents is quiet and expensive: a chapter that opens by
retelling the last one, and a piece of canon that existed only in the retelling.
