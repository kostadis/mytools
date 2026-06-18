# Research — Post-Capture Notes

**Feature**: 003-post-capture-notes
**Date**: 2026-05-09

The Technical Context in `plan.md` was filled in without `NEEDS CLARIFICATION`
markers — every technology choice has an existing precedent in the codebase
or was pinned by the spec's Clarifications session. This document records
the non-trivial decisions, the alternatives that were considered and
rejected, and pointers to where each decision is enforced in the plan.

---

## D1 — Where the new code lives (module placement)

**Decision**: Put the orchestrator at `src/notetaker/notes/` (top-level
sibling of `stages/`); put the format-specific transcript parsers under
`src/notetaker/stages/capture/adapters/zoom_transcript_parsers.py`.

**Rationale**: Article I.1 names exactly four stages (Capture, Extraction,
Understanding, Synthesis). The new `notes` command is not a stage — it is a
post-pipeline consumer of stage outputs. Putting it under `stages/` would
silently inflate the number of stages and confuse the contract surface.
Article I.2 says platform/format-specific logic belongs in capture adapters;
the three transcript shapes are all rooted in Zoom workflows (the browser
scrape produces the block format; Zoom Cloud Recording produces the VTT
download; the live scrape produces our `transcript.json`). Keeping the
parsers in adapters keeps platform knowledge isolated, and the orchestrator
imports a single `parse_transcript_file(path) -> TranscriptSchema`
dispatcher that has no Zoom or format branches.

**Alternatives rejected**:
- *Put everything inside an existing stage (e.g., `synthesis/`).* Confuses
  the role of `synthesis` and contradicts the spec's premise that synthesis
  stays as-is while `notes` becomes the documented path.
- *Put the parsers inside `notes/`.* Would put platform-specific format
  knowledge outside the adapters layer, violating Article I.2.
- *Make `notes` a fifth stage.* Would require a Constitution amendment
  (Article I.1 enumerates stages) — out of scope and disproportionate.

---

## D2 — Reconciling FR-018 (retention exempt) with Article VI.2

**Decision**: Implement FR-018 as a separate config knob
`[notes] retention_days` with a default of 365 days, not literal indefinite
retention. Setting the value to 0 explicitly opts in to keeping the
artifacts forever; 0 is *not* the default.

**Rationale**: The spec's clarification of Q2 (Option B) recorded the user
intent as "exempt from automatic purge — both persist until the user removes
them." A literal reading of that wording would default to indefinite
retention, which Article VI.2 forbids by default. A 365-day default honours
the user's intent (the notes survive any reasonable cache churn — the
existing cache retention is 30 days, so the notes outlast 12 cycles of
frame purges) while keeping the *default* finite. The user explicitly
choosing 0 is consistent with Article VI.2's "by default" language.

**Alternatives rejected**:
- *Strict 30-day retention matching the rest of the cache.* Contradicts the
  Q2 clarification.
- *No automatic cleanup at all.* Contradicts Article VI.2.
- *Re-open Q2 with the user.* Already used 3/3 clarification questions; the
  finite-but-generous default is a defensible interpretation of the user's
  recorded intent and does not change the user-visible behaviour for the
  expected use case.

---

## D3 — Transcript format detection strategy

**Decision**: Sniff the file content first; use file extension only as a
tiebreaker. Detection order:

1. If the first non-blank line starts with `WEBVTT` → WebVTT parser.
2. Else if the file parses as JSON and the resulting object validates
   against the existing `TranscriptSchema` → reuse the schema directly.
3. Else if the file contains the block separator `\n\n----\n\n` *or* a
   three-line "Speaker / HH:MM:SS / text" header on the first block → block
   parser.
4. Else → refuse with an actionable error naming all three supported
   shapes (FR-004a).

**Rationale**: Content sniffing is robust to misnamed files (a `.txt` that
is actually VTT, a `.json` saved without an extension). The order above is
unambiguous: `WEBVTT` is a magic string; valid JSON validating the existing
schema is a high-confidence signal; the block-format markers are
specific enough that false positives are unlikely. The extension tiebreaker
applies only when content sniffing is inconclusive (e.g., a file that is
both valid JSON and contains `----`, which is implausible in practice).

**Alternatives rejected**:
- *Extension-only.* Brittle to naming; the user often saves the browser
  download with a default name like `zoom_chat.txt`.
- *Always parse all three and pick the most populated.* Wasteful and
  ambiguous when two parsers both succeed.
- *Require the user to declare format via a flag.* Adds CLI surface for no
  user gain; sniffing is reliable for these three shapes.

---

## D4 — Single-call render vs. chunking for long meetings

**Decision**: Single LLM call. Document chunking as out of scope. The
default model (`claude-sonnet-4-6`, 200K-token context) is sufficient for a
1-hour meeting (~35K input tokens measured against the recovered fixture
from this session).

**Rationale**: The single-call architecture is the central design choice
captured in the spec ("LLM extracts → human reviews → LLM renders").
Chunking would either (a) require an LLM-driven scope decision about how to
split the working doc — exactly the precision-decision class the user's
global rules forbid as input to a downstream LLM call, or (b) require a
deterministic split that risks cutting topic threads in half. Either path
is materially harder than the single-call path and produces lower-quality
output for the meeting lengths in scope.

**Alternatives rejected**:
- *Map-reduce summarisation per slide.* This is what the existing synthesis
  stage already does and is exactly what we are replacing because of its
  alignment problems.
- *Stream the response and trim partial output if it overruns.* Adds
  complexity for a case (1-hour meetings exceeding 200K tokens) we have not
  observed.

---

## D5 — Default model and config wiring

**Decision**: Default to `synthesis.summary_model` (currently
`claude-sonnet-4-6`). Do not introduce a new model-selection surface in
`[notes]`. If a user wants a different model for notes than for the (legacy)
synthesis stage, they can override `notes.model` explicitly; absent
override, `notes.model` falls back to `synthesis.summary_model`.

**Rationale**: Article IV.2 (sensible defaults) and minimum surface area.
The synthesis stage already chose Sonnet for the same kind of work
(rendering polished prose from structured input + transcript). One source of
truth for "the model that renders meeting prose" reduces config drift.

**Alternatives rejected**:
- *Hard-code Sonnet in the new module.* Violates IV.1 (no magic numbers).
- *Require explicit model in `[notes]`.* Violates IV.2 (sensible defaults).

---

## D6 — Retry policy for the render call

**Decision**: Reuse the existing `@retry` decorator at
`src/notetaker/utils/retry.py` with the existing `[api] retry_count` and
`[api] retry_delay_seconds` config keys. Do not introduce a render-specific
retry knob.

**Rationale**: Q1 clarification: "Retry with existing project retry
policy." Spec FR-017 names the same configuration keys. Vision and
synthesis stages already use this decorator with these keys — the user has
one mental model and one tunable surface for "API call failure handling."

**Alternatives rejected**:
- *Custom retry knob in `[notes]`.* Violates Q1 ("existing project retry
  policy") and IV.2 (sensible defaults — fragmenting the surface).
- *Exponential backoff.* The existing policy is a fixed delay; changing
  that for one call would be inconsistent with the rest of the project.

---

## D7 — Working-doc placement inside the cache

**Decision**: Write `working_doc.md` and `notes.md` to a new
`<cache-root>/<url-hash>/notes/` subdirectory. Add this subdirectory to the
list of paths the existing retention purge SKIPS.

**Rationale**: Co-locating with the rest of the per-recording cache makes
the artifacts trivially discoverable (`ls
~/.local/share/notetaker/cache/<hash>/notes/`). A dedicated subdirectory
makes the purge-exemption rule simple ("skip any directory named `notes`
inside a cache root"), avoids ambiguity if other Markdown files appear in
the cache, and keeps the `[notes] retention_days` knob's blast radius small.

**Alternatives rejected**:
- *Write next to `slide_content.json` in `understanding/`.* Mixes a
  user-facing output with a stage's intermediate artifacts; understanding's
  retention rules then apply transitively.
- *Write outside the cache (e.g., to the working directory).* Loses the
  URL-hash → recording-cache association and makes re-render hard to
  resolve.

---

## D8 — Test fixture shape

**Decision**: Build a synthetic, byte-for-byte-stable fixture under
`tests/fixtures/notes/` containing:
- A `slide_content.json` with 5 slides covering the spec's edge cases
  (normal slide, empty-title-only-raw-OCR slide, slide with bullets but no
  visual, slide with visual but no bullets, slide with all fields).
- Three transcript files (`transcript_block.txt`, `transcript.vtt`,
  `transcript.json`) all encoding the same 12-utterance conversation.
- A `working_doc.expected.md` for assembly assertions.

The render-call test uses a hand-written stub `notes.expected.md` with
1–2 slides of text, fed by a mocked Anthropic client.

**Rationale**: Article VII.2 (golden fixtures). Three transcript shapes
encoding the same content lets one parameterised test cover dispatcher
correctness ("all three roads lead to identical `TranscriptSchema`") and
working-doc invariance ("identical inputs produce identical working doc").
A real recorded meeting would be expensive to scrub for fixture use
(speaker names, NDA content) and is unnecessary at this layer.

**Alternatives rejected**:
- *Reuse the recovered cache from this session as the fixture.* Contains
  identifying speaker names and confidential content; not committable.
- *Ship only an integration test against a mocked render.* Missing the
  parser-dispatcher and assembly unit-test coverage required by VII.1.
