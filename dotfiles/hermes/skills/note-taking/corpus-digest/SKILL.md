---
name: corpus-digest
description: Synthesize a folder of sources into a cited digest.
---

# Corpus Digest — turn a folder of sources into a cited, structured digest

Use when the user asks to read many files in a directory and synthesize them into a
single digest/summary at a specified path, especially with: explicit sections (events,
NPCs, locations, factions, timeline), a citation convention, a factual/neutral tone,
and/or a word-count floor. Common instances: campaign-history wikis, "read all
chapters and make a digest," repo or research synthesis, meeting-note rollups.

## Trigger conditions
- "Read ALL the files in <dir> and produce a digest at <path>."
- Any request naming required sections, a citation convention, a factual/neutral tone,
  and/or a word-count target.
- Downstream "wiki source" generation where the digest feeds other agents.

## Workflow
1. **Inventory first (verify the count).** Before reading, run `search_files`
   (target=`files`, pattern=`*.md` or as appropriate) on the directory. Report the
   count back to the user so "read them all, skip none" is provable. This also gives
   you the exact file list to batch through.
2. **Read in batches.** `read_file` accepts multiple calls per turn (parallel). Read
   ~5 files per turn. Do NOT skip any. Keep the content in context — you will cite it.
3. **Mind numbering/naming mismatches.** Filenames often run one number ahead of each
   file's internal H1 (e.g. `chapter_02_*.md` is titled "Chapter 01 ..."). Document the
   mapping in the digest header and cite by filename (`chNN`) so citations are stable.
4. **Build the digest** with the user's required sections. Tag EVERY fact with its
   source filename (`chNN`). Tone = factual and neutral; no interpretation, no padding.
5. **Manage the word-count target iteratively (see Pitfall 2).** Write the file, then
   measure word count programmatically, and expand with *extra sourced sections* rather
   than filler until you meet the floor.
6. **Verify and report.** Confirm the file exists; report its **absolute path** and
   **word count**. The user explicitly asked for this — do not omit it.

## Large-corpus path (too big for context)
When the corpus is too large to read into context (e.g. 174 files / 7+ MB), do NOT
batch-read. Extract programmatically with `execute_code`:
1. Size check first: `du -cb <dir>/*.md | tail -1` + count. Above ~1–2 MB total, go
   programmatic.
2. Parse structured fields with regex (frontmatter `name:`/`n_facts:`/`chapters:`,
   `**Current Status:**` etc.). **Field labels vary in capitalization across files**
   (`**Current Status:**` vs `**Current status:**`) — always use `re.I` and verify no
   empty entries in output afterwards.
3. Extract tagged lines (e.g. `- [chNN] (EVENT) ...`) into chapter-keyed dicts. Dedupe
   exactly (normalized-text key) then fuzzily (token-set overlap >0.75 within chapter).
4. Rank/select per chapter (score by named-entity mentions + length), cap bullets per
   chapter, clip long lines at sentence boundaries.
5. Dump intermediates to JSON (`/tmp/*.json`) and keep a `_notes_*.md` beside the
   output so a resumed session can pick up without re-parsing.
6. Hit word targets by tuning caps (bullets/chapter, words/line) and re-measuring with
   `wc -w` — works for CEILINGS as well as floors; iterate rather than rewriting prose.
Working example script: `scripts/tagged_dossier_digest.py`.

**Lighter variant for dossier-style corpora (~1 MB, 100–200 small files):** instead of
full JSON pipelines, one `execute_code` pass can condense the corpus into a single
`/tmp/*_condensed.txt`: keep each dossier body (strip YAML frontmatter blocks with
`re.sub(r'---\nname:.*?---\n','',t,flags=re.S)`, drop `## Uncertainty` sections),
extract only `- [chNN] (EVENT) ...` lines, dedupe first per-file then GLOBALLY across
files (key = `re.sub(r'\W','',line.lower())[:100]` — these corpora repeat the same
event verbatim in many dossiers; global dedupe cut 275KB→245KB). Then read the
condensed file in 2–3 `read_file` pages and write the digest from it. Much faster than
ranking pipelines when the per-file bodies are already summaries.

## Pitfalls
- **Pitfall 1 — read_file "unchanged / dedup" cache misses.** When content is already
  in context, `read_file` can return `{"status":"unchanged","dedup":true}` or
  "File unchanged since last read" instead of the body. This is NOT a skip — the
  content is in context. But to be certain nothing was missed across a 40+ file batch:
  * Run `search_files` with `target=content`, `pattern=^# ` (or `^# Chapter`) over the
    directory to pull every file's H1 into one view.
  * Cross-check that each expected file's title appears in what you ingested. If any
    file's H1/content is absent, `read_file` that specific file (use offset/limit to
    page large files).
  * Only then proceed. Never assume a "dedup" response means you lack the content, and
  never re-read blindly dozens of times — verify once with the grep.
  (Full recipe in `references/bulk-read-dedup-recovery.md`.)
- **Pitfall 2 — word-count floors.** Users often specify a range (e.g. 6000–10000
  words). A first draft is frequently short (a 46-file digest landed at ~3900 words).
  Do not pad with vague prose. Add *sourced* sections that wiki agents value: a
  "Notable Combats / Set-Pieces" list, "Key Themes & Recurring Motifs," an "Items of
  Note" catalog, and a "Chapter Index" mapping each file to its principal
  NPCs/locations/factions. Each adds real density from facts already in context.
  Re-measure after each expansion. Verify with `execute_code`:
  `print(len(open(path).read().split()))`.
- **Pitfall 3 — fabrication.** With large corpora it is tempting to infer. Every
  bullet must trace to a read file. If a fact is ambiguous, cite the chapter it came
  from and state it neutrally; do not invent connections.
- **Pitfall 4 — oversized write_file stream timeouts.** A single `write_file` of the
  whole digest (~50KB) can stall the stream and the write is NOT executed. Compose the
  digest as ~8–10 small part files (`/tmp/digest_pNN.md`, each under ~5KB / well under
  8K tokens per tool call), then `cat /tmp/digest_p*.md > <output>` in terminal and
  verify with `wc -w -c`. Write parts in order so numbering sorts correctly
  (`p01..p09` + `p10`, or zero-pad consistently).
- **Pitfall 5 — hermes_tools scripts are pure Python.** `execute_code` bodies are
  Python source; a stray non-Python token (even a comment-style `/**/`) is a
  SyntaxError. Keep scripts plain Python.

## Support files
- `references/bulk-read-dedup-recovery.md` — exact tool calls to detect/recover
  read_file cache misses across a large batch.
- `templates/digest_skeleton.md` — starter skeleton with the standard four sections
  plus optional extras and the citation convention.

## Verification checklist (end of task)
- [ ] Directory inventory count confirmed before reading.
- [ ] All files read (grep H1 cross-check passed).
- [ ] Every fact tagged with source filename.
- [ ] All user-required sections present.
- [ ] Word count within target (if specified).
- [ ] File exists; absolute path + word count reported to user.
