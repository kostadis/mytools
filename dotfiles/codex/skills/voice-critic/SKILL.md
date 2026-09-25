---
name: voice-critic
description: Critique existing campaign narration for voice drift, generic prose, ambiguous attribution, and genre or document-budget breaches. Use after narration, scrub, or dialogue-edit, including assembled fable documents. Produce evidence-backed reports and a standalone batch review page; apply only GM-approved fixes, to a separate derived revision.
metadata:
  short-description: Astra voice critique with batch GM review
---

# Voice Critic

Codex/Astra counterpart of the Claude `voice-critic` workflow. Read the actual
narration inputs, critique the selected prose, and present exact, individually
reviewable proposals. Use the active conversation for editorial judgment.
This skill does not select a model, launch a model runner, or regenerate narration.
Record model/effort only when observable; a skill name is not runtime evidence.

## Select the actual text

Resolve an explicit scene, session, narration directory/glob, approved revision,
or assembled document. Reuse an unambiguous active session and the user's batch
preference. Ask only when selection remains ambiguous. Missing narration means
not run; it does not authorize generation.

- Per-scene: obtain scene identity and narrator from YAML frontmatter; deduplicate
  raw and `.scrubbed.md` by scene, preferring the scrubbed copy for normal assembly.
- After dialogue-edit: read `dialogue_edit.sources.yaml`, application records,
  promotion status, and hashes. Critique the latest approved revision of each
  scene: a complete `applied/<revision>/` (its `application.json` present and its
  `scene.md` matching the recorded result hash), or a later voice-critic revision
  derived from it. It outranks a directory scan; an approved revision the GM
  names outranks both. Never critique `candidate.md` or any unapproved candidate.
  For promoted revisions, verify current narration against the promotion record;
  preserve original scene identity and source mapping even when the filename is
  `scene.md`. Resolve conflicts with the GM rather than selecting by modification
  time.
- Say which file was critiqued, per scene, in the report and the final reply.
- Assembled: identify sections from `## <Narrator> — <Scene>` headings and any
  assembly provenance. Do not invent frontmatter or scene numbers. If provenance
  is incomplete, identify the checks that cannot run.

Read every selected scene in full before concluding it is clean. For a session,
read across all selected scenes before reporting convergence and budget findings.
Prepare all requested scenes together; a shared page can contain independent
decisions across the session. Do not impose a scene-at-a-time approval cycle.

## Resolve the rules and provenance

Find the campaign and the applicable CampaignGenerator checkout from local
configuration and logs (common checkout: `~/src/CampaignGenerator`). Read the
current `session_doc/voice.py` and `session_doc/examples.py` to establish the
installed resolver's behavior. If unavailable, use explicit declarations and
record that pipeline-resolution verification could not run.

Read configuration, run records, `config/party.yaml`, `config/players.yaml`,
declared relevant voices and examples, shared examples, party prose if present,
and campaign register/ruling records. In particular, read
`notes/scrub_register_policy.md` and applicable dialogue-edit manifests.

Use declared character identities and paths. Do not infer voices from first names,
prefixes, filename similarity, or undeclared orphan files. A prose `docs/party.md`
is not a YAML voice roster. Only explicitly declared shared examples are global.
Report unused voice/example files without promoting them into prompt inputs.
Stage directions matter when the GM voices PCs; do not equate player and speaker.

Resolve the exact reviewed extraction from narration run/source records and
dialogue-edit provenance. Read it completely for each scene whose dialogue,
attribution, chronology, or interruption provenance is evaluated. Resolve its
verbatim predecessor/VTT only when that check requires it. Never choose the newest
extraction or infer a source solely from a similar filename.

Resolve genre from that render's `.knobs.json` or equivalent run record before
current `config/session_doc.yaml` (`paths.genre_file`). Record both rendered and
current configuration, paths, SHA-256 digests, line counts, and character counts.
Compare recorded digests with current contents; changed files are current guidance,
not proof of what the narrator received. Legacy embedded `narration_genre` text is
historical evidence. When it shows the rulebook was flattened (a multi-thousand-
character value with zero newlines, delivered as a single-line label), call the
flattening the probable cause of the generic or register-wrong prose it would
have governed, and say so in the verdict. Without that evidence, report delivery
uncertainty only. A retired config string is not an
effective rulebook unless the installed loader/run record establishes that.

Distinguish resolved, unset, missing, changed-since-render, and unknown. If an
unconfigured `voice/_genre.md` exists, label it as not established as delivered.
Do not silently use it to claim violations of delivered instructions. Report a
missing expected rulebook prominently; do not run migrations or invent budgets.
Read the actual generator `config/agents/session_doc/narrate/base.md`, including
HARD BANS, and `writing_brief.md` when the effective generation path includes it.
Use retained prompt logs for historical rules when available. Distinguish those
from the current checkout. Never copy a stale list of bans into this skill.

A missing spec disables spec-conflict claims. Use declared examples with an
explicit “grounded in examples only” label; if neither resolves, skip only that
narrator's voice-drift judgment. Every other check still runs on that narrator's
prose: rulebook and HARD BANS, em-dash budget, interruption provenance, orphan
quotes, the ledger, and hatches. The report and verdict say voice drift was not
judged for that narrator, and why. A `[no spec]` result is more often a lookup
bug than a missing file, because `sd_narrate` refuses to start without a declared
spec (#300); recheck the roster declarations first.
Every unavailable input/check must appear in the report, never as a pass.

## Critique and count

Read [references/checks-and-report.md](references/checks-and-report.md) before
performing the review. It defines the coverage, measurement boundaries, report
fields, and handoffs. Take actual bans and limits from resolved rule sources.

Use the installed `voice_lint` mechanical checker: inspect its CLI/help and source
as needed to confirm supported input shapes and aggregation. Run against the
selected revisions and effective genre file. Preserve stdout/stderr and command
details. If it requires assembled headings, build a temporary analysis document
with an exact source/line mapping; exclude duplicate raw/scrubbed variants.
Never count report prose or review copies as narration. If the tool is unavailable,
report that gap and continue the supported reading checks.

Interpret checker errors, warnings, and skipped/config notes separately. Exit 1
usually reports breaches; exit 2 is an invocation/input failure to resolve before
claiming coverage. Confirm semantics against the installed version. Do not edit
the checker or reproduce its hardcoded rule lists during an ordinary critique.

## Reports and the standalone page

Write Markdown review records, then build a standalone page as the default review
surface. Honour a GM who asks for chat only: present the same findings in chat as
one grouped pass and record their actual rulings in the same decision envelope.
No Claude Artifact tool or hosted publish step is required. A review page is a
local file.

For normal per-scene input, write `voice_critique_scene_<NN>_<narrator-slug>.md`
beside the selected narration and `voice_critique_summary.md` for a directory.
For an assembled file, use `<doc-stem>.voice_critique.md`. For dialogue-edit
revisions, put reports under a separate `<session>/voice_critic/<run>/` and record
the selected revision paths; leave frozen dialogue-edit records intact. Preserve
previous completed reviews with a new run/path when necessary.

Keep the review-page files in the session directory, never scratch:
`<session>/voice_critic_review/review_items.json`, `review.html`,
`decisions.json`, and the frozen sidecar `review_map.json`. A follow-up round
suffixes each of them with its round (`review_items_r2.json`, `review_r2.html`,
`review_map_r2.json`, `decisions_r2.json`) and its own `reviewId`
(`vc:<session>:r2`).

Read `../_shared/review-page/CONTRACT.md`, then use its existing
`build_review.py` with an escaped JSON queue covering every selected scene on one
page. Put the input-resolution table, budget ledger, and coverage summary before
detailed findings: a compact version in the page's lede (rulebook state and
digest, voices resolved or not, lint errors/warnings/skipped checks, every BREACH
and every not-checked row by name) and the full tables in the linked Markdown
report. Write "not checked" and its reason, never "ok", for a skipped check.
Per-scene prose counts/shares, locked-dialogue scope calls, hatch review, and
verdict live in the report. Zero findings still gets a report; the builder
refuses empty items, so do not invent a dummy decision or approval item, and
point the GM at the report.

Each card shows the passage, the rule broken, the proposed fix, and the evidence:

- `id`: stable and round-tripping to the sidecar (`s04-f03`; `doc-b02` for a
  ledger breach; `s03-h01` for a hatch).
- `t`: the decision as a sentence: severity (confirmed breach, plausible
  editorial concern, or scope decision), scene and line, and the rule broken.
- `y`: approve = act on the finding. The exact old span and replacement,
  including any dependent punctuation/attribution shown separately, and the
  derived revision it lands in, never the reviewed narration.
- `n`: reject = keep the passage as is; the rejection is recorded.
- `ev`: the passage verbatim in a blockquote, the rule source as `file:line`,
  the lint line if one fired, the examples cited, and your recommendation.

Discuss = defer or talk; it returns to chat in one grouped pass with its note.
Unmarked stays unresolved, never approval or rejection. Never pre-fill a verdict;
recommendations go in `y` or `ev`. Cross-narrator convergence is one card
containing both quotes. A cap breach is one card: `ev` gives where the instances
sit and the ranked keep/change recommendation; `y` gives the remedy the
distribution supports. An anachronism scope call recommends one disposition in
`y`, keeps the quote as spoken in `n`, and lists the others in `ev`. A hatch card
accepts the reclassification in `y` and, in `n`, records the span as in-fiction
and refers restoring it to re-narration. Unresolved identity/source issues get
discussion or referral, not an executable speculative replacement.

Freeze `review_map.json` before handing over the page: review ID, and per ID the
target path and SHA-256, reference hashes, exact old/new spans (with an offset
where the old span is not unique), and whether the item concerns narration or an
upstream workflow. Escape all source text before inserting it into trusted HTML
fields. The GM returns decisions with Copy output or Save output; validate them
with `read_decisions.py --in <session>/voice_critic_review/decisions.json --items
<session>/voice_critic_review/review_items.json`. Only returned decisions
authorize proposed edits; localStorage and file timestamps do not. Return the
page and report paths.

## After the GM returns decisions

Approve means act on the finding: apply the approved exact replacement. No
repeat confirmation is needed for the same replacement. Validate review ID, item
IDs, hashes, and unique spans against `review_map.json` before writing; a changed
proposal or stale target needs a fresh review rather than a guessed merge.
Show/inspect the complete intended diff, apply deterministically, then read
changed paragraphs and all affected joins. Reject keeps the text as is;
discuss/unmarked remains pending unless explicitly deferred.

The reviewed narration is never overwritten: not the raw scene, not the
`.scrubbed.md`, not a dialogue-edit revision. Write approved fixes to a separate
derived revision, as dialogue-edit does:
`<session>/voice_critic/<run>/applied/<revision>/` holding one file per changed
scene (built from the exact file critiqued, keeping its name), `approved.diff`,
and `application.json`, written last; without it the revision is incomplete.
The record carries the review ID, decisions path and `savedAt`; per scene the
source path, which copy it was (raw, scrubbed, dialogue-edit revision), and its
source and result hashes; per applied item the ID, category, old and new spans
and line; the rejected, discussed and unmarked IDs; and, where the source is one
half of a raw/scrubbed pair, whether each approved old span also occurs in the
other copy, so whoever promotes the revision knows what to mirror. Every later
revision is rebuilt from the same critiqued base plus the complete approved
subset under a new name. Promotion and assembly are the GM's separate actions.

`scrub` and `sd_narrate` regenerate the scene a revision was derived from, and
nothing replays voice fixes onto the new text. When the base hash no longer
matches the record, report the revision stale and re-critique the new text; do
not silently replay old spans onto it. Say this in the reply and the record.

Re-run lint and affected budget/convergence checks, report before/after counts,
and look for phrases introduced by the rewrites that collide elsewhere. New defects
require new proposals. Update the Markdown report's resolved state and corrected
counts; retain the original proposals and actual decisions as the audit record.

Finish with selected scenes and the file critiqued for each, reviewed/skipped
checks, counts, ledger verdicts, strongest supported finding, report/page paths,
and any applied revision paths. State that the reviewed narration is intact and
the actual promotion/assembly status. Do not claim full consistency or fidelity
certification from a voice review. Regeneration, policy edits, assembly, and
external publication require their own task authorization; a whole-document
re-render additionally needs the GM's explicit yes, because it is a paid run.
