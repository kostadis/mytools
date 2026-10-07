---
name: corpus-extraction-pipeline
description: Bulk-extract per document with one subagent, then merge.
---

# Corpus Extraction Pipeline (per-document subagent fan-out)

## When to use
- "Go through every chapter/file and produce a per-X summary"
- "Extract <structured thing> from each of these N documents"
- Any task where N documents (N>~5) each get identical processing and the results must combine into one ordered artifact.

## Core principle: ONE subagent per document
**Do NOT batch multiple documents into one subagent** (e.g. "1 agent per 3 chapters"). The user explicitly corrected this: *"start 1 sub-agent per chapter, then orchestrate the sub-agents."* One agent per document maximizes per-file fidelity and yields a clean, isolated output to merge. The parent is the orchestrator.

## Steps
1. **Granularity = 1 leaf per document.** Each leaf gets: the document path, the rubric/filter, the exact output schema, and a private output path.
2. **Stage to per-agent directories, never a shared one.** e.g. `parts/ch01/`, `parts/ch02/`. Prevents two agents overwriting the same file or interleaving appends. Each agent writes under its own dir.
3. **Orchestrate in waves of 3.** `max_concurrent_children = 3` here. Dispatch 3, wait for the consolidated `ASYNC DELEGATION BATCH COMPLETE` message, verify the output dirs, dispatch the next wave. Loop until all documents are covered. The parent does no heavy lifting — just pumps waves.
4. **Merge centrally with deterministic ordering.** Concatenate per-doc outputs into final files, ordered by chapter number / filename / embedded sequence. Recompute any sort key (dates, indices) from the *raw preserved value*, not an agent-computed field.
5. **Verify and spot-check.** Count files, confirm every input produced output, print the first few merged lines. Re-dispatch any missing slice.

## Pitfalls (these bit in a real 47-doc run)
- **Subagents drift on conventions.** Different agents parse the same date/format differently and emit inconsistent sort keys. FIX: have agents preserve the *raw* value verbatim (e.g. `date_label: "01-02-Taraskh 1495"`) and let the merge step normalize centrally. Never trust agent-computed `sort_date` for final ordering.
- **Async completion can truncate before the write.** A subagent's summary may report success while its final `write_file` was cut off (the batch-complete message arrived mid-write, file left unwritten). FIX: after each wave, assert the output file exists and parses cleanly; if missing/invalid, re-dispatch that single document.
- **"Incomplete — files not written" is a real outcome.** Subagents can exhaust their iteration budget mid-task. Treat any such report as "slice failed" and re-run just that document.
- **Don't make agents append to a shared file** — race conditions / lost writes. Isolate, then merge.
- **Concurrency capped at 3 leaf children.** Plan wave counts (47 docs ≈ 16 waves of 3). Work runs in background; the parent just waits.
- **Carry-forward rules must be explicit in the prompt.** For sequential documents (chapters), tell each agent its assumed starting state (e.g. "begins where chN left off") so continuity survives the merge.

## Reference
- `references/date-format-pitfall.md` — concrete example of the raw-vs-normalized drift problem (campaign date stamps), reusable as a template for the "preserve raw, normalize at merge" rule.
