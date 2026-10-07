# Codex ↔ Claude skill convergence — index

These are drafts for review, written by comparison agents on 2026-09-24. No skill file was edited.
Each report has 8 sections. Section 8, *Open questions for the GM*, lists the decisions you need to make. Items marked "Suggestion:" are input for you, not decisions.

The Claude-side reports for `consistency-check`, `staged-consistency` and `vtt-spell-pass` compare against your **uncommitted** working copy.

## Tier 1: nearly in sync (quick decisions)

| Report | Qs | Gist |
|---|---|---|
| [no-mech](no-mech.md) | 4 | Body identical except for `~/.codex`/`~/.claude` paths; scripts byte-identical. Codex adds "confirm before paid re-narration". Both sides use a `codex-cli`/`gpt-5.6-sol` example. |
| [remove-recap](remove-recap.md) | 5 | Scripts byte-identical. Codex adds 3 small safety rules. **Both sides:** the stated run order is impossible (reads `scene_extractions_smoothed/` "before scene-extract"), and the `rm` comes after `sd_narrate`. |
| [dialogue-edit](dialogue-edit.md) | 5 | Clean Codex→Claude port (`20069d6`). One sentence lost: "retain any already-returned decisions". Tests pass 15/15 on both sides. |
| [speaker-attribution-text](speaker-attribution-text.md) | 5 | Script and references byte-identical. Claude adds a paragraph on batch review. |
| [enhance-summary](enhance-summary.md) | 5 | Claude is the newer port. Claude probably mislabels `/session-summary-consistency` as "Stage 1". |

## Tier 2: one side is the base, the other has pieces to port back

| Report | Qs | Gist |
|---|---|---|
| [vtt-spell-pass](vtt-spell-pass.md) | 12 | Codex was forked from an older Claude snapshot and missed 4 main-line commits, so Claude is the superset. Codex's only extra is `render_review.py`. Claude contradicts itself on "one card per cluster" vs "one card per pair". Scripts it cites (`merge_proposals.py`, `AGENT_BRIEF.md`) live only in Phandalin/notes. |
| [voice-smooth](voice-smooth.md) | 12 | Codex condenses Claude and adds about 10 guardrails. **Claude lost its Artifact batch-review mode in merge `d81cc3f`** (verified), but `CONTRACT.md` still lists voice-smooth as a caller. |
| [consistency-check](consistency-check.md) | 10 | Codex is a condensed port and lacks most of Claude's settling lessons. Codex's "minimum config" recipe reproduces the registry-drop bug. |
| [staged-consistency](staged-consistency.md) | 11 | Close in structure. **Merge `d81cc3f` dropped about 200 Claude lines**, leaving `verify_quotes.py` referenced nowhere (verified). |
| [session-summary-consistency](session-summary-consistency.md) | 8 | Same method. Claude auto-applies some fixes (including speaker-label scrubs); Codex requires approval for every edit. Claude also carries two artifact flows left over from the merge. |

## Tier 3: real design divergence (needs your judgment)

| Report | Qs | Gist |
|---|---|---|
| [scene-extract](scene-extract.md) | 11 | Opposite approaches. Claude runs a mandatory attribution interview; Codex keeps parity with the UI. They conflict on output directory, per-scene `--max-tokens` (8192 vs 32000), `--force`, bundle mode and `sd_verify_quotes`. |
| [speaker-attribution](speaker-attribution.md) | 13 | Claude is the field manual; Codex is the stricter port. 16 conflicts, mostly "decisive" vs "clue for the GM". **Claude scripts have defects that Codex fixed**, e.g. labels with parentheses are dropped (verified). |
| [voice-critic](voice-critic.md) | 10 | Two separate writings. Claude has the measured cases and the scans; Codex has dialogue-edit awareness and a hash-frozen apply loop. 13 conflicts. |
| [_shared-review](_shared-review.md) | 11 | Same schema, different transport. **Claude's `renderDoc()` writes the title unescaped on save, which undoes `4aababa`** (verified). With Codex, `savedAt` makes the unsaved guard dead, and localStorage leaks marks from the previous run. |

## Cross-cutting findings

1. **Merge `d81cc3f` (2026-08-30) damaged three Claude skills**: staged-consistency (about 200 lines lost), voice-smooth (Artifact mode lost) and session-summary-consistency (two flows stitched together). The recommended first move is to audit that merge.
2. **`20069d6`'s claim that the "remaining pairs are in sync" is false** for scene-extract and voice-critic.
3. **Bugs shared by both sides** (fixing them is not a convergence choice): remove-recap run order and `rm` placement; `prepare_input.py:218` false "none detected"; neither `read_decisions.py` checks ids against the queue.
4. **Claude `tools:` frontmatter** in voice-critic and voice-smooth omits `Artifact`, although both skills publish one (verified).
5. **`/home/kroussos/...` paths** appear in 7 files across both trees and don't resolve on this machine.
6. **An untracked third copy** exists at `dotfiles/hermes/skills/productivity/vtt-spell-pass/` and was not compared.
7. The `_shared` review code is a dependency of every review skill, so converge it **before** the skills that call it.
