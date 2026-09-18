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
SKILL_ROOT="$HOME/.codex/skills/dialogue-edit"
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
- `review_page.json`: the shared page queue, omitted if there are no proposals.
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

For page review, read [the shared contract](../../_shared/review-page/CONTRACT.md)
and render the existing prepared queue:

```bash
REVIEW_PAGE="$HOME/.codex/skills/_shared/review-page"
python3 "$REVIEW_PAGE/build_review.py" \
  --in /campaign/summaries/session/dialogue_edit/scene01-r1/review_page.json \
  --out /campaign/summaries/session/dialogue_edit/scene01-r1/review.html
```

Use a fresh page path; retain any already-returned decisions. The prepared
queue HTML-escapes source text. It names the original and derived output area
and shows exact before/after text and evidence. Only pasted or saved decision
JSON from this page authorizes its changes; browser state is not a callback.
Return `discuss` notes to chat; explicit deferral can be recorded in notes and
the session manifest while retaining the original text.

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
