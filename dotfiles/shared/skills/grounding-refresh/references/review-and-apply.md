# Incremental update: review through application

Read before preparing a grounding or NPC delta review. Aim for a complete, concrete review-to-apply handoff within the user's requested scope. Required source, identity and canon decisions still belong to the GM; fewer prompts must not mean inferred approvals.

## Establish the intended result

Reuse the campaign, reviewed chapter, model/effort, data-sharing choices, review transport and existing permissions already supplied in the session. Do not ask for them again merely because a stage or skill changed. Briefly state the selected chapter, inherited baseline and intended stop: drafts, applied/published documents, or explicitly requested Git delivery. An ordinary request to update documents calls for preparing their application as well as their content; it does not grant a missing exception, authorize unrelated changes, or override an explicit draft-only request.

Resolve only choices that change the result. Prepare independent work while a required ruling is pending. Make new or ambiguous identities/contextual links reviewable before dependent drafting; reuse already settled selections. Routine read-only planning and checks do not need their own permission round.

## Prepare the application before the final review

Inspect the installed capabilities and campaign origin rules early. Prefer the native writer. If a local editable-live correction is both documented and permitted by campaign guidance, prepare its exact guarded plan and the required exception request before presenting the content for final review. Do not discover a known publication limitation only after the GM has approved draft-only cards.

Bind the final candidates, checks, destinations, before/after hashes, retained origins, backups and application method. Include any disclosure/header change in the proposed applied bytes now. Explain the user-visible limits: for example, four live grounding documents advance while the timeline and reference tree retain their earlier coverage. Keep native promotion, a local correction and draft acceptance distinct in the record.

If neither the native path nor a permitted local correction can complete the requested update, say what cannot be applied before handing off the drafts. Preserve the bounded work; do not silently migrate the campaign, rescan history or invent an exception. A real unresolved capability/authorization gate is a reason to stop; an omitted application plan is avoidable rework.

## One final review handoff where possible

Honor the requested review format; reuse authorized Tailscale hosting. Lead with readable changes and their effect, with complete candidates, source evidence, paths and exact hashes available in details. Show diffs for existing material, full prose for new dossiers and a keep-baseline option. Group related rulings so the user does not have to repeat settled choices across skills.

State the approval scope on the page and in the handoff. When application is requested and its plan is ready, the same artifact can collect exact content decisions plus explicit authorization for the displayed application/exception. If the native gate needs a separate application decision, include that action in the same handoff when supported. Do not manufacture extra sign-off items, weaken native gates, or skip an earlier genuinely required identity/selection ruling to achieve a fixed number of reviews.

- **Update review:** “Approve the changes you want and Save. Approval also authorizes the displayed application plan; I’ll validate the saved decisions, apply the approved scope and verify it.”
- **Draft-only review:** “This approves the displayed drafts only. Live documents stay unchanged.” Use this when the user chose that stop or no applicable write path exists, and explain the consequence before review.

Keep decisions unselected until the GM acts. Discuss, unmarked and unsaved items remain unresolved. If only some items are approved, honor the recorded application scope: publish that subset only where native semantics and dependencies permit it; otherwise report the held scope. Do not silently turn a four-document plan into a partial managed grounding generation.

## Consume decisions and finish

A user saying “done” prompts reading the actual saved decisions; it is not a substitute for them. Validate the review identity, complete item set, explicit scopes and all source/baseline/candidate/check/application bindings. Resolve only Discuss/unmarked items or changed bindings. Preserve prior approvals as history when new evidence makes them stale.

If the saved approval already authorizes the exact application, proceed through the appropriate writer, verify the resulting bytes/receipts and report completion. Do not ask “may I apply?” again or create another application card solely because the draft review has finished. If an existing page really was draft-only, preserve that boundary: prepare the concrete application and explain why its one missing authorization is still required. Do not repeat content review unless its bindings changed.

Recheck native previews/preconditions immediately before application. Reuse existing explicit authorization when intent, reviewed content, destinations and effects remain the same; a changed proposal needs renewed affected review. A changed source or live baseline must not be overwritten to keep the handoff short.

## The NPC verification review loop (card contract)

When the delta's review is a summary_native `npc_verification` review, the page goes through CampaignGenerator's card contract. You never translate page verdicts into `review decide` or `review npc sign` calls, and you never build a decision batch by hand. The kit is `_shared/review-artifact/` under the runtime's skills directory (`~/.claude/skills/` for Claude, `${CODEX_HOME:-~/.codex}/skills/` for Codex). Its contract is `CONTRACT.md` there, section "NPC reviews". Where the runtime has no Artifact tool (Codex) the page is built with `--save local`, which never writes state into the page; the GM's export is a `decisions.json` instead.

1. `npc_review_items.py REVIEW_DIR --out items.json`: a shim over `summary_native review cards export`. It lists only items with no current approve or reject and never shows a card the GM cannot validly approve.
2. `build_review.py --in items.json --out page.html` (Claude: publish it as an Artifact) or `build_review.py --in items.json --out page.html --save local` (Codex: serve it with `serve_review.py --items items.json`, or hand over the file).
3. The GM marks cards and saves. An unmarked card stays unmarked.
4. Write the CampaignGenerator decisions file:
   - Claude, from the saved artifact page: `read_decisions.py --npc --html saved.html --review REVIEW_ID --out decisions-cards.json`. The `members` and `draftSha256` echoes come from the page.
   - Codex, from the exported `decisions.json`: `read_decisions.py --npc --in decisions.json --items items.json --review REVIEW_ID --out decisions-cards.json`. The export is validated against `items.json` (item set and reviewId = the packet id), and `members` and `draftSha256` come from `items.json`, never from the export.

   Either way CampaignGenerator refuses the whole file if the echoes differ from its stored packet. A note written on a card the GM left unmarked cannot be recorded; the command prints each one under "UNMARKED CARDS WITH A NOTE". Ask the GM what it means.
5. `summary_native review cards decide REVIEW_ID --decisions decisions-cards.json --reviewer GM`: prints the **plan** and records nothing.
6. Show the plan to the GM and get their confirmation. A Discuss note is an instruction to talk, not a verdict.
7. Re-run with `--write --plan-sha256 HASH`. The hash binds the write to the plan the GM saw; a changed plan is refused.

Then compose and publish through the native writers as above.

## Review availability and status

Verify the Tailscale URL and decision-saving capability before sharing it. Keep the task's server in a persistent session while review is pending and retain its identity. If the user reports a dead endpoint, check it, restart only that task's server when needed, verify the new URL and provide it without another permission question within the existing hosting authorization. Preserve the review ID, candidate revision and decision destination; restarting serving must not rerun generation, reset saved choices or imply approval.

Stop the temporary server when its saved review is consumed and no longer needed, or when deliberately replacing that task's page. Keep runtime URLs/session handles separate from durable review and publication evidence.

Progress messages should identify what is ready, what remains uncertain and the next user action. Lead the final response with **applied/published**, **approved drafts only**, **partial**, or the exact blocked action. Then give the main changes, verification and receipt, with inherited coverage limits where relevant. Do not describe native publication as complete when only a local correction or draft review occurred. Commit/push/PR/merge remain within the user's separate Git scope.
