# Convergence report: vtt-spell-pass (Codex vs Claude)

Paths: `codex/skills/vtt-spell-pass/` (C) and `claude/skills/vtt-spell-pass/` (L), relative to `dotfiles/`.
Line numbers for L's SKILL.md are from the **working copy**, which includes uncommitted edits.

## 1. Summary

The two versions diverge a lot, but the cause is branch timing, not deliberate design. Codex was ported in `567fbc0` (2026-08-29 13:04:44), 17 s after `2d9cc62`, on the `kostadis/skills/20260829-transcript-attribution` branch. That branch had forked before four main-line Claude commits: `b601e9f` (edge-aware wrong-form boundaries, 08-09), `7780fab` (corrections record instead of a cleaned tape, 08-11), `8c919e3` (native `--registry`, 08-17) and `8309e5c` (at-volume downloads artifact, 08-18). So every Codex script is **byte-identical to Claude@2d9cc62**, and Codex's SKILL.md is Claude@2d9cc62 plus platform rewrites. Claude only picked up the four main-line commits later, in merge `d81cc3f` (2026-08-30). Codex never received them. That makes **Claude the more developed side** on substance: the record/`sd_corrections` delivery model, registry ingestion, edge-aware matching and the write guards. Codex is ahead on one thing, a structured batch-review queue and its `render_review.py` adapter. **The Claude working copy has 68 lines of uncommitted additions** (see `git diff claude/skills/vtt-spell-pass/SKILL.md`), in four blocks: (a) the "speakers: none detected" detector bug and a grep cross-check (L:219-232); (b) "`--npcs-dir` is REQUIRED", with an empty-scratch-dir workaround (L:292-302); (c) the real-world-proper-noun blind spot (`Cisco`) and "NEVER promote a cue-scoped GM ruling into a glossary row" (L:770-798); (d) "cannot see ordinary-word garbles" (L:800-809). Blocks (a) and (b) describe script behaviour that is identical on both sides, so they apply to Codex too. One of them is partly inaccurate (see Q10).

## 2. File inventory

| file | codex | claude | status |
|---|---|---|---|
| SKILL.md | 869 lines | 1113 lines (working copy; 1045 committed) | differs |
| add_to_glossary.py | 131 | 131 | identical (verified `cmp`) |
| dmetaphone.py | 546 | 546 | identical (verified) |
| sibling_context.py | 155 | 155 | identical (verified) |
| state.py | 88 | 88 | identical (verified) |
| zoom_context.py | 106 | 106 | identical (verified) |
| apply_replacements.py | 114 | 183 | differs (C == L@39e99b0/2d9cc62) |
| cluster_unknowns.py | 409 | 423 | differs (C == L@2d9cc62) |
| find_unknowns.py | 448 | 486 | differs (C == L@2d9cc62) |
| lint_glossary.py | 239 | 245 | differs (C == L@2d9cc62) |
| prepare_input.py | 277 | 280 | differs (help text only; C == L@2d9cc62) |
| render_review.py | 136 | — | only-codex |
| `__pycache__/` | ignored | ignored | — |

(Out of scope but worth knowing: there is also an untracked `dotfiles/hermes/skills/productivity/vtt-spell-pass/SKILL.md`, which is a third copy.)

## 3. Only in Codex

1. **A structured queue schema for batch review.** C:774-790 defines per-item fields (`token`, `canonical`, `section`, `count`, `chapters`, `context`, `reason`, `confidence`, `sibling_verdict`, `recommended_decision`, `decision`, `note`), and a script renders them. Claude writes cards directly in page vocabulary (`t`/`y`/`n`/`ev`, L:999-1005).
2. **New canon can be approved from the page.** C:815: *"**approve**, proposed canonical is null | Append the confirmed name and context to `notes/vtt_known_additions.md`; do not add a glossary row"*. Claude does the same thing through reject (see Conflicts #6).
3. **A per-item `edit_mode: targeted` escape hatch.** C:814: *"use a targeted edit instead when the queue says `edit_mode: targeted`"*. Claude has no per-item flag; its equivalent is a Phase 4 record entry.
4. **Explicit validation of the returned decisions.** C:805-808: *"Validate that every returned id exists in the queue and that each decision is one of `approve`, `reject`, or `discuss`. Never infer approval from the HTML or queue file's mere existence or modification time."* Claude's `read_decisions.py` checks verdict values but never checks ids against the item list. The nearest Claude equivalent is "A notification means *the page was republished*, nothing more" (L:1031).
5. **An explicit freeze while review is pending.** C:748: *"Do not modify the glossary or transcript while the page is awaiting review."* In Claude this is only implied by "Hand over the link and **stop**" (L:1016).
6. **Phase 2 drops are summarised in the batch page.** C:762-766: *"Tokens Phase 2 drops as unambiguously non-campaign names. Summarize their counts and reasons, but do not create queue items for them. Record the counts in a top-level `summary` object"*. Claude's footer rule (L:993) covers only `auto_dismissed` and existing rows. Caveat: `render_review.py` never reads `summary` (see §7), so in practice the GM never sees these counts.
7. **Correct required-input numbering.** C numbers the items 1–8. L has two items numbered `8.` (L:141, L:149). This is a minor defect in L, not a rule.

Everything else Codex has (paths, `update_plan`, `apply_patch`, chat questions) is platform. See §6.

## 4. Only in Claude

Items 1–9 arrived via merge `d81cc3f`. Items 10–13 are uncommitted.

1. **The deliverable is a record, not a cleaned tape.** L:24-52: *"**The deliverable is a set of entries in `transcript_corrections.yaml`, not a cleaned `.vtt`.**"* and *"**Never write into the session directory.**"* I searched Codex for `transcript_corrections`, `sd_corrections`, `record` and `candidate`: none of them appear.
2. **Phase 7: `sd_corrections import` → review → `apply` → `check`.** L:910-963. It includes: *"Pass `--raw` explicitly whenever the session has more than one non-cleaned `.vtt`"*; *"**delete** rather than approve any cue the GM did not rule on"*; *"`apply` is all-or-nothing"*; and deleting an entry as the revert mechanism. Codex ends at Phase 6.
3. **The entity registry is a first-class input.** L:67-76 (required-input #5) and the `--registry` flag on both scripts (L:276, L:282, L:354-356): *"A registry name or alias is, by construction … an approved canonical alternate name — **never** a mishearing"*. Codex mentions the registry only as the source of the generated `entity_inventory.md` (C:65-67). Its scripts have no `--registry`.
4. **A `registry_names_count` sanity check.** L:338-340: *"also check `registry_names_count` is nonzero"*.
5. **`vtt_known_additions.md` is not auto-promoted.** L:113-116: *"a name confirmed here today does not promote itself into the registry; that's still a separate, manual step via `/entity-triage` or `registry add`."*
6. **Filtered or deduped copies must not be applied.** L:250-257: *"**But do not feed a `--filtered-output` or `--dedup-output` file to Phase 5.** … `sd_corrections import` pairs the two transcripts by cue index"*.
7. **One-off fixes become cue-scoped record entries, not edits.** L:811-831 includes the YAML template and *"`was` must match the cue exactly, speaker prefix included"*.
8. **The "at volume" downloads artifact inside Phase 3.** L:667-723: one card per cluster, `capabilities: {"downloads": true}`, a Markdown decision record, and a WSL `/mnt/c/Users/...` read-back. This conflicts with Claude's own Artifact-mode section; see Conflicts #9.
9. **The auto-dismiss gate and action taxonomy from `merge_proposals.py`.** L:986-997: *"`auto_dismissed[]` under the `AGENT_BRIEF.md` gate: **`count == 1` AND `kind == ordinary_words`**. Never on `inconclusive`, never on `count ≥ 2`."* The card actions are `{propose, propose_low_confidence, escalate, escalate_blocking}`. Note that `merge_proposals.py` and `AGENT_BRIEF.md` are not bundled with the skill. The only copy I found is `~/src/campaigns/Phandalin/notes/spell_pass_batch/merge_proposals.py`.
10. **"Glossary and record are different objects"** (L:1082-1088), plus the Phase 7 paragraph in "Why this design" (L:1104-1113).
11. *(uncommitted)* **Don't trust "speakers: none detected".** L:219-232: *"**Verify a `none detected` before acting on it — the detector has a bug.**"* It adds a grep cross-check and a roster/absent-player check. Verified: `prepare_input.py:218` in *both* copies only computes speakers when `fmt == "labelled_markdown"`, so the bug is real on the Codex side too.
12. *(uncommitted)* **The `--npcs-dir` requirement.** L:292-302: *"`find_unknowns.py` exits 2 with an argparse error rather than defaulting. Point it at an empty scratch directory"*. It applies to both sides, but see Q10.
13. *(uncommitted)* **Real-world proper nouns are a blind spot**, and cue rulings must never be promoted to glossary rows. L:770-798: *"`Cisco → A'lai` sat in a blanket row and rewrote a real company across ~8 sessions"*; *"**NEVER promote a cue-scoped GM ruling into a glossary row.**"* Codex has only the lowercase gate (C:638-653).
14. *(uncommitted)* **Ordinary-word garbles are invisible to this skill.** L:800-809: *"a clean spell pass is not evidence the tape is clean … the fix belongs back here as per-cue record entries — never as glossary rows"*.
15. **Doubling is fixed in the glossary, not the output.** L:906-908: *"**Fix these in the glossary and re-run Phase 5**, not by editing the candidate — a doubling is a bad *row*"*. Codex says the opposite; see Conflicts #4.
16. **Idempotence is checked against a second scratch path and tied to the trustworthiness of the record** (L:871-876). Codex re-applies to "the cleaned file" (C:689-692).
17. **Pair-consent is justified by a quote from `merge_proposals.py`** (L:974-980). Codex keeps the rule (C:750-756) but drops the citation. The substance is equivalent.

## 5. Conflicts

1. **Where the output goes and what it is.** C:697-704: *"`--output <vtt-stem>.cleaned.vtt` … (Default output: `<vtt-stem>.cleaned.vtt` next to the original. Pass `--in-place` only if the user explicitly asks to overwrite.)"* L:880-890: *"`--output "$SCRATCH/candidate.cleaned.vtt"` … `--output` is required, there is no `--in-place`, and the script refuses to write a `.cleaned.vtt` that an existing `transcript_corrections.yaml` claims"*. The scripts enforce each side's version.
2. **Where the entity inventory comes from.** C:64-70: *"`docs/entity_inventory.md` (produced from `docs/entity_registry.yaml` by `registry.py project`) is the current OOTA source"*, which gets flattened and passed via `--extra-known`. L:67-76: pass the YAML registry natively via `--registry`, and flatten `entity_inventory.md` only as a fallback when no registry exists.
3. **How one-off (unsafe-to-glossary) fixes are applied.** C:645-646: *"Apply that one correction as a targeted `Edit` on the *cleaned* output in Phase 5, touching only the specific line(s)."* C:40 (platform section) adds *"Use `apply_patch` for manual, targeted transcript edits."* L:811-816: *"A one-off fix used to be a targeted `Edit` on the cleaned output; it is now a `transcript_corrections.yaml` entry"*.
4. **How surname doubling is fixed.** C:719-720: *"grep the cleaned output for accidental doubling … and fix any with a targeted edit."* L:906-908: fix the glossary row and re-run Phase 5, *"not by editing the candidate"*.
5. **Using `--filtered-output`.** C:212-214: *"`--filtered-output` deletes content from the deliverable, so it needs the GM to have said so explicitly — feed its output to `apply_replacements.py` in Phase 5 in place of the original."* L:250-257: *"do not feed a `--filtered-output` or `--dedup-output` file to Phase 5."* The two sides' `prepare_input.py` help strings say the same opposing things.
6. **How "new canon" and "real name" come back from batch review.** C:815-816: `approve` with a null canonical → `vtt_known_additions.md`, and `reject` → `state.py ignore`. L:1042: *"**reject** | `state.py ignore "<token>"`, unless the card's `n` says "real name" — then append to `notes/vtt_known_additions.md` instead"*. A port that keeps both paths will route the same GM gesture differently on each side.
7. **What gets auto-dismissed.** C:760-766 lists no auto-dismiss gate, and C:770 says *"Every surviving candidate becomes an item"*. L:989-990 auto-dismisses at `count == 1 AND kind == ordinary_words`. Codex is stricter: it has no count-1 exemption.
8. **Writing into the session directory.** C:735-742 writes both `<session-dir>/vtt_spell_pass_review.json` and `<session-dir>/vtt_spell_pass_review.html`. L:46-50: *"**Never write into the session directory.** … `$SCRATCH` for everything."* Claude's rule exists because stray `.vtt` files break `sd_corrections`. The Codex files are `.json` and `.html`, so they don't trip that glob, but they do violate Claude's stated blanket rule.
9. **Claude contradicts itself about the batch path.** L:163-173 has the GM choose at Phase -1, and "Artifact mode" (L:965+) uses the shared review-artifact (`capabilities: {"artifact": {}}`, one card per **pair**, WebFetch + `read_decisions.py`). L:667-723, merged in from `8309e5c`, has the agent switch at volume to a different artifact: `capabilities: {"downloads": true}`, *"One card per cluster/singleton"*, and a Markdown decision record. Per-cluster cards contradict L:971-984's *"one card per `(token → canonical)` pair … never merge them into a single card"*. Codex has only the pair-based page, so on this point Codex is internally consistent and Claude is not.
10. **When the review mode is chosen.** C:141-152 and L:163-173 both ask at Phase -1. Only Claude's L:667-677 lets the agent pick the artifact on its own "once the queue is longer than a handful of clusters". This is the same issue as #9, from the consent angle.

## 6. Platform-only differences

- Frontmatter: L has `tools:` (AskUserQuestion, TaskCreate/TaskUpdate, Artifact, WebFetch, ToolSearch). C has `metadata.short-description`. The descriptions say `/vtt-spell-pass` vs `$vtt-spell-pass`.
- C:25-42 has a "Codex compatibility" block: resolve `SKILL_DIR`, ask in chat, use `update_plan`, don't edit the Claude directory, use `apply_patch`. The `apply_patch` line is not purely platform (see Conflicts #3).
- Script paths: `"$SKILL_DIR/…"` vs `~/.claude/skills/vtt-spell-pass/…`. Scratch variable: `CODEX_SCRATCH` vs `CLAUDE_SCRATCH` (C:160-161, L:181).
- Phase 3 questioning: chat + `update_plan` (C:484-486, C:544) vs `AskUserQuestion` + `TaskCreate`, with memory-file citations (L:547-550, L:608). Plan item vs `TaskUpdate` (C:635-636, L:757).
- Batch transport: a standalone HTML page, localStorage, Copy/Save output, and a paste or file handback (C:731-808) vs a published Artifact with a self-republish, an `artifact-changed` notification, a no-poll rule and a WebFetch read-back (L:965-1035). Details are in `_shared-review.md`.
- Queue/card field names (`context` vs `ev`) follow from the renderer choice. Whether Claude adopts a queue layer is a real decision; see Q5.

## 7. Script diffs

**apply_replacements.py.** Claude is the behavioural superset.
- *Edge-aware boundaries* (`b601e9f`). L adds `word_pattern()`, which uses `\b` only on word-char edges and `(?<!\w)`/`(?!\w)` on punctuation edges. It is used for the main rule, the possessive extension and `is_self_matching`. C uses a bare `\b…\b`, so a wrong-form such as `L.A.` or `Glabagul-` silently never fires in C.
- *Output contract* (`7780fab`). L makes `--output` **required**, removes `--in-place`, refuses when output == input (exit 2), and refuses to write the `.cleaned.vtt` that a sibling `transcript_corrections.yaml` claims. It parses `output:`/`transcript:` with a stdlib regex (`record_owned_output`). On success it prints the `sd_corrections import/apply/check` recipe and returns exit codes via `sys.exit(main())`. C defaults to `<vtt>.cleaned.vtt` next to the input and supports `--in-place`.

**find_unknowns.py.** Claude is a strict superset (`8c919e3`). It adds `--registry` and `load_registry_names()`, which reads every `entities[].name` plus `aliases[]` via a lazy PyYAML import. Those names are added to the known set, and the output gains `registry_names_count`. Nothing else changes.

**cluster_unknowns.py.** Claude is a strict superset. It adds `--registry`, merged into `knowns_set` and `canonicals_lc`, and a docstring warning that the value must match find_unknowns' or the two scripts' known sets diverge.

**lint_glossary.py.** Claude is the superset. The `corpus_lower` check uses the same edge-aware lead/tail as `word_pattern`, so lint agrees with what the applier would actually rewrite. C's `\b` version under-reports punctuation-edged forms.

**prepare_input.py.** Only the `--filtered-output` help text differs, and the two sides contradict each other (Conflicts #5). The detection code is identical, including the `speakers()` call gated on `labelled_markdown` at line 218, which is the bug that Claude's uncommitted text documents.

**render_review.py (only in Codex).** Behaviour: it loads `../_shared/review-page/build_review.py` by path. It maps queue items to the shared `t/y/n/ev` shape, HTML-escaping every transcript field. `edit_mode: targeted` changes the approve text, and a null `canonical` turns the card into "new campaign term". It pre-seeds page state from any item `decision` (`approve_correction|new_canon → approve`, `ignore → reject`) and sets `reviewId = "vtt-spell-pass:<target_vtt>"` and `outputName = vtt_spell_pass_decisions.json`. It then validates and writes the HTML (default `<queue>.html`).
- *Internal gaps on the Codex side.* It does not render the `reason`, `sibling_verdict`, `chapters` or `recommended_decision` fields that the SKILL.md example (C:774-790) tells the agent to write. It reads a `sibling: {text,line,score}` object instead, so a queue written to the SKILL example **shows no sibling verdict on the card**. It also ignores the top-level `summary` that C:765 asks for, and its footer is hard-coded. Pre-seeding from `decision` means a queue written with non-null decisions arrives pre-marked, which is a consent hazard even though the documented default is `null`.

**What a Claude port on `review-artifact` would need to change:**
1. Load `_shared/review-artifact/build_review.py`, not `review-page`.
2. Drop `reviewId`/`outputName`. Claude's builder ignores them harmlessly, but they are meaningless there.
3. HTML-escape `eyebrow` (it contains a session path), because Claude's builder injects eyebrow, lede, footer and the `<h1>` title **raw**. Codex's builder escapes them.
4. **Do not pre-seed `state.decisions`.** In Claude, whatever is in state at save time *is* the GM's ruling. Keep `savedAt: null` so `read_decisions.py` still refuses an unsaved page.
5. Rewrite `y` so approve means "add glossary row, then the Phase 7 record entry", not "apply that pair to `<target>`". For `edit_mode: targeted`, say "add a cue-scoped entry to `transcript_corrections.yaml`" (if Claude adopts that flag at all).
6. Write the HTML to `$SCRATCH/review.html`, not the session dir, and hand it to the Artifact tool with `capabilities: {"artifact": {}}`.
7. Render `summary` into `footer`, and render `sibling_verdict` and `reason` into `ev`. This fixes the Codex gaps too.
8. Reword the footer, which currently says "until Codex receives…".

## 8. Open questions for the GM

1. **Should the record/`sd_corrections` delivery model (Phase 7, the no-default `--output`, never writing the session dir) be ported to Codex?** Today Codex writes `<vtt>.cleaned.vtt` directly, which is exactly what Claude's L:36-42 says caused the 74 unenumerated substitutions in Phandalin ch46. Suggestion: yes. This looks like an accidental omission from branch timing, not a Codex design choice, and it is a correctness issue rather than a style one.
2. **Should Codex scripts simply be re-synced to Claude's five newer scripts?** All five are supersets, apart from the `prepare_input.py` help text, which follows Q1. Suggestion: yes. This would make every script except `render_review.py` identical.
3. **Should `--registry` become the canonical registry path on both sides, with `entity_inventory.md` flattening only as a fallback?** Suggestion: yes, and it follows from Q2.
4. **How should "real name, not a misspelling" come back from batch review?** Options are approve with a null canonical (Codex) or reject whose `n` says "real name" (Claude). Suggestion: Codex's form looks less error-prone, because "reject" meaning "keep and add to known set" inverts the verdict's plain reading. But it's your call.
5. **Should Claude adopt Codex's intermediate queue schema (`token`/`canonical`/`context`/…), with a `render_review.py` adapter, instead of writing `t/y/n/ev` by hand?** Suggestion: worth considering. It puts escaping and card wording in deterministic code, but see §7 for what the port must change.
6. **Resolve Claude's internal conflict. Should the "At volume" downloads artifact (L:667-723, per-cluster cards) be deleted in favour of Artifact mode (per-pair cards), or reconciled with it?** Suggestion: it looks like merge residue from `8309e5c` that `5092639` superseded on the other branch. Per-cluster cards contradict the pair-consent rule.
7. **Should auto-dismissal exist, and at what threshold?** Claude auto-dismisses `count == 1 AND ordinary_words` based on a campaign-local `merge_proposals.py`. Codex has no gate. And if the gate stays, should `merge_proposals.py`/`AGENT_BRIEF.md` be bundled or referenced by path, since the skill cites tools it doesn't ship?
8. **Should the uncommitted Claude additions (a)–(d) be committed, and ported to Codex?** (a) and (b) describe script behaviour shared by both sides, while (c) and (d) are workflow rules that are not platform-specific. Suggestion: port (a), (c) and (d) as-is once committed. For (b), see Q10.
9. **Should Codex's batch artifacts live in the session dir (C:736-741) or `$SCRATCH`?** Suggestion: Claude's "never write into the session directory" rule argues for scratch, unless you want the queue kept as an audit trail beside the tape.
10. **Should uncommitted note (b) be corrected?** It says `find_unknowns.py` "exits 2 with an argparse error rather than defaulting". That is true only when the flag is omitted. `parse_npc_dossiers()` returns an empty set when the directory does not exist (`find_unknowns.py:121-122` on both sides), so passing the conventional `<campaign>/docs/npcs` path even when it's absent already works, and the empty-scratch-dir workaround is harmless but unnecessary. Suggestion: reword it to "always pass `--npcs-dir`; a nonexistent path is fine".
11. **Should the Codex-only guard "validate every returned id exists in the queue" (C:805-807) become a script check on both sides, in `read_decisions.py` against the items file?** Suggestion: yes. At the moment it is prose only on Codex and absent on Claude.
12. **Minor: Claude's required-input list has two items numbered `8.` (L:141, L:149).** Renumber when converging.
