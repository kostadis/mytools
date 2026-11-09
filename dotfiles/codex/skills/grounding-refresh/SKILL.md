---
name: grounding-refresh
description: Refresh a campaign's world_state, campaign_state, party, and planning documents from structured session summaries. Choose full regeneration or an incremental update that applies selected new chapters to an existing baseline, then review and publish through supported gates. Use for grounding-document refreshes, summary-native grounding generation, official bundle promotion, or bounded corrections to published grounding prose. For latest-chapter NPC dossier updates alone, use summary-native-npc-delta.
---

# Grounding refresh

Use CampaignGenerator's summary-native pipeline to produce the four grounding documents as an index over reviewed summaries. Generation produces drafts; managed promotion publishes the four documents, canon timeline, and complete reference tree together. For a full refresh, do not hand-write replacement grounding documents or copy individual drafts over the live bundle. A chapter-delta run proposes minimal edits to bound baseline drafts; it is not a full-range synthesis.

Read [references/runbook.md](references/runbook.md) for execution and the relevant current CampaignGenerator manual section before each phase. Flags, hashes, review-item IDs, and recovery contracts must come from the installed CLI, not remembered examples. The toolkit normally lives at `~/src/CampaignGenerator`.

## Choose a mode

- **Full refresh:** use the range-wide workflow below and the runbook.
- **Incremental update** (`incremental`, also called `chapter-delta`): when the user requests incremental updates, only new/latest chapters, or no full scan, read [references/chapter-delta.md](references/chapter-delta.md) and use an exact baseline plus only those chapters. Do not execute the full-refresh steps as a fallback. Invocation example: `$grounding-refresh obelisk --mode incremental --chapters 013`. This is skill invocation syntax, not an installed CampaignGenerator CLI command.

## Scope and decisions

- Establish the campaign root, explicit chapter range, and requested stopping point. Reuse decisions already made. A draft-only request does not authorize migration or publication.
- Read campaign `AGENTS.md`/`CLAUDE.md` and applicable guidance. Preserve canon precedence, audience boundaries, and distinctions between GM truth, party knowledge, and NPC belief. Fix authored summaries at their origin and regenerate derived flat summary corpora where required.
- A full refresh is range-wide with reusable extraction caches. A chapter delta must bound source reads to the selected new chapters plus the existing baseline and explicitly relevant rulings. For NPC-only changes, use `$summary-native-npc-delta`; its sparse corpus is not a complete grounding baseline.
- Pass explicit authorized backend, model, and supported reasoning effort on every model call. Honor the user's generation and consistency model choices; do not carry over Claude defaults. Ask only for material choices still missing. Do not silently change providers or models on failure or limits.
- The GM decides thread ratification, claims coverage and scope rulings, normalized claim meanings, reviewer identity, canon corrections, and each document's exact current sign-off. Model findings propose decisions. Never infer reviewer identity from Git or treat unanswered questions as approval.
- Ask necessary questions one at a time when requested. Use a review page for long queues when applicable guidance calls for it. Phone review may save decisions; it does not independently authorize source selection, model calls, migration or publication.
- Migration requires review of its concrete plan. Publication requires valid current review/check bindings and a fresh eligible preview. Honor existing explicit authorization without repeated permission requests.

## Incremental review experience

Before a delta review, read [review through application](references/review-and-apply.md). Prepare the exact application plan before the final handoff, make approval scope explicit, and consume saved approvals through application without another confirmation when they already cover that action. Preserve explicit draft-only requests and every native gate.

## Incremental workflow

1. Bind the existing live documents and retained origin drafts to a baseline snapshot, then select only the new reviewed chapters. Keep gaps in baseline coverage explicit.
2. Give generation numbered baseline paragraphs or lines. Let the host validate identifiers and preserve untouched text; the model proposes replacement text rather than reconstructing exact old strings.
3. Check new claims, superseded current state, citations, headings/tables and retained history with the selected consistency model. Restore original fragments directly instead of regenerating unrelated prose.
4. Present complete candidates, readable changes, evidence and the prepared application effect in the same final review where possible. Bind content approval and the required application authorization explicitly; validate saved decisions and resolve only pending or stale items.
5. Apply through the supported native path, or a documented and explicitly authorized guarded local correction with retained origins and an honest receipt. Reuse an already granted exception within its exact scope; otherwise request it with the concrete plan in the final review. Never bypass managed publication or alter immutable members.
6. Verify live bytes equal the approved origins, preserve baseline backups and evidence, stop temporary review serving after saved decisions are validated, and report the actual application status.

## Full-refresh workflow

1. Inspect configuration/capabilities; validate and build the explicit range.
2. Extract checked notes and inspect dropped evidence. Synthesize `world_state`, audit tracking claims, then synthesize `campaign_state`, `party` and `planning`.
3. Review drafts and references against summaries, GM rulings and applicable prep. Resolve source errors and regenerate; surface budget overruns and unratified threads.
4. For requested publication, inspect migration status and complete an approved migration only if needed.
5. Confirm claims scope/coverage, review meanings/findings, obtain current exact document sign-offs, and rerun checks after changes.
6. Preview/promote the whole bundle and verify its receipt/layout. Preserve operation IDs for recovery.
7. Report results and pending work. Commit/push/open a PR only within the user's Git scope.

For maintenance, read [references/port-review.md](references/port-review.md), which records the Claude source and deliberate adaptations. It is not required for an ordinary refresh.
