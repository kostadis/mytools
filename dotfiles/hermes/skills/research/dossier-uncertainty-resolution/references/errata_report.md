# Generating an errata / QA report from the batch files

After resolving a large corpus of dossiers into `batch_NN.md` files (see
`assembly_and_orchestration.md`), you often want a single readable *quality*
report — the "errata" — that isolates the dossiers the pipeline got wrong or
that contradict the source. This is how to build `errata.md` from the batch
files without hand-reading 327 dossiers.

## Why it exists
The per-dossier answers are exhaustive but low-signal for "what's interesting."
The user usually wants: (1) dossiers whose *own facts* contradict the source
(not just an open question), (2) genuine internal source contradictions,
(3) questions the corpus cannot answer, (4) references that point outside the
corpus. A report groups exactly these.

## Parsing the batch files (gotchas)
Each `batch_NN.md` has one `## <name>(.md)?: <Entity> [type]` block per dossier,
with `Chapters cited:`, `Q:`/`A:` pairs, and a final `Status:` line.

- **Heading regex** must allow the optional `.md`: `^##\s+<name>(?:\.md)?\s*:`.
- **Status line is NOT always bracketed.** Real output uses bare
  `Status: Resolved` / `Status: Partially resolved (…)` / `Status: Unresolved`
  — NOT `Status: [Resolved]`. A regex requiring `[...]` will return `?` for
  almost every dossier. Parse with:
  `^Status:\s*(?:\[(.*?)\]\s*)?(.+)$` and normalize: "partial"→Partially
  resolved, "unresolved"→Unresolved, "resolved"→Resolved; else Unknown.
- **Block end**: next `\n## ` OR end-of-file (`len(text)-start-2`). The last
  dossier in a batch has no trailing heading — without the EOF branch its
  parse truncates to ~2 chars and it silently gets no answers.
- **Split Q/A** on `\nQ:\s*`; for each segment, the Q is the text before the
  first `\nA:` and the A is everything after until the next `Q:` or `Status:`.

## Classifying each dossier (the report's four sections)
1. **Corrections (dossier wrong vs source).** Strong signal only — match the
   answer against: `dossier says | dossier claims | dossier is wrong |
   contrary to the dossier | against the dossier | mis-cited | corrects dossier
   | contradicting dossier`. WEAK phrases that cause false positives: "the
   cited chapters show", "the dossier's Uncertainty section states 'None.'",
   routine "no open questions". Filter out "None." passthrough dossiers (those
   whose `## Uncertainty` is literally `None.`). A good correction example:
   `monster_orc_scout.md` asserts "Dead" but ch20 says it escaped → alive.
2. **Internal source contradictions.** Match: `contradiction | inconsistent |
   two different | two distinct | two separate | genuine internal |
   disentangl | conflates | not a contradiction`. These are cases where the
   WORLD text conflicts with itself (different entities, mis-mapped chapters)
   and the subagent resolved by preponderance. e.g. `location_tower.md`
   conflates Tower of Storms (ch8) with Icespire Hold (ch36).
3. **Unresolvable questions.** Status `Unresolved`, or an answer containing
   `unresolved | no evidence | material outside | appear nowhere | doesn't
   contain | not in the cited chapters`. List a representative sample (first
   ~60) and point to per-dossier footers for the rest.
4. **Mis-cited / out-of-corpus.** `mis-cited | outside the phandalin corpus |
   material outside | appear nowhere in any | (as provided) has no | no chNN
   passage | references derive from material outside`. e.g. `npc_ilvara.md`
   (Ilvara/Serith appear in zero chapter files) → genuinely outside corpus.

Also emit §5: dossiers whose status line was malformed (the Unknown bucket) —
they were still answered; flag for manual status read from the footer.

## Report shape
- Title + one-line description + link to the per-dossier answers dir.
- `## Overall resolution status` table (Resolved / Partially / Unresolved /
  Unknown / Total).
- §1–§4 as above, each with a short preamble and per-dossier bullets
  (`**Entity** — \`file\` [type]`, status, the `Q:`/`A (corrected):` lines or
  the contradiction snippet with `chN` citations).
- Appendix: full per-dossier status index table (all dossiers) for audit.

## Citations inside answers
Answers embed `chN` (e.g. "ch43", "ch19, ch20"). To cite a resolved answer,
extract with `re.findall(r"ch(\d+)", answer)` and render
`(ch19, ch20)`. Normalize duplicates and sort numerically.

## Deliverable
Write to `<OUT>/errata.md`. Keep the four-section structure so the next
session can re-run the extractor against new batch files.
