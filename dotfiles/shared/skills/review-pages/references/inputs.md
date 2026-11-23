# Inputs and integration

This is the existing shared `review-artifact` card schema with the full-passage fields used by the preferred review page. All file paths passed to the scripts are explicit. The builder depends on the installed sibling `_shared/review-artifact` kit; `REVIEW_ARTIFACT_KIT` can name it when testing an isolated copy.

## Questions and exact outcomes

`review_items.json` requires `title`, an explicit unique `reviewId`, and nonempty `items`. Each item needs stable `id`, `t` (question), `y` (Approve consequence), and `n` (Reject consequence). These and `ev`/`edit` may use the shared contract's simple HTML; the page safely renders their text. Exact passage fields are plain strings and are never normalized.

```json
{
  "title": "Session wording review",
  "reviewId": "session-17-wording-v1",
  "lede": "Review the full passages, then save.",
  "footer": "Include mechanical fixes, non-card findings and retained uncertainty here.",
  "items": [{
    "id": "cue-12",
    "t": "Was the intended description a ball of light?",
    "y": "Use only the exact proposed text at cue 12 in the derived record.",
    "n": "Keep the displayed reviewed baseline; no new repair.",
    "sourcePassage": "GM: You see a ball.",
    "confirmedPassage": "GM: You see a ball.",
    "fullPassage": "GM: You see a ball of light.",
    "baselineLabel": "Reviewed baseline — Reject keeps this exactly",
    "ev": "Explain the surrounding exchange and identify the source.",
    "guess": "approve",
    "guessWhy": "A tentative reading from the following description, not verified audio.",
    "picks": ["Keep original source passage exactly"],
    "pickTexts": {"Keep original source passage exactly": "GM: You see a ball."},
    "uncertainties": ["The added words remain a contextual reconstruction."]
  }]
}
```

For **named-choice only** questions, set `choiceOnly: true`, declare every `picks` label and its complete `pickTexts` passage/outcome, and set `guessPick` to the recommended label. The UI exposes named picks and Discuss, never generic approval; scores cannot select a name. Use clear labels such as **Use contextual guess shown above**, **Keep original source passage exactly**, and, when needed, **Keep reviewed baseline shown above**. Avoid two options with identical text unless they deliberately authorize different non-text classifications and that distinction is explained.

Optional fields: `reviewGroup` (keep different owner/stage queues on separate pages in one bundle), `session` (short scope label), `deletionOnly` (Approve removes the before passage), `audioData`, `extraAudio`, and `uncertainties`. Omission placeholders are metadata, not invented dialogue. For non-edit decisions, `pickTexts` can describe the exact consequence rather than a replacement passage. Extra verdict types should be adapted to named picks; this renderer does not silently reinterpret `extraVerdicts`.

`reviewKind` may be `text-edit` (default), `interpretation`, or `decision`, set on the root specification or overridden per item. It changes presentation only; stored verdicts remain `approve`, `reject`, and `discuss`, and the owner still defines their exact application. For `interpretation`, put the unchanged passage in `sourcePassage`, readable statements to check in `fullPassage`, and technical mapping fields in `ev`. `confirmedPassage` is optional when there is no distinct reviewed baseline. Write `y`/`n` to say whether a reading is recorded or rejected; neither implies a prose edit or canon ruling. The UI must not label such statements “Approve writes this exact proposed text” or call them proposed corrections.

## Scope map

`review_map.json` is an object keyed by exactly the item IDs. Each entry needs a nonempty `scope`. The owner supplies the remaining fields needed by its apply helper: target file, exact old/new/count edits, cue ordinals, layer limits, and pick-to-action mappings. The renderer does not execute them.

```json
{
  "cue-12": {
    "scope": "Only cue 12 in the derived correction record; original source unchanged.",
    "cue": 12,
    "approve": {"old": "You see a ball.", "new": "You see a ball of light."},
    "picks": {"Keep original source passage exactly": {"action": "keep raw words"}}
  }
}
```

Conditional entries may declare `requires` (item IDs) or `requires_named` (ID → required pick). These are displayed and kept outside bulk groups; the owning workflow still checks the dependency before applying.

## Optional scores

Provide one record per item in a JSON array, or omit scoring. Each record needs `id`, finite `p_approve` between 0 and 1, `model`, and exact bindings:

```python
# common.digest is canonical JSON SHA256, not a hash of pretty-printed file bytes.
from common import digest
score = {
    "id": item["id"], "p_approve": prediction, "model": "clef",
    "item_sha256": digest(item), "scope_sha256": digest(scope_map[item["id"]])
}
```

The builder also accepts the existing Clef archive shape: `request`, its canonical `input_sha256`, and a request `state` object/JSON containing exactly `question_as_displayed` and `exact_apply_scope`. It verifies all three bindings. `tier` from callers is not authoritative; the renderer computes groups from probabilities and decision type. Freeze the complete question and scope before scoring; changed wording, evidence, picks or targets requires fresh scoring. This skill does not choose an endpoint or authorize an API transfer.

## Audio

Use the shared `attach_audio.py` helper to embed an actual WAV in `ev`, or pass a `data:audio/...;base64,...` URL in `audioData`/`extraAudio`. Authorized HTTP(S) clip URLs are also supported. The builder never fetches audio. Relative filesystem/audio paths are rejected because this bundle server does not expose arbitrary assets; use inline clips or a separately authorized allowlisted audio server. Keep recording/clip hashes and offsets in the owning evidence map.

## Outputs

`bundle.json` holds the unique page IDs, complete membership and hashes of each page's questions, scope map, scores and HTML. `page-001/`, etc. contain `review.html`, `review_items.json`, `review_map.json`, `scores.json`, and, after actual saves, `decisions.json`, raw `saved_exports/`, and a save receipt. The index and page links work offline too; local files download decisions instead of claiming they were saved on the VM.

`read_results.py` returns normalized decisions and notes without changing page exports or inventing a new GM save. It includes missing pages, unmarked IDs, Discuss IDs, note-bearing IDs, exact scopes and originating page/ID/save hashes. Keep this provenance when adapting results back into the owner's original queues; never rewrite a stale export's ID to force validation. Read and resolve notes before treating a result as ready to apply.
