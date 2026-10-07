# Convergence report: staged-consistency

Paths are relative to `/home/kostadis/src/mytools/dotfiles/`. Claude citations refer to the **working copy**; lines from the uncommitted edit are marked **(U)**. "codex" means `codex/skills/staged-consistency/SKILL.md` and "claude" means `claude/skills/staged-consistency/SKILL.md`.

## 1. Summary

This is the one pair where Codex is longer: 454 lines against Claude's 340. The two versions are close in structure. Both use the same stages, the same orchestrator/method split, the same severity rubric, the grouped Stage 2 and the same stage-manifest naming. They differ mainly in the batch-review mechanism and in how much worked evidence each carries.

The lineage runs in both directions:
- Claude is the original (`4210f6f` 2026-05-25).
- Codex was ported on 2026-08-27 (`5b6d721`).
- Grouped Stage 2 landed on Codex first (`b8e42d0` 2026-09-01, "batch Stage 2 staged-consistency audits") and was adapted to Claude the same day (`eea1d1b`).
- Codex then pulled in Claude's later orchestration material (`8bfd959` 2026-09-18: Orchestration Boundary, inventory-first, NOT RUN, `docs/chapters/` backfill).
- `50afe91` and `23fa8ed` changed both sides together.

All four named recent Codex changes are present on Claude. "Record resolved consistency context" (`621c6cf`) touched only consistency-check on both sides, so it is at parity here.

Claude has an uncommitted +6-line edit (`claude:175-179`). It adds evidence that Stage 0 pays for itself (Ch 48 OOTA: 12 findings at Stage 0, then 6 at Stage 1) and a new ordering rule: "fix gm-assist before enhancing, never after."

A significant lineage finding: Claude commit `2d9cc62` (2026-08-29) added about 200 lines to this SKILL.md, along with `verify_quotes.py`. Merge `d81cc3f` (2026-08-30) kept the script and took the other parent's SKILL.md. As a result `verify_quotes.py` is **orphaned**: no current SKILL.md on either side references it. The lost guidance covered:
- the raw VTT as attribution authority
- `zoom-summary.md` as a dropped-beat cross-check
- stage filenames that vary
- checking input mtimes and `.cg/activity.jsonl`
- reading prior rulings before carding
- the "never say RAW without naming the edition" rule
- a verbatim-sweep step 1b

## 2. File inventory

| file | codex | claude | status |
|---|---|---|---|
| `SKILL.md` | 454 lines | 340 lines (working copy, +6 uncommitted) | differs |
| `verify_quotes.py` | absent | 73 lines | only-claude (orphaned, not referenced by the SKILL.md) |
| `agents/openai.yaml` | absent | n/a | not present |
| *Shared dependency:* review page builder | `codex/skills/_shared/review-page/{CONTRACT.md,build_review.py,read_decisions.py}` | `claude/skills/_shared/review-artifact/{…same names}` | differs (hundreds of diff lines per file). Outside this pair's scope but load-bearing; see §6 |

## 3. Only in Codex

1. **`sd_verify_quotes` exit-code semantics.** `codex:190-193`: "Exit `1` means the verifier ran and found unverified quotes or refusals; review them. Exit `2` means it could not run; mark quote verification degraded and do not describe the stage as fully cleared." Claude runs the tool at `claude:192-201` and `:260` but never says how to read its exit status. I confirmed the 0/1/2 contract in `~/src/CampaignGenerator/session_doc/sd_verify_quotes.py` docstring.
2. **Exclude `.reviewed` scene files.** `codex:97`, `:231`: "Exclude `.prev`, `.reviewed`, and `.scaffold` scene files." Claude excludes only `.prev` and `.scaffold` (`claude:91`, `:224`, `:290`).
3. **`gm-assist-update.md` in the inventory,** and Stage 1 uses whichever Stage 0 source was chosen. `codex:89`, `:174-176`: "Pass the selected Stage 0 source (`gm-assist-update.md` or `gm-assist.md`) as additional context." Claude inventories only `gm-assist.md` (`claude:89`) and always passes `gm-assist.md` at Stage 1 (`claude:187`). See §5 C5.
4. **Choose the review mode up front, every run, as its own step.** `codex:114-119`: "Ask whether to review each stage in a batch page or interactively in chat. Ask every run and do not remember a default." Claude has no up-front step. It offers the artifact when findings cross roughly a dozen (`claude:151`). See §5 C1.
5. **Auto-apply unambiguous mechanical fixes and report them in the footer.** `codex:412-413`: "Apply only unambiguous mechanical corrections that need no ruling, and name their count and touched files in the review `footer`." Claude staged has no footer or auto-apply class (Claude session-summary-consistency does).
6. **Cards state the consequences of both choices, and show both sides when grounding may be stale.** `codex:432-434`: "Each card must state the actual consequences of both choices … Where the audit may be wrong because its grounding source is stale, include evidence for both sides." Claude's card is "id, scene, severity, title, one-line detail, evidence, your recommendation" (`claude:154`), with no approve/reject consequence fields.
7. **An `unmarked` verdict, and approval never inferred from files.** `codex:444`: "**unmarked** | Keep unresolved; do not silently treat it as rejected or advance past unresolved Critical findings without saying so." Also `codex:446-447`: "Never infer approval from an HTML or queue file's existence, mtime, or browser storage." Claude's export has a `"pending"` status (`claude:156`) but no rule for what pending means at apply time.
8. **Apply each stage's rulings before the next stage runs.** `codex:402-404`: "Do not combine all stages into one end-of-run review: the user must rule on a stage, approved fixes must be applied, and only then may the next stage run against the corrected input." Claude implies one artifact per stage but never states the rule. Its "run every remaining check first, unstaged" (`claude:153`) is scoped to scenes within a stage. I am unsure whether Claude would allow a cross-stage artifact; the text doesn't forbid it.
9. **Record the transcript used for quote verification separately.** `codex:370-372` records both "the transcript used for quote verification and the transcript manually consulted." Claude records only the hand-consulted one (`claude:308`).
10. **The final summary includes what deterministic verification caught and the result of the propagation sweep.** `codex:385`, `:387`. Claude's final summary (`claude:316-327`) covers "What the VTT caught" but not verifier results or the sweep. Claude does include NOT RUN at `:111`.

## 4. Only in Claude

1. **(U) Stage 0 pays for itself, and gm-assist is fixed before enhancing.** `claude:175-179`: "fix gm-assist before enhancing, never after. Stage 0 on a gm-assist that has already been enhanced from is … no longer a virgin pass … the manifest has to say so."
2. **A table of the delegated steps that are REQUIRED at every stage.** `claude:17-27`: config, prep, context set, VTT adjudication and manifest, with "why staging makes it more important". Codex states the boundary in prose (`codex:37-45`) without the per-step rationale.
3. **External methodology doc.** `claude:9, 11, 340` reference `~/campaigns/STAGED_CONSISTENCY_HOWTO.md`. That file **does not exist** on this machine (`/home/kostadis/campaigns/…` is missing). It may exist under `kroussos`.
4. **Settle config before Stage 0, framed as the most expensive error.** `claude:47`: "a config mistake repeated across every stage is the most expensive error this skill can make." Codex has "Resolve config once and reuse it" (`codex:123`) without the rationale.
5. **Date-bounded prep, flat location-named prep, AskUserQuestion, explicit answer.** `claude:51`, `:58`. Codex delegates this to consistency-check (`codex:128-132`). Neither Codex skill has the date-bound concept (see the consistency-check report).
6. **Record `session_prep_used: false` in every stage's manifest.** `claude:58`. Codex records a prep-less run only "in the final summary" (`codex:141-142`). See §5 C6.
7. **Grep recipe for the bible chapter,** and the renumbering example (Phandalin ch08 = bible ch10). `claude:62-66`. Codex has the rule without the recipe or example (`codex:144-149`).
8. **Pre-read the glossaries while building the tiers.** `claude:81`.
9. **Speaker-label grep recipe.** `claude:96-101`. Codex has the concept (`codex:98-101`) but no command.
10. **The session-shape rationale:** a session with only gm-assist is "one `/consistency-check` with extra ceremony". `claude:109`. Codex has the choice (`codex:110-112`) but not the framing.
11. **ASCII severity-table template, "Going 1x1?", and sequential numbering.** `claude:117-143`.
12. **Inspect the report after a claude-code auto-continue warning.** `claude:147`. This is platform-specific (§6).
13. **Artifact sign-off details** (`claude:149-163`):
    - Confirm the batching choice and its scope with the user: "don't silently decide to batch, and don't silently decide what's in scope" (`:153`).
    - Load the `artifact-design` and `artifact-capabilities` skills (`:154`).
    - `downloads` rather than `artifact` capability (`:155`).
    - Export schema `{id, scene, severity, title, target, status, note}`, with an explicit `target` file per finding (`:156`).
    - "Treat an unambiguous note as a ruling and apply it" (`:159`).
    - Propagate to the sibling document's own Summary/Scenes/Items sections, not just one place (`:161`).
    - Record in the manifest that a ruling came via the artifact's JSON export (`:163`).
14. **Where `sd_verify_quotes` is blind,** with evidence. `claude:203-205`: the Phandalin ch08 run showed 27/27 verified while an invented "Santorini" sat in inline prose, and 26 blockquotes added by enhancement were all verbatim. Also `claude:201`: "a different one reports edits nobody made." Codex has the rule (`codex:195-197`) but not the evidence.
15. **Grouped-mode internals** (`claude:226-258`):
    - Loads a different agent prompt, `config/agents/session_doc/consistency_grouped.md` (`:226`).
    - "Duplicate paths are rejected outright" (`:240`).
    - The full list of fail-closed triggers (`:250`).
    - An older report is untouched on failure, so "check its timestamp" (`:248`).
    - Report shape: `# Grouped Consistency Report`, `## D01 — <path>`, `CLEAN`, and "count `**Location**` within each `## D` section" (`:256`).
    - "peer targets are not evidence for each other … neither the model nor you should pick a winner by frequency" (`:258`).
16. **Size the output ceiling:** `CG_CONSISTENCY_MAX_TOKENS` defaults to 32000 and should be raised before a large batch. `claude:242`. The environment variable belongs to `check_consistency.py`, so it may apply to codex-cli too; I could not verify whether the codex-cli backend honours it. Only the `CLAUDE_CODE_MAX_OUTPUT_TOKENS` forwarding is Claude-specific.
17. **"Changing the shape is fine if you say so and re-record it."** `claude:247`. This softens Codex's flat "do not silently retry per scene" (`codex:271`). The two are compatible: both forbid *silent* changes.
18. **Stage 2's two highest-value catches restated:** retracted GM slips and fused garbles. `claude:264-267`. Codex leaves these to consistency-check, whose Codex version has only one-line forms of them.
19. **Worked examples for quote-fix conventions:** the italic editorial note (Prutha "great-uncle said dawn") and the Phandalin "blacklist" table vocabulary. `claude:271-273`. Codex has the rules without the examples (`codex:300-304`).
20. **In grouped mode the gate moves to the artifact;** every finding needs an explicit ruling. `claude:275`.
21. **Notes** (`claude:333-340`):
    - "Method lives in `/consistency-check`; sequencing lives here … Duplicating method here is how the two drifted apart before" (`:334`).
    - Failure profile per stage (`:337`).
    - Grouped Stage 2 is a call-shape change, not a review-gate change: "If a grouped report ever starts auto-applying anything — glossary anchors included — that is the bug" (`:338`).
    - The Ch 41 discovery case (`:339`).
22. **Lost content, not currently on either side.** This was in Claude `2d9cc62:SKILL.md` and dropped by merge `d81cc3f`. Listed so the GM can decide whether to restore it (quotes are from `git show 2d9cc62:dotfiles/claude/skills/staged-consistency/SKILL.md`):
    - "**The raw VTT is the attribution authority.** … Read *from* the cleaned one and *adjudicate against the raw one*."
    - "`zoom-summary.md`, if present … use it for exactly one thing: a structural cross-check … Two summaries agreeing on 'who' is not corroboration — it is a shared failure mode."
    - "**Filenames vary.** … Do not conclude a stage is missing from a failed `ls`", covering `session_summary.md` and `scene_extractions/` without `_new`. Both current versions hard-code `session-summary.md` and `scene_extractions_new/`.
    - "**Check the input mtimes before checking anything else**", plus `.cg/activity.jsonl`.
    - Read `consistency_report_stage*.sources.yaml` rulings before carding: "A finding whose subject already carries a GM ruling is not a fresh question."
    - "**Never write 'RAW' without naming the edition.**", with the 5etools on-disk spell paths.
    - "Step 1b. The verbatim sweep", which invokes `verify_quotes.py`.
    - Also: "Planned vs. resolved", "Never edit `logs/*_enhance_summary.md`", and "A flag written into a regenerated file does not survive."

## 5. Conflicts

**C1. When and whether to ask about review mode.**
- Codex `:116-117`: ask every run, up front, before any stage.
- Claude `:151`: "When the finding count crosses roughly a dozen, or the user asks for a batch/downloadable review, offer this". Claude `:219` also says Stage 2's call shape must be settled "*before* running anything."
- Codex asks unconditionally at the start. Claude offers the artifact based on a threshold, per stage, except that the Stage 2 choice is up front.

**C2. The batch-review mechanism and decision schema.**
- Codex `:398-430`: shared page at `~/.codex/skills/_shared/review-page/`, `build_review.py`, input JSON `staged_consistency_stage_<N>_review.json`, ids like `s1-03`, verdicts approve/reject/discuss/unmarked, and the user pastes JSON or points to a file.
- Claude `:154-156`: a hand-built HTML artifact with `downloads` capability. The export is `{id, scene, severity, title, target, status, note}` with status `pending|accept|reject|discuss`.
- The two schemas do not match (Codex `t/y/n/ev` cards versus Claude `title/target/status`), and neither do the verdict vocabularies (`approve` versus `accept`). The harness accounts for part of this (§6), but Claude has its own shared builder (`claude/skills/_shared/review-artifact/build_review.py`) that sibling skills use (claude session-summary-consistency `:171-183`). The staged skill has stopped using it; the pre-merge `2d9cc62` version did use it. So Claude staged now differs from its own sibling Claude skills as well as from Codex.

**C3. The count pattern for single-document stages.**
- Claude `:147`: "Derive your own count from the saved report (`grep -c "^### "`)".
- Claude consistency-check (U) `:213`, `:233` says `^### ` is a guess and to run every pattern, so the Claude pair now contradicts itself.
- Codex `:329-331`: "count findings from its body; grouped Stage 2 uses its per-document sections", with no pattern given. That is closer to the new consistency-check guidance.

**C4. The expected campaign root markers.**
- Claude `:41`: "confirm CWD is a campaign workspace (contains `docs/`, `summaries/`, `config.yaml`)."
- Codex `:68-69`, `:82`: "`docs/`, `summaries/`, and `config/` … Do not require a root `config.yaml`."
- This is the same layout conflict as consistency-check C1.

**C5. The Stage 1 context file.**
- Codex `:174-176`: the chosen Stage 0 source, `gm-assist-update.md` or `gm-assist.md`.
- Claude `:187`: "Also pass `gm-assist.md` as context." Yet Claude `:181` says the `-update.md` is canonical when it exists.
- Codex is internally consistent here. Claude is not.

**C6. Where a prep-less run is recorded.**
- Codex `:141-142`: "record in the final summary".
- Claude `:58`: "record `session_prep_used: false` with the reason in every stage's manifest."
- These are compatible if both are done. As written, Codex omits the manifest record.

**C7. Step order versus text.**
- Claude numbers config and prep as step 0 and the inventory as step 1 (`:38`, `:83`), but `:109` says "Do this inventory FIRST, before config, before prep discovery."
- Codex orders it correctly: step 0 is inventory (`:84-85`), step 2 is config and prep.
- This isn't a cross-side conflict so much as a Claude internal inconsistency that Codex has already fixed.

**C8. Backend.** `--backend codex-cli` (`codex:257`) versus `--backend claude-code` (`claude:169`, `:235`). This is platform-only; see §6.

## 6. Platform-only differences

- **Frontmatter:** `tools: … AskUserQuestion` (`claude:4`) versus `metadata.short-description` (`codex:4-5`).
- **Port header and compatibility block:** Codex `:14-35` includes "Do not use Claude Artifact mode. Codex has no equivalent save notification", "Keep the user informed as each stage starts, stops…" and `apply_patch`.
- **Backend:** `claude-code` versus `codex-cli`. The Codex side has the "do not switch providers" stop rule (`codex:31-35`). Claude's `CLAUDE_CODE_MAX_OUTPUT_TOKENS` forwarding and the auto-continue seam (`claude:147`, `:242`) are Claude-backend-specific.
- **Review UI plumbing:** a Claude Artifact with the `downloads` capability and the `artifact-design`/`artifact-capabilities` skills (`claude:154-155`), versus a standalone HTML file from Codex's shared builder with pasted or downloaded JSON (`codex:24-26`, `:417-427`). The *transport* is platform-only. The *decision schema and verdict set* are not (§5 C2).
- **The shared builders themselves differ:** `codex/skills/_shared/review-page/*` versus `claude/skills/_shared/review-artifact/*` show 290, 295 and 123 diff lines for CONTRACT.md, build_review.py and read_decisions.py. Codex's contract uses `reviewId`/`outputName` with Copy/Save output. Claude's uses `capabilities: {"artifact": {}}` and `artifact-changed` notifications. This probably needs its own convergence pass.
- **Invocation:** `/consistency-check` slash-skill (`claude:27`) versus reading `~/.codex/skills/consistency-check/SKILL.md` (`codex:27-29`).
- **`agents/openai.yaml`:** absent.

## 7. Script diffs

**`verify_quotes.py` (Claude only, 73 lines; orphaned).**
- **What it does.** It strips a VTT to cue text (drops `WEBVTT`, numeric cue ids, `-->` timing lines, and leading `Name:` speaker prefixes of up to 25 characters) and joins the cues into one normalised string: NFKD, curly quotes and dashes folded, lower-cased, non-alphanumerics removed. It then scans **every line** of `--doc` for `"…"` spans of at least `--min` (default 12) characters. Each span, or each ellipsis-separated fragment of it, is checked to be a contiguous substring of the normalised transcript. Misses are printed as `NOT CONTIGUOUS IN VTT` with a total. It always exits 0.
- **Compared with `session_doc.sd_verify_quotes`,** which both SKILL.md files use (read in `~/src/CampaignGenerator/session_doc/sd_verify_quotes.py`). `sd_verify_quotes` checks only `> "…"` blockquotes. Its help says "inline quotes in prose are not reliably" checked. It returns graded `verified/near/unverified` verdicts, R1/R3 contract refusals and meaningful exit codes (0/1/2), and it can annotate artifacts.
- **Neither is a superset.** `verify_quotes.py` covers `sd_verify_quotes`'s declared blind spot, inline prose quotes: exactly the "Santorini" class Claude cites at `:203`. It has none of the fuzzy "near" verdicts, refusals or exit semantics.
- **Overstated docstring.** It claims to catch "quotes attributed to the wrong speaker" (`verify_quotes.py:6`), but the code strips speaker labels before matching (`:40-41`), so it cannot detect misattribution.
- **Codex has no equivalent** local script. Its only verifier is the same `sd_verify_quotes` module.

## 8. Open questions for the GM

1. **Orphaned `verify_quotes.py` and the lost `2d9cc62` guidance.** Restore any of the §4 item 22 material to Claude and port it to Codex? Or delete the script?
   *Suggestion:* at least restore the "raw VTT is the attribution authority", "filenames vary", and "check input mtimes" rules. Wire `verify_quotes.py` in as an inline-prose complement to `sd_verify_quotes`, and fix its docstring or add a speaker-aware mode. Otherwise delete it so it doesn't look supported.
2. **Commit the uncommitted Stage 0 edit (`claude:175-179`)?** Port the ordering rule "fix gm-assist before enhancing, never after" to Codex?
   *Suggestion:* the ordering rule is sequencing, so it belongs in this skill on both sides.
3. **Review-mode prompt (C1).** Ask up front every run (Codex), or offer based on a threshold (Claude)?
4. **Decision schema (C2).** Converge on one card and verdict schema (`t/y/n/ev` plus approve/reject/discuss/unmarked), even though the transport differs by harness? Should Claude staged go back to `_shared/review-artifact/build_review.py` like its sibling skills?
   *Suggestion:* one schema across both harnesses would let one reader tool parse decisions from either. Codex's `unmarked` and "never infer approval from file existence" rules look worth keeping in any case.
5. **Count pattern (C3).** Remove the `grep -c "^### "` instruction from `claude:147` in favour of consistency-check's "run every pattern"?
6. **Stage 1 context file (C5).** Use the chosen Stage 0 source (Codex) rather than always `gm-assist.md`?
   *Suggestion:* Codex's version is consistent with the `-update.md` convention both sides state.
7. **Exclude `.reviewed` scene files on Claude too** (§3 item 2)? And interpret `sd_verify_quotes` exit codes (§3 item 1)?
8. **Claude's step numbering (C7).** Renumber so the inventory is step 0, matching the "do this FIRST" text and Codex's order?
9. **`~/campaigns/STAGED_CONSISTENCY_HOWTO.md`.** Missing on this machine. Keep the reference, vendor the doc into the repo, or drop it?
10. **Worked evidence in Codex.** Should Codex gain Claude's grouped-mode internals (§4 item 15: report shape, duplicate-path rejection, peer targets are not evidence) and the `CG_CONSISTENCY_MAX_TOKENS` sizing, once someone checks whether codex-cli honours that variable?
11. **Should the shared review builders (§6) get their own convergence report?** They are a dependency of this skill and of session-summary-consistency on both sides.
