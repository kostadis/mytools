# Session-summary narrative refactor (docs/summaries/*.md)

Class of task: each summary file has a `## Summary` section (chronological
narrative paragraphs) and a `## Scenes` section (`### Title` + `#### bullets`).
The refactor moves each narrative paragraph under its matching `### Scene`, so
the final shape is `### Title` + narrative + existing bullets. Hard constraint:
**zero content change** — every non-blank line preserved verbatim; only ordering
and removal of the `## Summary` heading are allowed. Re-run
`scripts/refactor_summaries.py` (dry-run prints per-file JSON mappings + flags;
`--apply` writes, with a built-in multiset self-check that refuses to write on
mismatch).

## How alignment works
Paragraph order and scene order are both chronological, so the assignment is a
monotonic contiguous partition: DP over dp[i][j] = best score assigning the
first i paragraphs to the first j scenes. Similarity = 0.7·Jaccard +
0.3·SequenceMatcher over stopword-filtered content words (paragraph vs whole
scene blob).

## Pitfalls (each cost a debugging round-trip to discover)
- **argmax-per-paragraph breaks chronology.** Assigning each paragraph to its
  globally best scene produces out-of-order interleavings (observed on ~16 of
  50 files). Keep the monotonic DP; do not "fix" it with per-paragraph argmax.
- **Empty scenes: fix inside the DP, not with a post-hoc repair.** A post-hoc
  "pull a paragraph from the neighbor into the empty scene" pass must move ONLY
  a boundary paragraph (last of previous / first of next) or it breaks
  contiguity — and even then it stalled. The clean fix: penalize the "skip
  scene j, assign nothing" DP transition by a constant (EMPTY_PEN=1.0, only
  when n_paras >= n_scenes so truly-uncoverable files are exempt). The DP then
  spreads paragraphs to cover scenes itself. Went 7 empties -> 0, zero order
  violations, no repair code needed.
- **Rebuild slicing must end at the FIRST SCENE, not the `## Scenes` header.**
  `between = lines[summary_end : scenes_header_idx]` silently DROPS any intro
  text sitting between `## Scenes` and the first `###` — this caused
  VERIFY-FAIL on all 50 files. Slice `lines[summary_end : scenes[0]["start"]]`.
- **Some files legitimately lack Summary/Scenes** (the
  `NNN-session-not-written.md` stubs). The script must skip them and leave them
  byte-identical; count them (3 in Phandalin as of 2026-09) so "50 files
  touched" is checkable.
- **Duplicate-content files exist** (e.g. `049-` and `049a-` same session) —
  they process independently; don't dedup by hand.
- **Ad-hoc verify scripts: capture the exit status BEFORE `rm`-ing the
  script.** Deleting first loses the status signal. Pattern:
  `python3 "$VF"; rc=$?; rm -f "$VF"; echo "exit=$rc"`. Use
  `mktemp /tmp/hermes-verify-XXXXXX.py`, not a fixed path in a guarded dir.

## Verification gate (run ALL before declaring done; all must pass)
1. In-script multiset check: built into `--apply` (Counter of non-blank lines
   old-minus-`## Summary` vs new); any `VERIFY FAIL` on stderr = bug, fix and
   re-apply from a git-clean state
   (`git -C <repo> checkout HEAD -- <dir>`).
2. Independent check vs git HEAD: per file, `git show HEAD:<path>` and compare
   the non-blank line Counter against the working-tree file; assert no file
   still contains `## Summary`; assert every `### Scene`'s first non-blank body
   line is NOT a heading (narrative precedes bullets); assert untouched stub
   files are byte-identical to HEAD.
3. Idempotency: `process()` on the refactored files must return `skip=True`
   (a re-run is a no-op). Strongest end-state check.
4. `git diff --stat` sanity: churn ≈ insertions+deletions of the same moved
   lines (paragraphs moved, not rewritten).

## Resuming a truncated "continue"
This task spanned sessions: `session_search()` browse -> newest session ->
`session_search(session_id=...)` read, then reconstruct the script state from
the tool-call history (the last patch diff in the transcript shows the exact
script state). Check `/tmp/refactor_summaries.py` still exists and use
`git status` to see whether `--apply` already ran before re-applying.
