---
name: voice-critic
description: Critique existing campaign narration for voice drift, generic prose, ambiguous attribution, and genre or document-budget breaches. Use after narration, scrub, or dialogue-edit, including assembled fable documents. Produce evidence-backed reports and a standalone batch review page; apply only GM-approved fixes when requested.
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
  promotion status, and hashes. An explicitly selected approved revision outranks
  a directory scan. Never critique `candidate.md` as approved. For promoted
  revisions, verify current narration against the promotion record; preserve
  original scene identity and source mapping even when the filename is `scene.md`.
  Resolve conflicts with the GM rather than selecting by modification time.
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
historical evidence: report suspicious flattening and delivery uncertainty, without
claiming it proves the cause of a prose defect. A retired config string is not an
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
explicit “grounded in examples only” label; if neither resolves, skip that
narrator's voice judgment while retaining independently supported checks.
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

Write Markdown review records and a standalone page as the default review surface.
Reuse an explicit chat-only preference. No Claude Artifact tool or hosted publish
step is required. A review page is a local file.

For normal per-scene input, write `voice_critique_scene_<NN>_<narrator-slug>.md`
beside the selected narration and `voice_critique_summary.md` for a directory.
For an assembled file, use `<doc-stem>.voice_critique.md`. For dialogue-edit
revisions, put reports under a separate `<session>/voice_critic/<run>/` and record
the selected revision paths; leave frozen dialogue-edit records intact. Preserve
previous completed reviews with a new run/path when necessary.

Read `../_shared/review-page/CONTRACT.md`, then use its existing
`build_review.py` with an escaped JSON queue. The shared builder is the Codex
replacement for the Claude proof-sheet Artifact surface. Put the input-resolution
table, budget ledger, and coverage summary before detailed findings, in the page's
lede or a linked companion report. Keep missing/skipped checks visually distinct
from passes. Include per-scene prose counts/shares, locked-dialogue scope calls,
hatch review, and verdict. Zero findings still gets a report and a readable page;
if the builder requires nonempty items, write a static report page with no dummy
decision or invented approval item.

Each decision needs a stable ID, severity, exact target path/line and quoted span,
exact proposed replacement (including any dependent punctuation/attribution),
reason, and cited rule/source/example evidence. Cross-narrator convergence belongs
in one card containing both quotes. Distinguish confirmed breach, plausible
editorial concern, and scope decision. Unresolved identity/source issues get
discussion or referral, not an executable speculative replacement.

Freeze a sidecar mapping of IDs to exact old/new spans, original target hashes,
reference hashes, and review ID. Record which candidates concern narration versus
upstream workflows. Escape all source text before inserting it into trusted HTML
fields. Use the page's approve/reject/discuss controls, Copy output and Save output.
Only returned decisions authorize proposed edits; localStorage and file timestamps
do not. Preserve unknown/unmarked items as pending. Return the page and report links.

## After the GM returns decisions

Apply approved exact replacements when requested or already authorized by the
review's stated approve consequence. No repeat confirmation is needed for the same
replacement. Validate review ID, item IDs, hashes, and unique spans before writing;
a changed proposal or stale target needs a fresh review rather than a guessed merge.
Show/inspect the complete intended diff, apply deterministically, then read changed
paragraphs and all affected joins. Keep/reject preserves text; discuss/unmarked
remains pending unless explicitly deferred.

Choose destinations from the user's instruction and the selected revision's
provenance. Default to a separate derived revision before promotion. Explicit
promotion authorizes narration writes. For an existing raw/scrubbed pair, mirror
the approved voice change to both where the exact span applies, preserving
scrub-specific differences. If the pair diverges at that span, resolve it rather
than widening approval. Never overwrite frozen snapshots or silently lose prior
dialogue edits by regenerating from raw narration.

Re-run lint and affected budget/convergence checks, report before/after counts,
and look for phrases introduced by the rewrites that collide elsewhere. New defects
require new proposals. Record fixes, decisions, original and result hashes,
destinations, and remaining issues in `voice_fixes_<session>.md` or the review run
manifest. Update the review surface's resolved state and corrected counts; retain
the original proposals and actual decisions as the audit record.

Finish with selected scenes, reviewed/skipped checks, counts, ledger verdicts,
strongest supported finding, report/page paths, and any applied revision paths.
State actual promotion/assembly status. Do not claim full consistency or fidelity
certification from a voice review. Regeneration, policy edits, assembly, and external
publication require their own task authorization.
