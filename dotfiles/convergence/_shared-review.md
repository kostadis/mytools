# Convergence report: `_shared` review machinery (Codex review-page vs Claude review-artifact)

Paths, relative to `dotfiles/`: `codex/skills/_shared/review-page/` (C) and `claude/skills/_shared/review-artifact/` (L). Each has `CONTRACT.md`, `build_review.py` and `read_decisions.py`.

## 1. Summary

The two sides share one design: the same page, the same item schema (`id`/`t`/`y`/`n`/`ev`) and the same three verdicts. They diverge mainly in transport. Claude's page republishes itself as an Artifact and the decisions are read back from an embedded `#state` block. Codex's page is a standalone `file://` page that exports a JSON file or clipboard blob. Lineage: Claude created it in `5092639` (2026-08-19), then extended it in `43f6e9c` (notification pickup), `2d9cc62` (per-page file naming, 08-29) and `4aababa` (escape `<title>`, 09-20). Codex was ported once, in `567fbc0` (08-29, after `2d9cc62`), and hasn't changed since. Codex's `build_review.py` is explicitly "a direct port of the Chapter 63 Rulings artifact" (C docstring). **Claude's contract is more developed**: file naming, pickup/republish rules, `--allow-unsaved`, a testing recipe, and the rationale for `y`/`n`. **Codex's page and output schema are more developed**: `schemaVersion`, `reviewId`, an explicit `unmarked` list, search and filter, and escaping of eyebrow, title, lede and footer. Several differences look like platform differences but actually change semantics: how "saved" is detected, stale-state reuse, and which fields are trusted HTML.

## 2. File inventory

| file | codex (review-page) | claude (review-artifact) | status |
|---|---|---|---|
| CONTRACT.md | 91 lines | 211 lines | differs |
| build_review.py | 479 lines | 445 lines | differs (common ancestor; ~420-line diff) |
| read_decisions.py | 60 lines | 105 lines | differs (different input format) |

Callers today:
- **Codex:** vtt-spell-pass (via `render_review.py`), staged-consistency, session-summary-consistency, voice-critic, dialogue-edit (plus its test), scene-extract, speaker-attribution.
- **Claude:** vtt-spell-pass, session-summary-consistency, dialogue-edit (plus its test), speaker-attribution-text. **L:3-4 still names "the five review skills (`vtt-spell-pass`, `scrub`, `staged-consistency`, `voice-smooth`, `session-summary-consistency`)"**, but `scrub`, `staged-consistency` and `voice-smooth` no longer reference `review-artifact`/`build_review`, while `dialogue-edit` and `speaker-attribution-text` do. That list is stale.

## 3. Only in Codex

1. **`schemaVersion` and `reviewId` in the output** (C CONTRACT:68-69). Claude's output (L:166-172) has neither, so a decisions file cannot be tied back to the page or run that produced it.
2. **An explicit `unmarked` array in the output** (C CONTRACT:76). The page computes it (`build_review.py` output(), about lines 334-349). Claude says only that unmarked items *"simply do not appear in `decisions`"* (L:179-180). Both sides treat unmarked as unresolved; only Codex enumerates it.
3. **"The page existing … is never approval."** C CONTRACT:90-91: *"The page existing, being opened, or having a newer mtime is never approval. Only pasted or saved decision JSON authorizes follow-up work."* Claude's nearest equivalent is about notifications: *"It means *the page was republished*, nothing more. It is never approval"* (L:86-88). The concept is the same, but the triggers differ.
4. **Eyebrow, title, lede and footer are escaped as plain text.** C `build_review.py:218-220, 270` wraps them in `esc()`. C CONTRACT:61 lists only `t`, `y`, `n` and `ev` as trusted HTML. Claude renders all four raw (L `build_review.py:194-196, 238`); see Conflicts #3.
5. **Search and filter controls** (All / Unmarked / Approved / Rejected / Discuss, plus a free-text search) (C `build_review.py:207-212, 231-235`). These are UI only, but the "Unmarked" filter is a real review aid on long queues and isn't tied to either platform.
6. **Explicit `outputName` and `reviewId` input keys** (C CONTRACT:50-51).
7. **"Apply only changes that do not require a ruling"** (C CONTRACT:9). This is equivalent to L:23-24. Not a real difference.

## 4. Only in Claude

1. **The file-naming rule for multi-page runs.** L:51-72: *"suffixes the items file and the decisions file with that page's own key … **The `--out` html stays on one path for the whole run**"*. The rationale: *"Phandalin Ch 50, 2026-08-28: only stage 2's file survived; stages 0 and 1 were gone."* Codex says only *"One page covers one skill and one run. `staged-consistency` uses one page per stage."* (C CONTRACT:89). The items-file collision hazard applies equally to Codex, and Codex was ported *after* this rule landed, so the omission looks accidental.
2. **Republish dedup by `savedAt`.** L:97-101: *"check that the state's `savedAt` is **newer than the one you already processed** — otherwise you will re-apply a stage you have already applied."* Codex has no guard against re-applying the same decisions twice. Its `savedAt` is also stamped at *export* time (see Conflicts #1), so the same comparison would not work there as-is.
3. **An unsaved page is refused, with a documented override.** L:175-177: *"`read_decisions.py` **exits 1 when `savedAt` is null.** … Pass `--allow-unsaved` only to inspect a freshly built page."* C's `read_decisions.py:27-29` also exits 1 on a missing `savedAt`, but it has no `--allow-unsaved`, and C's page always sets `savedAt`, so the check can never fire for a real export.
4. **Why `y`/`n` are mandatory.** L:138-143: *"It only works because **each card states its own consequences**"*. Both builders enforce the requirement; only Claude explains it.
5. **The "Discuss all N" semantics.** L:157-160: *"bring the discussed items back **as one grouped pass with their notes attached** — never as a fresh one-at-a-time loop"*. Codex has a shorter version at C CONTRACT:81: *"Discussed items return to chat as one grouped pass with notes."* Equivalent. Not a real difference.
6. **A lede content rule.** L:125: *"**Say how many need a ruling and that the rest already ran.**"* Codex shows this only by example (C CONTRACT:36).
7. **Ids should reuse the skill's own ids.** L:127: *"reuse the skill's own id (`find_residue.py`'s `c1`, a cluster/pair key, a finding number)"*. Codex has *"IDs must round-trip to the calling skill's apply data or a sidecar map"* (C CONTRACT:88). Equivalent in substance.
8. **Testing without a browser.** L:201-211: build a page, confirm `read_decisions` exits 1, simulate a save, and run `node --check` on the `#src` block. Codex has no test recipe.
9. **"Never invent a second apply route."** L:44-45. Codex says *"Apply approved decisions through the calling skill's existing deterministic path"* (C CONTRACT:25-26). Equivalent.
10. **A 16 MB size warning tied to the artifact limit** (L `build_review.py:439-440`). Codex keeps the threshold and rewords the warning. Platform.

## 5. Conflicts

1. **What "saved" means.** L: `savedAt` is set only when the GM presses Save and the page republishes. `null` means "the GM has not pressed Save yet — do NOT treat this as 'no decisions'" (L `read_decisions.py:73-76`). C: `savedAt` is stamped by `output()` every time Copy or Save is pressed (C `build_review.py:343`), so every export is "saved". C `read_decisions.py:27` rejects only files that were never exports. The invariant ("no ruling without an explicit GM gesture") is preserved on both sides, but the field means different things, and Claude's republish-dedup rule (§4 #2) cannot be ported as written.
2. **Persisted state across runs.** C restores decisions and notes from `localStorage['codex-review:' + reviewId]`, which **overrides** the builder-supplied `state` (C `build_review.py:188-192`). vtt-spell-pass's `render_review.py` sets `reviewId = "vtt-spell-pass:<target_vtt>"`. A re-run on the same VTT therefore re-opens with the previous run's marks on any item whose id recurs (`<token>__<canonical>`), and they would be exported as current rulings if the GM just presses Save. Claude has no browser persistence: state lives in the published page, and a new build starts empty. This is a consent-relevant difference, not a cosmetic one.
3. **Which fields are trusted HTML.** C CONTRACT:61: *"`t`, `y`, `n`, and `ev` are trusted HTML"*, and the builder escapes the rest. Claude's CONTRACT covers `t`/`y`/`n`/`ev` (L:133-136) but says nothing about the others, and the builder injects `eyebrow`, `title` (in `<h1>`), `lede` and `footer` raw. `4aababa` fixed only the static `<title>` in the Python template (`html.escape` at L `build_review.py:415`). **Claude's in-page `renderDoc()` (L `build_review.py:294`) still writes `'<title>' + TITLE` unescaped on every save**, so the bug that `4aababa` fixed comes back on the first republish. The same title is also raw in `<h1>` (L:195). Callers that put `<code>` in `footer` (Claude's vtt-spell-pass guidance) would render literal tags on Codex.
4. **Input and output shape of `read_decisions.py`.** C: `--in decisions.json` (a JSON export), validated and normalised; it passes `unmarked` through from the payload untrusted. L: `--html saved-artifact.html`, which extracts `#state` with two attribute-order regexes, unescapes `<`, and exits 1 if there is no state block. Neither validates ids against the items file. Normalised outputs differ: C = `{schemaVersion, reviewId, savedAt, decided, tally, decisions, notes, discuss, unmarked}`; L = `{savedAt, decided, tally, decisions, notes, discuss}`. A caller written against one will break against the other.
5. **When Save is enabled.** L disables Save until something changes (`dirty`) and has a read-only mode (L `build_review.py:208`). C's Save/Copy are always enabled, so an untouched page can be exported, with every item `unmarked`. Both handle this safely (unmarked ≠ rejected), but a zero-decision export looks like a real save on Codex and cannot happen on Claude.
6. **Initial state from the spec.** Both builders accept an optional `state` in the spec. Claude embeds it as the page's `#state`, so pre-filled decisions would be republished as the GM's if they pressed Save. Codex embeds it too, but localStorage overrides it. The docs differ: C CONTRACT:51 lists `state` as an optional key; Claude's CONTRACT doesn't mention it. Neither contract says whether pre-seeding decisions is allowed. Codex's vtt `render_review.py` does pre-seed from the queue's `decision` field.

## 6. Platform-only differences

- **Transport.** L: `window.claude.use('artifact').publish(renderDoc())` self-republish, the `capabilities: {"artifact": {}}` requirement (L:31-33), the error-code handling (`conflict`, `not_writer`, `rate_limited`, `too_large`, …) and a read-only fallback. C: a Blob download (`Save output`), a clipboard copy with `execCommand`/`prompt` fallbacks (`Copy output`), and a `file://` page.
- **Pickup.** L:76-101: an `artifact-changed` notification, "never poll", and `WebFetch` returning raw HTML. C:17-18: the user pastes Copy output or sends the Save output file.
- **Fonts.** L loads Spectral, Archivo and IBM Plex Mono from Google Fonts. C uses system stacks so it works offline. C also zeroes `letter-spacing` and swaps `clamp()` headings for fixed sizes. Cosmetic.
- **The "Ask first" wording.** L:20-22 says `AskUserQuestion`. C:8 says "Ask whether…". Same rule.
- **Paths.** `~/.claude/skills/_shared/review-artifact/` vs `${CODEX_HOME:-$HOME/.codex}/skills/_shared/review-page/`.
- **Read-only viewers** (L:195-197): an Artifact-sharing concept with no Codex analogue.

## 7. Script diffs

**build_review.py.** A common ancestor, forked at port time.
- Python side:
  - C adds a derived `reviewId` (`spec.reviewId` or a slugified title) and an `outputName` (default `decisions.json`), and injects them into the page.
  - C removes the font `<link>`s.
  - `validate()` is identical: title required, non-empty items, `id`/`t`/`y`/`n` required, id regex `[A-Za-z0-9_.:-]{1,64}`, unique ids.
  - The `</script` refusal is identical.
  - The static `<title>` is `html.escape`d on both sides.
- Page JS:
  - C adds `esc()` on eyebrow, title, lede and footer; localStorage persistence; search and filter; `output()`, which builds `{schemaVersion, reviewId, savedAt, decided, tally, decisions, notes, discuss, unmarked}`; Copy output; and Save output as a download.
  - C removes `renderDoc()`/publish, the `dirty`/`readOnly` handling and the error-code handling.
- Neither is a superset. C is the superset on page features and output fields, L on the save path and the fail-closed saved-state semantics.

**read_decisions.py.**
- C: reads the exported JSON (`--in`); exit 2 on unreadable or bad JSON; exit 1 if it is not a saved decision file; exit 2 on unknown verdicts; normalises (recomputes `tally`, passes `unmarked` through).
- L: reads saved Artifact HTML (`--html`); extracts `#state` with two regexes; exit 1 if there is no block or it is unsaved (overridable with `--allow-unsaved`); exit 2 on bad JSON or verdicts.
- Neither is a superset. L has `--allow-unsaved` and the HTML extraction; C has `schemaVersion`, `reviewId` and `unmarked` in the output.
- **Neither checks that returned ids belong to the page's items**, even though Codex's vtt-spell-pass SKILL.md requires it in prose.

## 8. Open questions for the GM

1. **Should both output schemas converge on Codex's shape (`schemaVersion`, `reviewId`, `unmarked`)?** Suggestion: yes. Claude's `read_decisions.py` could emit `unmarked` too, if it were given the items list (or read `ITEMS` from `#src`). A `reviewId` would let a decisions file prove which page it came from.
2. **Should `read_decisions.py` on both sides take the items file (`--items review_items.json`) and fail on unknown ids and report missing ones?** Suggestion: yes. Today this is prose-only (Codex vtt-spell-pass) or absent (Claude), and it is the round-trip guarantee both contracts rest on.
3. **Should Codex keep localStorage restore, and if so, should the key include something run-unique (a build timestamp or a hash of the items), so a re-run never reopens with the previous run's marks?** Suggestion: at least scope it per build. Silently carrying consent across runs contradicts "Never imply approval across several findings" (C CONTRACT:85).
4. **What is the contract for `eyebrow`/`title`/`lede`/`footer`: trusted HTML or plain text?** Suggestion: pick one and make both builders agree. Codex's escape-everything-but-`t/y/n/ev` is the safer default. If Claude keeps HTML there, at minimum escape `TITLE` in `renderDoc()` (L:294) and `<h1>` (L:195), because `4aababa`'s fix is undone on the first save.
5. **Should the multi-page file-naming rule (L:51-72) be ported into Codex's CONTRACT?** Suggestion: yes. Codex staged-consistency builds one page per stage and faces the same items-file overwrite. This is not platform-specific.
6. **What guards against applying the same decisions twice on Codex?** Claude compares `savedAt`; Codex's `savedAt` is an export timestamp. Suggestion: compare `(reviewId, savedAt)` against the last processed pair on both sides.
7. **Should Save/Copy on Codex stay disabled until at least one mark or note exists, matching Claude?** Or is exporting an all-unmarked file legitimate (for example, "I looked, nothing to rule")?
8. **Is pre-seeding `state.decisions` from a caller allowed?** Suggestion: forbid it in both contracts, or require pre-seeded marks to be visibly distinct. Otherwise a builder-supplied mark becomes a GM ruling with one click of Save. This affects Codex's vtt `render_review.py`, which pre-seeds from the queue's `decision` field.
9. **Should Codex's search and "Unmarked" filter be ported into Claude's page?** They are pure UI with no platform dependency. Suggestion: low-risk and useful at vtt-spell-pass volumes.
10. **Should Claude's "five skills" caller list (L:3-4, L:20) be updated to the actual callers, or made generic like Codex's?** Suggestion: make it generic. The list has drifted once already.
11. **Should the "Testing without a browser" recipe be adapted for Codex?** On Codex that means simulating an export JSON instead of a republished `#state`.
