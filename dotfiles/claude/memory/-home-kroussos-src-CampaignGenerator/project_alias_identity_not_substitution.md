---
name: project-alias-identity-not-substitution
description: "An alias is an identity assertion, not a rewrite rule — passing the equivalence set to a model as a text transform destroys which surface form was spoken; 7 call sites still do it."
metadata: 
  node_type: memory
  type: project
  originSessionId: 1d9a0cda-e7bf-463a-a9a8-4a161baf615b
  modified: 2026-08-04T05:03:53.133Z
---

**The rule:** pass the equivalence set to a model as **knowledge**, never as a **transform**.
An index answers *"are these the same?"*; it is not licensed to answer *"what should this text
say?"* The moment a consumer treats it as the latter, every *correct* alias becomes a
corruption vector.

**How it burned us.** `session_doc/scene_extract.py` piped the VTT through
`campaignlib.npc.build_alias_normalizer` — a whole-word regex replacing every registry alias
with its canonical — *before the model saw it*. Phandalin ch. 47 got 24 corrupted "verbatim"
quotes: `Lord Lord Cassian Meliamne`, `Spire of the Lathander` (tape said Morninglord),
`a Cryovain?` (tape said a dragon). DeepSeek and Opus 4.8 produced the *same* errors — they
faithfully transcribed a pre-corrupted transcript. Fixed in **`6e00f54` (PR #231)**:
`input_normalizer` removed from scene extraction (the roster still reaches the model via
`format_npc_roster` in the system prompt), plus an idempotency guard in
`build_alias_normalizer`.

**The corollary that makes it non-obvious: the correct aliases do most of the damage.**
Stripping the five genuinely-bad aliases fixed only 4 of 11 corrupted lines. Cleaning alias
data cannot fix a consumer asking the index the wrong question.

**Still live — verified on `origin/main` 2026-08-03, 7 call sites in 6 files:**
`session_doc/sd_narrate.py:191`, `pipelines/grounding/campaign_state.py:242`,
`pipelines/grounding/distill.py:108`, `pipelines/grounding/party.py:295`,
`pipelines/grounding/planning.py:548,679`, `server/routers/connections.py:427`.
`sd_narrate` is the one that still matters for verbatim — narration renders quotes, so
form-loss there reaches the table. The `6e00f54` guard stops the *doubling* at all of them but
not the form-loss at any of them.

**Why:** this is Constitution Principle IV (*Verbatim is Sacred*) generalized. A verbatim
record's whole payload is *which words were used*; a write-time normalization deletes exactly
that while looking like a correctness improvement. Synthesis pipelines want the aggregation
benefit ("these three mentions are one entity") — the roster gives them that with none of the
loss.

**MEASURED 2026-08-03 — the damage was ~22 points of verbatim fidelity.** Same session
(Phandalin 20260623), same VTT, same 6 scenes, same Stage 1 summary, scored by
`sd_verify_quotes`:

| extraction | quotes | exact verbatim | unverified |
|---|---|---|---|
| Claude, **pre**-`6e00f54` (2026-06-26) | 522 | 374 (**71%**) | 31 |
| Claude, **post**-fix (subscription backend) | 377 | 352 (**93%**) | 12 |
| DeepSeek V4 Flash, post-fix | 390 | 371 (**95%**) | 12 |

Post-fix Claude and post-fix DeepSeek are **indistinguishable**. Two consequences worth
carrying: (1) the pre-fix corpus also extracted 38% *more* quotes (522 vs 377) — unexplained;
(2) spec 007's founding measurement, *"only 64% of quotes are exact verbatim even from
Claude"*, was measuring **this bug**, not model behaviour. Any argument resting on that 64%
(alarm-fatigue estimates, "186 findings per session") is void. Caveat: June's model version is
unknown, so "pre-fix era" bundles code path + model version; the delta is definitely not
Claude-vs-DeepSeek, but `6e00f54` is not isolated to the exclusion of prompt/model drift.

**How to apply:** when extraction output looks systematically wrong, **regenerate with a
different model first** — identical errors across model families means deterministic code, not
hallucination. Tells: *doubling* around a canonical name is always find-and-replace; and
"fabrications" that are canon-*correct* every time point at a lookup table, since a
hallucinating model gets some wrong. Before adding any alias handling, ask whether the consumer
needs to *know* the identity or to *rewrite* the text — and never choose rewrite on a path that
carries quotes. Pre-`6e00f54` scene extractions are still corrupt on disk; the remedy is
re-extraction, not repair — and the table above is the argument for actually doing it.

**Do not try to reconstruct the old corruption with today's code to "prove" it happened.**
Tried it; the test was invalid. `build_alias_normalizer` now carries the idempotency guard
added *in `6e00f54` itself*, so re-normalising a VTT today does not reproduce June's
normaliser — it made scores *worse*, which briefly looked like evidence against the alias
hypothesis. Re-run the real extraction instead.

Related: [[project-alias-fragmentation]] (the four-store fragmentation this registry replaced),
[[project-registry-import-order-and-check]], [[project-entity-registry-rollout]],
[[project-fact-atomicity]].
