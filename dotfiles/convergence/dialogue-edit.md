# Convergence report: dialogue-edit

Compared: `codex/skills/dialogue-edit/` vs `claude/skills/dialogue-edit/` (paths relative to `/home/kostadis/src/mytools/dotfiles/`).

## 1. Summary

This pair has **low substantive divergence**. The Claude side is a one-way port of the Codex side, made on 2026-09-20 in `20069d6` ("Port direction for this change is codex -> claude"). The Codex original was authored on 2026-09-06 (`40761e1`) and re-landed unchanged in `8bfd959` (2026-09-18). Neither side has changed since.

The "~208 changed lines" in `SKILL.md` are almost all re-wrapping and light copy-editing: bolding, em-dashes, British "neighbouring/labelled", "shared-page" → "shared-artifact". Only about five hunks change meaning, and every one of them is a harness adaptation. The script is byte-identical, `editorial-guide.md` is identical, and the test differs by one path. Codex is the source of truth; Claude is current with it. I found no rule that was lost in the port except one small sentence in the reference (§3).

## 2. File inventory

| file | codex | claude | status |
|---|---|---|---|
| `SKILL.md` | 220 | 218 | differs (reflow + harness adaptation) |
| `references/editorial-guide.md` | 91 | 91 | identical |
| `references/review-and-apply.md` | 158 | 174 | differs (the review-surface section rewritten for Artifact) |
| `scripts/review_edits.py` | 360 | 360 | identical |
| `tests/test_review_edits.py` | 240 | 240 | differs (1 line: the builder path) |
| `agents/openai.yaml` | 4 | — | only-codex (platform metadata) |

`__pycache__/` and `.pytest_cache/` are ignored. Running the tests below may have created or refreshed them on both sides; they are gitignored.

## 3. Only in Codex

1. **Use a fresh page path and keep returned decisions.** `codex/skills/dialogue-edit/references/review-and-apply.md:110`: "Use a fresh page path; retain any already-returned decisions." The Claude rewrite of that paragraph (`claude/.../review-and-apply.md:110-131`) drops this sentence. Claude instead says the page is "one page per scene run, and each run owns its own `run-dir`" (`:112-114`). That covers the fresh-path half by construction. The "retain any already-returned decisions" half is **not restated**, and it matters when a run is re-published after a partial save. This is the only substantive loss I found. Confidence is medium, because the concept may be implied by the helper's decision-file handling.
2. **Browser state is not a callback.** Codex `review-and-apply.md:111-113`: "Only pasted or saved decision JSON from this page authorizes its changes; browser state is not a callback." Claude has the equivalent at `:128-130`: "a mark left on screen but never saved is not a ruling." **Concept present on both sides** and adapted, not lost.
3. **The Codex-harness execution note.** `codex/SKILL.md:207-208`: "The active Codex conversation does not expose a standalone submitted prompt pair; do not fabricate one." Claude keeps the rule ("Do not fabricate a submitted prompt pair", `claude/SKILL.md:206`) and drops the Codex-specific reason. This is platform only.

Everything else in Codex `SKILL.md` has a Claude counterpart at the same position. I checked each diff hunk.

## 4. Only in Claude

1. **The Artifact publish, stop and read-back loop.** `claude/.../review-and-apply.md:110-125` and `claude/SKILL.md:152-157`:
   - "Publish that file with the `Artifact` tool using **`capabilities: {"artifact": {}}`** — without it the page cannot save and the GM silently gets the read-only fallback."
   - "Then **stop** … Never poll for it. Read it back with `WebFetch` … `read_decisions.py --html <saved-artifact.html> --out …/decisions.json`."

   Codex has no equivalent because its page has no callback. This is platform-driven (§6), but it adds one real mechanism: `read_decisions.py` as the reader of the decision envelope. Codex relies on pasted or downloaded JSON.
2. **A richer frontmatter description.** `claude/SKILL.md:3` adds:
   - "so players recognize their own speech"
   - "never applies 'obvious cleanup' unreviewed"
   - "Runs after narration and any /scrub pass, before the final /voice-critic gate. The original narration, every extraction layer and the VTT are read-only."

   All of these rules already exist in the body on both sides. Only the trigger text is new.
3. **Asking via `AskUserQuestion`.** `claude/SKILL.md:84`: "if several sessions or scenes remain plausible, ask with `AskUserQuestion`." Codex says "ask" (`codex/SKILL.md:87`). Platform only.

## 5. Conflicts

None of substance. Two naming mismatches follow from the harness:

1. **What the review mode is called.** Codex `codex/SKILL.md:114` offers "**chat** or a **standalone review page**". Claude `claude/SKILL.md:111` offers "**chat** or an **artifact** review". Same choice, different surface.
2. **Where the shared contract lives.** Codex `../_shared/review-page/CONTRACT.md` (`codex/SKILL.md:155-156`); Claude `~/.claude/skills/_shared/review-artifact/CONTRACT.md` (`claude/SKILL.md:157`).

Neither is a convergence candidate.

A minor note, not a conflict between the pair: Claude's `_shared/review-artifact/CONTRACT.md:56-64` names the skills that follow its file-naming convention, and dialogue-edit is not listed. Dialogue-edit publishes one artifact per scene run, each at a new `run-dir` path and therefore a new URL. That is consistent with its own reference (`:112-114`), but it departs from the contract's multi-page rule ("The `--out` html stays on one path for the whole run"). It is worth knowing if the GM expects one page per session.

## 6. Platform-only differences

- Frontmatter:
  - Codex has `metadata.short-description` (`codex/SKILL.md:4-5`) and `agents/openai.yaml` ("Dialogue Edit", `$dialogue-edit` default prompt).
  - Claude has `tools: Read, Bash, Glob, Grep, Write, Edit, Artifact, WebFetch, AskUserQuestion` (`claude/SKILL.md:4`). This allowlist is correct for its review loop, unlike voice-critic and voice-smooth.
- `codex/SKILL.md:15-16`, "This is a **Codex skill** … It does not modify the Claude skill collection," was removed in Claude.
- Paths:
  - `$HOME/.codex/skills/dialogue-edit` → `$HOME/.claude/skills/dialogue-edit` (`review-and-apply.md:55`).
  - `_shared/review-page` → `_shared/review-artifact`.
- The review surface: a local page with paste or download (Codex) vs. an Artifact with a save callback, `WebFetch` and `read_decisions.py` (Claude). See §4.1.
- Asking the user: chat vs. `AskUserQuestion`.
- The Codex-conversation prompt-pair reason (§3.3).

## 7. Script diffs

- **`scripts/review_edits.py`**: byte-identical (`diff -q`). One property depends on the harness:
  - At prepare time, `review_edits.py:220-226` fingerprints `SKILL.md`, itself and `references/*.md` into `review.json` (`skill_sha256`). The two sides' `SKILL.md` and `review-and-apply.md` differ, so a run frozen under one harness records different fingerprints than the other would.
  - `apply` does not validate those fingerprints (grep finds `skill_sha256` only in `prepare`), so this does not stop a cross-harness apply. It only makes the audit record harness-specific.
- **`tests/test_review_edits.py`**: one-line difference at `:206`.
  - Codex: `builder = SKILL.parent / "_shared" / "review-page" / "build_review.py"`.
  - Claude: `… "review-artifact" …`.
  - The behaviour is identical: each tests HTML escaping through its own harness's shared builder.
  - I ran both suites: **15 passed, 15 subtests passed** on each side.
- The two shared builders (`codex/skills/_shared/review-page/build_review.py`, `claude/skills/_shared/review-artifact/build_review.py`) are out of scope here but do differ. From string literals: the Codex page has copy, filter and search features; the Claude page has font preconnect and stylesheet. Both accept the `review_page.json` that `review_edits.py prepare` emits, which the passing tests confirm.
- **Superset:** neither. The script is identical, and each test is correct for its own tree.

## 8. Open questions for the GM

1. **Should Claude restore "retain any already-returned decisions" when re-publishing a review?** Suggestion: yes. It is one sentence, and it guards against losing a partial save.
2. **Which side is the source of truth going forward?** Until now it has been Codex → Claude. Suggestion: pick one and note it in both `SKILL.md` headers. Otherwise the next edit on the Claude side will be invisible to Codex, the reverse of what happened with voice-smooth.
3. **One artifact per scene run, or one per session?** Today each scene run gets its own URL (`claude/.../review-and-apply.md:112-114`). Suggestion: either keep it and add dialogue-edit to the contract's file-naming list as a per-run page, or switch to the contract's single-URL multi-page pattern. The GM's review ergonomics decide this.
4. **Should `skill_sha256` in `review.json` be made harness-neutral?** One way is to fingerprint only `scripts/` and `editorial-guide.md`, which are identical. Suggestion: low priority. It matters only if runs move between harnesses and someone audits the fingerprints.
5. **Should the shared review builders (`review-page` vs `review-artifact`) be converged?** This is out of this pair's scope, but dialogue-edit depends on both, and they have drifted in features (copy, filter and search exist only in the Codex page).
