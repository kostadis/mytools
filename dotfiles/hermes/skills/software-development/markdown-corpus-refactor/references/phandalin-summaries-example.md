# Worked example: Phandalin docs/summaries refactor (2026-09-20)

Live artifact left on disk at `~/phandalin/scripts/summaries-refactor/`:
- `refactor_summaries.py` — dissolve `## Summary` into `### Scenes` via word-set
  similarity + monotonic DP (the technique in the parent skill), `--apply` flag,
  JSON dry-run report with LOW/EMPTY flags.
- `refactor_memorable.py` — section splice moving `## Memorable Moments` to sit
  between `## Scenes` and `## NPCs`, with an already-ordered skip guard.
- `README.md` — corpus-specific runbook: what each script does, run order
  (summaries first, then memorable), verification recipe, and the pitfalls hit
  (slice-boundary drop, argmax out-of-order, repair-pass contiguity break).

Corpus facts (verified against git HEAD): 53 files in `docs/summaries`; 50 with
Summary+Scenes; 3 `*-not-written.md` stubs (verified byte-identical after); 44
with `## Memorable Moments` — 35 before Scenes, 9 after Items; 12 distinct
`## ` section orderings across the corpus. Final end state: 50 files changed,
multiset-verified, both scripts idempotent (skip all 53).

Recovery path throughout: `git -C ~/phandalin checkout HEAD -- Phandalin/docs/summaries/`.

Note: the summaries in this corpus are near-duplicates in one case (049 vs
049a, same session, 049a later revision) — refactor each independently, never
assume one stands for the other.
