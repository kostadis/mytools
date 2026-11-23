---
name: review-pages
description: >
  Build paginated exact-text review pages with Clef score groups, inline decisions, explicit original/baseline choices, audio evidence, and saved progress. Use directly or as another skill's review presentation and decision-readback layer.
---

# Review pages

Use this for the review step of another workflow. The calling skill owns the findings, evidence, exact edit map and eventual apply procedure. This skill builds and serves the pages and returns validated rulings; it never edits target documents or turns predictions into approvals.

## Calling contract

Accept the caller's `review_items.json`, `review_map.json`, and optional proposal-bound scores. Read [references/inputs.md](references/inputs.md) when preparing those files or adapting another skill. Reuse the shared [review contract](../_shared/review-artifact/CONTRACT.md), especially its verdict semantics. Keep every finding, note and dismissed/unrecoverable span in the caller's ledger and a readable footer; presentation must not silently discard them.

Prepare meaningful complete-passage questions, not isolated word pairs. Where wording is uncertain, read the surrounding exchange and show a concrete tentative guess when defensible, why it fits, and the remaining uncertainty. If no wording can be recovered, explain the likely contextual meaning without inventing a quote. Keep actual GM notes/rulings separate from agent guesses. Do not re-ask a clear instruction merely because it arrived as a Discuss note.

Give raw source, reviewed baseline and proposed text distinct, permanent meanings. **Keep original source passage exactly** must match `sourcePassage` byte-for-byte as a string. If the reviewed baseline differs, give it a separate named choice. Never let selecting an option change the text or meaning of a source box. Each named option has an exact `pickTexts` preview and a matching application entry in the caller's map. A deletion uses an explicit deletion preview, never replacement prose that says “delete this”. For a decision with no text edit, show its exact outcome and scope instead.

Set `reviewKind: interpretation` for checking what a passage asserts, or `reviewKind: decision` for other non-edit decisions; the default is `text-edit`. Explain the practical question in plain language. Interpretation approval records a reading of the passage, not replacement prose or an assertion that the passage is true canon. Keep registry-link status separate from uncertainty about the story: an unassigned thread link does not make the described plan uncertain. Put native identifiers and indexing fields in evidence details rather than presenting them as proposed narrative text.

When matching original audio exists, use short inline clips and the shared [audio evidence helper](../_shared/review-artifact/AUDIO.md). The builder supports that helper's embedded clips, `audioData`, and `extraAudio`. Describe transcript-only/contextual guesses honestly when audio is absent; never synthesize evidence.

## Build the bundle

Resolve `SKILL_DIR` to this skill's installed directory. Run:

```bash
python "$SKILL_DIR/scripts/build_pages.py" \
  --items /absolute/path/review_items.json \
  --map /absolute/path/review_map.json \
  --out /absolute/path/review-bundle \
  --scores /absolute/path/scores.json
```

Omit `--scores` for an unscored review; it is labelled **Not scored**, not 0%. When scores are supplied, they must bind the exact question and scope. The builder validates their hashes and never calls a model or invents probabilities. Use the caller's authorized decision model to obtain scores. Defaults match the requested page: over 90%, 80–90%, then individual cards. Only binary approval recommendations enter bulk groups. Named-choice, conditional, and Discuss/reject-recommended items stay individual.

Pages hold at most 100 decisions (`--page-size` may reduce that). The builder emits an offline index, numbered pages, distinct page review IDs, separate item/map/score files and a `bundle.json` membership/hash receipt. It rejects changed inputs at an existing output directory, preserving saved decisions. For a changed question or scope, make a new bundle version; retain prior exports and explicit cross-version mappings. Rebuilding identical inputs is a no-op, not a reset.

Inline Approve/Reject/Discuss and named picks record decisions on the same page. Bulk approval affects only that page's undecided binary items in its score group; it leaves individual choices and items with notes alone.

## Serve and verify

Reuse an appropriate healthy server when it can serve this frozen bundle and preserve its saves. Otherwise follow `/tailscale-publish` and [the durable serving guidance](../_shared/review-artifact/SERVING.md), using this bundle server:

```bash
python "$SKILL_DIR/scripts/serve_bundle.py" \
  --bundle /absolute/path/review-bundle \
  --host THE_EXACT_TAILSCALE_IPV4 --port 8765
```

Use loopback only for local tests. Keep the capability file in the default `~/.local/state/review-pages/` location or an explicit runtime `--state` path outside the bundle. Keep URLs/tokens out of committed review evidence. Run the service under the available durable process manager for long reviews; record its unit and the decisions paths. Restart only its exact service when needed, preserving the capability and saves. Do not restart the Tailscale daemon to repair a review server.

The default is Tailscale when the complete pending set exceeds three; the user's explicit routing choice takes precedence, including chat for Discuss follow-ups. Count the whole set before routing; pagination does not reset that count.

Before handoff, check the exact URL, current-page navigation, **Save to VM**, and narrow-screen layout. Test a temporary fixture for individual selection, note preservation under bulk, exact keep-original mapping, reload restoration, and stale/foreign-save rejection. Never write synthetic approvals to a live review. Fresh queues start unmarked. Hosted saved queues restore validated real choices, notes and picks; the index shows per-page saved counts.

Give the index or first-page URL and the item/page counts, then hand control to the reviewer. Tell them to save each page before navigating. Leave the managed server available. Do not infer decisions from page visits, “done”, or modification times; “done” triggers read-back.

## Read back and return to the owner

```bash
python "$SKILL_DIR/scripts/read_results.py" \
  --bundle /absolute/path/review-bundle \
  --out /absolute/path/review-results.json
```

This verifies frozen artifacts, normalizes each page against its own exact items/ID, and returns original item IDs, scopes, notes, missing/unmarked/Discuss items and page provenance. The server archives raw exports before replacing the current normalized save. A choice-only item cannot be resolved by generic approval. **All marked** does not mean approved: Discuss and relevant notes still require interpretation.

Return these results to the calling skill. Preserve saved notes verbatim; interpret clear instructions at their exact layer, and bring unresolved meanings back with your best reading and explicit alternatives using the user's chosen routing. Apply only through the owner's existing deterministic procedure, then verify it. Do not create a second apply path inside this presentation skill.

Other skills can delegate with: “Use `/review-pages` for this review's presentation, hosting and read-back; retain this skill's findings, scope and apply procedure.”
