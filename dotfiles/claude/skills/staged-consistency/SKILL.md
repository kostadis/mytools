---
name: staged-consistency
description: Run consistency checks at every LLM-pipeline boundary (gm-assist → session-summary → scene extractions → narration) with a human-review gate between stages. Use when the user invokes /staged-consistency [session-dir] and wants the multi-stage check rather than a one-shot. Prevents fix-propagation drift where stale per-scene quotes silently re-inject errors into the next narration run.
tools: Bash, Read, Write, Edit, Glob, AskUserQuestion
---

# Staged Consistency

Run the multi-stage consistency check pattern documented in `~/campaigns/STAGED_CONSISTENCY_HOWTO.md`. The pattern: a `check_consistency.py` run gated by a human-review/fix cycle at each LLM extraction boundary in the session-doc pipeline — gm-assist, session-summary, scene extractions, and (optionally) the final narration.

The point of this skill is to **catch verbatim transcription errors before they reach the narrator**. A single late-stage check misses the per-scene-quote layer, which is the layer that silently re-injects errors into every subsequent narration run. See `STAGED_CONSISTENCY_HOWTO.md` for the rationale.

## This skill is an orchestrator, not a second implementation

Every stage below runs the **full `/consistency-check` workflow**. That skill owns the method — context selection, the script's failure modes, VTT adjudication, the triage rules, the manifest. This skill owns only the *staging*: which artifact, in what order, with a human gate between each.

**Do not shortcut the delegated workflow.** In particular these `/consistency-check` steps are REQUIRED and apply at every stage:

| Step | What it is | Why staging makes it more important, not less |
|---|---|---|
| 2 | Config resolution | `find_default_config()` is CWD-only with a fallback to CampaignGenerator's *own* config. Get it wrong once and every stage checks against the wrong campaign. |
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

### 0. Locate the session directory, the script, and the context set

If the user passed a path argument, use it. Otherwise:
- Run `pwd` to confirm CWD is a campaign workspace (contains `docs/`, `summaries/`, `config.yaml`).
- List recent session directories: `ls -t summaries/ | head -10`
- Ask: "Which session — pass the path under `summaries/` (e.g. `summaries/20260512`)?"

**Locate the script; don't assume the path.** It lives at `<repo>/session_doc/check_consistency.py` (it moved out of the repo root), and the repo may be `~/CampaignGenerator` **or** `~/src/CampaignGenerator`. There is also an installed console script, `check_consistency`. `ls` before building any command.

**Resolve config once, here.** Per `/consistency-check` step 2: run from the workspace root, or pass `--config <abs-path>`. Some workspaces (Phandalin) have no root `config.yaml` at all and need a throwaway absolute-path config. Settle this before stage 0 — a config mistake repeated across every stage is the most expensive error this skill can make.

#### Prep discovery — delegate to `/consistency-check` step 2.5, do not use a shortened version

Run that step's **full** sweep, not a two-directory `ls`. It is date-bounded (an old session may predate the entire prep corpus), it covers three different real-world prep layouts including flat location-named files (`notes/redbrand_hideout.md` *is* prep), and it ends in a tiered HIGH/MEDIUM/LOW choice presented via `AskUserQuestion`.

**Ask explicitly and do not proceed without an explicit answer.** If the user says `none` — or prep genuinely does not exist for this session — run anyway and record `session_prep_used: false` with the reason in every stage's manifest.

**On a backfilled chapter with no prep, look for the campaign's own bible split before concluding there is no source.** `/consistency-check` step 2.5 date-bounds the prep hunt and will correctly tell you a 2025 session predates a prep corpus that starts in 2026. That is a true answer about `notes/`, and it is not the whole answer: a campaign with `docs/chapters/` has a per-chapter narrative rendering of that very session, and for a played chapter it is often the only session-specific document that exists. On Phandalin ch08 it settled the run's single biggest finding — two independent POV sections both contradicting the recap on who landed a killing blow.

**Match it by CONTENT, never by number.** Chapter numbering drifts: a campaign renumber can leave the session directory, the recap header, `campaign_state.md` and the bible all disagreeing. On ch08 the session dir was `20250812-chapter-08` and `gm-assist.md` said `# Chapter 8`, but the bible's chapter 8 was a different session entirely and this one was **chapter 10**. Grep the bible for the session's distinctive beats and confirm the hit before using it:

```bash
grep -ric "<npc>|<location>|<distinctive item>" docs/chapters/*.md | grep -v ':0$'
```

Two cautions. It is downstream prose, so it is corroboration, not the tape — a fact it agrees with the recap on is still a VTT question if it matters. And when a fix makes the recap diverge from the bible (a registry-canonical spelling the bible doesn't use), that divergence is a `carry_forward` item for the GM, not licence to edit `docs/chapters/`.

Hold the resolved prep list in the conversation. **Discover once, reuse at every stage** — that is the one thing this skill legitimately does differently from N independent `/consistency-check` runs.

#### The campaign-standard context set — passed at EVERY stage

Per `/consistency-check` step 3, none of these are auto-loaded, and all of them go in a single `--context` flag (`nargs="+"` — a second flag silently overwrites the first):

- `docs/party.md` — the PCs.
- `docs/entity_registry.yaml` — canonical entities **with aliases**. Highest-yield source for the most common finding class; it is what separates a legitimate alternate name from a transcription error. Skip only if the campaign has no registry.
- `notes/vtt_transcription_corrections.md` — the wrong→right ASR glossary. Literally a table of the errors this skill hunts.
- `notes/vtt_known_additions.md` — names confirmed real but not yet promoted to the registry.

Pre-read the glossaries while building the tiers; they routinely surface findings outright.

### 1. Inventory the pipeline artifacts in this session

Determine which stages exist:

```bash
SESSION=<session-dir>
ls "$SESSION"/gm-assist.md 2>/dev/null
ls "$SESSION"/session-summary.md 2>/dev/null
ls "$SESSION"/scene_extractions_new/0*.md 2>/dev/null | grep -v ".prev\|.scaffold"
ls "$SESSION"/narration/enhanced_sections.md 2>/dev/null
ls "$SESSION"/narration/*.md 2>/dev/null   # final narration if generated
```

**Also inventory the transcripts, and check which carry speaker labels** — step 4.7 needs one at every stage, and Stage 2 cannot be done properly without one:

```bash
ls -la "$SESSION"/*.vtt "$SESSION"/*.md
grep -oE '^\*\*[a-zA-Z][a-zA-Z ._-]{1,30}:\*\*' <candidate>.md | sort | uniq -c | sort -rn
```

Prefer `*.retranscribed.cleaned.vtt` for wording questions and a speaker-labelled Zoom `.md` for attribution questions. Count distinct speakers against the party: **a missing player means someone else ran their PC all session**, which is the usual root cause of attribution collapse — see `/consistency-check` step 4.7.

**Check for prior `*.sources.yaml` manifests in the session dir and read them.** They record what was already fixed, what the GM ruled, and what is still `OPEN` in `carry_forward`. Treat their claims as hypotheses, not settled facts — re-verify any your findings touch.

Tell the user which stages were found and what will be checked. Some sessions may be partial. Run the check on whatever exists; don't try to generate missing artifacts (that's the pipeline's job, not this skill's).

**Do this inventory FIRST, before config, before prep discovery, and tell the user the shape of the run before spending anything on it.** A session that has only `gm-assist.md` — no `session-summary.md`, no scene extractions, no narration — is not a staged run at all; it is one `/consistency-check` with extra ceremony, and the user should get to decide whether that is what they want. Phandalin ch08 (2026-09-03) was exactly this: the pipeline had never been run, so Stage 2 — the load-bearing stage, the entire reason to prefer this skill over a one-shot — had nothing to check.

**A stage that did not run did not pass, and the final summary must say so in those words.** The failure mode is a closing summary reading "Stages 0-3 complete, 13 issues, all resolved," which is true of every stage that ran and dangerously false about the three that didn't. Write `Stages 1-3: NOT RUN — no artifacts exist` and put it in the manifest as its own `carry_forward` item with `status: OPEN`, naming Stage 2 specifically. Then recommend the pipeline run and a re-invocation, rather than implying the session has been cleared.

When only Stage 0 exists, offer the choice explicitly rather than defaulting: run Stage 0 alone; run Stage 0 plus a hand VTT sweep of whatever attribution is most at risk; or stop and run the pipeline first.

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

**Never auto-advance on a zero count from the banner.** `check_consistency.py` counts the literal string `**Location**`, but models routinely emit `**Location:**`, so `No issues found.` is an unreliable false negative while the body lists a dozen issues. Derive your own count from the saved report (`grep -c "^### "`) and trust the body. Advance automatically only when *your* count is zero and you have read the body. (A grouped Stage 2 report counts differently — see step 4.) Likewise, if `--backend claude-code` printed an auto-continuation warning, inspect the report for a seam before believing any count.

### Alternative sign-off: interactive artifact (many scenes / large finding count)

The severity-table-plus-1x1-ask flow above is fine for a handful of findings. It breaks down at Stage 2's normal scale — 8–10 scenes, 5–15 findings each, 60+ findings total — where a chat 1x1 walkthrough is exhausting for both sides and easy to lose track of. When the finding count crosses roughly a dozen, or the user asks for a batch/downloadable review, offer this instead of table-by-table 1x1. Confirmed useful on a 64-finding, 8-scene Stage 2 run (Phandalin Ch. 3, 2026-08-17).

1. **Run every remaining check first, unstaged.** Don't gate scene N+1 behind scene N's fix — run all `/consistency-check` passes for the whole stage back to back, VTT-adjudicate every finding the same way you would 1x1 (still required, not optional — see the delegated-workflow table above), *then* build one artifact covering everything at once. Confirm the reordering with the user first (ask: build incrementally as each scene closes, or run everything then present one artifact?) — don't silently decide to batch, and don't silently decide what's in scope (e.g. whether already-closed scenes/stages are included as a read-only record). **At Stage 2, "back to back" is now literally one call** — see the grouped invocation in step 4 — which is another reason to settle the choice before running anything rather than after N per-scene reports already exist.
2. **Build ONE interactive HTML artifact**, not one per scene. Load `artifact-design` before writing it — a decision ledger still deserves real typographic/layout care, not a bare form — and `artifact-capabilities` before declaring any capability. Each finding becomes a card: id, scene, severity, title, one-line detail, evidence, your recommendation, and Accept / Reject / Discuss controls. A Discuss selection reveals a free-text note field.
3. **Use the `downloads` capability, not `artifact`.** `artifact`'s live-sync semantics (`<artifact-sync>` regions, conflict/not_writer states) are built for pages that ARE the shared record — a poll, a shared checklist that multiple people edit over time. A one-shot decision export doesn't need that. `downloads.save({filename, data})` has a simple, fully-specified contract and matches what the user actually asked for ("download the artifact and my choices"). Don't reach for `artifact` just because it sounds more capable — read both type definitions and pick the one whose contract you can actually verify without live-testing.
4. **Export schema**: a flat JSON array of `{id, scene, severity, title, target, status, note}` per finding — `status` is `"pending" | "accept" | "reject" | "discuss"`, `note` carries the Discuss free text. Keep `target` explicit per finding (which file the fix lands in — a scene doc, `gm-assist.md`, a glossary, even a GitHub issue) since one artifact will often span fixes landing in different documents.
5. **When the exported JSON comes back:**
   - `accept` → apply the fix to `target` exactly as evaluated during VTT adjudication.
   - `discuss` → **read the note first.** Users often write the actual ruling directly in the note ("Fix to Norbus", "It was on Valphine", "Everyone but Vukradin saw it") rather than waiting for a live back-and-forth — treat an unambiguous note as a ruling and apply it; don't manufacture a redundant round of questions the note already answered. Only take a `discuss` item to actual conversation when the note is genuinely ambiguous, asks *you* to go do something first (re-check the tape, check what a rules module says) before a decision is possible, or is empty/silent.
   - `reject` → no edit; record the ruling in the manifest and move on.
6. **Fix-propagation (step 6 below) still applies, at full strength, and often surfaces gaps the artifact review didn't cover.** An artifact-driven review usually scopes itself to one document class (e.g. "scenes 03–10 only," explicitly excluding already-closed stages) by the user's choice — respect that scope for what gets *reviewed*. But the propagation sweep still has to check every sibling document (`session-summary.md`, `gm-assist.md`, grounding docs, and — if the user says so — already-closed earlier scenes) for the same stale facts, even ones outside the review's scope, and that includes checking the sibling document's OWN prose/bullet sections, not just the one place you already touched (a doc can restate the same fact in its Summary paragraph, its Scenes bullets, and its Items section — fixing one and missing the other two is a real, repeatable mistake). Don't silently expand what gets *reviewed*; don't silently skip propagating an *approved* fix to a sibling document just because that document wasn't in the review's scope — those are different questions. If the user later asks why a sibling wasn't fixed, that's the answer, and propagating it now is a mechanical follow-up, not a new review round.
7. **Visible external actions drafted from a finding (e.g. "post a comment on GitHub issue #N") still need explicit go-ahead separately from the Accept click.** An artifact Accept authorizes the *content* of the action; posting itself may still be blocked by the permission layer as a visible external effect. Draft it, hold it, and post only once the user says so in chat — then record the resulting URL in the manifest.
8. Manifest each finding the same as any other ruling (step 7 below) — note in `resolution.applied`/`resolution.rejected` that the ruling came via the artifact's JSON export, and whether a `discuss` item was resolved straight from the note or required actual back-and-forth.

### 2. Stage 0 — gm-assist check

> Stage 0 — running `/consistency-check $SESSION/gm-assist.md` with the standard context set + prep.

Run the full `/consistency-check` workflow against `$SESSION/gm-assist.md`, passing the standard context set and every prep file from step 0 in one `--context` flag, with `--backend claude-code`. Then:

- Present the severity table (format above).
- Ask: "Apply any of these fixes to `gm-assist.md` before moving to stage 1?"
- If yes, edit `gm-assist.md` directly. If no, log what was deferred so it can be revisited.

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

Stage 2 has **two call shapes**. Which one you use is the same decision as "Alternative sign-off" above, so settle it with the user *before* running anything:

- **Interactive (per-scene).** Run `/consistency-check` once per `$SESSION/scene_extractions_new/0N_*.md` in numbered order, present a severity table per scene, and gate each scene on the previous one's fixes. Unchanged.
- **Batch (grouped).** Pass **every selected scene path, in scene order, to one `check_consistency.py` invocation**. The script audits all of them in a single model call: the shared material (system prompt, canon section, `campaign_state` + `world_state`, registry, glossaries, prep) is transmitted once instead of N times, and the model must return one result section per scene plus one cross-scene section. Use this when you are heading for the artifact sign-off.

In both shapes, exclude `.prev` and `.scaffold` and enumerate the scenes explicitly. **Never say "all" and never let a shell glob decide the list** — the manifest has to record exactly which documents were audited, and in grouped mode the order you pass is the order attribution is keyed to.

**Do not fake grouped mode.** N single-document checks with their reports concatenated is a different run: it re-sends the whole context N times, produces no cross-scene section, and gets none of the attribution validation below. Grouped mode is not a flag — the script switches on it as soon as it receives more than one document path, and loads a different agent prompt (`config/agents/session_doc/consistency_grouped.md`).

#### The grouped invocation

```bash
python <repo>/session_doc/check_consistency.py \
  "$SESSION"/scene_extractions_new/<scene-01>.md \
  "$SESSION"/scene_extractions_new/<scene-02>.md ... \
  [--config <campaign-config.yaml>] \
  --backend claude-code \
  --context docs/party.md docs/entity_registry.yaml notes/vtt_transcription_corrections.md notes/vtt_known_additions.md <prep files...> \
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

**Read and count the grouped report yourself.** It is `# Grouped Consistency Report`, then one `## D01 — <path>` section per scene in the order you passed them, then `## Cross-document findings`; a clean scene is the literal word `CLEAN`. The single-document habit of `grep -c "^### "` returns 0 here — count `**Location**` within each `## D` section instead, and reconcile the per-scene totals against the banner before building the severity table. Grouped mode is at least stricter about the `**Location:**` variant that makes single-document runs report a false zero: there, format drift is a protocol failure that stops the run rather than a scene quietly reported clean.

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

In the interactive shape, after each scene's fixes ask: "Continue to next scene, or revisit this one?" Don't auto-advance through all scenes silently. In the grouped shape that gate moves to the artifact rather than disappearing: the grouped report is advisory until the user rules on it, and every finding still needs an explicit Accept / Reject / Discuss before an edit lands. **This is the stage where finding counts routinely justify the artifact alternative** (see "Alternative sign-off" above) instead of a 1x1 walkthrough per scene — offer it once you can see the likely total finding count is large. One grouped call plus one artifact is the flow that scales.

### 5. Stage 3 — narration check (optional)

If a final narration file exists, run `/consistency-check` on it and present a severity table.

At this stage the check is mostly catching narrator-layer voice drift and prose fabrications. Findings here are usually candidates for a narrator re-run (after fixing upstream) rather than direct edits, since editing final prose tends to fight the narrator's voice.

### 6. Fix-propagation pass

After all stages have been checked and fixed, sweep for residual bad patterns — fixes applied to a deep stage may need to propagate upward, and vice versa:

```bash
grep -n "<bad pattern>" $SESSION/gm-assist.md $SESSION/gm-assist-update.md \
  $SESSION/session-summary.md $SESSION/narration/enhanced_sections.md \
  $SESSION/scene_extractions_new/0*.md 2>/dev/null | grep -v ".prev\|.scaffold"
```

Run this for every applied fix. If grep finds the bad pattern in a file that wasn't checked or fixed, surface it and ask whether to apply the fix there. **This step is what catches the scenario where session-summary was fixed but the scene extractions still carry the original error.**

**Also sweep the grounding docs.** Per `/consistency-check` step 5, a VTT-confirmed correction usually lands in more places than the recap — `world_state.md`'s timeline and `party.md`'s per-character notes both carry attributions. Check the direction before editing: in one run the GM asked for a grounding-doc fix and the docs were already right; the recap was the wrong one. Survey first, then say plainly which file was actually wrong. Anything you don't fix goes in `carry_forward`.

**Never bulk-replace a name, colour, adjective or title across the campaign.** Enumerate and read every hit first.

### 7. Manifests — REQUIRED

Per `/consistency-check` steps 4.5 and 6, every check gets a provenance record. Staging changes only the granularity:

- **One manifest per stage**, in the session dir, named for the stage: `consistency_stage0_gmassist.sources.yaml`, `consistency_stage1_summary.sources.yaml`, `consistency_stage2_scenes.sources.yaml`, `consistency_stage3_narration.sources.yaml`.
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
- **The standard context set is not optional and not `party.md` alone.** An earlier version of this skill passed only `docs/party.md`, silently dropping `entity_registry.yaml` and the VTT glossaries from every stage — the three sources that carry the name/alias/garble finding class this skill exists to catch.
- Different pipeline stages fail differently, and the staging should reflect it: **gm-assist** fails on names (prep + glossaries catch it), **session-summary** is an enhanced recap and fails on numbers, attribution and ordering (only the VTT catches those), **scene extractions** fail on verbatim quote fidelity (only the VTT), **narration** fails on voice drift. Expect a poor report hit-rate on the enhanced and verbatim stages and say so, so it doesn't read as the documents being clean.
- **Grouped Stage 2 (#362) is a call-shape change, not a review-gate change.** It batches the Stage 2 audit into one model call so shared context is sent once and cross-scene contradictions become visible at all; it removes no human checkpoint. Findings remain advisory, still need VTT adjudication, and still need an explicit ruling before an edit. If a grouped report ever starts auto-applying anything — glossary anchors included — that is the bug, not a shortcut.
- The Phandalin Ch 41 run (2026-05-17) was the discovery case — 11 prep-canonical issues survived a late-stage one-shot check that returned "no major issues." The same issues were trivially catchable at stage 0 with prep wired in. That's the failure mode this skill exists to prevent.
- See `~/campaigns/STAGED_CONSISTENCY_HOWTO.md` for the methodology rationale, the pipeline diagram, and the per-stage table of what each check catches that the others miss.
