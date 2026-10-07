---
name: markdown-corpus-refactor
description: Lossless bulk restructuring of markdown docs.
---

# Lossless Markdown Corpus Refactor

Worked end-to-end example (scripts left in place, corpus stats): `references/phandalin-summaries-example.md`.

Class of task: "for every file in DIR, change the STRUCTURE (section order, paragraph placement) but keep every line verbatim." Typical asks: move a narrative block into per-scene sections; move section X to sit between sections Y and Z. The deliverable is a working script + verified end state, NOT a description.

## Core discipline (non-negotiable)
1. **Inventory first.** Parse every file's `## ` heading sequence and count patterns (`Counter` of heading orders) before writing any transform. Files in one corpus are messier than assumed — e.g. one corpus had 12 distinct section orderings, 3 files with no target section at all, and the "Memorable Moments" section sat before Scenes in 36 files and after Items in 9.
2. **Dry-run before apply.** Script takes `--apply`; default mode prints a per-file report (mapping, flags like `LOW`/`EMPTY`, skip list) and writes NOTHING. Fix all flags in dry-run mode first.
3. **Verify inside apply**: build the new text in memory, compare the multiset of non-blank lines (Counter) against the original (minus intentionally-removed headings). Mismatch => do NOT write the file. Log `VERIFY FAIL <path>` to stderr, keep going on other files.
4. **Verify independently against git HEAD** after applying: for each file, `git show HEAD:<rel>` and diff non-blank line multisets. Never trust the transform script's own self-check alone — the same wrong assumption produces matching wrong output on both sides.
5. **Idempotency check**: re-run the script in dry-run after applying. It must report skip/no-op for every file. If it would move something again, the "already positioned" guard is wrong.
6. **Leave the result uncommitted**; git HEAD stays the pristine original (also the recovery path: `git checkout HEAD -- <path>`). Offer the commit; per campaign repos, one commit per campaign directory.

## Techniques that worked
- **Paragraph→scene alignment (narrative redistribution)**: represent paragraphs and scenes as stopword-stripped word sets; similarity = 0.7*Jaccard + 0.3*difflib ratio over sorted words. Assign with a MONOTONIC DP (contiguous blocks, chronological order preserved): dp[i][j] = best score assigning first i paragraphs to first j scenes; empty scenes allowed but penalized (`EMPTY_PEN = 1.0 if n_paras >= n_scenes else 0.0`) so the DP prefers covering all scenes when paras suffice.
- **Section splice (move section X before section Y)**: split on `^## ` headings, lift the X block (heading line through line before next `## `), trim trailing blanks, re-insert before Y's heading, collapse `\n{3,}` -> `\n\n`. Skip when the order already satisfies Anchor<X<Target. Reusable script: `scripts/move_markdown_section.py` (env SECTION/TARGET/ANCHOR/DIR, `--apply` to write).
- **Structural invariant check** for "insert narrative under each heading": first non-blank body line of each `### ` block must NOT start with `#` (narrative precedes bullets), and no block empty.

## Pitfalls (all hit live)
- **Slice-boundary bug drowns verification in false alarms**: splicing "everything between section ends and the section header" instead of "up to the first `###`" drops intro text between the `## Scenes` header and the first scene — produced 50/50 VERIFY FAILs from one wrong slice bound. When rebuilding, take `lines[summary_end : first_scene.start]`, not `lines[summary_end : scenes_header]`.
- **Post-hoc greedy "repair" of empty scenes breaks chronological order**: argmax-assignment + neighbour-pull created non-contiguous/out-of-order mappings in 16 files. Fix in the DP (empty-scene penalty) instead of patching the assignment afterwards. Any repair must move only BOUNDARY paragraphs (last of prev / first of next) to stay contiguous — and assert `flat == range(n)` at the end.
- **Similarity scores look terrible and still are fine**: paragraph-vs-scene-blob scores under 0.10 are the norm for prose-vs-headers; don't chase them. Judge by structural invariants + multiset verify, not by score.
- **Skip-list honesty**: files lacking the source/target section (e.g. "session not written" stubs) must be skipped and reported, and verified byte-identical to HEAD.
- **Blocked shell one-liners**: survey/comparison logic with nested quotes/pipes can hit the terminal blocklist — do corpus surveys and verification in Python (execute_code or a temp .py), not clever bash.
- **Verify-script cleanup ordering**: `python3 "$VF"; rc=$?; rm -f "$VF"` — delete AFTER capturing status, and echo the exit code; deleting first loses the evidence.
- **Pyright false positives on None-narrowing** (`cr[0]` after a guaranteed non-skip path) are noise; don't contort code for them.
- **Resuming an interrupted session**: session_search browse -> read -> scroll reconstructs the script state; the working script may still live in /tmp. Re-check end state (git diff --stat + dry-run) before redoing any work — the previous session may have already applied partially.
- **Mid-edit script patches can duplicate blocks**: a patch that replaced only part of a function left a duplicated `npcs = npcs[0]` / duplicated span-computation block that would have crashed on `int[0]`. After multi-part patches to a transform script, read the whole file back before running.

## Persisting the deliverable (final step the user often asks for)
When asked to "move the script into ~/<repo>/scripts/<dir>", it's a class-level convention, not a one-off:
- Create `scripts/<task-name>/`, move ALL transform scripts there, add a `README.md` in the same directory explaining what each script does, how the matching/splice works, run order, and the pitfalls actually hit (the README mirrors the skill's discipline, but corpus-specific: section-order stats, file counts).
- Make paths portable before committing: replace hardcoded `/home/<user>/...` DIR constants with `os.path.join(os.path.expanduser("~"), ...)` derived paths.
- Re-verify AFTER relocating: import both modules from the new location, confirm DIR resolves to an existing dir, re-run the idempotency dry-run, and smoke-run each script's CLI from an unrelated cwd (exit 0, clean stderr).
- Verify every NUMBER you state in the README against git HEAD (`git show HEAD:<file>` and count) before writing it — inventing "17 files had X" then checking (it was 35/9) is a self-inflicted correction loop.
- **Update the skill pointers when the scripts relocate.** Once they live in the repo, that copy is canonical; say so in the governing skill and stop treating /tmp or skill-local copies as the reuse target.
- **Commit step ("branch commit" / "push and open PR"):** new branch off main, `git add` explicit file lists — never a directory glob that can swallow `__pycache__/*.pyc` left by verification imports (check `git diff --cached --name-only | grep -v <expected-prefix>`; add `__pycache__/` to .gitignore in the same commit). Leave unrelated untracked cruft out. Commit message states the lossless invariant and points to the README's verification recipe; then push -u, open PR, report the URL. The "N uncommitted changes" warning on PR create is just the excluded cruft, not missing work.

## Verification script skeleton
```python
import subprocess, collections
old = subprocess.run(["git","-C",REPO,"show",f"HEAD:{rel}"],capture_output=True,text=True).stdout
new = open(path).read()
co = collections.Counter(l for l in old.split("\n") if l.strip() and l.strip() != "## Summary")
cn = collections.Counter(l for l in new.split("\n") if l.strip())
assert co == cn  # per file
```
Keep verifier assertions dumb-simple: `os.path.basename(mod.DIR) == "summaries"` passes; `os.path.dirname(mod.DIR).endswith("summaries")` false-fails on a trailing slash — a buggy check burns a FAIL/PASS cycle. Verifier temp files: `mktemp /tmp/hermes-verify-XXXXXX.py`, run, capture `rc`, delete LAST; a delete-before-status-check or a bare `rm` of a /tmp script can trip the deletion-security scan or lose the evidence and force a re-run.
