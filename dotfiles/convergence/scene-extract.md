# Convergence report: scene-extract

Compared: `codex/skills/scene-extract/` vs `claude/skills/scene-extract/` (paths relative to `/home/kostadis/src/mytools/dotfiles/`).

## 1. Summary

This is the **most divergent** of the four pairs. The two files are not a port and its original. They are two different philosophies of the same stage.

- **Claude (207 lines)** is a speaker-attribution workflow. It surveys labels, builds the voicing map, dry-runs `speaker_map`, then makes a mandatory strategy checkpoint. It ends by handing over an attribution review queue as its deliverable.
- **Codex (172 lines)** is a "UI-parity" workflow. It runs the same command the Session Doc Editor builds, with bundle mode, resume and `sd_verify_quotes`. It explicitly rejects Claude's shape: "Do not replace ordinary extraction with a mandatory attribution interview, custom review workflow, or pipeline audit" (`codex/.../SKILL.md:14-15`).

**Lineage.** Claude came first: created in `5c6986c` (2026-08-03), last changed in `6c7b240` (2026-09-04, "skill fixes from the obelisk chapter 10 run"). Codex was added in `8bfd959` (2026-09-18) and has not been touched since. It is the more recent side and reads like a deliberate rewrite, not a port.

The later Claude commit `20069d6` says "The remaining pairs are in sync because recent commits touched both sides". That is not true of this pair.

**Which side is more developed.** Claude is richer in operational lessons: the label-survey regex trap, `speaker_map` semantics, the truncation evidence, label-shape variance. Codex is more current on CLI surface: bundle mode, `ExtractKnobs`, resume and `--force` semantics, the quote verifier.

## 2. File inventory

| file | codex | claude | status |
|---|---|---|---|
| `SKILL.md` | 172 lines | 207 lines | differs (near-total rewrite) |
| `agents/openai.yaml` | absent | absent | n/a |

Neither side ships scripts. Claude embeds three inline Python snippets in `SKILL.md`: the map dry-run, the output census and the attribution queue.

## 3. Only in Codex

1. **The UI-parity source of truth.** `codex/.../SKILL.md:34-38`: "For UI parity, the source of truth is CampaignGenerator's `server/routers/scene_editor.py::_build_reextract_cmd`, with settings in `server/session_editor_config_shared.py::ExtractKnobs`." Claude never mentions the UI command or `ExtractKnobs`.
2. **One output directory, no competitors.** `:26-27`: "use `scene_extractions_new/` for a new run. Do not create competing output directories." Claude writes to `scene_extractions/`. See Conflict 4.
3. **No automatic prerequisites.** `:30-31`: "Do not automatically launch Stage 0/1 checks, recap removal, or summary regeneration as prerequisites." Claude does not launch them either, but it never says so. Claude's step 1 (`:17-26`) only checks that the inputs exist.
4. **Keep three identities distinct; a map is a possibility, not proof.** `:60-66`: "Keep human identity, primary-PC normalization, and in-fiction voice distinct … A confirmed voicing map records possibilities, not proof of who a particular line portrays … do not … infer a voice from a character's mere mention." Claude covers the same ground in practice (step 9's "label is correct / label is wrong" split, `:191-194`) but never states the principle. **Partial overlap.**
5. **Check whether the voicing map can actually reach the model; never smuggle it.** `:68-82`: "check whether the installed UI-equivalent command has a supported way to pass this confirmed voicing context into the bundled prompt … Do not invent a flag, assume conversation answers reach the model, or repurpose the summary, VTT, or NPC dossiers to smuggle them in. If no supported input exists, tell the user that the map is available for subsequent attribution review only." Claude's nearest statement is `:102`: "there is no flag that expresses it". Claude uses that as the reason for the checkpoint. It does not add Codex's rule against smuggling, or the rule to disclose the limitation.
6. **Bundle mode.** `:104-105`, `:114-119`: `--batch-scenes`, `--batch-max-tokens 32000`. "For per-scene mode render `--no-batch-scenes` explicitly. If the user has not chosen, follow the UI's resolved setting … `--batch` … is incompatible with `codex-cli` and with `--batch-scenes`." Claude has no bundle-mode concept at all.
7. **Resume by default; `--force` only on request.** `:127-130`: "Default execution skips existing files and supports resuming partial runs. Use `--force` only for requested regeneration: changed prior files receive `.prev` snapshots and review markers are cleared. Never delete existing outputs or snapshots to force a fresh run." Claude always passes `--force`. See Conflict 6.
8. **No duplicate calls, no silent switching.** `:133-137`: "silence alone is not failure or grounds for a duplicate call … Do not silently switch providers, models, or reasoning effort." Claude's step 7 (`:128`) covers background running and watching progress. It does not forbid a duplicate call or a silent switch.
9. **The deterministic quote verifier.** `:148-162`: `python3 -m session_doc.sd_verify_quotes --vtt … --scene-extractions … --out <session>/quote_report_scene_extract.md --report-only`. "Exit 1 means findings; exit 2 means verification failed to run." Claude's verification (`:130-165`) is census-only: line counts, label shapes, duplicate quotes. It never runs `sd_verify_quotes`.
10. **Per-file structural check and output-count hygiene.** `:141-146`: "one nonempty file per expected scene, with scene summary and verbatim-moments sections … Exclude logs, snapshots, review markers, and scaffolds from output counts." Claude excludes only `.prev` files (`:141`, `:176`).
11. **Honor configured token budgets.** `:108-110`: "Honor configured token budgets; absent overrides, the UI defaults are 8192 per scene and 32000 per bundle group. Do not raise the per-scene budget merely for this workflow." See Conflict 5.

## 4. Only in Claude

1. **Permissive speaker-label survey and its guards.** `claude/.../SKILL.md:28-45`. The survey is `grep -oP '^[^:]{1,40}(?=: )' <vtt> | sort | uniq -c …`, backed by the incident: "`Filavandrel (Fil)` (363) — the parentheses failed the class, the second speaker vanished from the survey, and the session was misdiagnosed as the single-mic no-attribution case." There are two guards: compare the count against `grep -c ':'`, and eyeball the first lines with `sed -n '1,12p'`. Codex says only "inspect the source labels" (`:47`).
2. **Never infer voicing from `party.md`.** `:49`: "Do not infer it from `party.md`, which records who *owns* a character, not who *speaks* for one." Codex reuses "campaign configuration" for the map (`:53`). This may be a softer conflict.
3. **How `speaker_map` is built.** `:63-78`: "`party.md` is still passed as `--party`, but only as prose context; the map does not come from it." Rule 1: "A binding to a character `party.yaml` lacks contributes *nothing*." Rule 2: "Game masters are applied **last and overwrite** … (FR-021a). This is deliberate". Also: "`display_names` is a literal list with no aliasing … Fix it in `players.yaml`; never hand-rewrite the VTT." Codex has only the last point: "do not … rewrite the VTT" (`:48`).
4. **A dry-run gate before spending anything.** `:80-98`. An inline Python call to `speaker_map` and `normalize_vtt_speakers` must return "`UNREWRITTEN` must be 0". Codex relies on the command's own preflight: "The command performs its speaker-label preflight and reports the mapping and rewritten line count" (`:41-42`). **The concept is present on both sides; the mechanism differs.** Claude checks before the paid call. Codex reads the report from the paid call itself.
5. **A mandatory attribution-strategy checkpoint.** `:100-109`: "**Do not skip this and do not pick for the user.**" There are two options, "Rewrite, review after" and "No rewrite, assign by hand", and the choice is recorded. Codex rejects this. See Conflict 1.
6. **Truncation evidence at 8192 tokens.** `:126`: "At 8192 scenes silently lose content and continuation seams collide mid-heading. Observed: a scene truncated from 264 to 205 lines, and a heading emitted as `**[The Cellar — Read**[The Cellar — Read-Aloud Description]**`." Also `:206`: "Scale `--max-tokens` up, never down." See Conflict 5.
7. **Stdout buffering.** `:128`: "Python block-buffers stdout when it is not a tty, so the log stays empty until exit; watch the output directory (or `.prev` files on a re-run) for progress". Codex says only "Use a pollable process/session" (`:132`).
8. **The output census and its caveats.** `:134-165`. The census covers per-file line counts, `**GM**` vs `**[GM]**` label shapes and cross-scene duplicate quotes. Its caveats: "Do not flag a final line as truncated just because it lacks terminal punctuation"; "Label format varies per scene and per run … Report it so downstream parsing handles all shapes"; "Cross-scene duplicate quotes are partly inherent". Codex says only "Investigate visibly malformed or truncated output" (`:145-146`).
9. **The attribution queue as the deliverable.** `:167-200`. It is built by regex over `**X** — *voicing …*` context fields and split into "Label is correct" (third-person narration) and "Label is wrong" (first-person voicing), with `file:line` for each entry. Codex forbids creating one automatically. See Conflict 7.
10. **Operational notes.** `:204`: "a glob that silently matches nothing reports `TOTAL: 0`, which reads exactly like 'no problems found.'" `:205`: a `speaker-mismatch` abort "blames a wrong/stale VTT … a display name missing from `players.yaml` is at least as likely". Neither note appears in Codex.
11. **Named pipeline neighbours.** `:207`: "`/gmassist-precheck` runs before this …, `/session-summary-consistency` and `/voice-smooth` run after." `:198`: the stop message. Codex names no sibling skills. Both sides forbid auto-advancing: Claude `:200`, and Codex `:170-172` ("Do not … smooth dialogue … or generate narration as part of extraction").

## 5. Conflicts

1. **Is the attribution interview mandatory?**
   - Codex `:14-15`: "Do not replace ordinary extraction with a mandatory attribution interview". `:56-58`: "Do not repeat an already answered interview or require a label-strategy choice on every run; keep the UI mapping default unless the user requests preserved recording labels."
   - Claude `:49`: "Ask the user directly." `:102`: "**Do not skip this and do not pick for the user.**"
   - This is the central disagreement. Codex treats the voicing map as reusable configuration. Claude treats every run's strategy as a precision decision that needs a checkpoint.
2. **What is the default attribution strategy?**
   - Codex `:40`: "Use the UI's configured party/player mapping by default."
   - Claude `:109`: "Recommend the first [rewrite, review after] … Record the choice." The default is only a recommendation, and the user must still choose.
   - Both lean toward rewriting. They differ on whether the choice is asked.
3. **"Preserve labels" mode and `--allow-speaker-mismatch`.**
   - Claude `:107`: "**No rewrite, assign by hand** — drop `--party`/`--party-config`/`--players-config`, pass `--allow-speaker-mismatch`."
   - Codex `:45-48`: "omit `--party`, `--party-config`, and `--players-config` together. If the command reports a mapping problem … do not conceal it with `--allow-speaker-mismatch`."
   - Codex never tells you to pass the flag in preserve mode. Claude does. **I am unsure whether the CLI requires `--allow-speaker-mismatch` when the party flags are omitted**, which would make Codex's instruction fail. The CLI's `--help` or preflight would settle it.
4. **Output directory.**
   - Codex `:26-27`, `:96`: `scene_extractions_new/`.
   - Claude `:116`, `:137`, `:174`: `scene_extractions/`.
   - Context: `claude/skills/session-doc-run/SKILL.md:124-127` says `config/session_doc.yaml` `paths.scene_extractions_dir` "is the authority for where Stage 2 writes, and it does **not** always match what other skills grep for (`scene_extractions` vs `scene_extractions_new`)". `staged-consistency` on both sides greps `scene_extractions_new/`.
5. **Per-scene `--max-tokens`.**
   - Codex `:103`, `:108-110`: `--max-tokens 8192`. "Do not raise the per-scene budget merely for this workflow."
   - Claude `:121`, `:126`: "**`--max-tokens 32000`, not the 8192 default.**" `:206`: "Scale `--max-tokens` up, never down."
   - Claude's evidence was gathered on the `claude-code` backend in per-scene mode. Codex notes its adapter may ignore the ceiling (`:111-112`). The two may be measuring different backends, so the "right" value could legitimately be backend-specific. Uncertain.
6. **`--force`.**
   - Codex `:127-130`: "Use `--force` only for requested regeneration … Default execution skips existing files and supports resuming".
   - Claude `:122`: `--force` always appears in the run command. `:127`: "keep those [`.prev`] for diffing."
   - Codex also notes that `--force` clears review markers, which Claude does not mention.
7. **Is the attribution queue the deliverable?**
   - Claude `:169`: "This is the deliverable". `:196`: "Present the queue with `file:line` for each entry. Then stop".
   - Codex `:164-167`: "Do not automatically create an attribution queue, HTML review page, or extra manifest … a full attribution or consistency review is separate work when requested."
8. **Bundle vs per-scene mode.** Codex's example runs bundle mode (`--batch-scenes`, `:104`) and defers to the UI's resolved setting. Claude's command (`:113-123`) passes neither `--batch-scenes` nor `--no-batch-scenes`, so it gets whatever the CLI defaults to. That is exactly what Codex warns against: "For per-scene mode render `--no-batch-scenes` explicitly" (`:114-115`).
9. **Locating the binary.**
   - Codex `:33`: "Locate `scene_extract` with `command -v`".
   - Claude `:114`: hard-coded `/home/kroussos/.venvs/main/bin/scene_extract`, a different user's home. It will not resolve on the `kostadis` machine.
10. **Verification method.** Codex uses `sd_verify_quotes` (`:148-162`). Claude uses its own census scripts (`:134-159`). These are complementary, not incompatible: neither does what the other does. They are listed here because each side presents its method as *the* verification step.

## 6. Platform-only differences

- Frontmatter. Codex has `metadata.short-description` (`:4-5`) and a description triggered by `$scene-extract`. Claude has `tools: Bash, Read, Edit, AskUserQuestion` (`:4`) and a much narrower description ("when the party's PCs are voiced by one or more people").
- The Codex maintenance note: "Maintain this Codex skill under `dotfiles/codex/skills/scene-extract/`; leave the Claude version intact." (`:10-11`).
- Backend and model. Codex uses `--backend codex-cli --model gpt-6-astra --codex-reasoning-effort medium` (`:97-99`). Claude uses `--backend claude-code` (`:117`).
- Billing. Claude `:125`: "`--backend claude-code` routes through `claude -p` headless and **strips `ANTHROPIC_API_KEY`** so billing lands on the subscription". Codex `:87-88`: "For the saved-Codex-login approach, use `--backend codex-cli`; do not substitute a metered API backend." The goal is the same (subscription, not metered); only the mechanism is platform-specific.
- The output-ceiling signal. Claude `:132`: "The `WARNING: claude -p hit its output ceiling` banner … is a turn-count heuristic … Ignore the banner". Codex `:111-112`: "The Codex adapter may report that the output-token ceiling is ignored by its backend; report that accurately". Each side documents its own backend's misleading message.
- Checkpoint mechanism. Claude uses `AskUserQuestion` (`:104`). Codex asks in conversation.
- Blocked transmission. Codex `:124`: "if execution review rejects the transmission". Claude does not mention transmission approval at all. **This may be a substantive gap in Claude, not just a platform difference.** Its sibling `enhance-summary` does carry the rule (`claude/skills/enhance-summary/SKILL.md:94-98`).
- Hand-off form. Codex ends with "a link to the extraction directory" (`:169`). Claude ends with a queue listed as `file:line` (`:196`).

## 7. Script diffs

None. Neither side ships script files.

Claude's inline snippets (map dry-run `:82-94`, census `:134-159`, queue `:171-189`) have no Codex counterpart. The census and queue are Codex-agnostic Python and would run unchanged on either side.

## 8. Open questions for the GM

1. **Which philosophy does this skill follow?** Either a mandatory attribution checkpoint every run (Claude), or UI-parity extraction with attribution review as separate, on-request work (Codex).
   Suggestion: a split may serve both. Run the cheap deterministic gates every time (label survey, `UNREWRITTEN == 0` dry-run). Ask the strategy question only when the voicing map shows a person voicing more than one character and no prior ruling exists. That keeps Claude's precision checkpoint where it matters and Codex's "don't re-interview" elsewhere.
2. **Is the attribution queue produced automatically at the end of extraction, or on request?** Suggestion: keep the queue script, and decide whether it is part of this skill or moves to a separate step (for example `/session-summary-consistency`, which already runs next).
3. **Which output directory is canonical: `scene_extractions/` or `scene_extractions_new/`, or always read `paths.scene_extractions_dir` from `config/session_doc.yaml`?** Suggestion: read the config value, as `session-doc-run` already recommends.
4. **Per-scene `--max-tokens`: 8192 (UI default) or 32000?** Should the answer depend on the backend? Claude's truncation evidence is concrete; Codex's objection is UI parity.
   Suggestion: settle it per backend, and record whichever value the UI's `ExtractKnobs` uses.
5. **Should `--force` be the default, or only on requested regeneration?** Note that Codex says `--force` clears review markers. If so, Claude's always-`--force` could silently discard review state on a re-run.
6. **Bundle mode.** Should Claude adopt `--batch-scenes` / `--no-batch-scenes` explicitly, as Codex requires?
7. **Preserve-labels mode.** Is `--allow-speaker-mismatch` required when the party flags are dropped (Claude), or forbidden (Codex)? This needs a check against the installed CLI.
8. **Should Claude add `sd_verify_quotes` after extraction?** Codex runs it; Claude does not. Suggestion: yes. It is deterministic and costs no model call.
9. **Should Codex add the label-survey regex lesson, the `speaker_map` semantics (GM overwrites last; unknown characters contribute nothing), and the truncation caveats?** Suggestion: yes. These are platform-neutral facts about CampaignGenerator.
10. **The hard-coded `/home/kroussos/.venvs/main/bin/scene_extract` in Claude.** Replace it with `command -v scene_extract`? Or is the `kroussos` machine the intended runtime for this skill?
11. **Should Claude add Codex's transmission-approval paragraph (`:121-125`) and its "never smuggle the voicing map into the prompt" rule (`:75-82`)?**
