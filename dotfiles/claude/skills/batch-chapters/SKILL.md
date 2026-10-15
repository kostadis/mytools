---
name: batch-chapters
description: Run one or more campaign chapters through a requested range of the post-recording pipeline — transcript front end, Stage 0 consistency, enhancement, Stage 1 consistency, remove-recap — with inventory first, one general-purpose agent and one review page per chapter per stage, all-or-nothing apply, and a run ledger that keeps every chapter × stage accounted for. The stage skills still own their methods. Use when the user says "batch these chapters", "run BATCH.md", "run chapters X–Y through <stage>", or "take the new chapter through every phase up to <stage>". Invoke as /batch-chapters [through-stage] [session-dir ...].
tools: Read, Write, Edit, Bash, Glob, Grep, Agent, AskUserQuestion, Artifact, Skill
---

# Batch chapters

This skill owns the **whole requested run**: inventory, stage order, review
gates, carry-forward between stages, and a final completeness audit. It works
for one chapter or several. It does not own any stage's method: read each
stage skill's `SKILL.md` before running that stage, and let it decide how the
stage is done and checked.

Read these before the first stage:

- `~/.claude/skills/_shared/batch-chapters/BATCH.md` — the mechanics: inventory
  and cohorts, the per-stage loop, agent briefs, the findings schema, read-back
  without rubber-stamping, cross-chapter checks, tool gaps and environment
  traps. This skill does not restate it.
- `~/.claude/skills/_shared/review-artifact/CONTRACT.md` — the review page.
- `~/src/CampaignGenerator/docs/design/SkillPipelineOrder.md` — the single
  authoritative stage order.
- The campaign's `CLAUDE.md` — canon chain, glossary-inversion rule, the
  dozen-rulings artifact threshold, one campaign per commit.

Plumbing: `~/.claude/skills/_shared/batch-chapters/batch.py`
(`validate | read | apply | manifest`). Archived agent briefs:
`~/.claude/skills/_shared/batch-chapters/briefs/{stage0,enhance,stage1,recap}.md`.

## 1. Define the run

1. **Inventory from a fresh branch off `origin/main`**, plus
   `git log --all --oneline -- <chapter dir>` for unmerged work. Media
   (`.m4a`, `.mp3`) are untracked: look for them in the main checkout by
   absolute path. Record per chapter: recording, each transcript's tool and
   coverage, speaker labels against the roster, Stage 0 source filename, and
   which stage outputs already exist (BATCH.md, "Before the first stage").
   Never infer that a stage ran from a filename alone.
2. **Resolve the endpoint against the pipeline order.** "Through X" means every
   required stage from the earliest one *any* chapter is missing, through X, in
   order — never just X. For a stage already done, check its decisions,
   applied edits, manifest and verification before counting it complete.
   Optional stages (`[ ]` in the order) run only when the user's scope says so;
   record why each was run or skipped.
3. **Split into cohorts by path.** A chapter that needs a different attribution
   route or lacks an input goes under `"blocked"` in `batch.json` with a
   reason. It is never forced through a path it does not fit, and never
   silently dropped.
4. **Show the gaps, then ask once.** A table, one row per chapter: what it has,
   what it lacks, what each gap costs. Then one `AskUserQuestion` set for every
   run-wide decision: stages per chapter, model, each blocked chapter, each
   chapter's single-source acceptance, replacing older `session-summary.md`
   files (name the `scene_extractions*/` and `narration/` dirs that go stale),
   and the prep set (with commit dates beside each file). An unanswered or
   timed-out question is not a decision: re-ask.
5. **Write the run ledger** at `$S/batch_<name>/LEDGER.md` (`$S` = the session
   scratchpad), and `batch.json` beside it. One row per chapter × stage:

   | chapter | stage | status | inputs | outputs | decisions file | verification | carry-forward |
   |---|---|---|---|---|---|---|---|

   Status is one of `NOT STARTED`, `RUNNING`, `AWAITING GM`, `COMPLETE`,
   `BLOCKED` (with the missing input or ruling), `NOT APPLICABLE` (with
   reason). Update it after every stage. Keep the cycle's standing rulings in
   `$S/batch_<name>/RULINGS.md` and append each one the moment the GM makes it.

## 2. Run each stage through the endpoint

Follow BATCH.md's loop. In short:

- **Deterministic run:** the stage's CLI, one process per chapter, with the
  model the GM chose passed explicitly. Prefix CampaignGenerator CLIs with the
  backend the campaign requires (Phandalin: `CG_BACKEND=claude-code`).
- **Agent per chapter:** `subagent_type: "general-purpose"`, never `fork`, with
  `model` passed explicitly. Spawn each chapter's agent as soon as its
  deterministic run exits. The brief is a copied archive brief plus the
  chapter-specific facts and the path to `RULINGS.md`. Agents write only
  findings, items and the page builder: no publishing, no campaign edits.
- **Validate:** `batch.py validate --config batch.json --stage <s>`.
- **Below about a dozen cards across all chapters**, rule in chat, one question
  per card with exact before and after text. Otherwise **publish** one Artifact
  per chapter, record each URL under `urls.<stage>`, hand over the links, and
  **stop** until the GM says "done". Watches run out at 10 per session, so plan
  on "done" from the start.
- **Read back** every page (`Artifact read`, `path: index.html`, record the
  saved path under `artifacts.<stage>`), then `batch.py read`. Unsaved pages,
  unmarked cards, Discuss notes, approvals with no replacement text, and
  approvals whose own evidence argued against them all go back to chat, with
  ±4 cues of context and speaker labels. A Discuss with no note comes back
  with your best guess from that context as the first option, for the GM
  to confirm. Record answers, in the GM's own words, in `chat_rulings.json`.
- **Apply:** `batch.py apply ... --dry-run`, then for real. It writes nothing
  in any chapter until every card resolves and every count matches.
- **Manifest** (`batch.py manifest`), the stage's own verification (quote
  checks and so on), then **one commit per stage, one campaign per commit**.
  Check `git diff --cached` for audio files after any broad `git add`.

Transcript front-end stages (`/speaker-attribution`, `/vtt-spell-pass`) use
steps 0–7 only (`batch.py read --review-dir ... --plain-names`); their apply
belongs to their own skill. Diarization is a queue, not a fan-out: start it
first and publish each chapter's page as its job finishes.

### Gates before advancing a chapter to the next stage

- Its inputs came from the intended recording and the previous *reviewed*
  artifact. A later stage never consumes output still `AWAITING GM`.
- Every card has a saved page ruling or a recorded chat ruling.
- Approved edits landed in the named files with exact counts. Tape corrections
  went through `transcript_corrections.yaml` and `sd_corrections apply/check`.
  Edits to the Stage 0 source were made only where the ruling covered that file.
- Every edit landed in its **origin** file, and the files generated from it
  were regenerated with their own tools, never hand-edited. See BATCH.md,
  "Edits go to the origin file, never a replica", and the campaign
  `CLAUDE.md`.
- The stage manifest records sources, rulings, false positives, open items and
  verification.
- The next stage's output is searched for wording an earlier ruling removed. A
  re-introduction becomes a card that quotes the earlier ruling.

For a run ending at remove-recap, the ledger must account for speaker
attribution (or its alternative), the spell pass, Stage 0, enhancement,
Stage 1 and remove-recap, for every chapter.

### Pausing

At a review gate or a context boundary, leave the ledger with the exact next
action and the open card ids. On resume, re-read the ledger and re-validate
the current files. Never skip a pending gate, and never re-apply an edit that
already landed.

## 3. Close the run

Audit the ledger: every in-scope row is `COMPLETE`, `NOT APPLICABLE` with a
reason, or `BLOCKED` with what is missing. Report the chapters completed, the
stages not run, open items, the commits, and the next pipeline stage per
chapter. Do not call the requested flow complete while any in-scope row is
unresolved.
