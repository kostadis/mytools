# Exact proposals, review, and application

Use the standard-library helper at `../scripts/review_edits.py`. It performs no
model calls. It checks evidence text exists and that hashes/spans are current;
it does **not** establish whether that evidence semantically supports an edit.
The skill's full reading and the GM's ruling remain required.

## Prepare one scene

Author proposal JSON with the exact strings from the original scene. Keep
dependent changes in a single clearly explained replacement; overlapping
proposals are refused. The `start` offset is optional when `before` is unique.
It is a zero-based Python Unicode-character offset, not a byte offset. If text
occurs more than once, supply its exact offset or use a longer unique span.

```json
{
  "scene": "Scene 01 — narrator name",
  "edits": [
    {
      "id": "s01-01",
      "before": "Exact existing words, including punctuation.",
      "after": "Exact proposed replacement.",
      "scope": "dialogue",
      "support": "supported",
      "reason": "The specific readability gain and what must be preserved.",
      "evidence": [
        {
          "path": "/absolute/path/to/reviewed-extraction.md",
          "quote": "Exact source passage establishing the intended meaning."
        }
      ]
    }
  ],
  "observations": ["Unchanged cadence worth preserving or an upstream carry-forward."]
}
```

Allowed scopes: `dialogue`, `adjacent-attribution`, `out-of-scope`.
Support: `supported` or `unresolved`. These are declared judgments, not helper
verdicts. An approved unresolved/out-of-scope edit is still refused; settle the
issue and prepare a new proposal set for fresh review. Supported proposals need
at least one anchor from the declared extraction or references, never just the
draft being edited. Evidence `quote` also accepts `start` for disambiguation.
Empty `after` deletes the exact span. Empty `before` and no-op edits are refused.

Use absolute paths when practical. Command arguments resolve from the working
directory; evidence paths resolve from the proposal JSON's directory. Declare
all files actually used, including identity configuration, voices, examples,
campaign rules, and any manually consulted transcript, as references so they
participate in freshness checks. The draft must be narration Markdown within
the selected session; the source must be a separate file.

```bash
SKILL_ROOT="$HOME/.claude/skills/dialogue-edit"
python3 "$SKILL_ROOT/scripts/review_edits.py" prepare \
  --session-dir /campaign/summaries/session \
  --draft /campaign/summaries/session/narration/scene_01.md \
  --source /campaign/summaries/session/scene_extractions_smoothed/01_scene.md \
  --reference /campaign/config/party.yaml \
  --reference /campaign/config/players.yaml \
  --reference /campaign/voice/narrator.md \
  --proposals /campaign/summaries/session/dialogue_proposals_01.json \
  --run-dir /campaign/summaries/session/dialogue_edit/scene01-r1
```

The run must be a **new direct child** of `<session>/dialogue_edit/`. Inputs and
completed runs cannot be overwritten. The helper creates:

- `original.md`: exact original bytes (UTF-8, including existing newlines).
- `candidate.md` and `candidate.diff`: all proposed changes, still unapproved.
- `review.md`: exact replacements, surrounding context, and evidence.
- `review_page.json`: this scene's page queue, omitted if there are no proposals. Artifact
  mode normally combines all scenes with `session-page` instead of publishing this one.
- `review.json`: frozen proposal/input identities and skill-file fingerprints.

`review.json` is written last. Its absence means preparation is incomplete.
The review ID binds the entire frozen proposal set. Do not hand-edit prepared
artifacts; revise the authoring JSON and prepare a fresh run. Changing an
approved replacement needs fresh approval, even if the change seems small.

## Collect actual decisions

For chat review, show the exact prepared proposals and record the GM's actual
responses in the same decision envelope the page uses:

```json
{
  "schemaVersion": 1,
  "reviewId": "copy the exact reviewId from review.json",
  "savedAt": "the actual UTC time the ruling was recorded",
  "decisions": {"s01-01": "approve"},
  "notes": {"s01-01": "Actual GM note, if any."}
}
```

Never populate an approval speculatively. Valid decisions are `approve`,
`reject`, `discuss`. Omitted IDs stay unresolved. The helper rejects foreign
IDs, duplicate JSON keys, invalid verdicts, and mismatched review IDs.

For artifact review, read [the shared contract](../../_shared/review-artifact/CONTRACT.md).
Prepare every selected scene first; then collect their frozen runs onto **one
session page**:

```bash
python3 "$SKILL_ROOT/scripts/review_edits.py" session-page \
  --run-dir /campaign/summaries/session/dialogue_edit/scene01-r1 \
  --run-dir /campaign/summaries/session/dialogue_edit/scene02-r1 \
  --spec /campaign/summaries/session/dialogue_edit/session-r1/review_page.json \
  --map  /campaign/summaries/session/dialogue_edit/session-r1/session_map.json
REVIEW_ARTIFACT="$HOME/.claude/skills/_shared/review-artifact"
python3 "$REVIEW_ARTIFACT/build_review.py" \
  --in  /campaign/summaries/session/dialogue_edit/session-r1/review_page.json \
  --out /campaign/summaries/session/dialogue_edit/session-r1/review.html
```

`session-page` re-verifies every run before collecting it. Item ids are
prefixed by scene (`s01:<id>`), and the page's `reviewId` is derived from the
runs' own review ids. It writes nothing it would overwrite, so each review
round gets a fresh session directory; **retain any already-returned decisions**
from earlier rounds rather than asking them again.

Publish `review.html` with the `Artifact` tool using
**`capabilities: {"artifact": {}}`** — without it the page cannot save and the
GM silently gets the read-only fallback. One page covers the whole session.

Then **stop**. The save comes back on its own — the `artifact-changed`
notification, or the GM's word, whichever arrives first. Never poll for it.
Read it back with the `Artifact` tool (CONTRACT step 5), recover the decision
envelope, and split it into one record per scene run:

```bash
python3 "$REVIEW_ARTIFACT/read_decisions.py" \
  --html <saved-artifact.html> \
  --items /campaign/summaries/session/dialogue_edit/session-r1/review_page.json \
  --out /campaign/summaries/session/dialogue_edit/session-r1/decisions.json
python3 "$SKILL_ROOT/scripts/review_edits.py" split-decisions \
  --map /campaign/summaries/session/dialogue_edit/session-r1/session_map.json \
  --decisions /campaign/summaries/session/dialogue_edit/session-r1/decisions.json \
  --out-dir /campaign/summaries/session/dialogue_edit/session-r1/split
```

Each split record carries that run's own `reviewId`, so `apply` checks it
exactly as for a single-scene ruling. `split-decisions` refuses decisions from
another session page, ids with an unknown scene prefix or proposal, and any run
that changed after the page was built.

The prepared queue HTML-escapes source text. It names the original and derived
output area and shows exact before/after text and evidence. Only the returned
decision JSON authorizes changes — a mark left on screen but never saved is not
a ruling. Return `discuss` notes to chat; explicit deferral can be recorded in
notes and the session manifest while retaining the original text.

## Dry-run and apply the approved subset

```bash
python3 "$SKILL_ROOT/scripts/review_edits.py" apply \
  --run-dir /campaign/summaries/session/dialogue_edit/scene01-r1 \
  --decisions /campaign/summaries/session/dialogue_decisions_01.json \
  --revision approved-01 --dry-run

# After inspecting the dry-run, apply the same already-approved decisions:
python3 "$SKILL_ROOT/scripts/review_edits.py" apply \
  --run-dir /campaign/summaries/session/dialogue_edit/scene01-r1 \
  --decisions /campaign/summaries/session/dialogue_decisions_01.json \
  --revision approved-01 --write
```

Default application mode is a dry-run. Writing produces a new
`applied/approved-01/` containing `scene.md`, `approved.diff`, and
`application.json`. The record is written last; without it, the revision is
incomplete, not approved. No original, source, or previous revision is written.
Refusals exit 2; normal preparation/application exits 0. An all-rejected or
unresolved review reports `no_approved_changes` and creates no revision.

Every later revision is rebuilt from the frozen original plus the complete
current approved subset. To add a newly approved edit without dropping earlier
ones, retain earlier approvals in the new decisions file. Use a new revision
name. Revalidate reviewed inputs when resuming; do not repair stale hashes.

The helper refuses stale input/reference content, changed original snapshots
or candidates, mutated frozen proposals, conflicting spans, and symlinked run
or application directories. It does not detect semantic scope mistakes, judge
cadence, or choose which revised scene should enter assembly. Read the final
scene and its joins before reporting it ready for the GM's next decision.

## Session index

Use `dialogue_edit.sources.yaml` at the session root to index these records.
Preserve earlier entries; include run/revision paths, reading status, exact
selected source, actual rulings or decision-file links, seam findings, and
carry-forward items with explicit open/resolved status. If no revision is
written, the saved decision file is still part of the audit. Parse the YAML
after writing it. New entries describe this run; they do not certify unrun
scenes or silently settle upstream issues.
