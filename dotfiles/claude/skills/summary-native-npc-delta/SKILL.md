---
name: summary-native-npc-delta
description: Update a campaign's summary-native NPC dossiers from one newly reviewed chapter, reusing the published history and cached evidence instead of rescanning the campaign. Changed NPCs get their history carried forward byte-for-byte with the new events appended; newly established NPCs get a new dossier; mentioned-but-unchanged NPCs are explained, not rewritten. Native verification, a GM review page, exact-draft signoffs and the native publisher gate every change. Use for latest-chapter NPC updates or "apply only what changed"; not for an initial dossier build (npc-compose over the full range) or a grounding-doc rebuild (/grounding-refresh). Invoke as /summary-native-npc-delta [campaign-dir] [new-chapter].
tools: Read, Edit, Write, Bash, Glob, Grep, AskUserQuestion, Artifact
---

# Incremental summary-native NPC updates

Use the last reviewed publication as the baseline and the newly reviewed
chapter as the delta. Preserve prior history; update only NPCs with material
new facts and create dossiers for newly established NPCs. A passing mention
does not automatically require a rewritten dossier.

**What this removes from the GM:** nothing. The model proposes which NPCs
changed and drafts the appended prose; the GM rules on every selection and
every draft before a native writer publishes it. Selection (which NPCs are
touched) is a scope decision, and contextual links (a pronoun or title tied to
a named NPC) are attribution decisions. Both are reviewed, never inferred.

## Establish the bounded inputs

Read the campaign's `CLAUDE.md` and the current CLI help
(`summary_native --help`, `summary_native npc-link --help`, and so on).
Locate the published dossiers, their reviewed source drafts, the cached
evidence and the native review/publication records. Identify the latest
reviewed summary and the baseline end chapter. Do not pick an older,
unreviewed export over the working branch's reviewed artifact.

Record the baseline and new ranges, input hashes, output paths and the
requested endpoint in a durable delta manifest. Do not infer permission to
commit, push, merge, rebuild grounding docs or change unrelated configuration.

## Process only the new chapter

Use a native incremental command if one is installed. Otherwise read the
[current-toolkit bridge](references/current-toolkit.md) before using
lower-level APIs. Proposed feature commands are not installed capabilities.

Isolate the new chapter as the validator's input. A range filter over an entire
directory may still scan older files. If a numbered flat summary is required,
reuse the repository's publication/refactor functions on a one-chapter scratch
root. Do not run an all-chapter publisher to obtain one new file. Keep any
necessary source-heading normalization separate from narrative edits.

Inspect the complete new chapter and the link report. Account for NPCs named
only inside scenes, without their own heading. Literal linking can miss a known
captive referenced by pronoun or a boss referenced by title. Record the exact
source and reasoning for any contextual link, preserve the source text and make
the link reviewable. Do not invent aliases or speaker identities. Resolve every
name through the campaign's canonical source chain and keep similar names
distinct; a name that deviates from canon is asked, never normalised.

Classify each candidate:

- **Changed:** a material new disposition, location report, relationship,
  obligation, identifying fact, behavior or knowledge boundary.
- **New:** an established NPC without a reviewed published dossier.
- **Mentioned but unchanged:** keep the dossier; explain the disposition from
  the new occurrences. Do not fabricate an unchanged-dossier attestation when
  the toolkit has no receipt mechanism for one.
- **Excluded or unresolved:** party characters, local or generic entities,
  unknown names and ambiguous identities stay explicit.

Show the GM this classification, with the contextual links, before drafting
anything. Drafting against an unreviewed selection is the bad pattern
(LLM extracts → LLM structures → LLM renders).

## Prepare the smallest supported update

Read cached history only for the selected NPCs. Verify that each reused draft
is the one actually published and reviewed. Carry forward historical prose,
citations and quotations; append the new events and revise the current-state
text. Do not re-summarize old chapters. If a relevant baseline is stale or
missing, name the affected NPC and the repair it needs rather than silently
running a full scan.

Keep testimony attributed: reported captivity is not a direct sighting, and a
canonical GM identity is not automatically player knowledge. Carry authored
secrets through the native composer. Do not repair unrelated historical claims,
and do not feed secrets into player-facing prose, during this pass.

A sparse selection spanning old and new chapters is **not** a complete rebuilt
campaign corpus. Label it as sparse and record its baseline dependencies.

If a step calls a backend model, pass the model the campaign has agreed on
explicitly. Never rely on a CLI's default model, and pass only the needed
baseline and delta, not every earlier summary.

## Verify, review, publish

Run the native verifier on the selected drafts against the exact cached-plus-new
evidence. Check new claims for entailment as well as for valid citations.
Remove stale current-state statements when new evidence supersedes them. Keep
unresolved findings as findings.

Prepare a concrete delta review: prose diffs for existing dossiers, full prose
for new ones, the supporting evidence and the exact draft hashes. Explain the
unchanged baseline advisories without turning them into a new editing pass.

- **A handful of NPCs:** ask in chat with `AskUserQuestion`, one dossier at a
  time, each with its diff and evidence.
- **More than about a dozen rulings:** publish one Approve / Reject / Discuss
  review page with the `Artifact` tool, one card per dossier, each with a
  keep-baseline option, and a Markdown export the decisions can be parsed back
  from.

Read the saved decisions back before acting. An unmarked card is not a verdict:
re-ask it. A Discuss note is an instruction to talk: state your reading and
confirm it before applying. Bind only explicit approvals to the native
exact-draft signoffs. The GM signs; you never sign on their behalf.

Compose and publish through the native writers with an explicit NPC selection.
Do not hand-edit published replicas, use `--force`, override a signoff checker
or manufacture authority receipts. If a native gate refuses, keep the verified
work and report the specific blocker.

Finish by recording the changed, new and skipped NPCs, the decisions and how
many came back unmarked, the published hashes, the verification results, the
unresolved items and the new-summary scan count (it should be one file).
Confirm that no unselected dossier and no earlier summary was regenerated.
