# Resolving `## Uncertainty` blocks (open lore questions)

Problem: every merged_dossier ends in one or more `## Uncertainty`
sections of open questions about contradictory / unspecified facts in the
campaign record. The user wants each question answered with an opinion
grounded in the authoritative `docs/chapters/` narrative-wing files.

## Deliverable model: READ-ONLY sidecars (not dossier edits)
The user's hard constraint (stated explicitly this session): **never modify
the source dossiers.** Answers live in a `<entity>.answers.json` sidecar next
to each dossier. The dossier stays byte-identical; the sidecar is the store;
a separate `*.resolved.md` is an optional human-readable render.

## Working pattern (proven this session)
1. **Parse each dossier into its constituent merged blocks.** A file can
   stack multiple blocks (monster + faction + npc) for the SAME entity. Each
   block has YAML frontmatter (`name:` / `type:` / `n_facts:` / `chapters:`),
   optionally preceded by `<!-- source: X.md -->`, and its own `## Uncertainty`
   list of `- ` bullets.
2. **For each question, retrieve grounding evidence** from `docs/chapters/`,
   scoped to the block's `chapters:` range — and, if the question itself
   cites an explicit `(chNN)`, narrow to those chapters.
3. **Form an opinion** per question (LLM call OR authored by a human/agent)
   and store `question → evidence → opinion` in the sidecar. Re-render the
   `*.resolved.md` from the sidecar at any time.

## Canonical scripts (stdlib-only, drop-in)
- `/home/kostadis/src/campaigns/out-of-the-abyss/docs/ensemble/resolve_uncertainty.py`
  — per-dossier agent. Reads the dossier, writes the sidecar, renders the md.
  - LLM backend: `--base-url <openai-compat>/v1 --model <name>` (OpenAI,
    OpenRouter, Ollama, LM Studio, vLLM). Calls the model per question with a
    "cite chapter evidence, never invent" prompt. Reads creds from
    `OPENAI_BASE_URL`/`BASE_URL`, `OPENAI_API_KEY`/`API_KEY`, `MODEL` env.
  - No backend (this env had none — no keys, no Ollama): just run it; it
    creates the sidecar scaffold (evidence retrieved, `opinion: null`) without
    an LLM. A human or the live agent then fills `opinion` and re-renders.
  - Idempotent + safe: re-running NEVER clobbers a filled sidecar. `--render`
    only reads the existing sidecar. **Do not add a `--render` flag that
    rebuilds the scaffold** — that destroys injected opinions (this bug cost a
    re-run this session).
- `/home/kostadis/src/campaigns/out-of-the-abyss/docs/ensemble/orchestrate_batch.py`
  — batch runner over all 300 dossiers. Phases: `--scaffold` (build sidecars,
  local/fast), `--fill` (LLM-fill opinions, concurrent via ThreadPoolExecutor,
  resumable), `--none-pass` (see pitfall #1). Backend configured at top of the
  file or via `BACKEND_URL` / `BACKEND_MODEL` / `BACKEND_KEY` env. `--workers N`
  controls concurrency; `--limit N` is a smoke-test switch.

## PITFALLS (cost real time this session — do not relearn)
1. **`## Uncertainty: None.` dossiers produce NO sidecar.** A dossier whose
   only uncertainty content is the literal line `## Uncertainty\nNone.` has
   zero `- ` bullets, so the block parser (which requires ≥1 bullet) skips it.
   Result: 272 of 300 dossiers get sidecars; 28 are silently skipped. Fix: a
   `--none-pass` phase that emits a sidecar marked `resolved_with:
   "no-open-uncertainties"` for exactly those 28. Verify the count matches the
   sidecar-less dossiers before assuming "all 300 done".
2. **`---` fence collision when splitting blocks.** The dossier's own
   frontmatter uses `---` fences, so a naive `split("---")` also shreds the
   frontmatter and yields blocks with EMPTY name/type/chapters. Fix: split on
   `^---\s*$` lines, but reconstruct a block only when a segment STARTS with
   `name:`. Treat `<!-- source: … -->` segments as setting the pending-source
   marker for the next block, and flush on the next `name:` (or EOF).
3. **Retrieval must be scoped, or it dumps the whole bible.** Naive keyword
   matching (generic tokens like "name", "whether", "still", "active") hits
   ~all 61 chapter files. Fix: STRONG keywords = entity NAME + Capitalized
   proper nouns only; AND bound the file set to the block's `chapters:` range
   + any explicit `(chNN)` refs in the question. Rank matched lines by
   keyword-hit count; cap snippet chars (~2.4k).
4. **Pipeline dossiers can contain their OWN errors — cross-check, don't
   trust.** Example: the Zuggtmoy npc block claims Sarith/Zalthir/Phylo
   "revere" Zuggtmoy as infected, but ch50 has Zalthir explicitly state Daz is
   "already infected" and he does NOT want to be. The synthesized dossier was
   WRONG about Zalthir. When an opinion contradicts a dossier claim, FLAG the
   dossier error (and offer to fix the source), don't echo the dossier.
5. **Multi-block files share the file name but differ by type.** Opinion keys
   are `<block_index>.<question_index>` (0-based), not question text, so
   answers survive re-ordering. First block's uncertainty list = index 0.
6. **Evidence is "authoritative" only from chapters/summaries, never the
   dossier itself.** The dossier is the artifact under review, not the source.
7. **vLLM/Qwen3-Next served at an IP returns valid completions; respect the
   OpenAI-compatible `/v1/chat/completions` contract.** Local servers often
   ignore the API key (pass "EMPTY"). Add retry+backoff (3 tries, doubled
   sleep capped at 8s) and a ~90s per-question timeout — a single dead call
   otherwise blanks an opinion with no error surfaced.
8. **stdout is block-buffered when piped** — a long batch's progress preview
   freezes at the first flush. Track real progress with a disk count
   (`glob answered sidecars, count fully-filled`), not the log tail.

## Verification (ad-hoc, not a suite)
After editing parse/retrieve/render/orchestrate, run a throwaway script in
/tmp (`hermes-verify-*.py` prefix, cleaned up after) asserting: block count,
block types, total question count, frontmatter survives parsing, retrieval
returns expected evidence AND is scoped to the chapter range, sidecar path is
`<name>.answers.json` next to the dossier, render-with-answers → N opinions / 0
PENDING, and **the source dossier's hash is byte-identical before/after** (the
read-only guarantee). Also assert `--none-pass` matches exactly the 28
sidecar-less dossiers and none of them have real bullet questions. The
Zuggtmoy run: 3 blocks / 15 questions / 15 opinions / 0 PENDING / dossier
unchanged across two re-runs.
