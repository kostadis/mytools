---
name: staged-consistency
description: Run consistency checks at every LLM-pipeline boundary (gm-assist → session-summary → scene extractions → narration) with a human-review gate between stages. Use when the user invokes /staged-consistency [session-dir] and wants the multi-stage check rather than a one-shot. Prevents fix-propagation drift where stale per-scene quotes silently re-inject errors into the next narration run.
tools: Bash, Read, Write, Edit, Glob, AskUserQuestion, Artifact, WebFetch
---

# Staged Consistency

Run the multi-stage consistency check pattern documented in `~/campaigns/STAGED_CONSISTENCY_HOWTO.md`. The pattern: a `check_consistency.py` run gated by a human-review/fix cycle at each LLM extraction boundary in the session-doc pipeline — gm-assist, session-summary, scene extractions, and (optionally) the final narration.

The point of this skill is to **catch verbatim transcription errors before they reach the narrator**. A single late-stage check misses the per-scene-quote layer, which is the layer that silently re-injects errors into every subsequent narration run. See `STAGED_CONSISTENCY_HOWTO.md` for the rationale.

## This skill is an orchestrator, not a second implementation

Every stage below runs the **full `/consistency-check` workflow**. That skill owns the method — context selection, the script's failure modes, VTT adjudication, the triage rules, the manifest. This skill owns only the *staging*: which artifact, in what order, with a human gate between each.

**Do not shortcut the delegated workflow.** In particular these `/consistency-check` steps are REQUIRED and apply at every stage:

| Step | What it is | Why staging makes it more important, not less |
|---|---|---|
| 2 | Config resolution | The only valid config is `<campaign>/config/config.yaml`, always passed with `--config`; anything else is a STOP. Get it wrong once and every stage fails, or checks the wrong campaign. |
| 2.5 | Prep discovery + tiered choice | Prep is what catches transcription errors — the entire reason this skill exists. |
| 3 | Campaign-standard context set | See below. Staged runs it N+3 times; a dropped source is dropped N+3 times. |
| 4.7 | VTT adjudication | Stage 2 is *made of* verbatim quotes. The grounding docs are structurally blind to them; only the tape settles a quote. |
| 4.5 + 6 | YAML manifest (sources + rulings) | With many stages, the manifest is the only record of what was ruled where. |

Read `/consistency-check`'s SKILL.md before the first stage and keep its guidance in play throughout. When it and this file disagree on *method*, `/consistency-check` wins; this file only overrides on *sequencing*.

## When to use this skill vs. the others

- `/consistency-check <file>` — one-shot check on a single file. Use when you already know which document needs checking.
- `/gmassist-precheck [session-dir]` — covers stage 0 → stage 1 only (gm-assist enrichment + check). Use when you only want the cheap pre-extraction pass.
- `/staged-consistency [session-dir]` — **this skill**. The full pipeline with checks at every boundary. Use when you're preparing a session-doc you'll share with players, or when a prior narration run produced output that doesn't match prep.
- `/session-doc-run [session-dir]` — the *runner*, not a checker. Use it when the inventory in step 1 finds the artifacts don't exist yet; it produces them stage by stage, then hand back here.

## Workflow

### 0a. Choose the review mode

Before locating anything, one `AskUserQuestion`:

> **Review each stage's findings in an artifact, or here in the shell?**
> - **Artifact** — one page per stage at a single URL, mark the rulings at your own pace, save once per stage.
> - **Shell** — the severity table and "Going 1x1?", the way this skill has always worked.

Ask this every run; do not remember a default. In artifact mode the severity
table is still presented in the shell — it is the at-a-glance summary — but
the *rulings* move to the page. See **Artifact mode** below. At Stage 2 this is
also the grouped-vs-per-scene choice (step 4), which is why it is settled before
anything runs.

### 0. Locate the session directory, the script, and the context set

If the user passed a path argument, use it. Otherwise:
- Run `pwd` to confirm CWD is a campaign workspace (contains `docs/`, `summaries/`, `config/config.yaml`).
- List recent session directories: `ls -t summaries/ | head -10`
- Ask: "Which session — pass the path under `summaries/` (e.g. `summaries/20260512`)?"

**Locate the script; don't assume the path.** It lives at `<repo>/session_doc/check_consistency.py` (it moved out of the repo root), and the repo may be `~/CampaignGenerator` **or** `~/src/CampaignGenerator`. There is also an installed console script, `check_consistency`. `ls` before building any command.

**Resolve config once, here.** Run `/consistency-check` step 2's preflight and pass `--config <abs campaign>/config/config.yaml` at every stage. A misplaced config, unresolvable document paths or a missing registry is a STOP to report, never something to work around. Settle this before stage 0 — a config mistake repeated across every stage is the most expensive error this skill can make.

#### Prep discovery — delegate to `/consistency-check` step 2.5, do not use a shortened version

Run that step's **full** sweep, not a two-directory `ls`. It is date-bounded (an old session may predate the entire prep corpus), it covers three different real-world prep layouts including flat location-named files (`notes/redbrand_hideout.md` *is* prep), and it ends in a tiered HIGH/MEDIUM/LOW choice presented via `AskUserQuestion`.

Let `/consistency-check` own the per-file character counts, tier subtotals, and
choice totals. Do not recreate or shorten that calculation here. Hold the
approved `prep_selection`—tier, exact files, per-file counts, and prep-only
`total_chars`—and reuse it unchanged at every stage.

**Ask explicitly and do not proceed without an explicit answer.** If the user says `none` — or prep genuinely does not exist for this session — run anyway and record `session_prep_used: false` with the reason in every stage's manifest.

**On a backfilled chapter with no prep, look for the campaign's own bible split before concluding there is no source.** `/consistency-check` step 2.5 date-bounds the prep hunt and will correctly tell you a 2025 session predates a prep corpus that starts in 2026. That is a true answer about `notes/`, and it is not the whole answer: a campaign with `docs/chapters/` has a per-chapter narrative rendering of that very session, and for a played chapter it is often the only session-specific document that exists. On Phandalin ch08 it settled the run's single biggest finding — two independent POV sections both contradicting the recap on who landed a killing blow.

**Match it by CONTENT, never by number.** Chapter numbering drifts: a campaign renumber can leave the session directory, the recap header, `campaign_state.md` and the bible all disagreeing. On ch08 the session dir was `20250812-chapter-08` and `gm-assist.md` said `# Chapter 8`, but the bible's chapter 8 was a different session entirely and this one was **chapter 10**. Grep the bible for the session's distinctive beats and confirm the hit before using it:

```bash
grep -ric "<npc>|<location>|<distinctive item>" docs/chapters/*.md | grep -v ':0$'
```

Two cautions. It is downstream prose, so it is corroboration, not the tape — a fact it agrees with the recap on is still a VTT question if it matters. And when a fix makes the recap diverge from the bible (a registry-canonical spelling the bible doesn't use), that divergence is a `carry_forward` item for the GM, not licence to edit `docs/chapters/`.

Hold the resolved prep list in the conversation. **Discover once, reuse at every stage** — that is the one thing this skill legitimately does differently from N independent `/consistency-check` runs.

#### The campaign-standard context set — present at EVERY stage

Per `/consistency-check` step 3, the registry is auto-loaded as authoritative canon. The remaining sources go in a single `--context` flag (`nargs="+"` — a second flag silently overwrites the first):

- `docs/entity_registry.yaml` — auto-loaded canonical entities, aliases, `distinct`, and `rejected_aliases`; do **not** pass the raw YAML through `--context`.
- `docs/party.md` — the PCs.
- `notes/vtt_transcription_corrections.md` — the wrong→right ASR glossary. Literally a table of the errors this skill hunts.
- `notes/vtt_known_additions.md` — names confirmed real but not yet promoted to the registry.

Pre-read the glossaries while building the tiers; they routinely surface findings outright.

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
cat  "$SESSION"/consistency_*stage*.sources.yaml 2>/dev/null        # <- the RULINGS live here (step-7 and report-stem names)
ls   "$SESSION"/logs/*_enhance_summary.md 2>/dev/null
```

⭐ **Filenames vary.** The stage-0 artifact is often not called `gm-assist.md` — a
GMAssistant export lands as `session_<date>_session_<date>.md`, and the enhance
output as `session_summary.md` rather than `session-summary.md`. The scene
extractions land in `scene_extractions/` or `scene_extractions_new/`. Do not
conclude a stage is missing from a failed `ls` — check the directory listing
itself.

⭐ **Check the input mtimes before checking anything else.** `ls -t` on the stage
files tells you whether stage N was generated from *corrected* stage N-1 input or
from the pre-review version. If the extract ran before the stage-1 fixes landed,
every ruling you already applied is absent downstream and the run is a re-do, not
a new stage. Say which it is in the opening message. **`.cg/activity.jsonl` names
the real paths** and is the fastest way to learn which file feeds which; confirm
the mapping with the user before checking anything.

**Also inventory the transcripts, and check which carry speaker labels** — step 4.7 needs one at every stage, and Stage 2 cannot be done properly without one:

```bash
ls -la "$SESSION"/*.vtt "$SESSION"/*.md
grep -oE '^\*\*[a-zA-Z][a-zA-Z ._-]{1,30}:\*\*' <candidate>.md | sort | uniq -c | sort -rn
```

Prefer `*.retranscribed.cleaned.vtt` for wording questions and a speaker-labelled source — a Zoom `.md`, or the raw `*.transcript.vtt` real-name labels — for attribution questions; `/consistency-check` step 4.7 has the rule that attribution is never settled from a summary. Load `zoom-summary.md` too if the session has one, and use it the way step 4.7 says: a dropped-beat cross-check, zero evidence on "who". Count distinct speakers against the party: **a missing player means someone else ran their PC all session**, which is the usual root cause of attribution collapse — see `/consistency-check` step 4.7.

**Check for prior `*.sources.yaml` manifests in the session dir and read them.** They record what was already fixed, what the GM ruled, and what is still `OPEN` in `carry_forward`. Treat their claims as hypotheses, not settled facts — re-verify any your findings touch.

**If a `consistency_report_stage*.md` already exists**, a prior run checked that
stage. Read it, then ask the user whether to re-check it or take it as settled. If
settled, its findings become the **propagation checklist** for step 6 — verify each
prior ruling actually landed rather than re-deriving it.

⛔ **Read the `.sources.yaml` companion BEFORE you build a single card or table
row.** The `.md` holds the *findings*; the stage's `.sources.yaml` (named `consistency_stage<N>_*` per step 7, or `consistency_report_stage<N>_*` by older runs) holds
`resolution.gm_rulings_this_run`, `resolution.applied` and
`resolution.open_items` — the GM's actual words, and any item a prior stage left
open. A finding whose subject already carries a GM ruling is **not** a fresh
question, and asking it as one invites the GM to reverse themselves without
knowing they are doing it.

> **Before presenting any finding, grep the rulings logs for its subject.** If a
> prior ruling exists, the card or row must quote it and say plainly that
> approving reverses it. If it exists and *contradicts* what the documents now say,
> do not present it as a finding at all — surface it as an open conflict and let
> the GM settle it with both sides in view. See the Ch 65 case in Notes.
>
> **And when a prior ruling looks wrong, check the rule before calling it wrong.**
> The Ch 65 miss was not only that a settled question got re-asked — the audit was
> confident about RAW while reading the wrong edition, twice (`/consistency-check`
> step 5).

Tell the user which stages were found and what will be checked. Some sessions may be partial. Run the check on whatever exists; don't try to generate missing artifacts (that's the pipeline's job, not this skill's).

**Do this inventory FIRST, before config, before prep discovery, and tell the user the shape of the run before spending anything on it.** A session that has only `gm-assist.md` — no `session-summary.md`, no scene extractions, no narration — is not a staged run at all; it is one `/consistency-check` with extra ceremony, and the user should get to decide whether that is what they want. Phandalin ch08 (2026-09-03) was exactly this: the pipeline had never been run, so Stage 2 — the load-bearing stage, the entire reason to prefer this skill over a one-shot — had nothing to check.

**A stage that did not run did not pass, and the final summary must say so in those words.** The failure mode is a closing summary reading "Stages 0-3 complete, 13 issues, all resolved," which is true of every stage that ran and dangerously false about the three that didn't. Write `Stages 1-3: NOT RUN — no artifacts exist` and put it in the manifest as its own `carry_forward` item with `status: OPEN`, naming Stage 2 specifically. Then recommend the pipeline run and a re-invocation, rather than implying the session has been cleared.

When only Stage 0 exists, offer the choice explicitly rather than defaulting: run Stage 0 alone; run Stage 0 plus a hand VTT sweep of whatever attribution is most at risk; or stop and run the pipeline first.

### 1b. The verbatim sweep — run this on every prose document, before the LLM check

A deterministic pass that catches what an LLM reviewer reads straight past:
inline quotes spliced from two moments minutes apart, and quotes completed with
words nobody said. It complements `sd_verify_quotes` (steps 3 and 4), which checks
only `> "…"` blockquotes — this checks the inline `"…"` quotes in prose that
`sd_verify_quotes` skips.

```bash
python3 ~/.claude/skills/staged-consistency/verify_quotes.py \
  --doc "$SESSION/<artifact>.md" --vtt "$SESSION"/*.transcript.cleaned.vtt
```

It prints every quoted span whose text is not contiguous in the transcript. Expect
false positives from deliberate stutter-smoothing — **each hit is a lead, not a
finding.** Open the transcript at that point and decide. It answers *were these
words said*, **not** *who said them* — attribution is still a speaker-label
question (`/consistency-check` step 4.7).

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

Sort by severity (Critical first). Number issues sequentially across the whole table.

**Severity ranks findings; it does not rule on them.** `/consistency-check` step 5's triage still applies underneath — a **canon-judgment** finding (a new fact no doc establishes, or a beat that contradicts prep because play diverged) is the user's call regardless of how severe it looks. Mark those in the table (e.g. `Critical · GM ruling needed`) and never auto-apply one. Run step 5's false-positive filters — table rulings that outrank the PHB, module-vs-table vocabulary, backfilled-chapter anachronism, the report pointing at the wrong half of a contradiction — **before** anything reaches this table.

**Never auto-advance on a zero count from the banner.** `check_consistency.py` counts the literal string `**Location**`, but models routinely emit `**Location:**`, so `No issues found.` is an unreliable false negative while the body lists a dozen issues. Derive your own count from the saved report the way `/consistency-check` step 4 does: the finding delimiter changes from run to run, even for the same stage on the same campaign, so no single pattern is safe. `grep -c "^### "` can return a confident 0 on a report with twelve findings, and `^- \*\*` can return 48 against 12. Run every candidate pattern, read enough of the body to see which one matches, and record the delimiter you counted. Advance automatically only when *your* count is zero and you have read the body. (A grouped Stage 2 report counts differently — see step 4.) Likewise, if `--backend claude-code` printed an auto-continuation warning, inspect the report for a seam before believing any count.

### Artifact mode (batch review)

Chosen in step 0a. Replaces the "Going 1x1?" adjudication at each stage. The
severity table, the stage order, the fix-propagation pass and the final summary
are all unchanged. Full contract: `~/.claude/skills/_shared/review-artifact/CONTRACT.md`.
It pays off most at Stage 2's normal scale — 8–10 scenes, 5–15 findings each,
60+ findings total — where a chat 1x1 walkthrough is exhausting for both sides
(Phandalin Ch. 3, 2026-08-17: a 64-finding, 8-scene Stage 2).

#### One page per stage, one URL for the run

**Publish once per stage, republishing to the same `file_path` so the URL
never changes.** This is the whole point of the staged pattern: a stage-1
error ruled on now is fixed in one file, and stage 2 runs on corrected input
instead of copying the error forward. Do not collate all stages into a single
end-of-run page — that gives up the gate the skill exists for.

Sequence per stage: run the check (at Stage 2, the grouped call — step 4) →
VTT-adjudicate every finding exactly as you would 1x1 (still required) → present
the severity table in the shell → build the items → publish → **stop** → the save
comes back → read back → apply → **then** start the next stage.

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
which is what step 8's `consistency_report_stage<N>_*.md` is written from, and
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

#### What is auto-applied, footer only

- **Trivial**, per the rubric — surface but do not push. List them; do not ask.
- Unambiguous corrections with exactly one right answer: a two-word factual
  correction, or a proper-noun spelling already settled in the glossary or the
  entity registry.

Everything else — every Critical, Moderate and Minor needing a judgement —
becomes a card. So does **any real-name scrub in a speaker label**: it asserts
who said the line, which is an attribution change (`/consistency-check` step 5),
not a mechanical fix. Name the auto-applied count and the files touched in the
`footer`.

#### Card shape

Reuse the finding's table number as the id (`s1-03` = stage 1, finding 3) so
the shell table and the page line up.

```json
{ "id":  "s1-03",
  "t":   "Manshoon in person, or a simulacrum?",
  "y":   "Edit <code>entity_registry.yaml:2361</code> to drop “appears as Manshoon’s Simulacrum.” The recap and both grounding docs are correct; the registry is the stale side.",
  "n":   "He was a simulacrum. The recap, campaign_state and world_state get corrected instead.",
  "ev":  "All four checks ruled against the recap citing the registry under “canon outranks generated docs.” But <code>20260810_race_to_the_vile_door.md:28</code> rebuilds him as “the real man, depleted” at CR 12." }
```

Say which file each fix lands in on the card — one page often spans fixes in
different documents (a scene, `gm-assist.md`, a glossary). **Where the audit
itself may be wrong, say so in `ev`.** The most valuable cards are the ones
where a check fired against stale canon — the GM is the only one who can
overturn that, and they can only do it if the card shows both sides. A finding
that carries a prior GM ruling (step 1) quotes it in `ev`.

#### Verdict mapping

| verdict | action |
|---|---|
| **approve** | Apply the fix with `Edit`, then run the step-6 fix-propagation grep across every touched artifact |
| **reject** | Log as deferred, with the location, for the final summary |
| **discuss** + note | **Read the note first.** GMs often write the ruling itself there ("Fix to Norbus", "It was on Valphine") — an unambiguous note is a ruling; apply it without a redundant round of questions. If it settles a canon question, the fix may belong in a grounding doc rather than the recap. Take it to conversation only when the note is ambiguous or asks you to check something first |
| **discuss**, no note | Back to the shell, grouped with the other discussed findings for that stage |
| **unmarked** | Undecided — carry into the final summary as unresolved, and do not advance past a stage with unresolved Criticals without saying so |

**Grounding-doc rewrites still stop.** `campaign_state.md`, `world_state.md`,
`planning.md` and `party.md` are CampaignGenerator outputs. An approved card
that implies changing one of them means fixing the *source* and regenerating
— never a hand-edit. Say this on the card's `y` when it applies.

**Fix-propagation (step 6) still applies at full strength**, including to
sibling documents outside the page's scope. The review scope decides what gets
*reviewed*; it does not excuse skipping propagation of an *approved* fix to a
sibling — and check every section of the sibling (Summary prose, Scenes
bullets, Items), not just the first place the fact appears.

**Visible external actions still need a separate go-ahead.** An approve
authorizes the *content* of, say, a GitHub comment drafted from a finding;
posting it is a separate yes in chat. Record the resulting URL in the manifest.

Manifest each ruling like any other (step 7), noting it came via the artifact
and whether a `discuss` item was settled from the note or needed back-and-forth.

### 2. Stage 0 — gm-assist check

> Stage 0 — running `/consistency-check $SESSION/gm-assist.md` with the standard context set + prep.

Run the full `/consistency-check` workflow against `$SESSION/gm-assist.md`, passing the standard context set and every prep file from step 0 in one `--context` flag, with `--backend claude-code`. Then:

- Present the severity table (format above).
- Ask: "Apply any of these fixes to `gm-assist.md` before moving to stage 1?"
- If yes, edit `gm-assist.md` directly. If no, log what was deferred so it can be revisited.

**Stage 0 pays for itself, and the evidence is worth citing when the user asks whether to skip it.** On Ch 48 of `out-of-the-abyss` the order was spell pass → Stage 0 → `/enhance-summary` → Stage 1, and the effect was measurable: **Stage 0 found 12 issues; Stage 1 then found 6**, on a document three times longer. Every one of Stage 0's fixes survived the regeneration, because `gm-assist.md` is the structural spec the enhancement renders from — so a class of error fixed at Stage 0 *cannot* recur at Stage 1.

One fix did more than survive, it **generalised**: an out-of-character label applied to a table-chatter quote at Stage 0 was re-applied by the enhancement to a second, previously unseen quote in the same anecdote, with the correct speaker. Fixing the spec changes what the renderer *produces*, not just what it copies.

The corollary is an ordering rule: **fix gm-assist before enhancing, never after.** Stage 0 on a gm-assist that has already been enhanced from is still worth running, but it is no longer a virgin pass — Stage 1's rulings will have been propagated back into it, the check cannot re-find them, and the manifest has to say so or the finding count reads as a clean bill of health.

**Important caveat about gm-assist.md**: this file may be the user's preserved-original artifact (paired with a `gm-assist-update.md` next to it). If a `gm-assist-update.md` exists, ask the user whether to check that file instead and treat it as the canonical first-pass artifact. The convention is "original preserved, corrected version alongside" — apply fixes to the `-update.md` if present, otherwise the original.

### 3. Stage 1 — session-summary check

> Stage 1 — running `/consistency-check $SESSION/session-summary.md` with the standard context set + prep.

Same flow. **Also pass `gm-assist.md` as context**: `session-summary.md` is an `enhance_summary` output built from it plus the VTT, so every difference between them is *something the enhancement pass added* — exactly the material under test. `/consistency-check` step 3 calls this the single highest-value context file for this document class.

**That context file is also this stage's dominant false-positive source, so grep the target before believing any finding.** The two documents are near-paraphrases, and the check routinely quotes gm-assist prose while naming a `session-summary.md` section as the **Location**. `/consistency-check` step 5 carries the test — run `grep -nF` for a fragment of every finding's quoted text against the target, first, before any other adjudication. A miss means the finding does not apply to this document; applying it would re-introduce into the recap an error the enhancement pass had already removed. Expect a cluster of these and read them as evidence the enhancement pass worked, not as noise.


**Run `sd_verify_quotes` FIRST, before the check and before any hand adjudication.** It is deterministic, calls no model, needs no backend, costs nothing, and the pipeline diagram puts it at exactly this gate. Skipping it means hand-checking a sample of quotes when an exhaustive pass was free:

```bash
python -m session_doc.sd_verify_quotes \
  --vtt <the VTT the artifact was generated from> \
  --summary "$SESSION"/session-summary.md \
  --out "$SESSION"/quote_report_stage1.md --report-only
```

Use `--report-only` until the GM has ruled — without it the tool writes `<!-- cg:unverified -->` markers into the artifact. The `--vtt` must be the *same* transcript the artifact was generated from; a different one reports edits nobody made.

**Read a 100% result narrowly — the tool names its own two blind spots, and they are where the interesting defects live.** It checks only `> "…"` blockquotes, not inline `"…"` in prose; and it answers *were these words said*, **not** *did this person say them*. On Phandalin ch08 it returned 27/27 verified while the same document carried an invented "Santorini" (inline prose) and the upstream recap carried a quote attributed to the wrong player. It is a complement to VTT adjudication, never a substitute — and `near`, not just `unverified`, is the verdict to skim, because `near` means traceable but *edited*.

What it does buy that hand-checking never does is exhaustiveness. It is also the cleanest evidence available that an enhancement pass is quote-faithful: on ch08 the pass added 26 blockquotes to gm-assist's 1, and every one was verbatim — which localises the remaining error surface to prose, attribution and numbers.

The **enhancement-pass failure modes** in `/consistency-check` step 4.7 apply in full here, and none are catchable from grounding docs — verify each against the tape:

- Invented precise dice values (grep the VTT for the literal number; timestamp-only hits mean invented)
- Attribution drift toward the prominent character (heals and kills migrate)
- Event duplication alongside event loss
- Quote truncation with the `*(truncated)*` marker left in
- DM asides relocated onto the wrong mechanical result

Plus the classic session-summary catches: cross-section contradictions (Summary prose vs. bulleted scene log), pronoun drift on PCs, NPC affiliation fabrications (Prutha "committed to the Order of the Gauntlet" — `party.md` says Lathander convert), and killing-blow attribution.

### 4. Stage 2 — scene extractions check (the load-bearing one)

Stage 2 has **two call shapes**. Which one you use follows the review mode chosen in step 0a — settle it with the user *before* running anything:

- **Interactive (per-scene).** Run `/consistency-check` once per scene extraction (`scene_extractions/` or `scene_extractions_new/`, whichever this session has — step 1) in numbered order, present a severity table per scene, and gate each scene on the previous one's fixes. Unchanged.
- **Batch (grouped).** Pass **every selected scene path, in scene order, to one `check_consistency.py` invocation**. The script audits all of them in a single model call: the shared material (system prompt, canon section, `campaign_state` + `world_state`, registry, glossaries, prep) is transmitted once instead of N times, and the model must return one result section per scene plus one cross-scene section. Use this in artifact mode.

In both shapes, exclude `.prev` and `.scaffold` and enumerate the scenes explicitly. **Never say "all" and never let a shell glob decide the list** — the manifest has to record exactly which documents were audited, and in grouped mode the order you pass is the order attribution is keyed to.

**Do not fake grouped mode.** N single-document checks with their reports concatenated is a different run: it re-sends the whole context N times, produces no cross-scene section, and gets none of the attribution validation below. Grouped mode is not a flag — the script switches on it as soon as it receives more than one document path, and loads a different agent prompt (`config/agents/session_doc/consistency_grouped.md`).

#### The grouped invocation

```bash
python <repo>/session_doc/check_consistency.py \
  "$SESSION"/<scene-dir>/<scene-01>.md \
  "$SESSION"/<scene-dir>/<scene-02>.md ... \
  --config <abs campaign>/config/config.yaml \
  --backend claude-code \
  --context docs/party.md notes/vtt_transcription_corrections.md notes/vtt_known_additions.md <prep files...> \
  --output "$SESSION"/consistency_report_stage2_scenes.md
```

Spell every scene out as a literal path in scene order — the `...` above is a placeholder for the rest of them, not a glob. Everything `/consistency-check` says about config resolution, the standard context set, the single `--context` flag and `--backend claude-code` still applies verbatim. Only the document list changes. Duplicate paths are rejected outright, so de-duplicate the list before you build the command.

**Size the output ceiling before a large batch.** `check_consistency.py` reads `CG_CONSISTENCY_MAX_TOKENS` (default `32000`) for `max_tokens`, and the `claude-code` backend forwards it as `CLAUDE_CODE_MAX_OUTPUT_TOKENS`. Eight scenes of findings plus a cross-scene section is several times a single-scene response, so raise it up front (`CG_CONSISTENCY_MAX_TOKENS=64000 python <repo>/session_doc/…`) rather than discovering the ceiling from an auto-continue warning — and in grouped mode a seam is likely to break the marker protocol and cost you the whole run.

**The grouped run is fail-closed. A failure is a stopped stage, not a prompt to retry differently.** On any setup, login, model, timeout, empty-result, context or grouped-protocol error:

- stop Stage 2 — do not build the artifact or review page, and do not write the Stage 2 manifest;
- do not quietly retry per scene, split the batch, or switch backends. Each of those audits something different from what just failed, and reporting it as the same run is the lie this rule exists to prevent. Changing the shape is fine *if you say so* and re-record it;
- an older `consistency_report_stage2_scenes.md` is history, not evidence this run succeeded. The script validates first and replaces the report atomically, so a failed run leaves the previous file untouched — check its timestamp before you believe it.

It fails closed on: a missing, duplicated, out-of-order, nested, empty or unknown section; a finding with an incomplete field set; a cross-scene finding without **Affected documents**; and — the load-bearing one — a scene finding whose **Target text** excerpt does not occur verbatim in the scene that section is attributed to.

**Attribution is validated, so never hand-repair it.** Every scene-level finding carries a single-line **Target text** excerpt copied from its own scene, and the script checks it against that scene's text. When validation rejects a run, do not move a finding into the section it "obviously" belongs to, trim an excerpt until it matches, or edit the report until it parses. Cross-scene misattribution is precisely the failure that grouping introduces — the model has all eight scenes in view at once — and this check is what catches it. Re-run instead.

**Glossary anchors are attention aids, not rulings.** The script scans each scene for exact wrong-form matches drawn from the correction glossaries you passed in `--context`, and lists them ("Mechanical glossary matches") ahead of that scene's text. This buys recall on the late scenes of a long batch without re-sending the glossary per scene. It pre-approves nothing: the glossary's own exceptions, longest-match notes and `DO NOT CORRECT` rulings still govern, and VTT adjudication below is still mandatory. An anchored match is a place to look, exactly like a reported finding.

**Read and count the grouped report yourself.** It is `# Grouped Consistency Report`, then one `## D01 — <path>` section per scene in the order you passed them, then `## Cross-document findings`; a clean scene is the literal word `CLEAN`. A single-document heading count such as `grep -c "^### "` returns 0 here — count `**Location**` within each `## D` section instead, and reconcile the per-scene totals against the banner before building the severity table. Grouped mode is at least stricter about the `**Location:**` variant that makes single-document runs report a false zero: there, format drift is a protocol failure that stops the run rather than a scene quietly reported clean.

**The cross-scene section is new information, not a summary.** It carries contradictions *between* scenes — an NPC in two places, an item changing hands twice, a chronology that only breaks when the scenes are read together — which N independent per-scene runs structurally cannot produce. Adjudicate it like any other finding, and hold onto the rule the grouped prompt is given: peer targets are not evidence for each other. Two scenes agreeing on a name does not make the name right, and neither the model nor you should pick a winner by frequency.

**Run `sd_verify_quotes --scene-extractions <dir>` before the grouped check here as well** — same flags, same `--report-only` discipline. At Stage 2 it also applies the extraction contract's refusal rules (R1/R3), which the Stage 1 shape cannot produce: R1 fires when a span's `## Scene summary` and `## Verbatim moments` copies disagree and *neither* is verbatim, R3 when a span marked verbatim carries an editorial insertion. A refusal is a stronger signal than an unverified quote — it is the pipeline declining to decide — so read the `## Refused` section before the findings table.

This stage exists because **the scene extractions contain the verbatim quotes the narrator reads literally**. Fixes applied only at the session-summary layer get silently undone the next time the narrator runs.

**This is the stage where VTT adjudication is not optional.** A quote is a span of the tape or it isn't, and no grounding doc can settle one. For every flagged quote, go to the transcript per `/consistency-check` step 4.7 — and watch for its two highest-value catches:

- **Retracted GM slips** — a name the GM misspoke, was corrected on, and fixed *on tape*, which the extractor captured in its uncorrected form. Grep ±20 lines for `"I meant"`, `"sorry"`, `"you're right"`, `"hold on"`, `"different character"`.
- **A garble that fused two characters.** A single invented name can hold two PCs' actions; a blind glossary replace then credits one character's deeds to another and looks *more* canonical afterwards. Read every instance in context and discriminate by class feature before replacing. A race+class pair matching nobody in `party.md` ("the tortle barbarian") is the loudest possible signal.

When applying fixes to verbatim quotes:
- **Preserve the speaker attribution and tone** of the original quote when correcting transcription drift — the players' table voice is the whole point of these quotes.
- **Add an italic editorial note** in the speaker attribution explaining the discrepancy between raw Otter/Zoom capture and prep canon, so the next narrator pass has an audit trail.
  - Example: `**GM** — *voicing Prutha (transcript per session-prep canon; raw Otter capture said "my uncle Seidan comes for everyone" — a mishearing of "great-uncle said dawn")*`
- **Do not strip table chatter, jokes, or player improvisations** that the table values. Some "errors" the check flags are intentional flavor. The Phandalin "blacklist" / "blood money list" terminology is real OOC table vocabulary — preserve it.

In the interactive shape, after each scene's fixes ask: "Continue to next scene, or revisit this one?" Don't auto-advance through all scenes silently. In the grouped shape that gate moves to the artifact rather than disappearing: the grouped report is advisory until the user rules on it, and every finding still needs an explicit Accept / Reject / Discuss before an edit lands. **This is the stage where finding counts routinely justify artifact mode** (step 0a) instead of a 1x1 walkthrough per scene. One grouped call plus one artifact page is the flow that scales.

### 5. Stage 3 — narration check (optional)

If a final narration file exists, run `/consistency-check` on it and present a severity table.

At this stage the check is mostly catching narrator-layer voice drift and prose fabrications. Findings here are usually candidates for a narrator re-run (after fixing upstream) rather than direct edits, since editing final prose tends to fight the narrator's voice.

### 6. Fix-propagation pass

After all stages have been checked and fixed, sweep for residual bad patterns — fixes applied to a deep stage may need to propagate upward, and vice versa:

```bash
grep -n "<bad pattern>" $SESSION/gm-assist.md $SESSION/gm-assist-update.md \
  $SESSION/session-summary.md $SESSION/narration/enhanced_sections.md \
  $SESSION/scene_extractions{,_new}/0*.md 2>/dev/null | grep -v ".prev\|.scaffold"
```

⛔ **Use `grep -F` with a full distinctive phrase, never a short token.** A bare
`grep -ci "Mechanis"` matches `Mechanist` and reports a fix that never regressed;
a bare `grep -c "damage stands"` matches your own corrected `**no damage stands**`.
Both produce phantom findings you then have to retract. Match on a whole clause.

Run this for every applied fix. If grep finds the bad pattern in a file that wasn't checked or fixed, surface it and ask whether to apply the fix there. **This step is what catches the scenario where session-summary was fixed but the scene extractions still carry the original error.**

**Also sweep the grounding docs.** Per `/consistency-check` step 5, a VTT-confirmed correction usually lands in more places than the recap — `world_state.md`'s timeline and `party.md`'s per-character notes both carry attributions. Check the direction before editing: in one run the GM asked for a grounding-doc fix and the docs were already right; the recap was the wrong one. Survey first, then say plainly which file was actually wrong. Anything you don't fix goes in `carry_forward`.

**Never bulk-replace a name, colour, adjective or title across the campaign.** Enumerate and read every hit first.

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

### 7. Manifests — REQUIRED

Per `/consistency-check` steps 4.5 and 6, every check gets a provenance record. Staging changes only the granularity:

- **One manifest per stage**, in the session dir, named for the stage: `consistency_stage0_gmassist.sources.yaml`, `consistency_stage1_summary.sources.yaml`, `consistency_stage2_scenes.sources.yaml`, `consistency_stage3_narration.sources.yaml`.
- Copy the approved `prep_selection` block into every stage manifest unchanged. Stage-specific inputs such as the Stage 0 source recap remain ordinary context and do not alter the prep-only total.
- Stage 2 gets **one manifest for the whole stage**, not one per scene — with a `scenes:` list recording per-scene issue counts and rulings. N per-scene manifests are unreadable and nobody will consult them.
- **A grouped Stage 2 run manifests the batch, not N checks.** Record `grouped: true`, a `documents_checked:` list in the exact order passed to the script, and the telemetry line the script printed (`model_calls`, `shared_context_chars`, `target_chars`, `repeated_context_chars_avoided`). That is what lets a later reader tell one grouped call from N concatenated single ones — a distinction no report body carries. Keep the per-scene `scenes:` counts too, derived from the `## D` sections, and give cross-scene findings their own `cross_scene:` list since they belong to no single scene.
- Use the schema from `/consistency-check` 4.5 (sources half) + 6 (ruling half), including `document_class`, `speaker_map`, `vtt_adjudicated`, and `carry_forward` with a `status:` on every entry.
- Record which transcript was consulted, and note it was read **by hand** — it is provenance for the ruling, not a `--context` input.

Validate each parses (`python -c "import yaml; yaml.safe_load(open(...))"`).

Carry `carry_forward` forward *between stages within this run*, not just between runs — an item opened at stage 0 is often closed at stage 2.

### 8. Final summary

End with a tight summary:

- Stages run, issue counts per stage (your counts, from the report bodies — not the banner)
- Fixes applied per stage
- **What the VTT caught that the check structurally could not** — on this skill's target artifacts that is usually most of the real defects
- Anything deferred, with its location
- Whether prep was available (or whether the run was prep-less and possibly blind to transcription errors)
- Whether `zoom-summary.md` was available, and what it actually changed — name the findings it caught and the ones it got wrong. It is a source with a known bias; reporting its scorecard each run is how that bias stays visible.
- Which stages did **not** exist (step 1's "NOT RUN" rule). If stage 2 was absent, say plainly that the per-scene verbatim layer was not exercised and that §1b only partly covered for it.
- **Offer to write `consistency_report_stage<N>_<artifact>.md`** beside each stage's `.sources.yaml` (step 7), matching whatever prior-stage reports the session already has. This is what step 1 of the *next* run reads; without it the next pass re-derives settled questions from scratch. Record `resolution.open_items` even when the list is empty, and put anything a stage could not settle there rather than in prose.
- The merged `carry_forward` list across stages
- Recommendation on next action — usually one of:
  - "Re-run `sd_narrate` to produce a clean narration from the corrected scene extractions"
  - "Ready to share session-doc with players"
  - "Stage X still has unresolved issues — revisit those before narrating"

Don't commit unless asked.

## Notes

- This skill is intentionally heavy. It exists for sessions that matter — chapter releases, sessions you're sharing externally, sessions where you've already produced a bad narration and need to root out why. For a quick sanity check on a single document, use `/consistency-check` directly.
- **Method lives in `/consistency-check`; sequencing lives here.** When adding a lesson learned about *how to check*, put it there — it will reach this skill through the delegation. Only staging, gating and propagation rules belong in this file. Duplicating method here is how the two drifted apart before.
- Skipping the prep step (step 0) collapses the value of this skill the same way it collapses `/consistency-check`. The whole reason this pattern beats a one-shot check is that prep is wired into every stage's check. Do not skip.
- **The standard context set is not optional and not `party.md` alone.** The auto-loaded registry and explicitly passed VTT glossaries carry the name/alias/garble finding class this skill exists to catch. Do not reintroduce the raw registry into `--context`.
- Different pipeline stages fail differently, and the staging should reflect it: **gm-assist** fails on names (prep + glossaries catch it), **session-summary** is an enhanced recap and fails on numbers, attribution and ordering (only the VTT catches those), **scene extractions** fail on verbatim quote fidelity (only the VTT), **narration** fails on voice drift. Expect a poor report hit-rate on the enhanced and verbatim stages and say so, so it doesn't read as the documents being clean.
- **Grouped Stage 2 (#362) is a call-shape change, not a review-gate change.** It batches the Stage 2 audit into one model call so shared context is sent once and cross-scene contradictions become visible at all; it removes no human checkpoint. Findings remain advisory, still need VTT adjudication, and still need an explicit ruling before an edit. If a grouped report ever starts auto-applying anything — glossary anchors included — that is the bug, not a shortcut.
- **The OOTA Ch 65 stage 2 run (2026-08-27) is why step 1 reads `.sources.yaml` before presenting anything.** It carded "did Manshoon take 13 psychic damage?" as a document-internal contradiction and the GM approved the fix — while `consistency_report_stage0_gmassist.sources.yaml:56` already held an explicit, opposite GM ruling from earlier the same day. The card never showed it. Worse, that earlier ruling was right: the audit had been reading the wrong PHB edition (`/consistency-check` Notes). **A prior ruling makes a finding a conflict to surface, never a question to re-ask.** The method half of that run — attribution, retraction, read-aloud and edition — lives in `/consistency-check`'s Notes.
- The Phandalin Ch 41 run (2026-05-17) was the discovery case — 11 prep-canonical issues survived a late-stage one-shot check that returned "no major issues." The same issues were trivially catchable at stage 0 with prep wired in. That's the failure mode this skill exists to prevent.
- See `~/campaigns/STAGED_CONSISTENCY_HOWTO.md` for the methodology rationale, the pipeline diagram, and the per-stage table of what each check catches that the others miss.
