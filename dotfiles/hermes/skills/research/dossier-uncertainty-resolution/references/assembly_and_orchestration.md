# Assembly & Orchestration (Dossier Uncertainty → per-dossier answers)

Companion to the SKILL.md "Assembly" section. Captures the working assembler
logic (`scripts/assemble_answers.py`) and the fan-out orchestration shape used
to resolve 327 Phandalin dossiers against 46 chapters.

## Fan-out shape used
- 327 dossiers → `batches.json` = `batch_01`…`batch_11`, ~30 filenames each.
- 11 subagent tasks, dispatched in **waves of 3** (cap), background-async:
  wave1 = b01–03, wave2 = b04–06, wave3 = b07–09, wave4 = b10–11.
- Each subagent reads ONLY its batch's dossiers + the cited chapter files
  (and other chapters only if the cited range is silent), resolves every
  `## Uncertainty` bullet with `chN` citations, writes `batch_NN.md`.
- Parent waits for each wave's "ASYNC DELEGATION BATCH COMPLETE" message, then
  launches the next. No need to poll.

## Assembler (`scripts/assemble_answers.py`) — what it does
1. Loads `batches.json`; builds `dossier -> batch_NN` map.
2. For each batch file, `parse_qa(text, name)`:
   - heading regex `^##\s+<name>(?:\.md)?\s*:` (the `(?:\.md)?` is mandatory).
   - block end = next `\n## ` OR end-of-file (`len(text)-start-2`) — the
     no-next-heading branch is what saves the LAST dossier of each batch.
   - splits on `\nQ:\s*`, pairs each Q with the following A (up to next
     `Q:`/`Status:`).
3. `annotate(dossier_text, qa_pairs)`:
   - finds `## Uncertainty` via `^(##\s*Uncertainty\b.*?)(?=\n##\s|\Z)`.
   - for each `- ` bullet, fuzzily matches to a Q/A pair (token Jaccard OR
     difflib ratio ≥ 0.5, requires ≥3 shared content tokens) and appends inline
     `  -> Resolved [chN]: <answer>` (chN pulled from `ch(\d+)` in the answer).
   - inline match is best-effort; missing it is fine.
4. Appends a `## Resolved Answers (from chapter analysis)` footer with the FULL
   Q/A (every question + answer) so completeness never depends on inline match.
5. Writes `answers/<dossier>` (full original + annotations + footer) and
   `INDEX.md` (per-dossier: status, batch, inline matched/total).

## Parameterize
Hardcoded defaults in the script point at the Phandalin example. To reuse:
- `DOSSIER_DIR` — source dossier dir (read-only).
- `OUT` — output dir containing `batches.json` + `batch_NN.md`; `answers/` and
  `INDEX.md` are written under it.
Edit those two path constants before running in a new corpus.

## Known residual gap (honest note)
In this run, 1 dossier ended with no footer (its batch subagent left questions
unparsed). Mitigation: grep the batch files for any dossier heading whose Q/A
didn't land, or re-run just that batch. The `INDEX.md` "no-answers" row is the
fast way to spot them.
