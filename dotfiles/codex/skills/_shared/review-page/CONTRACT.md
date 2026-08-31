# Batch review page contract

Shared machinery for Codex skills that need human adjudication of many findings.
This directory is not a skill and intentionally has no `SKILL.md`.

## Workflow

1. Ask whether the user wants batch review or the skill's existing interactive flow.
2. Apply only changes that do not require a ruling. Put those changes in `footer`.
3. Write one shared-schema JSON file and build a standalone page:

   ```bash
   REVIEW_PAGE="${CODEX_HOME:-$HOME/.codex}/skills/_shared/review-page"
   python "$REVIEW_PAGE/build_review.py" --in review_items.json --out review.html
   ```

4. Give the user the page path. The user can paste **Copy output** into chat or
   send the JSON downloaded by **Save output**.
5. Validate a downloaded file when useful:

   ```bash
   python "$REVIEW_PAGE/read_decisions.py" --in decisions.json
   ```

6. Apply approved decisions through the calling skill's existing deterministic
   path. The page itself never edits source files.

## Input schema

```json
{
  "title": "Chapter 63 Rulings",
  "reviewId": "staged-consistency:chapter-63:stage-1",
  "outputName": "staged_consistency_stage_1_decisions.json",
  "eyebrow": "Out of the Abyss / Chapter 63 / staged consistency",
  "lede": "Ten decisions need a ruling. Mechanical corrections are already applied.",
  "footer": "Applied without asking: 20 mechanical corrections across 4 files.",
  "items": [
    {
      "id": "alkrist",
      "t": "Alkrist is alive; the recap says he died",
      "y": "Correct the cited recap and scene files.",
      "n": "Leave the cited files unchanged and defer the finding.",
      "ev": "The GM tally in <code>notes/session.md:84</code> says he is out."
    }
  ]
}
```

Required top-level keys are `title` and non-empty `items`. Optional keys are
`reviewId`, `outputName`, `eyebrow`, `lede`, `footer`, and initial `state`.

Each item requires:

- `id`: unique, stable, 1-64 characters from `[A-Za-z0-9_.:-]`.
- `t`: the decision as a sentence.
- `y`: the concrete consequence of Approve, including affected files.
- `n`: the concrete consequence of Reject, including affected files.
- `ev`: optional evidence with `file:line` citations.

`t`, `y`, `n`, and `ev` are trusted HTML. Callers must escape transcript text,
especially `<`, `>`, and `&`. The builder rejects an embedded `</script>`.

## Output schema

```json
{
  "schemaVersion": 1,
  "reviewId": "staged-consistency:chapter-63:stage-1",
  "savedAt": "2026-08-26 20:15 UTC",
  "decided": 10,
  "tally": {"approve": 6, "reject": 1, "discuss": 3},
  "decisions": {"alkrist": "discuss", "manshoon": "reject"},
  "notes": {"alkrist": "Treat this NPC as alive."},
  "discuss": ["alkrist"],
  "unmarked": ["keys"]
}
```

Verdicts are `approve`, `reject`, and `discuss`. Unmarked IDs are unresolved,
not rejected. Discussed items return to chat as one grouped pass with notes.

## Rules

- One item is one consent unit. Never imply approval across several findings.
- Never auto-apply an item that reached the page.
- Keep the skill's interactive mode intact; batch mode is additive.
- IDs must round-trip to the calling skill's apply data or a sidecar map.
- One page covers one skill and one run. `staged-consistency` uses one page per stage.
- The page existing, being opened, or having a newer mtime is never approval.
- Only pasted or saved decision JSON authorizes follow-up work.
