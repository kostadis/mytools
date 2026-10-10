---
name: batch-chapters
description: Run one or more campaign chapters through a requested range of the post-recording pipeline, including transcript front end, reviewed summaries, staged consistency, and recap removal. Use for "run BATCH.md", "batch these chapters", or "run every phase through a named stage"; individual stage skills still own their methods.
---

# Batch chapters

This skill owns the *whole requested run*: inventory, stage order, review gates, carry-forward, and a final completeness audit. It works for one chapter or several. Read [BATCH.md](BATCH.md) for the batch mechanics and `../review-page/CONTRACT.md` for review pages. The authoritative stage order is `~/src/CampaignGenerator/docs/design/SkillPipelineOrder.md`. Read each stage's `SKILL.md` before running it; that skill owns its method and output checks. Do not substitute this wrapper for a stage skill.

## Define the run

1. Start from a fresh view of `origin/main`, inspect unmerged chapter work, and inventory each chapter's source media, transcript provenance and coverage, speaker labels, Stage 0 source, and existing outputs. Follow BATCH.md's media and cohort checks. Do not infer completion solely from a filename.
2. Resolve the user's endpoint against the pipeline order. “Through X” includes every required preceding stage from the earliest missing one through X, in order. For an already completed stage, inspect its review decisions, applied edits, manifest, and verification before marking it complete. Treat optional stages as specified by the pipeline and the user's scope; record why an optional stage was run or skipped.
3. Make a durable run ledger, with one row per chapter and stage. Record `NOT STARTED`, `RUNNING`, `AWAITING GM`, `COMPLETE`, `BLOCKED`, or `NOT APPLICABLE`, the input and output paths, the review decision file, verification result, and any carry-forward item. Update it after every stage. A `BLOCKED` chapter is explicit; it is never silently omitted from the batch.
4. Show material input gaps and ask for decisions only where the existing session does not already authorize a choice. Preserve the selected model and prep set across every model-bearing consistency stage.

## Execute every stage through the endpoint

For each chapter, use the pipeline order. Transcript front-end stages use their own attribution and spell-pass apply procedures. Document-editing stages use BATCH.md's full review loop: deterministic run, adjudication, validation, review handoff, saved decision read-back, re-asks, dry-run, apply, manifest, verification, and stage commit when the repository workflow calls for it. A later stage cannot consume output that is still awaiting GM review.

Before moving forward, check the stage's own completion evidence:

- Inputs came from the intended recording and prior reviewed artifact; the transcript and prep choices are recorded.
- Every review card has a saved ruling or a recorded chat ruling. Unmarked, unsaved, and Discuss items remain open until resolved.
- Approved edits landed in the named target files with exact counts. Tape corrections were regenerated and checked through the owning transcript skill. Earlier-stage carry-backs were applied only when the ruling covers those files.
- The stage manifest records the sources, rulings, false positives, open items, and verification. Run the stage's quote and inline-quote checks where required; an automated flag needs manual VTT adjudication.
- Search the next generated artifact for ruled wording that may have been reintroduced. Resolve conflicts against the earlier ruling before advancing.

For a run ending at recap removal, the ledger must explicitly account for speaker attribution or its applicable alternative, VTT spell pass, Stage 0 consistency, enhancement, Stage 1 consistency, and recap removal. At Stage 1, record that the reviewed Stage 0 draft was supplied as context, and record both blockquote and inline quote results. If an old run omitted either check, complete that check before counting Stage 1 as done. These are evidence gates, not extra stages.

If work pauses at a review gate or context boundary, leave the ledger with the exact next action and unresolved IDs. Resume from that ledger and revalidate current files; do not skip a pending gate or repeat an already applied edit.

## Close the run

Audit the ledger against every stage from the earliest needed stage through the requested endpoint. Mark each `COMPLETE`, `NOT APPLICABLE` with reason, or `BLOCKED` with the missing input or ruling. Verify the final artifact and report the chapters completed, stages not run, open items, and the next pipeline stage. Do not describe the full requested flow as complete while any in-scope ledger row is unresolved.
