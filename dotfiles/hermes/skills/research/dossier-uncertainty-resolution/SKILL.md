---
name: dossier-uncertainty-resolution
description: Resolve dossier uncertainties against cited chapters.
---

# Dossier Uncertainty Resolution

Recurring workflow in the Phandalin campaign (and any ensemble-generated state
dossier pipeline): each dossier carries a `chapters:` citation field and a
`## Uncertainty` section listing open questions. The job is to read the cited
source chapters and resolve each bullet with textual evidence, then write one
markdown file per batch.

## Inputs and where they live (Phandalin campaign, current env)

- **Batch member list**: `/home/kostadis/phandalin-output/batches.json` — a JSON
  object keyed `batch_01` … `batch_11`, each value a list of dossier filenames
  (e.g. `monster_boar.md`). **PITFALL:** the user often says "read
  `batch_NN.md`" — there is no such input file. The member list is in
  `batches.json` under the `batch_NN` key. Read that.
- **Dossiers**: `/home/kostadis/src/campaigns/Phandalin/docs/ensemble/state_dossiers/<filename>.md`
- **Source chapters**: `/home/kostadis/src/campaigns/Phandalin/docs/chapters/chapter_<NN>_*.md`
  (NN is zero-padded; glob `chapter_05_*.md`).

> The campaign lives under `/home/kostadis/src/campaigns/Phandalin/`. If the
> dossiers/chapters have moved, re-find them with a glob under that tree before
> assuming paths.

## Steps

1. **Get the batch's dossier filenames** from `batches.json` (`batch_NN` key).
2. **Parse each dossier** for (a) the YAML `chapters:` field — ranges like
   `10-38` or single `5-5` — and (b) the `## Uncertainty` section. Expand ranges
   to a chapter-number list. **Also extract** the YAML `type:` field (npc/monster/
   location/object/faction) and the first `#`/`##` H1 heading (the entity name)
   so you can build the `## <dossier>.md: <Name> [type]` header — a separate
   bounded `execute_code` pass over the dossier files is the fastest way.
   **PITFALL — the `None.` sentinel:** some dossiers have an *existing*
   `## Uncertainty` section whose only content is the literal text `None.`
   (e.g. `npc_the_all_father.md`, `object_bone_whistle.md`). That is NOT an empty
   section and NOT a real bullet — treat it as *fully resolved* (one line:
   "No open uncertainties listed (Uncertainty section: 'None.')."), and do not
   emit Q/A pairs for it. A genuinely missing section is also "no uncertainties".
3. **Read the cited chapters — but DO NOT dump whole chapters.** They are large
   (10–60 KB each). Use the bounded keyword-extraction pass documented in
   `references/extraction_technique.md`: for each dossier, build entity-specific
   keyword lists and pull only the matching paragraphs (±1–2 context lines),
   truncating snippets to ~300–350 chars. This keeps `execute_code` stdout
   within bounds.
4. **Resolve each bullet**: cite the chapter number, quote the relevant evidence
   (short), then give a verdict — `Resolved`, `Partially resolved`, or
   `Unresolved`. For dossiers with no `## Uncertainty` content, output
   `Resolved (no uncertainties)`.
5. **Write the output** to `/home/kostadis/phandalin-output/batch_NN.md`:
   one `## <dossier>.md: <Name> [type]` section per dossier, Q/A pairs for each
   uncertainty, and a `Status:` line at the end of each section. See the format
   produced for `batch_04.md` for a concrete template.

## Pitfalls / corrections learned

- **NEVER use `search_files` / `hermes_tools.search_files` for corpus-wide search.** Their stdout is multi-line JSON that `json.loads` rejects with `JSONDecodeError: Extra data` once the result set is large (a whole-tree glob of `docs/chapters` triggers this reliably). Instead load the corpus in memory and search with `re`:
  ```python
  import os, re, glob
  chdir = "/home/kostadis/src/campaigns/Phandalin/docs/chapters/"
  chapters = {}
  for p in glob.glob(os.path.join(chdir,"chapter_*.md")):
      m = re.search(r"chapter_(\d+)_", p)
      if m: chapters[int(m.group(1))] = open(p).read()
  # then re.finditer over chapters[cn] with a context window
  ```
  This is also faster. Reserve `search_files` for tiny single-file lookups only.
- **Before declaring anything `Unresolved`, grep the ENTIRE corpus (all ch01–46), not just the dossier's cited range.** `Unresolved` is only correct when the exact entity/term returns ZERO matches across every chapter — that means the reference lives outside the Phandalin chapter corpus (e.g., another campaign's lore). Concrete example (batch_07): `npc_ilvara.md` and its "Serith" reference appear in zero chapter files → genuinely outside corpus → `Unresolved`. Do NOT mark `Unresolved` from a single-range miss; a silent cited range usually just means the answer sits in another chapter.
- **"Contradiction" bullets are frequently NOT contradictions.** Read both
  cited chapters before accepting the dossier's framing. Examples from batch_04:
  - balcony "six-foot foundation" (ch22) vs "10-foot balcony height" (ch44) —
    consistent (base vs upper-story height).
  - ch35 "sleeping" immediately self-corrects to "held" (chained); not a
    contradiction.
  - ch40 "anchorite removed in first exchange" vs ch43 "one Anchorite left
    casting" — *different* anchorites in *different* battles.
  Verify, then state the resolution.
- **Shared names across chapters are usually distinct individuals.** "boar",
  "anchorite", "blight", "bandit" recur in many chapters as separate creatures/
  encounters. Resolve by citing the specific chapter and explicitly stating they
  are different entities (e.g., Gorthok the dead storm-boar ch43 vs the living
  manse boars ch44 vs the mundane first-cave boar ch41).
- **A dossier's uncertainty bullet may itself rest on a false/misattributed
  premise** — verify the premise against the cited chapters before answering.
  From batch_09: `npc_the_speaker.md` asked about the Speaker "refusing the twig
  figures" based on a "past experience," but no such episode exists in ch38-45;
  the only twig figures there are the Talosian-made twig *blights* at the Woodland
  Manse, which the Speaker destroyed, not declined. Likewise `npc_xanthopoulos.md`
  references "Meryl," which is a confusion for **Meril** (the deceased druid who
  blessed Soma's staff). When a bullet's premise doesn't match the text, say so
  explicitly and resolve on what the text actually shows — don't manufacture an
  answer to fit the question.
- **End each batch file with a Summary Count block** so open-uncertainty load is
  tallyable across batches. From batch_09:
  `- Dossiers processed: 30` / `- Fully resolved (no open uncertainties): 5 — <list filenames>`
  / `- Partially resolved ...: 25 — <all remaining dossiers>` / `- Fully unresolved: 0`.
- **"Unresolved" is a valid verdict.** When the text genuinely doesn't say
  (e.g., a drone's later operational state, a captured creature's fate), say so
  rather than inferring. Only upgrade to Resolved when the cited chapter
  contains the answer.
- **Large `execute_code` stdout gets truncated** (head+tail, ~50 KB cap). Keep
  queries narrow: 3–8 keywords, `maxper` 6–12, snippet length bounded. Re-run
  with tighter keywords if a key passage is omitted.
- **Some dossiers have 25–30 members** (batch_04 had 30). Process in chunks;
  don't try to resolve all 30 in one giant script call.

## Assembly: from batch_NN.md to ONE file per dossier (Option A)

After the batch files exist, the user usually wants the answers delivered as
**one file per dossier** (NOT one combined dump). Two clarifications were
settled this session:

- **Per-dossier, not combined.** Write `answers/<dossier>.md`, one per source
  dossier, rather than merging everything into one file.
- **Option A = full-dossier + inline answers.** Each output file is the
  *entire original dossier* (YAML header + body + existing facts) kept
  byte-for-byte intact, with each `## Uncertainty` bullet answered **inline**
  (`- <question> -> Resolved [chN]: <answer>`) AND a `## Resolved Answers
  (from chapter analysis)` footer appended at the end carrying the complete
  Q/A (every question + chapter-cited answer) so nothing is lost. Dossiers with
  `None.` uncertainty are written byte-identical to the original.

Reason: subagents rephrase the question, so exact/substring bullet matching is
unreliable. The full Q/A footer guarantees completeness; inline annotations are
a bonus where they match.

### Orchestration pitfalls (fan-out)
- **`delegate_task` concurrency cap = 3.** Dispatching a `tasks` array with
  >3 entries FAILS outright. Send batches in **waves of 3**; wait for each wave
  (the async-complete message) before launching the next. This session ran 11
  batches (327 dossiers) as 4 waves: 3/3/3/2.
- **Subagent headings drop the `.md` extension.** They write
  `## faction_anchorites: Anchorites [faction]`, NOT `## faction_anchorites.md:`.
  The assembler's per-dossier heading regex MUST allow `(?:\.md)?`.
- **Last item in each batch has no trailing `##`.** `end = start + 2 +
  (nxt.start() if nxt else 0)` truncates the FINAL dossier of every batch to ~2
  chars → empty parse. Use `len(text) - start - 2` when no next heading exists.
  Always verify the last dossier of each batch got answers.
- **Don't pre-concatenate cited chapters into one evidence blob.** Ranges like
  `2-45` explode memory (327 dossiers → 58 MB). Pass the chapters dir and let
  subagents read chapter files directly.
- **`search_files` caps at 200 results max** and may under-report a directory's
  true size (this corpus had 327 dossiers but the tool surfaced only 200). Count
  via `glob` and parse programmatically; never eyeball the directory listing.

### Verifying the assembled output
- File count of `answers/` == dossier count (327 here).
- Every dossier with real questions contains the `## Resolved Answers` footer.
- A sample `None.`-uncertainty dossier is byte-identical to its original (proves
  originals were never touched — write only into the output dir).
- `INDEX.md` tallies inline-annotated vs footer-only vs no-answer dossiers so
  gaps are visible at a glance.

## Post-resolution deliverables (build from batch_NN.md)
After the per-dossier answers exist, two more artifacts are commonly wanted:

- **errata.md (QA report).** A single readable quality report isolating the
  dossiers the pipeline got *wrong* or that contradict the source — not just
  open questions. Build it by parsing the `batch_NN.md` files and classifying
  each dossier into: (1) corrections (dossier facts contradict chapters),
  (2) internal source contradictions, (3) unresolvable questions, (4)
  mis-cited/out-of-corpus references, (5) malformed status lines. Full recipe,
  the four-section shape, and the status-line parsing gotchas are in
  `references/errata_report.md`. **PITFALL reproduced here:** the `Status:` line
  is usually bare (`Status: Resolved`), NOT bracketed (`Status: [Resolved]`). A
  regex requiring `[...]` returns `?` for nearly every dossier — parse with
  `^Status:\s*(?:\[(.*?)\]\s*)?(.+)$` and normalize by substring. Block end
  must use the EOF branch (`len(text)-start-2`) or the LAST dossier per batch
  silently gets no answers.
- **Catch-all entity → per-instance dossiers.** When a generic entity (orc,
  boar, blight, bandit, anchorite…) is collapsed into one dossier but the
  chapters track several distinct individuals/groups, split it. Workflow,
  deliverable options (ledger vs new queryable dossiers vs both), schema, and
  the "create-only, never overwrite existing individualized dossiers" rule are
  in `references/entity_split.md`. **Three pitfalls reproduced here because they
  cost real time:** (1) sweep the whole corpus with ONE
  `grep -in -B1 -A1 '<term>' *.md | sed 's/^chapter_\([0-9]*\)_[^:]*/ch\1/'`
  then page the result — never read 46 chapters individually; (2) if a search
  returns zero hits for a term you expect, re-verify with shell `grep` before
  believing it — `search_files` `output_mode="count"` returned all-zeros on a
  corpus where `grep -ic` found 41 matching files; (3) write the new dossiers
  **2–3 per tool call**, never all 20 in one call, or the stream stalls
  mid-call and nothing lands.

## Output format (per dossier)

```
## monster_boar.md: Boar [monster]
Chapters cited: 41-44

Q: <verbatim uncertainty bullet>
A: <chapter cite> <quoted evidence> Resolution: <explanation>.

Status: Resolved | Partially resolved | Resolved (no uncertainties)
```

Use `Q:`/`A:` pairs and end each dossier block with a `Status:` line so a later
pass can tally how many uncertainties remain open across batches.

## Support files
- `references/assembly_and_orchestration.md` — the fan-out shape + assembler
  logic + parameterization for turning `batch_NN.md` into one answered file per
  dossier (Option A). Read it before writing/running the assembler.
- `scripts/assemble_answers.py` — **reusable, runnable assembler** for Option A.
  Reads `batches.json` + `batch_NN.md`, writes one full-dossier answer file per
  source dossier into `OUT_DIR/answers/` (inline `-> Resolved [chN]` annotations +
  complete `## Resolved Answers` footer). Paths overridable via env vars
  (DOSSIER_DIR / OUT_DIR / ANSWERS_DIR / BATCHES_JSON). Run: `python3 assemble_answers.py`.
  **Inline-completeness note:** subagents rephrase questions, so the fuzzy inline
  matcher lands ~80% (257/327 here); the appended footer always carries the full
  Q/A, so completeness is guaranteed regardless. Don't panic at a "no_match"
  count — check the footer presence instead.
- `references/extraction_technique.md` — the bounded keyword-extraction pass
  for reading large chapters without dumping them.
- `references/errata_report.md` — building the QA/errata report from the batch
  files (four sections + status-line parsing gotchas).
- `references/entity_split.md` — splitting a catch-all generic-entity dossier
  into per-instance dossiers grounded in the source chapters.

### Final placement / naming of NEW dossiers (learned this session)
The user's preferred end-state for new per-instance dossiers evolved through four
steps — encode all four so you don't re-ask:
1. **Create** in the campaign `state_dossiers/` (matching existing naming) so they
   are queryable alongside the others. Use `git status --short` to prove zero
   existing files were modified (all writes appear as untracked `??`).
2. **Copy** (not move) into the analysis output dir (`~/phandalin-output/answers/`)
   when the user wants the source tree left intact.
3. **Remove** the copies from `state_dossiers/` (plain `rm` — they were untracked,
   so no history impact) once confirmed present in `answers/`.
4. **Rename** to match the ensemble convention, THEN fix the word order if the
   user wants an entity word present. Concretely for orcs: created as
   `orc_chNN_*.md` → user wanted `monster_` prefix → renamed `monster_chNN_*` →
   user wanted "orc" in the name → renamed `monster_orc_chNN_*`. Keep the
   pre-existing same-entity dossiers (`monster_orc_scout.md`, etc.) untouched —
   they already satisfied the prefix and collide-free. Update the manifest's
   filename + path references at each rename step.
