# Incremental grounding updates (chapter delta)

Read for `--mode incremental` (alias `chapter-delta`) or a natural-language request to update existing grounding documents using only specified new chapters. These are skill method selections, not installed CLI flags. This mode preserves the existing historical projection and applies only new/superseding facts. `--since N --until N` on ordinary synthesis is a one-chapter rebuild, not a baseline merge.

## Establish the bounded inputs

1. Read campaign guidance and current CLI/manuals for an actual native grounding-delta capability. Prefer it if it preserves the bounds below. Do not invent a command from the skill's invocation example.
2. Select the exact existing baseline for `world_state`, `campaign_state`, `party` and `planning`: active managed generation and corresponding origins/review records where available, or an explicitly identified legacy baseline. Snapshot and hash each member before generation.
3. Read only the selected reviewed chapter source(s). Record paths/hashes, baseline identity/coverage, selected chapter numbers and exact extra rulings supplied to the run. Do not enumerate/read historical summary bodies through a convenience corpus loader. A range filter may still scan all files; use an isolated input containing only the selected chapters if validation/build is needed.
4. Track coverage per member: newer live prose does not advance an inherited timeline/reference tree. Distinguish selected summary parsing/model input from integrity-only hashing of historical custody; report both honestly.
5. Report baseline coverage honestly. A largely Chapter 9 baseline plus Chapter 13 is not a complete refresh through Chapter 13; preserve gaps without silently backfilling Chapters 10–12. Do not require a full scan merely because the baseline is imperfect. Flag a specific gap only when it prevents a particular delta decision.

Reusing the four baseline documents is expected. Reading all old summaries, rerunning their extraction, redrafting their history or substituting a sparse new-chapter corpus for complete campaign history is outside this mode.

## Prepare minimal edits

Use explicit authorized generation backend/model/effort and preserve its run identity. Send only bound baseline text, selected chapters, and relevant authorized rulings. When an unavailable model spelling must be resolved, ask before substituting it. A local bounded bridge may use CampaignGenerator's text-only model adapter if no native delta generator exists; label its artifacts as bridge proposals, not native synthesis records.

Assign stable paragraph or line IDs to the bound baseline. Generate replacements keyed by those IDs, with reasons and source citations. The host supplies exact before-text, validates IDs, rejects duplicate/overlapping edits and constructs derived origin drafts. Do not ask a text-only model to prove uniqueness or filesystem equality; that is host work. Use paragraph replacements for a first pass and narrow line replacements for localized corrections. Do not copy an entire large table merely to change a single cell if a smaller stable edit is practical. Leave unrelated baseline bytes unchanged, including open historical promises, citations, secrets and staging labels.

For each new fact, distinguish new information, superseded current state, resolved thread, historical event, and no material change. Update superseded present-tense claims wherever they recur. Merely appending a current snapshot while leaving a contradictory active threat/location in the body is insufficient. Keep the historical account as history.

Preserve certainty and audience boundaries: testimony is not direct observation; a plan is not an outcome; a planned rest is not a confirmed resource reset; one group's exclusive knowledge is not universal loss of knowledge; an NPC's confused faction account is not an objective map. Do not import GM prep secrets into party knowledge or promote tentative names into canonical faction names. Do not change unrelated old errors during this pass; list them as carried baseline limitations.

Record a conspicuous coverage note in the candidate documents and a manifest with baseline/new-source/output hashes, operation/model identity, changed/unchanged sections, source-read count, preserved gaps and publication status.

## Consistency and GM review

Use the selected consistency backend/model/effort. Check the exact proposed changes against their selected chapter/rulings and baseline, including omissions, duplicated events, superseded current assertions, unsupported new claims, historical preservation and audience leaks. The check is a bounded semantic review, not certification of all inherited prose or a substitute for native claims/sign-offs. Keep findings and dispositions; preserve unresolved issues for the GM. A first pass checks all proposed deltas; after repairs, verify the exact changed spans and outstanding findings instead of reopening history or growing the scope. Do not demand every document repeat every chapter detail. Never label a model failure, empty proposal, or stale output a passed run.

Check preservation as well as correctness: unrelated quotes, source lists and GM staging must survive. Restore unchanged material from the exact baseline rather than asking generation to recreate it. Check section-heading counts, table column widths and citation targets; deleting both copies of a duplicated heading is not a valid repair. Formatting corrections and copies of previously generated text retain their actual provenance. Final consistency bindings must match the exact candidates shown for approval.

Before the final handoff, follow [review through application](review-and-apply.md): present four complete candidates, readable changes, evidence, exact hashes and the prepared application plan. Include explicit application/exception authorization alongside content decisions when the requested update has an eligible path; avoid a draft-only review followed by another card for an already known write plan. Preserve an explicit draft-only request or an actual unsupported-path limitation. Reuse authorized review UI/Tailscale choices, keep approvals unselected, and resolve only Discuss/unmarked or stale items. A model’s consistency pass is not a GM sign-off.

## Apply only through an honest publication path

For managed campaigns, prefer a native delta publication that preserves previous generation lineage, carries unchanged members and binds the reviewed delta. Keep native authority, review, claims, stale-input and idempotency gates. Do not fabricate full-corpus manifests/run receipts, copy files over managed aliases, alter immutable published members or bypass gates just to make delta drafts publishable.

If native delta publication is unavailable, assess the two local cases below before presenting the final review. Do not fall back to a full refresh or describe a local correction as native promotion. If neither local case is permitted, retain the drafts and explain the exact missing capability and unapplied scope before review. File a feature request only when asked.

- **Legacy non-managed files:** follow campaign origin/replica rules. If no regeneration tool exists, prepare the concrete exact-byte application plan and the required exception for the final review. Honor an existing explicit exception within its saved scope.
- **Managed editable-live corrections:** only where the installed toolkit documents editable live files and campaign guidance permits an explicitly authorized between-build correction, use the [post-publication correction path](runbook.md#8-corrections-after-publication). Prepare its exact regular-file destinations, approved origins, backups, hashes and visible coverage limitations. Include the necessary exception authorization in the final review when not already granted. Preserve the active aliases and immutable published generation, metadata and historical receipts. This is a local editable-live correction, not a new managed generation or full timeline/reference refresh. A managed campaign alone is not permission for this exception.

For either local case, validate the saved review identity, complete decisions and explicit application scope; bind decision/mapping/plan hashes, source and retained-origin hashes, expected live bytes and exact planned output. Include any disclosure/header difference in the reviewed applied bytes. Stage the exact approved bytes with original modes, preserve originals, replace only the documented regular files, verify resulting hashes and retain a clearly labeled local receipt. Do not replace managed compatibility/current symlinks or touch immutable members. An already-applied identical update is a no-op; conflicting current bytes require reassessment. Validate completion against approved-after hashes.

A saved approval that already covers this exact plan authorizes proceeding without a second confirmation. A genuinely draft-only card does not: obtain only its missing application authorization after preparing the plan, and explain why the earlier decision did not cover the write. Do not reinterpret “done” as a broader exception or repeat unchanged content review.

Stop on any changed baseline, source or candidate after review. Rebase/regenerate/review affected edits rather than overwriting a concurrent change. An identical repeated update should refuse or become a no-op, not duplicate history.

## Completion record

Report selected chapters, baseline coverage, documents/sections changed, preserved gaps, new/old summary bodies read, consistency findings, GM decisions and exact application/publication status. Keep pending publication distinct from a completed update. Commit/push/PR only within the user's scope.

Example bridge artifacts from the first grounding-delta run live at `/home/kostadis/obelisk/obelisk/notes/grounding_delta/ch013/`. The run completed: four exact draft approvals and a separately recorded legacy-application authorization (that historical run used two handoffs, not a required review sequence), four live files equal to approved origin drafts, and zero older summary bodies read. `manifest.json`, `review_mapping.json`, `decisions.json`, `application_plan.json`, `application_manifest.json`, final consistency records and baseline/draft snapshots retain that lineage. These are campaign-specific examples, not generic commands to rerun blindly. See CampaignGenerator issue #588 for the missing native incremental publication feature.

When preparing a requested commit/PR, use an explicit allowlist for this update's four live documents, origin drafts, baselines, saved review/mappings, final validation/consistency records and application receipt. Retain useful provenance without committing runtime capability URLs, lock files, bulk model prompts/responses, discarded candidates or a private unsubmitted issue draft. Keep independent NPC work separate unless the user includes it in the requested scope.
