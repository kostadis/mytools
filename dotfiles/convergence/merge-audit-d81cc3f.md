# Merge audit: `d81cc3f` (2026-08-30)

`d81cc3f` merged `kostadis/skills/20260829-transcript-attribution` (second parent `b4bea66`) into `d59bea1`, from merge base `ce0ef5b`.

**Method.** The check is deterministic, not an impression. For each of the 25 files both branches changed, I took the lines each side added relative to the merge base. A line counts as **lost** if it is absent from the merge result, and as **still missing** if it is also absent from today's `HEAD`. The lost lines were then grouped into contiguous blocks. Every block is reproduced verbatim, with line numbers from `b4bea66`, in [merge-audit-d81cc3f-lost-blocks.md](merge-audit-d81cc3f-lost-blocks.md).

The "HEAD covers it?" column is my reading of today's file. It is a draft for you to check, not a ruling.

## Result by file

| File | Lost | Still missing on HEAD | Verdict (draft) |
|---|---|---|---|
| 5 × `dotfiles/claude/memory/…` | 99 | 99 | **Correct drop.** `main` had stopped tracking memory on 2026-08-08 (`fb617d1`, "claude-memory owns it"). The branch's edits to those files belong in `~/src/claude-memory`. Whether they reached it is not checked here. |
| `staged-consistency/SKILL.md` | 254 | 254 | Mixed. See §A and §B. |
| `voice-smooth/SKILL.md` | 66 | 66 | Review-mode design only. See §A. |
| `scrub/SKILL.md` | 73 | 73 | Review-mode design only. **Superseded** by `b52d11f` (2026-09-19); see §A. **Not in the original TODO.** |
| `session-summary-consistency/SKILL.md` | 0 | — | Nothing lost. Both sides' text was kept and stitched into two review flows; see §A. |
| the other 19 shared files | 0 | — | Clean. |

## §A. The review-page design: one decision covers four skills

Most of what was lost from `voice-smooth` and `scrub`, and part of `staged-consistency`, is one feature:
- a **"Choose the review mode" `AskUserQuestion`** (artifact or shell, asked every run), and
- an **"Artifact mode (batch review)"** section built on the shared builder `~/.claude/skills/_shared/review-artifact/`. The page republishes itself; the save arrives as an `artifact-changed` notification and is read back with `WebFetch` and `read_decisions.py`. The section also carries a verdict-mapping table, card shape, what is auto-applied, and the rules on notifications versus polling.

**What today's files do instead:**

| Skill | Review page today | Transport |
|---|---|---|
| `staged-consistency` | "Alternative sign-off: interactive artifact" (L149) | **`downloads`**. L155 argues explicitly *against* the `artifact` approach. |
| `voice-smooth` | "Reporting at volume — the interactive review artifact" (L220) | **`downloads`** |
| `session-summary-consistency` | **both**, stitched together by the merge | `downloads` + Markdown record, **and** the shared-builder `artifact` path |
| `scrub` | Phase 2 "batch review and explicit GM approval, ALWAYS" (`b52d11f`) | shell-side batch sheet; the GM replies `approve recommended batch` or lists exceptions |
| `dialogue-edit`, `speaker-attribution-text` | shared builder | `artifact` (self-republishing) |

So the Claude side currently runs **three review designs**. The merge didn't choose between them on purpose. It kept whichever text survived each conflict. `_shared/review-artifact/CONTRACT.md:4,57` still lists `voice-smooth` as a caller, and it no longer is one.

**Decision A1: which review page do Claude skills use?**
- **Shared builder (`artifact`):** one contract, and the page updates itself. It's what the lost sections, `dialogue-edit` and `speaker-attribution-text` use. The cost is the live-sync machinery that `staged-consistency:155` warns about.
- **`downloads`:** a simpler one-shot export. You download and paste, or give the saved path.

Draft suggestion: the shared builder. Two skills already depend on it, and TODO item 2 (converge `_shared`) exists to harden it. Either way, this should be settled **before** item 2, not after.

**Decision A2: `scrub`.** The lost artifact mode used to replace Phase 2. `b52d11f` has since rewritten Phase 2 as a shell batch sheet with an explicit batch approval. Draft: **reject restoring it.** It's superseded, and restoring it would put two Phase 2 designs back in the file.

**What follows from A1:**
- **Shared builder:** restore the lost sections in `voice-smooth` and `staged-consistency`, delete their `downloads` sections, and remove `session-summary-consistency`'s `downloads` half. Also restore `Artifact, WebFetch` to the `tools:` lines of `staged-consistency` and `voice-smooth`. The merge lost those lines too.
- **`downloads`:** move `dialogue-edit`, `speaker-attribution-text` and `session-summary-consistency` off the shared builder, and fix `CONTRACT.md`'s caller list.

## §B. `staged-consistency`: lessons lost that have nothing to do with review pages

These don't depend on §A. Each is a separate restore-or-reject.

| # | Lost block (L in `b4bea66`) | What it said | Does today's file cover it? | Draft |
|---|---|---|---|---|
| B1 | L50-77 | **The raw VTT is the attribution authority.** Read from `*.cleaned.vtt`, settle "who said X" against the raw labels. Never settle attribution from a summary, even two agreeing summaries. | No ("raw VTT": 0 hits). | Restore |
| B2 | L50-77 | **`zoom-summary.md`**: use it only as a structural cross-check for dropped beats. Its agreement with the recap on "who" counts as zero evidence. | No (0 hits). | Restore |
| B3 | L90-94, L97-110 | **Filenames vary** (`session_<date>_…md`, `session_summary.md`, `scene_extractions/` vs `_new/`); don't conclude a stage is missing from a failed `ls`. | No. L86/L263's `{,_new}` globs were lost too. | Restore |
| B4 | L97-110 | **Check input mtimes first.** Was stage N built from corrected stage N-1? If not, the run is a re-do. Plus `.cg/activity.jsonl` names the real input and output paths. | No (`activity.jsonl`: 0 hits; `ls -t` appears only for listing sessions). | Restore |
| B5 | L97-110 | **Read `.sources.yaml` before building a card.** Grep the rulings log for the finding's subject. A prior ruling makes the finding a *conflict to surface*, not a question to re-ask. | **Partly.** L105 says to read prior `*.sources.yaml` and treat them as hypotheses. It lacks the "never re-card a ruled question" rule and the `gm_rulings`/`open_items` fields. | Restore the missing half |
| B6 | L112-155 | **§1b verbatim sweep with `verify_quotes.py`**: a deterministic check of inline prose quotes, and a warning not to hand-roll it with grep across cue boundaries. | **Replaced** by `sd_verify_quotes` (L192, L260), which checks scene-extraction quote blocks but **skips inline prose quotes**. `verify_quotes.py` still ships in the skill dir with nothing referencing it, and its docstring wrongly claims it catches misattribution. | **Your call:** restore §1b alongside `sd_verify_quotes` (with the docstring fixed), or delete the script |
| B7 | L214-233 | **Attribution generally** (not just kills); check every named action against raw VTT labels. | Partly (attribution appears 13 times, but not as this checklist). | Restore |
| B8 | L214-233 | **A retraction is not self-justifying.** Check the rule before recording a GM take-back as correct. | Partly. L266 covers retracted *name* slips, not rule take-backs. | Restore |
| B9 | L214-233 | **Never write "RAW" without naming the edition.** Cite "PHB 2024, p.304"; the on-disk 5etools JSON settles it. | No ("edition": 0 hits). | Restore |
| B10 | L214-233 | **Planned vs resolved.** Extractors write a resolved action as an intention near session end. | No. | Restore |
| B11 | L268-272 | **Use `grep -F` with a whole distinctive clause**, never a short token (the `Mechanis` vs `Mechanist` phantom finding). | No. | Restore |
| B12 | L275-295 | **Upward propagation.** A ruling applied only at stage 1 leaves the error in the stage-0 input, and the next `enhance_summary` re-injects it. Ask: edit in place, write `-update.md`, or accept. | Partly (L11 describes re-injection in general, not this case). | Restore |
| B13 | L275-295 | **A flag written into a regenerated file doesn't survive.** Durable follow-ups go to `notes/issues/YYYYMMDD_slug.md`. Ask before filing. | No. | Restore |
| B14 | L275-295 | **Never edit `logs/*_enhance_summary.md`**; it's an append-only run log. | No. | Restore |
| B15 | L304-315 | **Final-summary items:** the `zoom-summary` scorecard, which stages did not exist, and offer to write `consistency_report_stage<N>_*.md` plus `.sources.yaml` with `open_items` even when empty. | Partly (L303 covers one manifest per stage). | Restore the missing items |
| B16 | L431-465 | **Notes: OOTA Ch 65 cases** (attribution miscredited by two summaries; read-aloud garble "Alyss proved right"; the rulings-log miss; the PHB 2014 vs 2024 edition trap). These are the evidence behind B1, B5 and B9. | No. | Restore (the evidence for the rules) |

## §C. What to decide

1. **A1:** shared builder or `downloads` for Claude review pages.
2. **A2:** reject restoring `scrub`'s artifact mode (superseded)? Draft: yes.
3. **B1–B16:** restore as drafted, or strike individual items.
4. **B6:** keep `verify_quotes.py` (restore §1b, fix the docstring) or delete it.
5. **Memory:** should I check whether the branch's edits to the five memory files reached `~/src/claude-memory`?

## §D. Rulings (GM, 2026-09-24) and what was done

| Item | Ruling | Done |
|---|---|---|
| A1 | Shared builder | `staged-consistency`: 0a review-mode question and Artifact mode restored; the `downloads` "Alternative sign-off" section replaced, with its points that don't depend on the page type kept (run everything first, read Discuss notes, propagation still applies, external actions need a separate yes). `session-summary-consistency`: `downloads` half removed. `CONTRACT.md` caller list fixed. |
| A1 · voice-smooth | Keep today's flow, switch the page to the shared builder | The garble-rulings page, re-asking unmarked cards and confirming Discuss notes are all kept; only the page mechanics changed. The lost pair-review Artifact mode was **not** restored, because it conflicted with the later "don't dump pairs after calibration" lesson. |
| A2 | Don't restore `scrub`'s artifact mode | Nothing restored; the contract now says `scrub` doesn't use the builder. |
| B1, B2, B7–B10 | Restore, **into `/consistency-check`** (method lives there, per `staged-consistency`'s own rule) | 4.7: attribution by speaker labels never by summary, `zoom-summary.md` as a dropped-beat check only, attribution generally, rule take-backs, planned vs resolved. 5: name the PHB edition. `staged-consistency` step 1 points to them. |
| B3–B5, B11–B15 | Restore into `staged-consistency` | Step 1: filenames vary, `{,_new}` globs, `activity.jsonl`, input mtimes, rulings before cards. Step 6: `grep -F`, upward propagation, `notes/issues/`, never edit enhance logs. Step 8: `zoom-summary` scorecard, stages NOT RUN, offer the stage report. |
| B6 | Keep both | §1b verbatim sweep restored; `verify_quotes.py` docstring no longer claims it catches misattribution (it strips speaker labels). Smoke-tested: a cross-cue quote passes, an invented quote is flagged. |
| B16 | Restore | Split by the same rule: attribution, retraction, read-aloud and edition cases go in `/consistency-check` Notes; the rulings-log case goes in `staged-consistency` Notes. |
| Memory | Check | **The edits never reached `claude-memory`.** Not one of the 99 lines is in any copy (e.g. the "Second mechanism… PR #246" paragraph in `reference_worktree_editable_install_shadowing.md`), and `project_claude_code_backend_thinking.md` doesn't exist there at all. They survive only in git at `b4bea66`. Nothing was changed. |

**Deliberate deviations from verbatim restoring, for review:**
- The restored `staged-consistency` auto-apply list **drops "GM real name scrubbed to GM"**: `/consistency-check` step 5 now classes a real-name scrub as an attribution change, so it becomes a card. `session-summary-consistency` still auto-applies player-name scrubs in speaker labels. That's the open conflict in [session-summary-consistency.md](session-summary-consistency.md) and wasn't changed here.
- The `staged-consistency` rulings lookup reads both manifest names (`consistency_stage<N>_*` from step 7, `consistency_report_stage<N>_*` from older runs). The two names already disagreed before this change.
- Stale config text in `staged-consistency` (CWD auto-detection, the throwaway Phandalin config) was rewritten to match the #484 rule, since it now contradicted `/consistency-check`.
