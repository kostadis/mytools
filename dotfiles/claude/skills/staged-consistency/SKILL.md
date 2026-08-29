---
name: staged-consistency
description: Run consistency checks at every LLM-pipeline boundary (gm-assist → session-summary → scene extractions → narration) with a human-review gate between stages. Use when the user invokes /staged-consistency [session-dir] and wants the multi-stage check rather than a one-shot. Prevents fix-propagation drift where stale per-scene quotes silently re-inject errors into the next narration run.
tools: Bash, Read, Edit, AskUserQuestion, Artifact, WebFetch
---

# Staged Consistency

Run the multi-stage consistency check pattern documented in `~/campaigns/STAGED_CONSISTENCY_HOWTO.md`. The pattern: a `check_consistency.py` run gated by a human-review/fix cycle at each LLM extraction boundary in the session-doc pipeline — gm-assist, session-summary, scene extractions, and (optionally) the final narration.

The point of this skill is to **catch verbatim transcription errors before they reach the narrator**. A single late-stage check misses the per-scene-quote layer, which is the layer that silently re-injects errors into every subsequent narration run. See `STAGED_CONSISTENCY_HOWTO.md` for the rationale.

## When to use this skill vs. the others

- `/consistency-check <file>` — one-shot check on a single file. Use when you already know which document needs checking.
- `/gmassist-precheck [session-dir]` — covers stage 0 → stage 1 only (gm-assist enrichment + check). Use when you only want the cheap pre-extraction pass.
- `/staged-consistency [session-dir]` — **this skill**. The full pipeline with checks at every boundary. Use when you're preparing a session-doc you'll share with players, or when a prior narration run produced output that doesn't match prep.

## Workflow

### 0a. Choose the review mode

Before locating anything, one `AskUserQuestion`:

> **Review each stage's findings in an artifact, or here in the shell?**
> - **Artifact** — one page per stage at a single URL, mark the rulings at your own pace, save once per stage.
> - **Shell** — the severity table and "Going 1x1?", the way this skill has always worked.

Ask this every run; do not remember a default. In artifact mode the severity
table is still presented in the shell — it is the at-a-glance summary — but
the *rulings* move to the page. See **Artifact mode** below.

### 0. Locate the session directory and prep

If the user passed a path argument, use it. Otherwise:
- Run `pwd` to confirm CWD is a campaign workspace (contains `docs/`, `summaries/`, `config.yaml`).
- List recent session directories: `ls -t summaries/ | head -10`
- Ask: "Which session — pass the path under `summaries/` (e.g. `summaries/20260512`)?"

Then locate the prep file(s) for this session — this is non-negotiable, the same as in `/consistency-check`:

1. Look in `notes/session_prep/`, `notes/prep/`, `notes/sessions/`, `notes/<date>/`.
2. List candidates: `ls notes/session_prep/ 2>/dev/null; ls notes/prep/ 2>/dev/null`
3. **Ask the user explicitly**: "Which session prep file(s) should I fact-check against? Found: [list]. Or pass `none` if there is no prep for this session."

If the user says `none`, run the skill anyway but explicitly note in the final summary that the run was prep-less and will have missed transcription errors. Do not silently proceed without asking.

Hold the prep path list in the conversation — every stage's check uses it.

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

### 1. Inventory the pipeline artifacts in this session

Determine which stages exist:

```bash
SESSION=<session-dir>
ls "$SESSION"/gm-assist.md 2>/dev/null
ls "$SESSION"/session-summary.md 2>/dev/null
ls "$SESSION"/scene_extractions{,_new}/0*.md 2>/dev/null | grep -v ".prev\|.scaffold"
ls "$SESSION"/narration/enhanced_sections.md 2>/dev/null
ls "$SESSION"/narration/*.md 2>/dev/null   # final narration if generated

# and the three things that tell you what already ran, and from what:
cat  "$SESSION"/.cg/activity.jsonl 2>/dev/null      # stage, rc, and the OUTPUT paths
ls   "$SESSION"/consistency_report_stage*.md 2>/dev/null
cat  "$SESSION"/consistency_report_stage*.sources.yaml 2>/dev/null   # <- the RULINGS live here
ls   "$SESSION"/logs/*_enhance_summary.md 2>/dev/null
```

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

```bash
python3 ~/.claude/skills/staged-consistency/verify_quotes.py \
  --doc "$SESSION/<artifact>.md" --vtt "$SESSION"/*.transcript.cleaned.vtt
```

It prints every quoted span whose text is not contiguous in the transcript. Expect
false positives from deliberate stutter-smoothing — **each hit is a lead, not a
finding.** Open the transcript at that point and decide.

⛔ **Do not hand-roll this with `grep`.** A grep over the raw `.vtt` fails on every
quote that crosses a cue boundary, because the cue index and timestamp line sit
between the halves — you get a page of false positives and stop trusting the
output. The script strips to cue text first, then joins.

## Report format (mandatory at every stage)

After each stage's check, **always** present findings as a severity-ranked table before asking about fixes:

```
● Stage N complete — M issues in <filename>. Going 1x1?

  Quick preview:

  ┌─────┬──────────┬──────────────────────────────────────────────────────┐
  │  #  │ Severity │                        Issue                         │
  ├─────┼──────────┼──────────────────────────────────────────────────────┤
  │ 1   │ Critical │ <one-line description>                               │
  │ 2   │ Moderate │ <one-line description>                               │
  │ 3   │ Minor    │ <one-line description>                               │
  │ 4   │ Trivial  │ <one-line description>                               │
  └─────┴──────────┴──────────────────────────────────────────────────────┘
```

**Severity rubric:**

| Level | Meaning |
|---|---|
| **Critical** | Contradicts established canon (NPC fates, event timing, faction state, established mechanics); would cause player confusion or DM embarrassment if it reaches narration. Must fix before narrating. |
| **Moderate** | Framing drift — what happened is right but characterised wrongly; wrong kill attribution; characterisation that conflicts with the voice file; missing context that changes meaning. Should fix before narrating. |
| **Minor** | Misspelling of a proper noun, wrong pronoun, single-word transcription error, inconsistency within the same document. Easy to fix; fix before narrating. |
| **Trivial** | Stylistic quirk, table-chatter artifact, item you flagged as "leave as-is" in a prior stage, or flavour call that is defensible either way. Surface but do not push. |

Sort the table by severity (Critical first, then Moderate, Minor, Trivial). Number issues sequentially across the whole table. If there are zero issues, say so in one line and advance automatically to the next stage.

### 2. Stage 0 — gm-assist check

Delegate to `/consistency-check`:

> Stage 0 — running `/consistency-check $SESSION/gm-assist.md` with prep as context.

Invoke the consistency-check skill workflow against `$SESSION/gm-assist.md`, passing `docs/party.md` and all prep files via `--context`. After it returns:

- Present the severity table (format above).
- Ask: "Apply any of these fixes to `gm-assist.md` before moving to stage 1?"
- If yes, edit `gm-assist.md` directly. If no, log what was deferred so it can be revisited.

**Important caveat about gm-assist.md**: this file may be the user's preserved-original artifact (paired with a `gm-assist-update.md` next to it). If a `gm-assist-update.md` exists, ask the user whether to check that file instead and treat it as the canonical first-pass artifact. The convention is "original preserved, corrected version alongside" — apply fixes to the `-update.md` if present, otherwise the original.

### 3. Stage 1 — session-summary check

Delegate to `/consistency-check`:

> Stage 1 — running `/consistency-check $SESSION/session-summary.md` with prep as context.

Same flow: invoke `/consistency-check`, present the severity table (format above), ask about applying fixes, edit if approved.

Pay particular attention at this stage to:
- **Cross-section contradictions** (Summary prose vs. bulleted scene log)
- **Pronoun drift** on player characters
- **NPC affiliation fabrications** (the canonical Phandalin example: Prutha "committed to the Order of the Gauntlet" — party.md says Lathander convert)
- **Killing-blow attribution** in combat scenes (LLM extractors often credit the wrong character)
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

### 4. Stage 2 — scene extractions check (the load-bearing one)

For each scene extraction `$SESSION/scene_extractions/0N_*.md` (or `scene_extractions_new/` — whichever this session actually has; excluding `.prev` and `.scaffold` files), delegate to `/consistency-check`. Run them in numbered order so the user sees them in scene order. Present a severity table (format above) per scene.

This stage exists because **the scene extractions contain the verbatim quotes the narrator reads literally**. Fixes applied only at the session-summary layer get silently undone the next time the narrator runs.

When applying fixes to verbatim quotes:
- **Preserve the speaker attribution and tone** of the original quote when correcting transcription drift — the players' table voice is the whole point of these quotes.
- **Add an italic editorial note** in the speaker attribution explaining the discrepancy between raw Otter/Zoom capture and prep canon. Future readers (and the next narrator pass) get a transparent audit trail.
  - Example: `**GM** — *voicing Prutha (transcript per session-prep canon; raw Otter capture said "my uncle Seidan comes for everyone" — a mishearing of "great-uncle said dawn")*`
- **Do not strip table chatter, jokes, or player improvisations** that the table values. Some "errors" the check flags are intentional flavor. The Phandalin "blacklist" / "blood money list" terminology is real OOC table vocabulary — preserve those.

After each scene's fixes, ask: "Continue to next scene, or revisit this one?" Don't auto-advance through all scenes silently.

### 5. Stage 3 — narration check (optional)

If a final narration file exists (typically `$SESSION/narration/<something>.md` or the session_doc output), delegate to `/consistency-check` on it. Present a severity table (format above).

At this stage the check is mostly catching narrator-layer voice drift and prose fabrications. Findings here are usually candidates for a narrator re-run (after fixing upstream) rather than direct edits, since editing final prose tends to fight the narrator's voice.

### 6. Fix-propagation pass

After all stages have been checked and fixed, do a quick propagation sweep — fixes applied to a deep stage may need to propagate upward, and fixes at a shallow stage may need to propagate downward. Use grep to verify:

```bash
# Grep all touched files for residual bad patterns
grep -n "<bad pattern>" $SESSION/gm-assist.md $SESSION/gm-assist-update.md \
  $SESSION/session-summary.md $SESSION/narration/enhanced_sections.md \
  $SESSION/scene_extractions{,_new}/0*.md 2>/dev/null | grep -v ".prev\|.scaffold"
```

Where "<bad pattern>" is the specific text that was wrong (e.g. `"bear comes"`, `"Order of the Gauntlet"`, `"Elemental Cleaver"`). Run this for every fix that was applied.

⛔ **Use `grep -F` with a full distinctive phrase, never a short token.** A bare
`grep -ci "Mechanis"` matches `Mechanist` and reports a fix that never regressed;
a bare `grep -c "damage stands"` matches your own corrected `**no damage stands**`.
Both produce phantom findings you then have to retract. Match on a whole clause.

If grep finds the bad pattern in a file that wasn't checked or fixed, surface it to the user and ask whether to apply the corresponding fix there. **This propagation step is what catches the scenario where session-summary was fixed but the scene extractions still carry the original error.**

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

### 7. Final summary

End with a tight summary:

- Stages run, issue counts per stage
- Fixes applied per stage
- Anything deferred (with the location)
- Whether prep was available (or whether the run was prep-less and possibly blind to transcription errors)
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
- Recommendation on next action — usually one of:
  - "Re-run `session_doc.py` to produce a clean narration from the corrected scene extractions"
  - "Ready to share session-doc with players"
  - "Stage X still has unresolved issues — revisit those before narrating"

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

```bash
python ~/.claude/skills/_shared/review-artifact/build_review.py \
    --in  $SCRATCH/review_items_stage<N>.json --out $SCRATCH/review.html
```

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

**Where the audit itself may be wrong, say so in `ev`.** The most valuable
cards are the ones where a check fired against stale canon — the GM is the
only one who can overturn that, and they can only do it if the card shows
both sides.

### Verdict mapping

| verdict | action |
|---|---|
| **approve** | Apply the fix with `Edit`, then run the step-6 fix-propagation grep across every touched artifact |
| **reject** | Log as deferred, with the location, for the final summary |
| **discuss** + note | Follow the note; if it settles a canon question, the fix may belong in a grounding doc rather than the recap |
| **discuss**, no note | Back to the shell, grouped with the other discussed findings for that stage |
| **unmarked** | Undecided — carry into the final summary as unresolved, and do not advance past a stage with unresolved Criticals without saying so |

**Grounding-doc rewrites still stop.** `campaign_state.md`, `world_state.md`,
`planning.md` and `party.md` are CampaignGenerator outputs. An approved card
that implies changing one of them means fixing the *source* and regenerating
— never a hand-edit. Say this on the card's `y` when it applies.

## Notes

- This skill is intentionally heavy. It exists for sessions that matter — chapter releases, sessions you're sharing externally, sessions where you've already produced a bad narration and need to root out why. For a quick sanity check on a single document, use `/consistency-check` directly.
- Skipping the prep step (step 0) collapses the value of this skill the same way it collapses `/consistency-check`. The whole reason this pattern beats a one-shot check is that prep is wired into every stage's check. Do not skip.
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
- The Phandalin Ch 41 run (2026-05-17) was the discovery case — 11 prep-canonical issues survived a late-stage one-shot check that returned "no major issues." The same issues were trivially catchable at stage 0 with prep wired in. That's the failure mode this skill exists to prevent.
- See `~/campaigns/STAGED_CONSISTENCY_HOWTO.md` for the methodology rationale, the pipeline diagram, and the per-stage table of what each check catches that the others miss.
