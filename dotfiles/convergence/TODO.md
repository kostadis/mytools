# Convergence: handle-first TODO

These are the prerequisites that must be settled before working through the per-skill open questions in [INDEX.md](INDEX.md).
They are ordered by dependency: each step changes what the steps below it are comparing against.

## 0. Pin the baseline

- [x] **Decide on the 3 uncommitted Claude edits**: committed as-is in `c4ae2c7` on branch `kostadis/claude-skill-field-lessons`.

Resolve the contradictions that commit left in place, on the same branch, before anything below. Each step changes what counts as "the Claude side".

- [x] **consistency-check: reconcile committed lines 77 and 81 with the new registry lesson.** The new text says a throwaway config drops the entity registry (fix: a `docs` symlink and an offline `find_registry` check). Lines 77 and 81 still describe the old recipe. Settled by your ruling: `<campaign>/config/config.yaml` is the only valid config, and anything else fails loudly. Step 2 was rewritten as a preflight that STOPs on a missing or misplaced config, on paths that don't resolve from `config/`, and on a missing registry. All throwaway/symlink workarounds were removed (uncommitted). The same bug is in Codex's "minimum useful config" recipe, which stays open for convergence.
- [x] **staged-consistency: fix line 147.** (mytools `5c701a3`) `grep -c "^### "` for counting findings contradicts the new consistency-check lesson that the report format changes from run to run. It depends on the item above, because it should point at whatever counting method consistency-check settles on. Step 1 below may also rewrite this file, so fix this first and re-check after the merge audit.
- [x] **vtt-spell-pass: correct the `--npcs-dir` note.** (mytools `5c701a3`: all three known-name flags optional, missing path fatal) The script only errors when the flag is *omitted*. A nonexistent path passes, because `parse_npc_dossiers` returns an empty set. Decide whether the note should say "pass the flag", or whether the script should also fail on a missing path, which would be a script change ([report](vtt-spell-pass.md) Q10). This item is independent of the two above.
- [x] Push `kostadis/claude-skill-field-lessons` and open a PR once the three items above are done.

- [x] **CampaignGenerator: `check_consistency.py:130` finds the registry from `base_dir` (`config/`) instead of the campaign root.** Every other tool uses the campaign root. Until this is fixed, the consistency-check canon STOP fires on every correctly placed campaign. `find_default_config` also ignores `<cwd>/config/config.yaml`. → Fixed in [CampaignGenerator#484](https://github.com/kostadis/CampaignGenerator/pull/484), along with fatal missing inputs and group rendering in `rejected_aliases`.
- [x] **After #484 merges (merged 7826178):** remove the skill's "Known bug: a correctly placed config currently trips this" paragraph in `consistency-check` step 2.
- [x] **Campaign configs failing the preflight:** (campaigns `b2e623fd`; Hillsfar and stormgiants still lack a registry) obelisk (stray root `config.yaml`), Phandalin and toee (`docs/` paths, need `../docs/`), Hillsfar and stormgiants (root config only, no registry). Only out-of-the-abyss passes.

## 1. Audit merge `d81cc3f` (2026-08-30)

Done. Rulings and changes are in [merge-audit-d81cc3f.md](merge-audit-d81cc3f.md) §D. Review design: **shared builder** for every Claude review skill except `scrub`.

This merge dropped content from three Claude skills. Restore or reject what it dropped, per skill, before comparing them to Codex.

- [x] **staged-consistency**: about 200 lines dropped from `2d9cc62`. They covered the raw VTT as the attribution authority, `zoom-summary.md`, variable stage filenames, checking input mtimes, and naming the edition when citing rules.
  - [x] Decide the fate of `verify_quotes.py`, which is now referenced by no SKILL.md. It checks inline prose quotes that `sd_verify_quotes` skips, and its docstring wrongly claims it catches misattribution.
- [x] **voice-smooth**: the "Artifact mode (batch review)" from `5092639`/`43f6e9c` was lost. `_shared/review-artifact/CONTRACT.md:4,57` still lists voice-smooth as a caller.
- [x] **session-summary-consistency**: two artifact flows were stitched together (`downloads` plus a Markdown record, and the shared-builder `artifact` capability). Pick one.
- [x] Check whether `d81cc3f` touched any other skill. Done with a merge-base line audit; **`scrub` also lost 73 lines** (its artifact mode, since superseded by `b52d11f`). Findings and decisions are in [merge-audit-d81cc3f.md](merge-audit-d81cc3f.md).

## 2. Converge `_shared` review code (every review skill depends on it)

- [x] **Bug (Claude):** `build_review.py:195,294`. `renderDoc()` writes `TITLE` unescaped into `<h1>`/`<title>` on save, which undoes `4aababa` on the first save.
- [x] **Bug (both):** neither `read_decisions.py` checks the returned ids against the queue.
- [x] **Ruled: Claude's meaning** (set only by an explicit GM save or export gesture). Codex already stamped only on Copy/Save; documented. Decide the semantics of `savedAt`. Codex stamps it at export, so its unsaved guard is dead and Claude's republish-dedup can't be ported.
- [x] **Ruled: removed.** Decide whether Codex's localStorage restore is allowed. It restores the previous run's marks on a re-review of the same VTT, a consent issue.
- [x] **Ruled: forbidden on both sides**; builders reject it, Codex `render_review.py` shows recorded decisions as text. Decide whether pre-seeded `state` decisions are allowed. Neither contract says, and Codex `render_review.py` does pre-seed.
- [x] Update Claude CONTRACT's out-of-date "five skills" caller list.
- [x] **Ruled: don't port** (Claude's vtt-spell-pass already covers it). Then decide whether to port `render_review.py` to Claude on top of review-artifact.

## 3. Fix bugs present on both sides (not a convergence choice)

- [x] **remove-recap order:** `SKILL.md:20` says to run "before `/scene-extract`", but the scripts read `scene_extractions_smoothed/`.
- [x] **remove-recap `rm` placement:** `SKILL.md:176` deletes `narration/session_doc_scene_*.md` *after* `sd_narrate` (`:174`), which wipes the new narration.
- [x] **vtt-spell-pass `prepare_input.py:218`:** `speakers` is only computed for `labelled_markdown`, so VTT input reports "none detected".
- [x] **no-mech:** both sides use a `--backend codex-cli --model gpt-5.6-sol` example (Claude `SKILL.md:311`). Decide whether that is intended on Claude.

## 4. Port known script fixes Codex → Claude (speaker-attribution)

- [x] `diarize_label.py` drops cues whose dialogue is only a number.
- [x] `--md-label` ignores the 50% coverage rule when the second source has no end times.
- [x] `name_clusters.py` label regex `[A-Za-z0-9_ ]{1,40}` silently drops labels like `Room (not at table)`, which the skill itself tells you to create (`SKILL.md:295-297`).

## 5. Small hygiene

- [x] Claude `tools:` frontmatter: add `Artifact` to voice-critic and voice-smooth, which both publish one.
- [x] `/home/kroussos/...` hard-coded paths in 7 files across both trees. This is your account on the other machines (MyDell2024, SiliconValley; see `dotfiles/CLAUDE.md`), so the paths break here on Linux-Alien. Make them portable (for example `~` or `$HOME`).
- [x] **Moved into `vtt-spell-pass/batch/`** (GM ruling), with `batch_scan.py`; Phandalin keeps the run data. vtt-spell-pass cites `merge_proposals.py` and `AGENT_BRIEF.md`, which exist only in `~/src/campaigns/Phandalin/notes/`. Bundle them or drop the reference.
- [x] `~/campaigns/STAGED_CONSISTENCY_HOWTO.md` is referenced, but on this machine it lives at `~/src/campaigns/STAGED_CONSISTENCY_HOWTO.md`. It's the same path-portability problem as `kroussos`.
- [ ] Decide whether the untracked `dotfiles/hermes/skills/productivity/vtt-spell-pass/` copy joins the comparison.
- [x] (Recorded in INDEX.md cross-cutting finding 2.) Commit `20069d6` claims the remaining pairs are in sync, which is false for scene-extract and voice-critic. Note this wherever that claim is relied on.

## 6. Per-skill decisions (from each report's §8)

Gaps against earlier rulings and the no-decision bugs are fixed (`kostadis/gaps-and-bugs`). What's left needs rulings, smallest first:

- [x] Small (done, GM-ruled 1x1): `_shared` review (output shape, multi-page naming on Codex, disable Save until marked, search/filter to Claude, Codex test recipe), `dialogue-edit` (source of truth, page per scene or session, portable fingerprint), `enhance-summary` (known-good command, backend pointer and scoping to Codex), `no-mech` + `remove-recap` (paid re-narration and exact-path gates on Claude, shared vs duplicated scripts), `speaker-attribution-text` (wording, description, cross-links, `AskUserQuestion`, batch review on Codex).
- [x] Medium (done, GM-ruled 1x1): `session-summary-consistency`, `consistency-check`, `staged-consistency`, `vtt-spell-pass`, `voice-smooth`.
- [x] Big design forks (done, GM-ruled 1x1): `scene-extract`, `speaker-attribution`, `voice-critic`.
