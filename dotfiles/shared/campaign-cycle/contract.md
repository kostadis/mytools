# Campaign cycle contract v1

CampaignGenerator owns `session_workflow.yaml`; Claude and Codex are native
specialists. Use the selected CampaignGenerator checkout's installed
`session_workflow` command. Do not run an ambient executable from another
worktree. Read `status` and `resume` for the explicit session directory first.

The pending run supplies selected inputs, immutable evidence hashes, resolved
roster/player identity/voice/example/rulebook paths, generation settings,
required checks, an output directory and the named human decision. Stay within
that task. A missing prerequisite or stale source is a refusal to resolve with
the operator, never a reason to bypass the gate. Do not reinterpret skill
Markdown as a server job.

For a generation task, work natively and put candidate outputs in the run's
output directory, preserving old files. Submit `run_id`, explicit `outputs`, and
the actual `generation` object through `session_workflow submit --request FILE
--expected-revision N`. Model/backend/effort must match the selected run; ask for
a distinct comparison run when changing them. Report available usage honestly.

For a check task, read every selected output and its immutable evidence. Submit
`run_id` and `check`: name, complete/failed/skipped status, all checked output
Evidence objects as `sources`, findings, producer and timestamp. A finding has
an ID, scene, evidence, exact location, description, proposed action, explicit
Approve/Reject/Discuss consequences, optional rule provenance and optional
exact before/after replacement. An empty findings list means a completed check,
never an approved draft. Do not launch a second independent audit when
staged-consistency already delegated that specialist check.

Read evidence and decision hashes from `export`. Human decisions go through
`decide` with individual finding IDs/hashes, the human actor, their ruling and
rationale. A group discussion still has one decision per selected item.
Unmarked and Discuss remain unresolved. Only explicit human sign-off may invoke
`approve` with the current draft binding. Never manufacture an actor or infer
approval from a clean scan, a prior version, a marker, or a scoped recurring
ruling. JSON import validates decisions; historical HTML is evidence only.

Approved changes apply through the engine after explicit selection. The result
is a new derived draft requiring checks and sign-off. Never apply scripts from
the standalone workflow directly to workflow-managed originals. Do not edit
source transcripts or captured extraction versions; a correction or smoothing
is derived and must not acquire a verbatim claim. Keep player identity separate
from character attribution. Unknown or shared speakers remain unresolved until
the GM rules. Preserve new information, discoveries, level changes, real
outcomes, in-world magic and genuine dialogue during recap/mechanics review.

Recap removal precedes extraction; mechanics review precedes narration. The
genre rulebook owns generation-time rules and keep-lists. Scrub policy records
scoped editorial rulings referencing that authority. Narration-wiki guidance
changes retain their separate Gate 1/Gate 2 approvals.

Check `resume` after submission. Report the actual next gate and artifact paths,
so another agent or the editor can continue. No live skill installation is part
of a pilot: invoke these worktree entrypoints directly and record this commit
alongside the CampaignGenerator acceptance commit.
