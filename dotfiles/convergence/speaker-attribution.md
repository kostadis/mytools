# Convergence report: speaker-attribution

Paths are relative to `/home/kostadis/src/mytools/dotfiles/`. "codex" means
`codex/skills/speaker-attribution/`, "claude" means `claude/skills/speaker-attribution/`.
Line numbers are from the working tree as of 2026-09-24. The working tree has no
uncommitted changes in either skill.

## 1. Summary

The two versions cover the same five-stage workflow: provenance, diarize, join and
cross-validate, name clusters, write. They differ a lot in form and in epistemic
stance. Claude is a 536-line field manual: concrete Spark commands, worked numbers
from Hillsfar and Phandalin, a Landmines list, and a "Why this design" rationale.
Codex is a 175-line procedure with three `references/` files. It keeps most of the
same facts in more general form and adds guardrails Claude lacks: single-source
handling, report-only first, a verification step, a run record with hashes,
`UNKNOWN` for unmapped voices, and GM confirmation before any mapping is used.

Git history shows the direction. Claude was created on 2026-08-29 (`11c1650`,
`7db63c3`), with its last edit on 2026-09-04 (`6c7b240`, the named-audit and
derivative-detection material). Codex arrived in one commit, `8bfd959`, on
2026-09-18. It says it is "the Codex port of the Claude skill" (codex `SKILL.md:12`),
and `git log --follow` traces its scripts back to Claude's commits. The Codex port
therefore postdates every Claude edit and incorporates the 09-04 material. It also
rewrites three of the four scripts in a hardening direction. Nothing has been ported
back from Codex to Claude.

In rigour and safety, Codex is the more developed version. In operational detail and
worked evidence, Claude is.

## 2. File inventory

| file | codex | claude | status |
|---|---|---|---|
| `SKILL.md` | 175 lines | 536 lines | differs (restructured) |
| `references/provenance.md` | 92 lines | — | only-codex (content is Claude's Phase 0 + Descript section, generalised) |
| `references/acoustic-workflow.md` | 94 lines | — | only-codex (content is Claude's Phase 2/3 + Landmines, generalised) |
| `references/identity-review.md` | 101 lines | — | only-codex (content is Claude's Phase 4, generalised) |
| `agents/openai.yaml` | 4 lines | — | only-codex (Codex harness metadata) |
| `transcript_provenance.py` | 260 lines | 260 lines | identical |
| `descript_turns.py` | 158 lines | 154 lines | differs (Codex superset) |
| `diarize_label.py` | 316 lines | 279 lines | differs (Codex hardened; behavioural changes) |
| `name_clusters.py` | 168 lines | 177 lines | differs (Codex reuses `diarize_label.load_vtt`; wider label regex) |

## 3. Only in Codex

Each item was checked against Claude's `SKILL.md` and scripts by concept, not only
by wording.

1. **No acoustic input means stop, not guess.** codex `SKILL.md:30-34`: "A speakerless VTT and a summary, without audio or saved acoustic turns, are insufficient to identify voices. Report that specific missing input; do not fabricate labels from dialogue style, alternating cues, narration, or character names." Claude never addresses the no-audio case. (It is the job of the sibling `speaker-attribution-text`, which Claude's skill does not name.)
2. **Participant facts are inputs, not questions.** codex `SKILL.md:26-29`: "Two people can voice an entire party. Do not ask again for facts already provided, or equate a known PC owner with an acoustic cluster ID." Claude has the related "`num_speakers` is the count of people" (claude `SKILL.md:487`), but not the don't-re-ask rule or the owner≠cluster rule.
3. **Single-acoustic-source path with an explicit GM acceptance.** codex `SKILL.md:35-39`: "If only one acoustic source exists, prepare an explicitly unvalidated cluster report and explain what is missing. Obtain the GM's acceptance of that limitation and the actual name mapping before producing named output; never report independent agreement." Also codex `SKILL.md:155-156` and `references/acoustic-workflow.md:92-94`. Claude makes Descript the primary source when no GPU is free (claude `SKILL.md:163-165`), which leaves one clustering, but it never says what to do then. See Conflict C1.
4. **Scratch run directory; originals preserved; audits produce a queue first.** codex `SKILL.md:40-47`: "preserve originals. Work in a unique scratch directory and write the approved result to a new `<stem>.speakers.vtt`." Claude writes `<stem>.speakers.vtt` directly in Phase 3 (Conflict C2).
5. **Keep summaries out of the provenance inventory; scanner thresholds.** codex `SKILL.md:62`: "Keep summaries out of the second-transcript inventory." codex `references/provenance.md:14-18` documents the 500-token / 20-block defaults, `--min-tokens`, and "`--include-prose` admits summaries and is usually inappropriate." The flags exist in both copies of the identical script, but only Codex documents them.
6. **`--limit-seconds` is a prefix cut, not an offset.** codex `SKILL.md:99-101`: "that option selects a prefix, not an arbitrary offset. Verify any slicing or retiming separately before joining." Also `references/provenance.md:23-24`. Claude (`SKILL.md:176-178`, `486`) presents `--limit-seconds` as the fix for any concatenation. That only works when the recording is the first part of the file.
7. **Remote-run etiquette.** codex `SKILL.md:78-82`: "Do not stop other GPU services or accept model-license terms on the user's behalf. Do not launch remote work just to inspect this skill." Claude has no do-not-stop-other-workloads rule. Its "try CUDA anyway" (claude `SKILL.md:496-502`) implies coexistence but does not forbid stopping vLLM.
8. **Token hygiene and error triage.** codex `references/acoustic-workflow.md:34-37`: "Use the configured token **path**, never print or inline its contents … distinguish permissions, gated-model access, and GPU memory failures rather than treating all as authentication errors." Claude covers only the root-owned-cache `PermissionError` (claude `SKILL.md:479-480`).
9. **Verified staging.** codex `references/acoustic-workflow.md:15-17`: "Create a unique remote working directory … check command exit codes and verify remote file sizes/hashes." Claude verifies with `ls -la` (claude `SKILL.md:470-472`), which is weaker (no hash check) but covers the same intent.
10. **Validate the returned turn envelope.** codex `references/acoustic-workflow.md:63-65`: "Confirm times are finite, ordered, in range, and end after start, and that the requested people did not collapse into a single voice." The Codex script enforces this (Section 7). Claude does not.
11. **Report-only first.** codex `SKILL.md:89`: "Use report-only mode first." Claude's first Phase 3 command already passes `--output` (claude `SKILL.md:217-219`).
12. **Mapping rule and agreement denominator.** codex `references/acoustic-workflow.md:74-79`: "A second-source cluster is mapped only when it contributes at least 5% of compared words and one primary cluster owns at least 60% of its row. Agreement is computed on words with a qualifying mapping. Report coverage and unmapped fragments alongside the percentage; excluded words are not successes." Both scripts implement 5%/60%. Only Codex documents it, and only the Codex script prints the mapped/total word denominator.
13. **Do not bulk-clear unrelated `[?]` flags after `--md-label`.** codex `references/acoustic-workflow.md:89-90`: "do not bulk-clear unrelated flags." Claude's "Do not 'fix' them in bulk" (claude `SKILL.md:506-508`) is the same idea in general form. This is near-coverage, noted for completeness.
14. **Attribution must not rewrite transcript text or spellings.** codex `references/identity-review.md:11-14`: "Preserve the source spelling in quotations; an existing approved spell-pass copy can help find known variants, but do not invent corrections or rewrite transcript text during attribution." Claude defers spelling to a downstream `/vtt-spell-pass` (claude `SKILL.md:26`) but states no rule.
15. **Weak anchors and audio excerpts.** codex `references/identity-review.md:26-30`: "Short acknowledgements crossing a cue boundary are often unreliable anchors. Prefer longer distinctive exchanges or playable audio excerpts for the GM to identify … With two people, do not assume the longest cluster is the GM or force cues to alternate." Claude does not mention audio excerpts or the two-person heuristics.
16. **Do not pick the largest bin on a SPLIT.** codex `SKILL.md:130`: "A `SPLIT` is unresolved evidence; do not select the largest bin." Claude treats SPLIT as a correct, informative result (claude `SKILL.md:373-381`). It has no explicit do-not-take-the-plurality rule, but its tone is compatible.
17. **Audit queue requires a GM-confirmed mapping, with a fixed item schema.** codex `references/identity-review.md:62-72`: "Apply only a **GM-confirmed** cluster-to-player mapping to calculate a proposed name … Retain lower-coverage cases as unresolved." It then lists per-item fields (source path, cue identity, span, verbatim dialogue, current and proposed name, cluster, covered fraction, word count, evidence, unset decision). It also says, at codex `references/identity-review.md:81-82`: "If a label map is unresolved, queue its evidence before proposing cue-level rewrites that depend on it." Claude computes the queue from the diarization's dominant speaker (claude `SKILL.md:336-338`) with no mapping-confirmation step and no item schema.
18. **Re-run on the original speakerless text; never feed labelled output back.** codex `SKILL.md:148-152`: "Re-run the join on the original speakerless text … Do not feed a labelled result back in as unlabelled speech. For a named audit, preserve labels until the exact changes are approved." Claude says "re-run Phase 3 with `--names`" (claude `SKILL.md:381-383`) and does not say on which input.
19. **Unmapped voices stay `UNKNOWN`.** codex `references/identity-review.md:94-96`: "Leave unmapped voices anonymous or `UNKNOWN`; an unresolved human identity must not become a plausible-looking name." No such rule appears in Claude's SKILL.md. Both scripts do print `UNKNOWN` when no turn overlaps.
20. **Outside voices keep their speech.** codex `SKILL.md:159-160`: "Label a confirmed outside voice `Room (not at table)` and retain its speech unless removal was requested." Claude labels the voice but is silent on retention.
21. **Output verification step.** codex `SKILL.md:164-167`: "Verify the selected cue count, exact dialogue payloads (apart from inserted labels), and timestamps against the source. Preserve spoken numbers, crosstalk, unresolved `UNKNOWN` labels, and disagreement markers. Report every omission caused by a selected time limit. Check that no original file changed." Claude has no verification step. Its script also drops numeric-only lines (Section 7), so this check would fail against Claude's output.
22. **Run record and hash-pinned decisions.** codex `SKILL.md:169-171`: "Save a run record beside the new output with source paths/hashes, model and speaker count, provenance findings, independent-source status, join method, agreement denominator, GM decisions, and unresolved cues." Also codex `references/identity-review.md:93-95`: "Persist explicit decisions alongside source hashes. Before writing final names, confirm the sources and turns still match the reviewed versions." Claude has neither.
23. **Reuse prior rulings.** codex `SKILL.md:112-113`: "An existing acceptance of these exact results need not be requested again." Also `references/identity-review.md:86-87`. Claude's checkpoints are "none is optional" (claude `SKILL.md:512`), with no reuse clause.
24. **Header content spec.** codex `references/identity-review.md:96-97`: "Final headers say player labels, acoustic source, second source if any, and unresolved disagreement semantics." Claude asks only that "players, not characters" appear in the header (claude `SKILL.md:456`).
25. **Glossary non-contamination.** codex `references/identity-review.md:100-101`: "Do not rename PCs in the glossary merely because the same player speaks their lines." Not in Claude.
26. **Record player/PC relationships separately; resume a pending spell pass.** codex `SKILL.md:159`: "Record known player/PC relationships separately." codex `SKILL.md:175`: "Resume any pending spell pass within its existing review rules." Not in Claude.
27. **mvhd version caveat.** codex `references/provenance.md:31-32`: "an M4A/MP4 `mvhd` atom can supply duration; account for the atom version before interpreting integer widths." See Conflict C4.

## 4. Only in Claude

Most of this is worked evidence and concrete commands. Codex often keeps the rule
but drops the example that justifies it. Rule-bearing items are marked **[rule]**.
Pure evidence or rationale is marked **[evidence]**.

1. **[rule] Routing table against `transcript-rebuild`.** claude `SKILL.md:11-19`: "Zoom's speaker labels | ~93% correct, keep them | **zero information**". Codex has only one sentence (codex `SKILL.md:15-17`: "If existing speaker identities are reliable and only their timestamps need alignment, that is a transcript alignment/rebuild task").
2. **[rule] Pipeline position and display-name hand-off.** claude `SKILL.md:21-36`: "The labels this skill writes are **short player names** … `/session-doc-run` does that mapping — do not rename the file this skill produces. Run it **before** `/scene-extract`. After means re-extracting." Codex says "before scene extraction" (`SKILL.md:15`) and leaves display-name mapping to "that pipeline's actual capabilities" (`SKILL.md:172-174`). The re-extract consequence and the do-not-rename instruction are only in Claude. The slash-command names are platform-specific (Section 6).
3. **[rule] Endpoint tolerance.** claude `SKILL.md:76-77`: "the two files should open and close on the same words within a second or two." Codex (`SKILL.md:58-59`) gives no tolerance. Claude also has a worked endpoint table at `SKILL.md:88-92` **[evidence]**.
4. **[rule] Concrete derivative test.** claude `SKILL.md:111-113` gives a runnable per-file speaker-tally `grep … | uniq -c` command. Codex describes comparing tallies (`references/provenance.md:41-44`) but gives no command.
5. **[rule] Choosing the best text layer.** claude `SKILL.md:123-134`: the Zoom / Descript / Whisper table ("Whisper — real timeline, best text, NO speakers") and "Take timings and text from the best ASR; take nothing from Zoom but the fact of the recording." Codex uses `$BEST_VTT` (`SKILL.md:94`) without saying how to choose it. See also Conflict C5.
6. **[rule] Descript is the only tool that can reveal an unbudgeted voice, because it picks its own speaker count.** claude `SKILL.md:138-139`, `300-306`: "Raising to `num_speakers=5` did **not** recover it — agreement fell 79.5% → 72.1% and the fifth cluster split the *GM*." Codex keeps the resulting rule (`references/acoustic-workflow.md:46-50`) but not this evidence or the "let Descript find the ones you do not" reasoning.
7. **[rule] Copy-pasteable Spark commands.** claude `SKILL.md:187-207`: `scp`/`ssh` staging, manifest, and the run line with `HF_HOME`. Codex gives structure only (`references/acoustic-workflow.md:11-44`).
8. **[rule] Confirm CUDA by log line.** claude `SKILL.md:501`: "grep the log for `running on cuda`; only fall back once it actually throws." Codex says "inspect actual errors" (`references/acoustic-workflow.md:55-56`) but names no success marker.
9. **[rule] OOM timing.** claude `SKILL.md:493-495`: "expect pyannote to OOM on `pipeline.to("cuda")` *after* it has decoded the audio, so the log looks like it got further than it did." Codex notes truncated nvidia-smi output (`references/acoustic-workflow.md:51-52`) but not this.
10. **[rule] Name/PC collision.** claude `SKILL.md:377-380` and `457-458`: "The player's real name **is** Daein, so every narration mention looks like an address … Where a player's real name collides with their PC's, label with the nickname and note why." Not in Codex.
11. **[rule] Expected shape of name probes.** claude `SKILL.md:445-447`: "Expect the real-name pass to be nearly empty and the PC pass to carry the run. Expect, too, that a player's **own** PC comes back `SPLIT`." Codex says to probe both (`SKILL.md:122`) but sets no expectation.
12. **[rule] Words as a single decision number.** claude `SKILL.md:348-350`: "'4.7%, largest single disagreement 16 words' is a decision they can make in one breath; 202 raw findings is not." Codex requires reporting the same totals (`references/identity-review.md:74-76`) but frames them differently. See Conflict C8.
13. **[evidence] Incident narratives:** the Hillsfar misfiling that would have produced 1145 wrong cues (claude `SKILL.md:70-74`); the Phandalin ch08 derivatives (`101-105`, `116`); the 24% header-shift statistic (`170-174`); the 32→24 `--md-label` cue comparison (`250-254`); the six-cluster confusion matrix (`267-283`); the coffee room voice (`289-298`); the Felkur/Bramgrim/Akritas outcomes (`371-380`); the Gary chat-sidecar absence probe with per-cluster seconds (`417-425`); and 297 of 1379 `[?]` cues being crosstalk (`506-508`).
14. **[evidence] Rationale sections.** "Why this design" (claude `SKILL.md:524-536`: "Attribution is a scope-and-identity decision, so no LLM makes one here … A confident label on the wrong voice is worse than no label") and checkpoint 3's "nothing further along re-checks speaker identity" (`519-522`). Codex's nearest equivalent is `references/identity-review.md:4-5`: "The deterministic tools propose and count; the GM supplies identity decisions." Codex never says explicitly that no LLM decides attribution.

Checked and **not** Claude-only, because Codex covers them: 4-gram thresholds, misfiled and concatenation detection, stem-vouching false positives, word-anchored Descript starts, chat sidecar, `community-1` over `3.1`, `num_speakers` = people, tilde expansion, `tail` buffering, re-`scp` the helper, root-owned HF cache, busy-GPU "try CUDA anyway", PC ownership not derivable from D&D Beyond, `[?]` is disagreement not error, named-profile bijection and shares, 75% coverage floor, and directional bias.

## 5. Conflicts

**C1. Is cross-validation mandatory?**
Claude's script: claude `diarize_label.py:8-9`: "That makes cross-validation mandatory rather than optional, because there is nothing else to catch a collapsed clustering." Claude's SKILL.md also expects a ~70% agreement floor before labelling (`SKILL.md:264-265`).
Codex: `SKILL.md:36-39`: "If only one acoustic source exists, prepare an explicitly unvalidated cluster report … Obtain the GM's acceptance of that limitation." The Codex script writes "Single acoustic source; no independent cross-validation." into the header.

**C2. When and where the output VTT is written.**
Claude: `SKILL.md:217-219` runs `diarize_label.py … --output <stem>.speakers.vtt` in Phase 3, before naming. It then runs `name_clusters.py <stem>.speakers.vtt` (`SKILL.md:363`) and re-runs with `--names` (`381-383`), so the session-directory file is written at least twice.
Codex: `SKILL.md:89` "Use report-only mode first". `SKILL.md:115-116` "write an anonymous, clearly provisional VTT into scratch". The final `<stem>.speakers.vtt` is written only after approval (`SKILL.md:40-42`, `148-150`). The Codex script also refuses to let `--output` overwrite an input.

**C3. Accepting gated-model licences.**
Claude: `SKILL.md:480-482`: "pyannote models are gated: accept conditions on `segmentation-3.0`, `speaker-diarization-3.1` *and* `speaker-diarization-community-1`."
Codex: `SKILL.md:81-82`: "Do not … accept model-license terms on the user's behalf." Also `references/acoustic-workflow.md:36`: "Model access must already be configured."
(Claude's line may mean "the user must have accepted", but as written it reads as an instruction.)

**C4. Parsing the MP4 duration.**
Claude: `SKILL.md:94-95`: "`timescale` and `duration` are two big-endian u32 at a fixed offset."
Codex: `references/provenance.md:31-32`: "account for the atom version before interpreting integer widths."
Codex is technically correct. A version-1 `mvhd` uses 64-bit times and different offsets, so Claude's recipe is wrong for such files.

**C5. Value of Zoom's labels.**
Claude: `SKILL.md:132-133`: "take nothing from Zoom but the fact of the recording."
Codex: `references/provenance.md:55-56`: "Zoom's labels can be useful if they actually distinguish participants; in the shared-microphone case, one host label carries no speaker information."
This follows from a scope difference (C12). Claude's own opening (`SKILL.md:17-19`) assumes the shared-microphone case.

**C6. A dominant cluster: collapse or not?**
Claude's script and checkpoint: `diarize_label.py:156-158` "largest cluster is {top}% of speech — clustering has probably collapsed. Re-run with speaker-diarization-community-1…". Also `SKILL.md:517-518`: "A collapsed clustering looks exactly like a valid one downstream."
Codex: `SKILL.md:106-108`: "A GM can legitimately dominate a two-person session, so a large share alone is not proof of collapse." The Codex script's warning says "check for collapse or a dominant speaker".

**C7. Is a derivative proven by identical tallies?**
Claude: `SKILL.md:119-120`: "Independent ASR passes never agree on turn counts. If they match to the digit, one is a copy."
Codex: `references/provenance.md:43-44`: "Identical tallies are a strong derivative clue, not mathematical proof."

**C8. What the disagreement percentage is.**
Claude: `SKILL.md:348-349`: "ask the GM whether to walk it or accept a stated error rate."
Codex: `references/identity-review.md:77`: "It is a disagreement measure, not a measured true error rate." And line 80: "Do not turn acceptance of a headline rate into approval of a silent relabel."

**C9. Agreement bands.**
Claude: `SKILL.md:261-265`: "**Expect ~80% word-level agreement**, and ~90% when `--md` is given real spans … Below ~70% either way, one of the signals has failed."
Codex: `SKILL.md:104-106`: "Historical runs measured about 80% with starts-only joins and 90% with spans; these are diagnostic examples, not guaranteed accuracy. Investigate low agreement." Codex's docs state no 70% threshold, although both scripts still print the <70% warning.

**C10. The chat-sidecar absence probe: decisive or advisory?**
Claude: `SKILL.md:402-403`: "find the cluster that goes quiet across the window, and that is the person." And `SKILL.md:424-425`: "Decided, on the diarization's own timeline."
Codex: `references/identity-review.md:50-52`: "Quiet players need not be absent, and typed names can be account labels; use the evidence to ask the GM, not to auto-select a voice."

**C11. Two PC names landing on one cluster.**
Claude: `SKILL.md:449-453`: "It means one person ran both, and it is *stronger* evidence than the campaign's own notes … proved Gary covered an absent player."
Codex: `references/identity-review.md:20-23`: "Two character names pointing to one voice may mean one player covered both … Neither result authorizes a permanent player/character mapping. Use explicit session information."
Both agree that ownership is not carried across sessions.

**C12. Scope statement.**
Claude: `SKILL.md:17-19`: "Use this when everyone was in one room on one mic, so there are no names anywhere." This contradicts Claude's own description and Phase 4 named-audit section (`SKILL.md:310-350`).
Codex: `SKILL.md:3` and `10-11` cover "missing, anonymous, shared under one microphone, or unreliable voice-profile guesses" throughout.

**C13. Naming the room voice.**
Claude: `SKILL.md:295-297`: "Label them **`Room (not at table)`** so `/scene-extract` cannot attribute coffee to a PC." This is done inline with `--md-label` in Phase 3, before the Phase 4 checkpoint.
Codex: `references/acoustic-workflow.md:82-83`: "Confirm with the GM before applying `Room (not at table)` or merging an acoustic fragment."

**C14. Bolded Descript labels.**
Claude: `SKILL.md:144-152` requires a `sed` pre-step: "Normalise bolded labels first, or the parse is silently wrong."
Codex: `references/provenance.md:66-68`: "The Codex helper accepts plain and Markdown-bold speaker labels." No pre-step.
These are compatible in practice (the `sed` is harmless with the Codex script), but the docs disagree about whether the step is needed.

**C15. How the `--names` / `--md-label` mapping is passed.**
Claude: `SKILL.md:243` and `382-383` use inline JSON ("inline JSON, or a path to a JSON file — both work").
Codex: `SKILL.md:148` "Save the approved mapping in a JSON file", and `references/acoustic-workflow.md:86` "use an approved JSON file with `--md-label`."
Both scripts accept both forms. The difference is procedural: a file leaves an auditable record.

**C16. Structural note (not a content conflict).**
Claude's phases are numbered 0, 2, 3, 4 (`SKILL.md:38`, `185`, `214`, `308`). Phase 1 was folded into Phase 0 in `6c7b240`, and the Descript subsection now sits under Phase 0. Codex numbers its steps 1–5.

## 6. Platform-only differences

These are expected harness differences and are not convergence candidates by default.

- **Skill path:** Claude hard-codes `~/.claude/skills/speaker-attribution/…` with `python` (e.g. `SKILL.md:44`, `157`, `217`). Codex resolves `SKILL_DIR` from `${CODEX_HOME:-$HOME/.codex}` and uses `python3` (`SKILL.md:44-47`).
- **Frontmatter:** Codex has `metadata.short-description` (`SKILL.md:4-5`) and `agents/openai.yaml` (display name, short description, `$speaker-attribution` default prompt). Claude's description is longer and carries anecdotes ("866 cues", "six anonymous clusters") as trigger text. Codex triggers on `$speaker-attribution` or `/speaker-attribution`.
- **Port self-reference:** codex `SKILL.md:12-13`: "This is the Codex port of the Claude skill … using it never requires editing the Claude collection."
- **Question and review tooling:** codex `SKILL.md:139-144`: "Ask in Codex chat … Do not reference Claude question tools, Artifacts, callbacks, or Claude task APIs. If the user requests batch review, use the installed shared review-page contract". The contract is `codex/skills/_shared/review-page/CONTRACT.md`, per `references/identity-review.md:84-91`. Claude's speaker-attribution offers **no** batch-review mechanism at all. Its Claude-side equivalent would be `claude/skills/_shared/review-artifact/CONTRACT.md`, which exists but is not referenced. This is platform-shaped, but whether Claude should gain a batch review option is a real choice (Question 9).
- **Downstream skills:** Claude names `/vtt-spell-pass`, `/session-doc-run`, `/scene-extract`, `/session-summary-consistency`, and `/voice-smooth` (`SKILL.md:23-36`). Codex says "do not assume Claude-only downstream skills are installed or start them automatically" (`SKILL.md:173-175`).
- **Project instruction files:** Codex says "Read applicable `AGENTS.md`" (`SKILL.md:24`). Claude's only `CLAUDE.md` mention is anecdotal (`SKILL.md:453`).
- **Search tool:** Codex says "Use `rg --files`" (`SKILL.md:22-23`).
- **Progress reporting:** codex `references/acoustic-workflow.md:60`: "use short polls so the user receives updates." Claude says "Launch it detached, redirect to a file" (`SKILL.md:501`). This is harness etiquette.

## 7. Script diffs

`transcript_provenance.py` is **identical** on both sides.

### `descript_turns.py` (Codex is a superset)

- Codex rewrites Markdown-bold headers (`[00:17:16] **Nikhil:** …`) to the plain form before parsing (`_BOLD_HEAD`). Claude's parser takes `**dave` as the label and leaves `**` in the text without erroring. That is why Claude's SKILL.md needs the `sed` step. Behaviour on plain input is unchanged.
- The fragment tag under 3% word share changes from "← fragment, not a person" (Claude) to "← small cluster; inspect before classifying" (Codex). The output text is different, but the threshold and logic are the same.

### `diarize_label.py` (Codex is hardened, and output differs)

- **VTT reading.** Claude reads line by line, joins payload lines with spaces, skips any line that is all digits, and uses `errors="replace"` decoding. As a result:
  - a cue whose dialogue is a spoken number ("20") is **dropped**;
  - multiline payloads are flattened into one line;
  - cue identifiers are renumbered 1..n;
  - timing lines are regenerated, so cue settings are lost.

  Codex parses blank-line-separated blocks, skips `WEBVTT`/`NOTE`/`STYLE`/`REGION` blocks, keeps the payload lines, the original timing line (with settings), and the original cue ID, and decodes strict `utf-8-sig`. It raises on an interval where end ≤ start. In Codex output, `cue_id` and `timing` come from the source.
- **Primary overlap join.** Claude uses a `bisect` to start one turn before the cue. It can miss a long earlier turn that is still overlapping when shorter turns intervene, and it assumes the turns are sorted. Codex sorts turns and scans every turn from the start (`overlap_by_speaker`): correct for overlapping turns, O(cues × turns).
- **Input validation (Codex only).** It rejects:
  - an `--output` path equal to any input;
  - `--md-label-coverage` outside [0.5, 1.0];
  - an empty turns list;
  - turns with non-finite, negative, or inverted times or a blank speaker;
  - second-source turns with an invalid interval.
- **`--md-label` without spans.** In Claude, if `--md` is starts-only, `de_cov` is `None` and the override applies to **every** cue assigned to that cluster regardless of coverage. The ≥50% rule in Claude's SKILL.md (`248-249`) silently does not hold in that mode. Codex errors: "--md-label requires real start/end spans".
- **Reporting.**
  - The agreement line gains a denominator: "`X% (compared/all words mapped)`".
  - A new "agreement unavailable — no qualifying mapped words" message.
  - The non-mapping row message changes from "treated as a spurious split" to "no qualifying mapping — review this cluster".
  - The >70% speech warning changes from "clustering has probably collapsed. Re-run with community-1…" to "check for collapse or a dominant speaker … A GM-heavy two-person session can be this uneven".
- **Output header.** Claude writes "Cross-validated against X." whenever `--md` is given. Codex writes the agreement percentage with its denominator plus "The caller must verify that the second clustering is independent.", or "inconclusive" when no mapped words exist, or "Single acoustic source; no independent cross-validation." when there is no `--md`.
- **Docstring.** Claude's opening docstring (the single-room rationale, "cross-validation mandatory", "Expect ~80%") is replaced by a neutral statement of caveats.
- **Unchanged:** CLI flags (`--turns --vtt --md --names --md-label --md-label-coverage --output --note --limit-seconds`), the 5%/60% mapping rule, `load_md`, `load_names` (inline or path), and the `[?]` semantics.

### `name_clusters.py` (Codex is a superset)

- Codex drops its own VTT loader and imports `load_vtt` from `diarize_label.py`, so it inherits the block-aware, lossless parsing. It must therefore sit beside `diarize_label.py`, as it does.
- The label regex widens from `[A-Za-z0-9_ ]{1,40}` to "anything up to the first colon, 1–80 chars", and it spans multiline payloads. With Claude's regex, a cue labelled `Room (not at table)` or `Filavandrel (Fil)` fails to parse, and the cue is **silently dropped** from scoring. Codex keeps it.
- The scoring and ranking logic is unchanged.

## 8. Open questions for the GM

1. **Which document shape should both converge to?** One option is Claude's inline field manual with incidents and landmines. The other is Codex's short SKILL.md plus `references/`.
   *Suggestion:* keep Codex's split structure and move Claude's incidents into the references as evidence under each rule. Claude's worked numbers are what justify the thresholds.
2. **Scripts.** Should Claude adopt Codex's `diarize_label.py`, `name_clusters.py`, and `descript_turns.py`? They fix real Claude defects: dropped numeric-only cues, dropped parenthesised labels, `--md-label` ignoring coverage in starts-only mode, and a possible missed overlapping turn.
   *Suggestion:* yes, then delete Claude's `sed` bold-normalisation step (C14). Confirm first that the Codex loop's O(n·m) join is acceptable on a 1400-cue, multi-thousand-turn session.
3. **Single acoustic source (C1).** Is a one-clustering run allowed to produce named output with an explicit GM-accepted limitation (Codex), or is cross-validation mandatory (Claude's docstring)?
4. **Output flow (C2).** Report-only first, anonymous draft in scratch, and the final `<stem>.speakers.vtt` written once after approval (Codex)? Or Claude's write-then-rewrite in the session directory?
5. **Gated licences (C3).** Should the skill ever tell the agent to accept model terms? Or state that access must already exist and stop if it doesn't?
6. **Evidence strength (C6, C7, C10, C11).** Four places where Claude calls something decisive and Codex calls it a clue to put to the GM:
   - collapse at >70%;
   - identical tallies prove a derivative;
   - a quiet cluster during a chat absence "is the person";
   - two PCs on one cluster "proved" coverage.

   Which stance should both sides take?
   *Suggestion:* keep Codex's advisory framing, but keep Claude's examples showing how often each signal was right.
7. **Disagreement percentage (C8, C9).** Present it as an "error rate" the GM can accept, or as a "disagreement measure, not a true error rate"? And should the ~70% floor be a documented threshold or only a script warning?
8. **Scope (C5, C12).** Should the Claude body's opening match its own description and cover the voice-profile audit case and Zoom labels that do distinguish participants? This affects the "take nothing from Zoom" rule.
9. **Batch review in Claude.** Codex offers a shared review-page for mapping and cue decisions. Should Claude's speaker-attribution offer the `_shared/review-artifact` equivalent, or stay chat-only?
10. **Run record, hashes, verification (Only-in-Codex 21–22).** Adopt the run record, the hash-pinned decisions, and the post-write verification on the Claude side?
11. **Room voice (C13).** Must `Room (not at table)` be GM-confirmed before `--md-label` is applied? Or is it covered by the Phase 4 checkpoint as Claude has it? Should its speech always be retained unless removal is requested?
12. **Claude-only operational rules (Only-in-Claude 1–12).** Should Codex gain these?
    - the transcript-rebuild routing table;
    - the "run before `/scene-extract` or re-extract" consequence;
    - the endpoint tolerance;
    - the tally `grep`;
    - the best-text layer table;
    - the `running on cuda` success marker;
    - the OOM-after-decode note;
    - the nickname rule for real-name/PC collisions.

    *Suggestion:* at least the nickname rule, the best-text table, and the `--limit-seconds`-is-a-prefix clarification. The last one is already in Codex and should go into Claude.
13. **mvhd (C4).** Correct Claude's "two big-endian u32" recipe to handle version-1 atoms, as Codex does?
