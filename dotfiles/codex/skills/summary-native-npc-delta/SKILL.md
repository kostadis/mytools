---
name: summary-native-npc-delta
description: Update summary-native NPC dossiers from newly reviewed campaign chapters, reusing published history and cached evidence instead of rescanning the campaign. Use for latest-chapter NPC updates or requests to apply only what changed; not for an initial dossier build or full grounding-doc regeneration.
---

# Incremental summary-native NPC updates

Use the last reviewed publication as the baseline and the newly reviewed
chapter as the delta. Preserve prior history; update only NPCs with material
new facts and create dossiers for newly established NPCs. A passing mention
does not automatically require a rewritten dossier.

Before preparing the final review, read [review through application](references/review-and-apply.md). Reuse the session’s model, privacy and review choices; prepare selected native publication alongside the content so the final handoff clearly covers the requested action.

## Establish the bounded inputs

Read campaign instructions and current CLI help. Locate the published dossiers,
their reviewed source drafts, cached evidence and native review/publication
records. Identify the latest reviewed summary and baseline end chapter; do not
pick an older unreviewed export instead of the working branch's reviewed artifact.

Record baseline/new ranges, input hashes, output paths and the requested endpoint
in a durable delta manifest. Do not infer permission to commit, push, merge,
rebuild grounding docs or change unrelated configuration.

## Process only the new chapter

Use a native incremental command if installed. Otherwise read the
[current-toolkit bridge](references/current-toolkit.md) before using lower-level
APIs. Proposed feature commands are not installed capabilities.

Isolate the new chapter as the validator's input. A range filter over an entire
directory may still scan older files. If a numbered flat summary is required,
reuse repository publication/refactor functions on a one-chapter scratch root.
Do not run an all-chapter publisher to obtain one new file. Keep necessary
source-heading normalization separate from narrative edits.

Inspect the complete new chapter and link report. Account for NPCs named only
in scenes, without their own heading. Literal linking can miss a known captive
referenced by pronoun or a boss referenced by title. Record the exact source
and reasoning for any contextual link; preserve source text and make the link
reviewable. Resolve genuinely new or ambiguous contextual/identity rulings before dependent drafting; reuse already settled selections. Do not invent aliases or speaker identities. Follow campaign name
rulings and keep similar names distinct.

Classify each candidate:

- **Changed:** a material new disposition, location report, relationship,
  obligation, identifying fact, behavior or knowledge boundary.
- **New:** an established NPC without a reviewed published dossier.
- **Mentioned but unchanged:** retain the dossier; explain the disposition from
  the new occurrences. Do not fabricate an unchanged-dossier attestation when
  the toolkit has no such receipt mechanism.
- **Excluded or unresolved:** party characters, local/generic entities, unknown
  names and ambiguous identities remain explicit.

## Prepare the smallest supported update

Read cached history only for selected NPCs. Verify that each reused draft is
the one actually published and reviewed. Carry forward historical prose,
citations and quotations; append new events and revise current-state text.
Do not re-summarize old chapters. If a relevant baseline is stale or missing,
identify the affected NPC and repair needed rather than silently running a
full scan.

Keep testimony attributed: reported captivity is not a direct sighting, and
a canonical GM identity is not automatically player knowledge. Carry authored
secrets through the native composer. Do not repair unrelated historical claims
or feed secrets into player-facing prose during this pass.

A sparse selection spanning old and new chapters is **not** a complete rebuilt
campaign corpus. Label it accordingly and record its baseline dependencies.

## Verify, review, publish

Run the native verifier on selected drafts against exact cached-plus-new
evidence. Check new claims for entailment as well as valid citations. Remove
stale current-state statements when new evidence supersedes them. Preserve
unresolved findings as findings.

Prepare a concrete delta review: prose diffs for existing dossiers, full prose
for new ones, supporting evidence and exact draft hashes. Explain unchanged
baseline advisories without turning them into a new editing pass. Honor the
GM's review preferences. Use Tailscale only with authorization for the payload
and destination, following its skill when available. Include the exact selected publication effect and explicit application scope in the final review when publication is requested; do not default an update request to draft-only cards.

Validate actual saved decisions and resolve Discuss/unmarked items. Bind only
explicit approvals to native exact-draft signoffs. When the saved decisions already authorize selected publication, continue directly to that publication and verification; do not create a second approval solely to apply the reviewed drafts. Compose and publish through
the native writers with an explicit NPC selection. Do not hand-edit published
replicas, use force, override a signoff checker or manufacture authority
receipts. If a native gate refuses, preserve the verified work and report the
specific blocker.

Record changed/new/skipped NPCs, decisions, published hashes, verification,
unresolved items and the new-summary scan count. Confirm no unselected dossier
or earlier summary was regenerated. Stop a temporary review server once the
saved review has been validated.
