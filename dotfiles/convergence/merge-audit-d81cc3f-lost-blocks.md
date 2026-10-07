## staged-consistency: 254 lost lines in 20 blocks (line numbers from b4bea66)

### staged-consistency L4-4
```markdown
tools: Bash, Read, Edit, AskUserQuestion, Artifact, WebFetch
```

### staged-consistency L21-32
```markdown
### 0a. Choose the review mode

Before locating anything, one `AskUserQuestion`:

> **Review each stage's findings in an artifact, or here in the shell?**
> - **Artifact** — one page per stage at a single URL, mark the rulings at your own pace, save once per stage.
> - **Shell** — the severity table and "Going 1x1?", the way this skill has always worked.

Ask this every run; do not remember a default. In artifact mode the severity
table is still presented in the shell — it is the at-a-glance summary — but
the *rulings* move to the page. See **Artifact mode** below.

```

### staged-consistency L50-77
```markdown
Then load the two corroborating sources. Neither replaces prep; both change what
you can settle.

**The raw VTT is the attribution authority.** A session dir normally holds two
transcripts: `*.transcript.vtt` (raw, real-name speaker labels) and
`*.transcript.cleaned.vtt` (PC-name labels, derived). Read *from* the cleaned one
and *adjudicate against the raw one*. Build the name map once and hold it —
`grep -oP '(?<=^)[A-Z][A-Za-z .\x27-]+(?=:)' <raw>.vtt | sort | uniq -c | sort -rn`,
matched by cue count against the cleaned file.

> ⛔ **For any "who said or did X" question, go to the raw labels.** Never settle
> attribution from a summary — not the recap, not the Zoom summary, not both
> agreeing. See the Ch65 case in Notes.

**`zoom-summary.md`, if present**, is Zoom's own detailed session summary. Load it
and use it for exactly one thing: **a structural cross-check.** It is good at what
was in a room, how many options an NPC offered, and which beats a scene had — so it
catches *dropped* material the recap silently lost. It is unreliable at attribution
in the same way the GMAssist extractor is, and for the same reason: neither has
speaker labels in front of it while it writes prose.

> ⭐ **Two summaries agreeing on "who" is not corroboration — it is a shared
> failure mode.** Treat agreement between the recap and the Zoom summary on an
> attribution as *zero* evidence, and go to the raw VTT.

If `zoom-summary.md` is absent, say so in the final summary — the run loses the
dropped-beat check, which is the one thing prep cannot supply.

```

### staged-consistency L86-86
```markdown
ls "$SESSION"/scene_extractions{,_new}/0*.md 2>/dev/null | grep -v ".prev\|.scaffold"
```

### staged-consistency L90-94
```markdown
# and the three things that tell you what already ran, and from what:
cat  "$SESSION"/.cg/activity.jsonl 2>/dev/null      # stage, rc, and the OUTPUT paths
ls   "$SESSION"/consistency_report_stage*.md 2>/dev/null
cat  "$SESSION"/consistency_report_stage*.sources.yaml 2>/dev/null   # <- the RULINGS live here
ls   "$SESSION"/logs/*_enhance_summary.md 2>/dev/null
```

### staged-consistency L97-142
```markdown
⭐ **Filenames vary.** The stage-0 artifact is often not called `gm-assist.md` — a
GMAssistant export lands as `session_<date>_session_<date>.md`, and the enhance
output as `session_summary.md` rather than `session-summary.md`. The scene
extractions land in `scene_extractions/`, not `scene_extractions_new/`. Do not
conclude a stage is missing from a failed `ls` — check the directory listing
itself.

⭐ **Check the input mtimes before checking anything else.** `ls -t` on the stage
files tells you whether stage N was generated from *corrected* stage N-1 input or
from the pre-review version. If the extract ran before the stage-1 fixes landed,
every ruling you already applied is absent downstream and the run is a re-do, not
a new stage. Say which it is in the opening message. **`.cg/activity.jsonl` names the real paths**
and is the fastest way to learn which file feeds which; confirm the mapping with
the user before checking anything.

**If a `consistency_report_stage*.md` already exists**, a prior run checked that
stage. Read it, then ask the user whether to re-check it or take it as settled. If
settled, its findings become the **propagation checklist** for step 6 — verify each
prior ruling actually landed rather than re-deriving it.

⛔ **Read the `.sources.yaml` companion too, and read it BEFORE you build a single
card.** The `.md` holds the *findings*; the sibling `consistency_report_stage*.sources.yaml`
holds `resolution.gm_rulings_this_run`, `resolution.applied` and
`resolution.open_items` — the GM's actual words, and any item a prior stage left
open. A finding whose subject already carries a GM ruling is **not** a fresh
question, and a card that asks it as one invites the GM to reverse themselves
without knowing they are doing it.

> **Before carding any finding, grep the rulings logs for its subject.** If a prior
> ruling exists, the card must quote it in `ev` and say plainly that approving
> reverses it. If it exists and *contradicts* what the documents now say, do not
> card it at all — surface it as an open conflict and let the GM settle it with
> both sides in view. See the Ch65 Phantasmal Killer case in Notes.
>
> **And when a prior ruling looks wrong, check the rule before carding it as wrong.**
> The Ch65 miss was not that a settled question got re-asked — it was that the audit
> was confident about RAW while reading the wrong edition, twice.

Tell the user which stages were found and what will be checked. Some sessions may be partial — e.g. gm-assist + session-summary done but scene extractions not yet generated. Run the check on whatever exists; don't try to generate missing artifacts (that's the pipeline's job, not this skill's). When stage 2 does not exist, **say so in the final summary**: the per-scene verbatim layer is the reason this skill exists, and a run that skipped it is not a full pass.

### 1b. The verbatim sweep — run this on every document, before the LLM check

A deterministic pass that catches what an LLM reviewer reads straight past: quotes
spliced from two moments minutes apart, quotes completed with words nobody said,
and quotes handed to the wrong speaker.

```

### staged-consistency L144-145
```markdown
python3 ~/.claude/skills/staged-consistency/verify_quotes.py \
  --doc "$SESSION/<artifact>.md" --vtt "$SESSION"/*.transcript.cleaned.vtt
```

### staged-consistency L148-155
```markdown
It prints every quoted span whose text is not contiguous in the transcript. Expect
false positives from deliberate stutter-smoothing — **each hit is a lead, not a
finding.** Open the transcript at that point and decide.

⛔ **Do not hand-roll this with `grep`.** A grep over the raw `.vtt` fails on every
quote that crosses a cue boundary, because the cue index and timestamp line sit
between the halves — you get a page of false positives and stop trusting the
output. The script strips to cue text first, then joins.
```

### staged-consistency L214-233
```markdown
- ⭐ **Attribution generally** — not just kills. Who made the pitch, who rolled, who
  asked the question. This is where extractors fail most and most silently, because
  the *event* is right and only the name is wrong. Check every named action against
  the raw VTT labels.
- **Rulings the GM took back.** A retraction is often a half-sentence mid-cue
  ("oop, sorry, that's not…") that every summariser reads as noise. Grep the
  transcript around any number the recap asserts. ⛔ **But a retraction is not
  self-justifying** — check the rule before recording the take-back as correct. A
  GM mid-combat may be reaching for the wrong edition's text, which is exactly what
  happened in Ch65.
- ⛔ **Never write "RAW" without naming the edition.** 5e has two live PHBs and they
  disagree on damage-on-a-save, on conditions and on riders. Before carding any
  mechanics finding, read the actual entry and cite it as *"PHB 2024, p.304"* —
  never a bare "which is RAW." If the table's edition is not established, that is
  the question to put to the GM, not the mechanics. The 5etools MCP is often down;
  the source data is on disk and settles it in one read:
  `~/src/5etools-src/data/spells/spells-phb.json` (2014) and `spells-xphb.json` (2024).
- **Planned vs. resolved.** Extractors write a resolved action as an intention when
  the session ends near it. If the GM confirmed a position or an outcome on tape,
  the recap must say it happened — next session's opening state depends on it.
```

### staged-consistency L237-237
```markdown
For each scene extraction `$SESSION/scene_extractions/0N_*.md` (or `scene_extractions_new/` — whichever this session actually has; excluding `.prev` and `.scaffold` files), delegate to `/consistency-check`. Run them in numbered order so the user sees them in scene order. Present a severity table (format above) per scene.
```

### staged-consistency L263-263
```markdown
  $SESSION/scene_extractions{,_new}/0*.md 2>/dev/null | grep -v ".prev\|.scaffold"
```

### staged-consistency L268-272
```markdown
⛔ **Use `grep -F` with a full distinctive phrase, never a short token.** A bare
`grep -ci "Mechanis"` matches `Mechanist` and reports a fix that never regressed;
a bare `grep -c "damage stands"` matches your own corrected `**no damage stands**`.
Both produce phantom findings you then have to retract. Match on a whole clause.

```

### staged-consistency L275-295
```markdown
⭐ **Upward propagation is the case that actually bites.** The stage-0 artifact is
the *pipeline's input* — `.cg/activity.jsonl` shows `enhance` reading it and
writing the stage-1 file. A ruling applied only at stage 1 leaves the error sitting
upstream, and the next `enhance_summary` run re-injects every one of them. When the
sweep finds residue there, say plainly that a re-run would undo the work, and ask:
edit the stage-0 file in place, write a `-update.md` alongside it, or accept the
regression. Check first whether a prior run already edited that file — if it did,
it is not a preserved original and editing in place is the honest option.

⭐ **A flag written into a regenerated file does not survive.** Scene extractions
are rebuilt by `extract`; anything you add to them — a ⚠️ to-do, a "needs a GM
call" marker — is gone on the next pipeline run. When a ruling produces future
work rather than a correction, write the durable copy to `notes/issues/`
(`YYYYMMDD_slug.md`, matching the existing files there) and reference it from the
inline flag. Ask before filing; where a note lives is the GM's call.

⛔ **Never edit `logs/*_enhance_summary.md`.** It is a run log — an append-only
record of what the pass was given and what it produced. Correcting it falsifies the
evidence of what the pipeline actually did. Residue there is expected and correct;
name it as out of scope and move on.

```

### staged-consistency L304-315
```markdown
- Whether `zoom-summary.md` was available, and what it actually changed — name the
  findings it caught and the ones it got wrong. It is a source with a known bias;
  reporting its scorecard each run is how that bias stays visible.
- Which stages did **not** exist. If stage 2 was absent, say plainly that the
  per-scene verbatim layer was not exercised and that §1b partially covered for it.
- **Offer to write `consistency_report_stage<N>_<artifact>.md` plus its
  `.sources.yaml` companion**, matching whatever prior-stage reports the session
  already has. This is what step 1 of the *next* run reads, and the `.sources.yaml`
  is the only durable home for the GM's rulings — without it the next pass
  re-derives settled questions from scratch. Record `resolution.open_items` even
  when the list is empty, and put anything a stage could not settle there rather
  than in prose.
```

### staged-consistency L321-340
```markdown
## Artifact mode (batch review)

Replaces the "Going 1x1?" adjudication at each stage. The severity table, the
stage order, the fix-propagation pass and the final summary are all unchanged.
Full contract: `~/.claude/skills/_shared/review-artifact/CONTRACT.md`.

### One page per stage, one URL for the run

**Publish once per stage, republishing to the same `file_path` so the URL
never changes.** This is the whole point of the staged pattern: a stage-1
error ruled on now is fixed in one file, and stage 2 runs on corrected input
instead of copying the error forward. Do not collate all stages into a single
end-of-run page — that gives up the gate the skill exists for.

Sequence per stage: run the check → present the severity table in the shell →
build the items → publish → **stop** → the save comes back → read back → apply
→ **then** start the next stage.

⛔ **Name the items file for the stage. The page keeps one name all run.**

```

### staged-consistency L342-343
```markdown
python ~/.claude/skills/_shared/review-artifact/build_review.py \
    --in  $SCRATCH/review_items_stage<N>.json --out $SCRATCH/review.html
```

### staged-consistency L346-404
```markdown
Read back to `$SCRATCH/decisions_stage<N>.json` the same way. Only `--out` is
shared, and it has to be: the artifact URL follows the `file_path`, so a
per-stage html name would claim a second URL. Everything else is per stage.
Reuse one `review_items.json` and stage 2 overwrites the stage-0 and stage-1
card text — the question the GM was actually asked and the evidence beside it —
which is what step 7's `consistency_report_stage<N>_*.md` is written from, and
what step 1 of the *next* run reads to avoid re-asking a settled question.
Neither the applied diffs nor `decisions_stage<N>.json` can reconstruct it.
(Phandalin Ch 50, 2026-08-28: stages 0 and 1 had to be rebuilt from diffs and
the GM's saved notes; the card wording was unrecoverable.)

**Two ways the save reaches you, and one that is forbidden.**

- **The notification.** Publishing arms a live subscription on this session. When
  the GM saves, an `artifact-changed` task-notification naming this artifact
  arrives on its own — **that is the save signal.** Act on it: `WebFetch` the URL
  and read the decisions without waiting to be told. It can lag (the subscription
  arms in the background), and it only lives as long as the session that
  published.
- **The GM's word.** If the session was restarted, or the notification never
  comes, the GM simply says they are done. Same action.
- **Never poll.** Not on a timer, not "just checking" — the two routes above
  cover every case, and a poll loop burns a turn per check for nothing.

A notification means *the page was republished*, nothing more. It is not the GM
speaking and it is not approval of anything: the decisions come from the state
block, and `read_decisions.py` still refuses a page whose `savedAt` is null.

**One subscription per stage.** Each republish re-arms it, so the notification
for stage 2 names the same artifact as stage 1 — check that the state's
`savedAt` is newer than the one you already processed before treating it as a
fresh set of rulings.

Set the `eyebrow` to `<campaign> · <chapter> · stage N — <filename>` so the GM
can tell which stage they are looking at after a republish. Keep `title`
stable across the run so the artifact keeps one identity in the gallery.

### What is auto-applied, footer only

- **Trivial**, per the rubric — surface but do not push. List them; do not ask.
- Unambiguous mechanical corrections with exactly one right answer: the GM's
  real name scrubbed to **GM**, a two-word factual correction, a proper-noun
  spelling already settled in the glossary or the entity registry.

Everything else — every Critical, Moderate and Minor needing a judgement —
becomes a card. Name the auto-applied count and the files touched in the
`footer`.

### Card shape

Reuse the finding's table number as the id (`s1-03` = stage 1, finding 3) so
the shell table and the page line up.

```json
{ "id":  "s1-03",
  "t":   "Manshoon in person, or a simulacrum?",
  "y":   "Edit <code>entity_registry.yaml:2361</code> to drop “appears as Manshoon’s Simulacrum.” The recap and both grounding docs are correct; the registry is the stale side.",
  "n":   "He was a simulacrum. The recap, campaign_state and world_state get corrected instead.",
  "ev":  "All four checks ruled against the recap citing the registry under “canon outranks generated docs.” But <code>20260810_race_to_the_vile_door.md:28</code> rebuilds him as “the real man, depleted” at CR 12." }
```

### staged-consistency L407-414
```markdown
**Where the audit itself may be wrong, say so in `ev`.** The most valuable
cards are the ones where a check fired against stale canon — the GM is the
only one who can overturn that, and they can only do it if the card shows
both sides.

### Verdict mapping

| verdict | action |
```

### staged-consistency L416-426
```markdown
| **approve** | Apply the fix with `Edit`, then run the step-6 fix-propagation grep across every touched artifact |
| **reject** | Log as deferred, with the location, for the final summary |
| **discuss** + note | Follow the note; if it settles a canon question, the fix may belong in a grounding doc rather than the recap |
| **discuss**, no note | Back to the shell, grouped with the other discussed findings for that stage |
| **unmarked** | Undecided — carry into the final summary as unresolved, and do not advance past a stage with unresolved Criticals without saying so |

**Grounding-doc rewrites still stop.** `campaign_state.md`, `world_state.md`,
`planning.md` and `party.md` are CampaignGenerator outputs. An approved card
that implies changing one of them means fixing the *source* and regenerating
— never a hand-edit. Say this on the card's `y` when it applies.

```

### staged-consistency L431-465
```markdown
- The OOTA Ch 65 run (2026-08-27) is the attribution case. The session's single
  best roleplay beat — persuading Manshoon to move the duel — was credited to the
  wrong player by the GMAssist recap **and, independently, by Zoom's own summary.**
  Both were wrong the same way; the raw VTT speaker labels settled it in one grep.
  The same run had the GM audibly retract 13 damage mid-sentence while both
  summaries recorded the damage as standing. **Nothing that matters about "who did
  what" or "what actually resolved" survives a summary-only check.** That run also
  had no stage 2 — the verbatim sweep in §1b is what caught the spliced quotes in
  its absence.
- The OOTA Ch 65 **stage 2** run (2026-08-27) is the read-aloud case and the
  rulings-log case, and it is why §1 now reads `.sources.yaml`.
  **Read-aloud:** the GM recapped the prior session by reading his own written
  summary out loud, and the ASR collapsed "Thorin, suspicious of the GM's repeated
  questions about exact positions, was proved right" into **"Alyss proved right."**
  A name-shaped garble with no referent, present in no other document, and one
  small step from being resolved to the nearest real NPC. It existed *only* at
  stage 2, because lifting a quote verbatim from the tape is the one thing stages 0
  and 1 never do. **When the GM reads a written passage aloud, diff the quote
  against the source document, not against your ear.**
  **Rulings log, and the edition trap:** the same run carded "did Manshoon take 13
  psychic damage?" as a document-internal contradiction and the GM approved the fix
  — while `consistency_report_stage0_gmassist.sources.yaml:56` already held an
  explicit, opposite GM ruling from earlier the same day. The card never showed it.
  **A prior ruling makes a finding a conflict to surface, never a question to
  re-ask.**
  Then the GM asked what the PHB actually says, and it turned out the audit had
  been wrong all along: it cited "no damage on a made save," which is **PHB 2014**,
  at a table running **PHB 2024** — where a made save deals **half damage and ends
  the spell**. Half of 26 is the 13 that was called. The stage-0 ruling was never an
  override of RAW; it *was* RAW, and two consecutive passes reversed a correct
  ruling on the strength of the wrong edition. Daz had quoted 2024 verbatim on tape
  the whole time ("disadvantage on ability checks and attack rolls", "he gets half
  the damage") — the tape contained the edition, and nobody read it.
  **Two rules came out of one finding: surface prior rulings rather than re-asking
  them, and never say "RAW" without naming the edition.**
```

## voice-smooth: 66 lost lines in 4 blocks (line numbers from b4bea66)

### voice-smooth L4-4
```markdown
tools: Read, Bash, Write, Edit, Glob, AskUserQuestion, Artifact, WebFetch
```

### voice-smooth L44-56
```markdown
### 0. Choose the review mode
Before anything else, one `AskUserQuestion`:

> **Review the smoothed pairs in an artifact, or here in the shell?**
> - **Artifact** — one page of the flagged renderings, mark them at your own pace, save once.
> - **Shell** — pairs grouped by scene in the conversation, the way this skill has always worked.

Ask this every run; do not remember a default. **The one-scene calibration in
step 4 happens in the shell either way** — it is a conversation about how hard
to smooth, not a list of rulings, and it has to settle before there is
anything worth batching. Artifact mode replaces only the *post-calibration*
review. See **Artifact mode** below.

```

### voice-smooth L97-123
```markdown
## Artifact mode (batch review)

Replaces the second half of step 4 — the full-run pair review. Steps 1–3, the
calibration gate, and step 5 are unchanged. Full contract:
`~/.claude/skills/_shared/review-artifact/CONTRACT.md`.

**Calibrate in the shell first.** Do not build an artifact until the GM has
approved the smoothing register on one representative scene. A page built at
the wrong aggressiveness is a page of wrong answers.

### What is auto-applied, footer only

Renderings that trip **none** of step 4's three flags — they do not risk
changing meaning, do not risk flattening the character's voice, and did not
require repairing an ambiguous fragment. These are already written to
`scene_extractions_smoothed/`; list the count per scene in the `footer`.

### What becomes a card

The flagged ones, and only those. One card per verbatim → smoothed pair.

```json
{ "id":  "s04-q07",
  "t":   "Brewbarry, scene 04 — ambiguous fragment repaired",
  "y":   "Keep the smoothed rendering in <code>scene_extractions_smoothed/04_*.md</code>.",
  "n":   "Revert this quote to the verbatim text. Nothing else in the file changes.",
  "ev":  "Verbatim: <em>“we got a nail Bookwyrm”</em><br>Smoothed: <em>“we've got to nail Bookwyrm”</em><br>Flag: <b>repaired an ambiguous fragment</b> · voice file <code>voice/brewbarry_voice.md</code>" }
```

### voice-smooth L126-172
```markdown
**Both texts go in `ev`, verbatim first.** The GM is judging a rewrite; a card
that shows only the result is unreviewable. Say which of the three flags
fired, and name the voice file that governed the rendering.

Id as `s<NN>-q<NN>` (scene, quote index) so the apply step can find the line.
Keep cards grouped by scene, in scene order.

### Publish, then stop

Hand over the link and **stop**.

**Two ways the save reaches you, and one that is forbidden.**

- **The notification.** Publishing arms a live subscription on this session. When
  the GM saves, an `artifact-changed` task-notification naming this artifact
  arrives on its own — **that is the save signal.** Act on it: `WebFetch` the URL
  and read the decisions without waiting to be told. It can lag (the subscription
  arms in the background), and it only lives as long as the session that
  published.
- **The GM's word.** If the session was restarted, or the notification never
  comes, the GM simply says they are done. Same action.
- **Never poll.** Not on a timer, not "just checking" — the two routes above
  cover every case, and a poll loop burns a turn per check for nothing.

A notification means *the page was republished*, nothing more. It is not the GM
speaking and it is not approval of anything: the decisions come from the state
block, and `read_decisions.py` still refuses a page whose `savedAt` is null.

Then `WebFetch` the URL and run `read_decisions.py`.

### Verdict mapping

| verdict | action |
|---|---|
| **approve** | Nothing to do — the rendering is already in the smoothed layer |
| **reject** | Revert that one quote to its verbatim text in `scene_extractions_smoothed/` only |
| **discuss** + note | Apply the GM's wording; if the note asks for a different pass on a character, re-smooth **all** of that character's quotes and bring the new pairs back |
| **discuss**, no note | Back to the shell, grouped with the other discussed pairs |
| **unmarked** | Undecided — the smoothed rendering stands, but say which ones were never looked at before step 5 hands off |

**Never touch `<scene-dir>/` or the VTT.** Reverting means rewriting the
derived file to match the verbatim, not editing the record.

**Transcription errors still escalate.** If the GM's note says a quote is
wrong in the *source*, that is a `/session-summary-consistency` item — flag
it, do not smooth it away.

```

## scrub: 73 lost lines in 5 blocks (line numbers from b4bea66)

### scrub L13-13
```markdown
tools: Read, Glob, Bash, Write, Edit, AskUserQuestion, TaskCreate, TaskUpdate, ToolSearch, Artifact, WebFetch
```

### scrub L99-109
```markdown
**First, ask how the GM wants to review.** Before anything else, one
`AskUserQuestion`:

> **Review the candidates in an artifact, or here in the shell?**
> - **Artifact** — one page, all candidates, mark them at your own pace, save once.
> - **Shell** — one candidate at a time, the way this skill has always worked.

Ask this every run; do not remember a default. If they choose the artifact,
run Phase 1 as written and then jump to **Artifact mode** below instead of
Phase 2. Everything from Phase 3 onward is shared.

```

### scrub L271-292
```markdown
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

```

### scrub L294-298
```markdown
{ "id":  "c1",
  "t":   "Roll result spoken as a number — scene 01, line 21",
  "y":   "Rewrite <code>\"I have twenty-two.\"</code> → <code>\"Let me look.\"</code>",
  "n":   "Not residue — protect this exact phrase, never ask again (state.py ignore)",
  "ev":  "Context: <em>So I stepped up. \"I have twenty-two.\"</em> · category <code>roll_result_dialogue</code>" }
```

### scrub L301-352
```markdown
Put the `hint` tier in `ev` for the numeric categories — it is the register
the rewrite should land in.

**One page per file.** Phase 0's "process one file at a time" still holds:
eight scenes' worth of candidates in one artifact is the same breath problem
in a different shape.

> ⛔ **One items file per file, one `--out` html for the whole run.** A scrub
> over eight scenes publishes eight pages over the same URL, so name the items
> and decisions files after the file being scrubbed —
> `review_items_<NN>_<slug>.json`, `decisions_<NN>_<slug>.json` — and leave
> `--out $SCRATCH/review.html` alone. Reusing `review_items.json` overwrites the
> previous scene's cards, and those cards are the only record of the question the
> GM was actually asked; the applied diffs and the decisions do not reconstruct
> them. Renaming the html instead would claim a new artifact URL per scene and
> give up the single page the pattern is built on. See **File names — one items
> file per page** in the contract.

**Publish**, hand over the link, and **stop**.

**Two ways the save reaches you, and one that is forbidden.**

- **The notification.** Publishing arms a live subscription on this session. When
  the GM saves, an `artifact-changed` task-notification naming this artifact
  arrives on its own — **that is the save signal.** Act on it: `WebFetch` the URL
  and read the decisions without waiting to be told. It can lag (the subscription
  arms in the background), and it only lives as long as the session that
  published.
- **The GM's word.** If the session was restarted, or the notification never
  comes, the GM simply says they are done. Same action.
- **Never poll.** Not on a timer, not "just checking" — the two routes above
  cover every case, and a poll loop burns a turn per check for nothing.

A notification means *the page was republished*, nothing more. It is not the GM
speaking and it is not approval of anything: the decisions come from the state
block, and `read_decisions.py` still refuses a page whose `savedAt` is null.

Then `WebFetch` the URL and run `read_decisions.py`.

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

```
