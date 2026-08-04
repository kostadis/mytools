---
name: project-similarity-cannot-separate-semantic-edits
description: A similarity threshold cannot tell a meaning-changing quote edit from a harmless disfluency edit — both are the same tiny edit distance; measured 0.92 corrupt vs 0.94 benign.
metadata: 
  node_type: memory
  type: project
  originSessionId: 1d9a0cda-e7bf-463a-a9a8-4a161baf615b
  modified: 2026-08-04T04:22:20.957Z
---

**The finding (measured 2026-08-03, first real DeepSeek calibration of
`sd_verify_quotes`, spec 007 T047).** Two quotes from the same DeepSeek run,
scored against the same VTT, both classified `near` (i.e. "traceable, probably a
disfluency edit"):

| score | extraction | transcript | what it is |
|---|---|---|---|
| **0.92** | "**My kind** has been spreading violence and pain…" | "**Mankind** has been spreading violence and pain…" | **meaning changed** — speaker made to talk about *his own kind* rather than humanity |
| **0.94** | "No, I have my soul is for rent." | "No, I, I have, my soul is for rent." | harmless filler removal |

The corrupting edit scored **below** the harmless one. `Mankind`→`My kind` is a
two-character edit; `I, I have,`→`I have` is three. **Edit distance ranks them
the same because they are the same size**, so no choice of threshold separates
them — lowering it to catch 0.92 sweeps in the whole mass of legitimate
disfluency edits, which is the alarm-fatigue failure the three-verdict design
existed to avoid.

**Why this matters beyond one CLI:** it is the general limit of similarity as a
*safety* signal. Similarity measures how much text changed; it is blind to
whether the change mattered. Same shape as the embedding-threshold lesson in
[[project-embedding-merge]] (0.93 tuned on nomic, silently wrong on
qwen3-embedding) — but worse, because there the right number existed and merely
had to be re-measured. Here **no number is right**: the two populations overlap.

**How to apply:** treat a similarity bucket as *"an edit happened here"*, never
*"the edit was safe"*, and never let one gate an automatic accept. Present the
band as a **triage queue sorted for human reading, scanned for changed words**,
not a pass/fail. When asked to "calibrate the threshold", check first whether the
two classes actually separate on the metric — if they overlap, the honest
deliverable is that finding, not a tuned number. Corollary for reports: any
copy saying a bucket is "overwhelmingly benign" is an active hazard; it trains
the reader to skim past the corruptions that live there.

Second measurement from the same run, worth keeping: **Stage 1 verification
covers only ~3% of DeepSeek's quoted material** (it emits 5 `> "…"` blockquotes
and 131 inline quoted spans; Claude emits 12 and 60 → 16%). Verifying blockquotes
only is correct — inline `"…"` is not reliably dialogue — but against this model
it means the check is near-decorative at Stage 1, and the volume is all in Stage 2.
The fix is a prompt contract (require `> "…"` for dialogue), not a looser parser.

Related: [[project-alias-identity-not-substitution]] (the other verbatim-integrity
scar), [[project-fact-atomicity]], [[project-embedding-merge]].
