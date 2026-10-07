# Convergence report: session-summary-consistency

Paths are relative to `/home/kostadis/src/mytools/dotfiles/`. "codex" means `codex/skills/session-summary-consistency/SKILL.md` (307 lines) and "claude" means `claude/skills/session-summary-consistency/SKILL.md` (263 lines). Claude has no uncommitted edits to this file.

## 1. Summary

The two versions agree on almost all of the method: the six-category table, the cross-reference rules, the player-name scrub, the "do not change" list, the proposal format, and the safe/unsafe glossary loop. They diverge in three places:
- **Batch-review mechanism.** Claude carries two artifact flows that contradict each other. Codex has one standalone-HTML flow.
- **Auto-application.** Claude's artifact mode auto-applies a "footer" class of fixes with no ruling. Codex forbids any edit without explicit approval.
- **Worked examples.** Claude keeps the campaign examples behind each rule; Codex keeps the rules.

Lineage:
- Claude is the original (`15ce943` 2026-06-17). It was hardened in `d70f1c6`/`5c6986c`, gained a `downloads`-based review artifact in `8309e5c` (2026-08-18), and gained a shared-contract "Artifact mode" in `2d9cc62` (2026-08-29). The merge of `2d9cc62` (`d81cc3f`) kept **both** artifact flows.
- Codex was ported on 2026-08-29 (`567fbc0`). Its batch flow was rewritten on 2026-09-18 (`8bfd959`) around the shared `_shared/review-page` builder.
- Codex is therefore the more recently changed side. Claude is the richer side in examples and in how finely it splits auto-apply from cards.

## 2. File inventory

| file | codex | claude | status |
|---|---|---|---|
| `SKILL.md` | 307 lines | 263 lines | differs |
| `agents/openai.yaml` | absent | n/a | not present |
| helper scripts | none | none | — |
| *Shared dependency:* review builder | `codex/skills/_shared/review-page/*` | `claude/skills/_shared/review-artifact/*` | differs (see the staged-consistency report, §6) |

## 3. Only in Codex

1. **Numbers may be fixed when the evidence settles it.** `codex:139-140`: "Numbers, dice results, or mechanics unless the transcription is plainly wrong and evidence settles it." Claude never allows this; see §5 C3.
2. **Approve by item id or range.** `codex:184`: "Item ids or ranges: apply only those accepted ids, and leave the rest." Claude's options are apply all / selective / none (`claude:138-141`).
3. **Confirmed authentic variants go to DO-NOT-CORRECT in the ordinary (non-batch) flow.** `codex:231-233`: "If the user confirms a suspicious variant is authentic table speech or a nickname, add it to the glossary's DO-NOT-CORRECT area instead of the garble table." Claude states this only inside Artifact mode (`claude:248`, `:252-254`), so shell-mode runs lack it.
4. **Report why a verification-grep hit remains.** `codex:199-200`: "Inspect and either apply the approved fix or report why it remains." Claude says "investigate and retry" (`claude:153`).
5. **A no-silent-edit rule for batch mode.** `codex:293-294`: "Auto-apply only after explicit user approval. Even in a batch queue, do not silently edit files based on confidence." Also `codex:36-37`. This is the direct opposite of Claude's footer class; see §5 C2.
6. **Safety and validation rules for the batch page:**
   - Keep the exact edit data in `quote_consistency_review.json`, separate from the page JSON (`codex:252-254`).
   - Run-specific `reviewId` and `outputName` (`codex:257`).
   - "Verify the generated page contains every queued ID and preserves the exact proposals" (`codex:258-259`).
   - "Validate its reviewId and item IDs against this run" (`codex:281`).
   - "merely generating or opening the page is never approval" (`codex:282-283`).
   - "Escape all transcript text" (`codex:255-256`).
   Claude's SKILL.md has none of these. Claude's shared contract does cover escaping (`claude/skills/_shared/review-artifact/CONTRACT.md:135`) and non-approval (`:87`), so the gap is only in the skill text for those two.
7. **Table vocabulary is on the "do not change" list.** `codex:137`: "Profanity or table vocabulary." Claude's list covers profanity only (`claude:90`). Claude's staged-consistency does protect table vocabulary.
8. **The description covers both directory names.** `codex:3` says "on scene_extractions_new/ or scene_extractions/". Claude's description (`claude:3`) names only `scene_extractions_new/`, although its body handles both (`claude:16`, `:40`).

## 4. Only in Claude

1. **Step 0: ask the review mode on every run.** `claude:21-32`: "Before locating anything, one `AskUserQuestion` … Ask this every run; do not remember a default." See §5 C1.
2. **Worked examples behind each cross-reference rule.** Codex has the rules at `codex:104-114`, but none of these examples:
   - `claude:70`: `Alley`/`Alle` resolving to A'lai in one place and Alkrist in another.
   - `claude:71`: Fembris Lancer doubling, and the "bowl cut" false two-option choice that was really Tadric.
   - `claude:72`: Grygumite is a real nickname; "Gaz"/"Dad" for Daz were mishearings.
   - `claude:73`: `Bolkut`/`Boldcut`/`bald cat`/`bowl cut`/`bolt cut`, all one garble found across separate passes.
3. **Worked examples behind the player-name scrub:**
   - the OOTA player→character mapping (`claude:78`)
   - "one scene labelled the GM `**Kostadis Roussos**` 47×" (`claude:81`)
   - summary leaks such as "`Kostadis laid out three options…`" and `go to "LI"` → A'lai (`claude:53`, `:83`).
4. **Why grammar is never smoothed.** `claude:89`: "The verbatim quote is a *record*, and it is the raw material the voice files are built from; grammar-smoothing it here would erase the very evidence that calibrates them." Codex has the rule (`codex:136`) but not the reason.
5. **A profanity nuance.** `claude:90`: "'passes' → 'asses' only when the correction is already in the glossary".
6. **Why this pass should grow the glossary.** `claude:157`: "This pass catches classes that `vtt-spell-pass`'s deterministic scanner structurally cannot — lowercase name-garbles … sentence-initial one-offs … meaning-dependent real-word swaps". Also the extra safe example `abald → Avowed` (`claude:162`), and "This closes the loop" (`:165`).
7. **A `downloads`-capability artifact** with a sticky tally dock, a Markdown decision record, and a WSL2 download path. `claude:120-130`, `:141`. This conflicts with Claude's own Artifact mode; see §5 C4.
8. **Artifact mode: the auto-apply footer class.** `claude:197-208`: "A quote fix needs no ruling only when two independent transcripts agree on the correction, or the glossary/registry already settles it AND the surrounding dialogue confirms the referent." This covers glossary proper nouns confirmed in a second transcript, homophones with only one reading, and "Player-name scrubs in speaker labels and scene summaries". Codex has no equivalent and forbids it; see §5 C2.
9. **Artifact mode: what is always a card.** `claude:210-226` lists:
   - reconstructions, where `ev` says which transcript said what
   - identity calls
   - possible authentic coinages, where `ev` should "say … that the check found no corroboration" (`find-us fee`, `Big Al`, `Orcanese`)
   - unrecoverable lines
   - player names inside quote content.
   Codex puts every item on a card, but gives no guidance on what the card must say for these classes.
10. **Page naming and eyebrow.** `claude:185-192`: plain `review_items.json` is correct because this skill publishes one page per run, while staged-consistency must suffix per stage. The eyebrow is `<campaign> · <chapter> · scene quotes`.
11. **A worked card example with `t/y/n/ev` content.** `claude:234-240`. Codex's JSON example (`codex:266-278`) shows the edit-data schema instead, and describes the `t/y/n/ev` mapping in prose (`codex:252-254`).
12. **"apply all" mechanics.** `claude:138`: "one per Edit call. Do fixes to different files in parallel; fixes within the same file sequentially." This is mostly platform-specific.

## 5. Conflicts

**C1. Asking for the review mode.**
- Claude `:23`, `:29`: always ask at step 0, every run, and never remember a default.
- Codex `:35`: "Preserve an already-selected batch mode across turns; do not ask again." Codex never asks up front. Batch mode applies "when the report is too large for comfortable chat adjudication or the user asks" (`codex:237-238`, `:168`).
- Claude's staged-consistency uses a threshold offer, and Codex staged-consistency asks up front every run. The four files hold three different policies.

**C2. Auto-applying fixes without a ruling (the substantive conflict).**
- Claude `:197-208` auto-applies the footer class, including "Player-name scrubs in speaker labels and scene summaries".
- Codex `:293-294`: "Auto-apply only after explicit user approval. Even in a batch queue, do not silently edit files based on confidence."
- Claude's own consistency-check now warns against this (uncommitted, `claude/skills/consistency-check/SKILL.md:413`): "A real-name scrub is not a mechanical fix — it is an attribution change … Verify the speaker on the tape before applying any real-name scrub." Claude session-summary-consistency's auto-applied player-name scrub in speaker labels is exactly that operation.

**C3. Numbers and dice.**
- Claude `:92`: "Numbers and dice results, even if oddly phrased" (never change).
- Codex `:139-140`: never change "unless the transcription is plainly wrong and evidence settles it."

**C4. The batch mechanism, including a conflict inside Claude.**
- Claude step 4 (`:120-130`): declare `capabilities: {"downloads": true}`, export "one Markdown decision record", and the user downloads it and pastes it back.
- Claude Artifact mode (`:167-193`): the shared `build_review.py` with `$SCRATCH/review_items.json`, "Publish with `capabilities: {"artifact": {}}`", and pick up the save from the `artifact-changed` notification.
- These two Claude sections came from different branches (`8309e5c` and `2d9cc62`) that merge `d81cc3f` concatenated.
- Codex has a single flow (`codex:235-294`): standalone `<session-dir>/quote_consistency_review.html` from the shared builder, and decisions in `quote_consistency_decisions.json`, pasted or saved.
- Files are placed differently too: session dir (Codex) versus scratchpad (Claude Artifact mode). Codex keeps the decision artifacts beside the session. Claude's live in scratch unless the user downloads them.

**C5. Description scope.** `claude:3` names `scene_extractions_new/` only. `codex:3` names both directories. This is minor, but the description is what triggers the skill.

## 6. Platform-only differences

- **Frontmatter:** `tools: Read, Bash, Edit, Artifact, AskUserQuestion` (`claude:4`) versus `metadata.short-description` (`codex:4-5`).
- **Port header and compatibility block.** `codex:23-37` covers chat questions, `update_plan` and `apply_patch`.
- **`Edit` versus `apply_patch`** (`claude:138, 145, 246`; `codex:189, 287`).
- **Review transport:** Claude Artifact publish with `artifact-changed` notifications (`claude:191-193`), versus a standalone HTML file with pasted or saved JSON (`codex:240-250`, `:280`). `~/.claude/skills/_shared/review-artifact` versus `${CODEX_HOME:-$HOME/.codex}/skills/_shared/review-page`.
- **The WSL2 Windows download path** (`claude:130`) is specific to the environment.
- **`agents/openai.yaml`:** absent.

As in staged-consistency, only the transport is platform-specific. What is auto-applied, the verdict set and the decision-file location are policy.

## 7. Script diffs

Neither side ships a script. The two shared review builders differ (roughly 120 to 300 diff lines per file) and are covered as a dependency in the staged-consistency report.

## 8. Open questions for the GM

1. **Auto-apply footer class (C2).** Keep Claude's "two independent transcripts agree" auto-apply, adopt Codex's "nothing without explicit approval", or a middle position?
   *Suggestion:* at minimum, take player-name scrubs in **speaker labels** out of the auto-apply class. Your uncommitted consistency-check lesson (Gabe → Zalthir, where the speaker was actually Daz) classes them as attribution changes, which your global rules treat as precision decisions. Homophones confirmed by two transcripts are a separate, lower-risk question.
2. **Claude's two artifact flows (C4).** Which one survives: the `downloads` + Markdown record (step 4), or the shared-builder `artifact`-capability mode?
   *Suggestion:* the shared-builder mode matches sibling Claude skills and uses the same `t/y/n/ev` card schema as Codex. Removing the step-4 block would clear the inside-Claude contradiction.
3. **Review-mode prompt (C1).** Ask every run (Claude), or ask only when large or requested and then persist the choice (Codex)? Consider settling this once across session-summary-consistency and staged-consistency on both sides; the four files currently hold three policies.
4. **Numbers (C3).** Never touch numbers, or allow evidence-settled fixes?
   *Suggestion:* if allowed, require a card (never the footer), since numbers feed mechanics rulings downstream.
5. **Port Codex's approval-hygiene rules to Claude's SKILL.md?** These are run-specific `reviewId`, id validation, "generating or opening the page is never approval", and exact edit data kept separately (§3 item 6). Some are already in Claude's shared CONTRACT.
6. **Port Claude's examples and "always a card" guidance to Codex** (§4 items 2–6 and 9)? The rules are already there. Only the evidence and card-content guidance are missing.
7. **Small additions to Claude:** item-id/range approval (§3 item 2), DO-NOT-CORRECT routing in shell mode (§3 item 3), table vocabulary on the "do not change" list (§3 item 7), and naming `scene_extractions/` in the description (C5).
8. **Decision-file location.** Session dir (Codex) or scratchpad (Claude)?
   *Suggestion:* the session dir leaves a record for audit, in the spirit of the consistency-check manifests.
