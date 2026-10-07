# Convergence report: enhance-summary

Compared: `codex/skills/enhance-summary/` vs `claude/skills/enhance-summary/` (paths relative to `/home/kostadis/src/mytools/dotfiles/`).

## 1. Summary

The pair is **low-divergence in substance**: the Claude version is a paragraph-for-paragraph port of the Codex version, with a scoping paragraph added and the backend section rewritten for the `claude-code` backend. Lineage is **Codex → Claude**: Codex was created in `8bfd959` (2026-09-18, "feat(codex): add campaign workflow skills"); Claude was ported from it in `20069d6` (2026-09-20), whose message says "Port direction for this change is codex -> claude: the Codex versions were edited after the original Claude -> Codex port, so they are the current source." Claude is therefore the most recently changed side. It is also slightly more developed: it carries the full backend flag vocabulary, names where the UI's model selection lives, and points at sibling skills. Codex has one thing Claude lacks, a known-good historical command with model and effort. One Claude addition looks like an error: it names `/session-summary-consistency` as "Stage 1 consistency" (see Conflicts).

## 2. File inventory

| file | codex | claude | status |
|---|---|---|---|
| `SKILL.md` | 126 lines | 143 lines | differs |
| `agents/openai.yaml` | absent | absent | n/a (neither side has one) |

No scripts on either side.

## 3. Only in Codex

1. **A recorded known-good command with model and effort.** `codex/skills/enhance-summary/SKILL.md:64-74`: "Successful Chapter 09 command shape (model and effort are historical settings, not universal defaults)", with `--model gpt-5.6-sol` and `--codex-reasoning-effort medium`. Claude's command block (`claude/.../SKILL.md:77-84`) has no model and no effort flag. It says "Add `--claude-code-effort <level>` only when the user has chosen one" (`:86`). Claude has no record of a run that worked. This is mostly a platform difference, since the model name is Codex-specific. The practice of recording a working run is not tied to either platform.
2. **Maintenance note**: `codex/.../SKILL.md:10-11`: "Maintain this Codex skill under `dotfiles/codex/skills/enhance-summary/`; leave Claude skills intact." Platform/housekeeping, not a workflow rule (see section 6).

I searched Claude for these concepts and found no other Codex rule missing from it: overwrite guard, snapshot, speaker-flag omission, `--allow-speaker-mismatch`, transmission approval, pollable process, `## Summary`/`## Scenes` check, `sd_verify_quotes` fallback, the exit 1/2 distinction, and no auto-advance are all present in both.

## 4. Only in Claude

1. **Scoping against sibling skills.** `claude/.../SKILL.md:14-18`: "This skill owns **one stage**. `/session-doc-run` runs the full pipeline … `/chapter-enhance` builds a summary from chapter *prose* when there is no recording at all … This skill is for the recorded case." Codex never mentions `/session-doc-run` or `/chapter-enhance`, and neither skill exists under `codex/skills/`, so this cross-reference cannot be copied to Codex as written.
2. **The full backend vocabulary and the claude-code flag rules.** `claude/.../SKILL.md:64-70`: "The backend vocabulary is shared across every model-bearing CG CLI (`campaignlib/api/client.py::add_backend_args`): `anthropic`, `dgx`, `openrouter`, `claude-code`, `codex-cli`. On `claude-code`, effort and thinking are `--claude-code-effort` and `--claude-code-thinking` / `--no-claude-code-thinking`; `xhigh` and `max` require thinking enabled or the call is refused. `--codex-reasoning-effort` belongs to the `codex-cli` backend and has no effect here." The backend list and the "effort flag must match the backend" rule are useful on both sides. The claude-code flag details are platform-specific.
3. **Where the UI's model selection is stored.** `claude/.../SKILL.md:72-74`: "otherwise resolve the UI's configured selection (`config/session_doc.yaml`, `backends.active`) rather than guessing a model." Codex (`:60-61`) says only "resolve the UI's configured selection" and does not say where it lives. This is a real, platform-neutral addition.
4. **Emphasis on the exit codes.** `claude/.../SKILL.md:128-129`: "Those are different outcomes — do not collapse them." Codex `:114` states the same exit-code meanings without this sentence. It adds emphasis, not a new rule.
5. **A named next step.** `claude/.../SKILL.md:139-140`: "Stage 1 consistency (`/session-summary-consistency`) is the next review step". Codex `:123` says only "Stage 1 consistency is the next review step". See Conflicts: the named skill looks wrong.

## 5. Conflicts

1. **Which skill is "Stage 1 consistency".** Claude `:139-140` names `/session-summary-consistency`. Codex `:123` names no skill. Elsewhere in the repo, Stage 1 is defined as `/consistency-check` on `session-summary.md`, driven by `/staged-consistency`: `claude/skills/staged-consistency/SKILL.md:183-185` reads "### 3. Stage 1 — session-summary check … running `/consistency-check $SESSION/session-summary.md`". `/session-summary-consistency` is the quote-level check on `scene_extractions_new/` (its skill description), which is Stage 2-adjacent. This is an internal inconsistency in Claude, not a Codex-vs-Claude design disagreement, and Codex is the correct one by omission.
2. **Default backend.** Codex `:59`: "Use `--backend codex-cli` for this saved-login workflow". Claude `:63`: "Use `--backend claude-code` for this saved-login workflow". The difference comes from the harness (each side uses its own subscription login), so it is listed in section 6 and is not a convergence conflict by default.
3. **CampaignGenerator path.** Codex `:44`: "normally `/home/kostadis/src/CampaignGenerator`". Claude `:47`: "normally `~/src/CampaignGenerator`". These are equivalent for user `kostadis`, but other skills hard-code `/home/kroussos/...` (for example `codex/skills/consistency-check/SKILL.md:143`), so the portable `~` form is probably what you want. This is minor.
4. **`--batch` compatibility statement.** Codex `:77-79` says `--batch` "is not compatible with `codex-cli`". Claude `:89-91` says it "is Anthropic-backend only and is **not** compatible with `claude-code`". These do not conflict: both follow from "Anthropic backend only". Only Claude states the general rule.

## 6. Platform-only differences

- Frontmatter. Codex has `metadata.short-description` (`:4-5`). Claude has `tools: Read, Bash, Glob, AskUserQuestion` (`:4`) and a longer, trigger-rich `description`. Codex's description mentions `$enhance-summary` invocation; Claude's says "Invoke as /enhance-summary [session-dir]".
- The Codex maintenance note (`:10-11`).
- The regeneration-authority prompt. Claude `:39` says "get explicit regeneration authority with `AskUserQuestion`". Codex `:35-36` says "replacement of an existing reviewed summary needs clear regeneration authority" and names no mechanism.
- Backend and effort flags: `codex-cli` + `--codex-reasoning-effort` vs `claude-code` + `--claude-code-effort`/thinking flags (Codex `:59-74`, Claude `:63-86`).
- Blocking mechanism. Codex `:84`: "If execution review blocks transmission". Claude `:96`: "If a permission prompt blocks transmission".
- Wording of the final hand-off. Codex `:122`: "End with the output link". Claude `:138`: "End with the output path". Codex `:125-126`: "No extra HTML review queue or manifest". Claude `:142-143`: "no review artifact and no manifest of its own". Same rule; only the artifact vocabulary differs.
- No `agents/openai.yaml` exists on the Codex side for this skill.

## 7. Script diffs

None. Neither side ships scripts.

## 8. Open questions for the GM

1. **Should the "Stage 1 consistency" pointer name a skill, and which one?** Claude currently names `/session-summary-consistency`. That appears to be the wrong stage.
   Suggestion: point both sides at `/staged-consistency` Stage 1 (`/consistency-check <session>/session-summary.md`), or name no skill, as Codex does.
2. **Should Claude keep a "last known-good command" example with a model and effort, like Codex's Chapter 09 block?** Suggestion: yes, as a clearly labelled historical example, since it anchors "what worked" without making it a default.
3. **Should the backend vocabulary and the `config/session_doc.yaml` / `backends.active` pointer be back-ported to Codex?** Suggestion: port the location of the UI selection and the rule that the effort flag must match the backend. Leave the claude-code-specific flags on the Claude side only.
4. **Should Codex gain the scoping paragraph?** Neither `/session-doc-run` nor `/chapter-enhance` exists under `codex/skills/`. Suggestion: keep the paragraph Claude-only, unless those skills are ported to Codex.
5. **Which CampaignGenerator path form should be canonical: absolute `/home/kostadis/...` or `~/src/...`?** Suggestion: `~/src/CampaignGenerator`, given the second machine (`kroussos`) seen in other skills.
