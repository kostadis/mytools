---
name: campaign-dev palace + Spark mempalace work
description: Parallelism rollout complete + verified at scale. Mining = 1.0× (GPU saturated). LLM refinement = 4.18× (synthetic). closet_llm = 5.86× (real corpus, 16 sources, 5m09s → 52s). campaign-dev re-mined from scratch — 90,435 drawers / 906 sources across 3 wings.
type: project
originSessionId: 9241685e-607b-4534-84cc-a4f591ae63f2
---
**State as of 2026-05-10 (cumulative):** parallelism shipped, embedding verified (no speedup, GPU-saturated), LLM refinement verified (4.18× speedup against vLLM chat). Production config updated.

## Spark setup reference

Authoritative: `~/src/dgx/current-setup.md`. Quick summary:

| port | service | model | notes |
|---:|---|---|---|
| 11434 | Ollama (systemd) | qwen2.5:14b, nomic-embed-text | **fallback only**, not production |
| 8000 | vllm-embed (docker) | nomic-ai/nomic-embed-text-v1.5 | embeddings — 5% GPU cap |
| 8001 | vllm-chat (docker) | Qwen/Qwen2.5-14B-Instruct-AWQ | chat — 50% GPU cap, 32K context |

Ollama has `OLLAMA_NUM_PARALLEL=8` set but only honors it for `/api/chat` and `/api/generate`; `/api/embed` serializes regardless on 0.23.2.

## Embedding (PR #6, commit `79c09fe`) — shipped

- `OllamaEmbeddingFunction` + `OpenAICompatEmbeddingFunction` + provider router.
- Config: `embedding_provider` / `embedding_model` / `embedding_endpoint` (+ `MEMPALACE_EMBEDDING_*` env).

## LLM config-mirror (PR #7) — shipped

`MEMPALACE_LLM_PROVIDER` / `_MODEL` / `_ENDPOINT` / `_API_KEY` env + config-file keys. Defaults: ollama / gemma4:e4b / None / None.

## Parallel miner (PR #9) — shipped + verified (no speedup)

- `mempalace/parallel.py` (NEW): `ParallelPipeline` producer/consumer harness.
- `mempalace/miner.py`: `process_file` split into `_prepare_file` / `_embed_prepared` / `_write_prepared`. `_mine_impl` runs the pipeline.
- `--workers N` CLI flag. Default from `MempalaceConfig().workers` = **1 onnx / 8 remote**.
- HNSW single-writer invariant pinned by `test_parallel_mine_consumer_runs_in_single_thread`.

**Spark verification (CG corpus, 183 files / 3550 drawers):**
- ✅ Correctness: 5/5 top-search sources match between workers=1 and workers=8 palaces.
- ✅ Idempotency: 3s re-mine, 0 new drawers.
- ❌ Wallclock: 79s → 83s (no improvement).

**Why no speedup:** total tokens ≈ 700K, serial HTTP wait ≈ 55s → ~12.7K tok/s, right at the 11.4K tok/s ceiling. **One vLLM client already saturates the Spark GPU on nomic-embed-text-v1.5.** Parallelism is correct but doesn't move wallclock on this workload. To push throughput: bigger model, multi-replica vLLM, or different model architecture.

## Parallel LLM refinement (PR #10) — shipped + VERIFIED ✅

- `mempalace/llm_refine.py`: `refine_entities` batch loop on `ParallelPipeline`. `workers` parameter.
- `mempalace/closet_llm.py`: `regenerate_closets` source loop on `ParallelPipeline`. Single-thread consumer for closet upserts.
- `mempalace/llm_client.py`: `urllib3.PoolManager` keep-alive behind `MEMPALACE_HTTP_KEEPALIVE` shim.

**Spark verification (vLLM chat on port 8001, Qwen2.5-14B-Instruct-AWQ, 200 candidates / 8 batches):**

| workers | wallclock | batches | errors | reclassified |
|---:|---:|:-:|:-:|---:|
| 1 | 530.85s | 8/8 | 0 | 130 |
| 8 | 127.12s | 8/8 | 0 | 132 |

**4.18× speedup** — hits the design's `≥ 4×` pass gate. Not 8× because vLLM's continuous batching has diminishing returns at 8-way concurrency (each parallel call ~2× slower than serial, but aggregate ~4× higher throughput). Expected curve, not a bug.

**Important: the initial bench against Ollama port 11434 was a red herring.** Ollama serializes chat by default and gave 1.22× — but the production LLM endpoint per `~/src/dgx/current-setup.md` is vLLM at port 8001, not Ollama. The vLLM measurement is the canonical one.

## Production config (`~/.mempalace/config.json`)

Updated 2026-05-10 to point LLM at vLLM chat. Now ALL mempalace commands honoring config-driven LLM defaults will hit vLLM on the Spark, not localhost Ollama, without per-invocation flags:

```json
{
  "embedding_provider": "openai-compat",
  "embedding_model": "nomic-ai/nomic-embed-text-v1.5",
  "embedding_endpoint": "http://192.168.1.147:8000",
  "llm_provider": "openai-compat",
  "llm_model": "Qwen/Qwen2.5-14B-Instruct-AWQ",
  "llm_endpoint": "http://192.168.1.147:8001"
}
```

`workers` is unset → resolves to 8 (the asymmetric default for `openai-compat`). Backup at `~/.mempalace/config.json.bak`.

## Parallel convo_miner (PR #11, commit `a2151df`) — shipped

Mirrors PR #9's miner refactor: `_file_chunks_locked` split into `_prepare_convo` / `_embed_prepared_convo` / `_write_prepared_convo`. `mine_convos` runs the same `ParallelPipeline`. The existing `--workers` flag on `mempalace mine` now applies to both `--mode projects` and `--mode convos`. Producer-side outcome tags (`None` = skip / `"register"` = sentinel / `"drawers"` = full upsert) preserve the existing `_register_file` behavior for 0-chunk transcripts via the consumer thread.

No new wallclock bench — same embedding endpoint, same architecture as PR #9, same single-client-saturation ceiling expected.

## closet_llm pagination fix (PR #12, commit `2dd4729`) — shipped

`regenerate_closets` called `drawers_col.get(limit=total)` which binds one SQL parameter per drawer id. SQLite's `SQLITE_MAX_VARIABLE_NUMBER` is 32766, so any palace with > ~32K drawers errored on:
```
chromadb.errors.InternalError: too many SQL variables
```
Bug pre-dates the parallelism work; only surfaced today against the 90K-drawer campaign-dev palace. Fix: paginate with `limit=10000, offset=N`. No behavior change for small palaces.

## campaign-dev re-mine (2026-05-10, after PR #11)

Deleted the prior 741 MB palace and re-mined from scratch with `workers=8` against vLLM-embed:

| tree | files | drawers | wallclock |
|---|---:|---:|---:|
| CampaignGenerator | 178 | 3,551 | 1m 12s |
| mytools | 450 | 17,532 | 7m 34s |
| mempalace (this repo) | 278 | 69,352 | 15m 47s |
| **total** | **906** | **90,435** | **~24m 33s** |

Same wallclock band as the workers=1 baseline from PR #9 — confirms the GPU-saturation finding holds at scale. Embedding is throughput-bound; parallelism gives correct results, not faster results, on this workload.

The mempalace repo's drawer count (69K from 278 files) is high because of `tests/benchmarks/` fixtures and structured JSON data; one file (`enrichment.json` in mytools) alone produced 8,324 drawers.

## closet_llm pre-existing 60s timeout bug (PR #13, commit `7a38e5a`) — shipped

`closet_llm._call_llm` hard-coded `HTTP_TIMEOUT_S = 60`. Surfaced during a workers=16 full-palace run that recorded 78% failure rate (541 of 691 processed): a single 56K-char file at slot [3] (`planning.py`) monopolised vLLM's prefill budget for ~90s, and every other in-flight request blew the 60s client-side timeout and got recorded as "LLM failed" even though vLLM would have answered correctly given another minute. The 60s ceiling, not vLLM behaviour, was the bottleneck. Fix: bump default to 600s, allow env override via `MEMPALACE_LLM_HTTP_TIMEOUT_S`.

## closet_llm scaled verification (16 sources of campaign-dev)

The real-world Phase 3 demonstration — heterogeneous file sizes (790 chars to 56K chars), real LLM calls to vLLM chat:

| workers | wallclock | succeeded | failed | tokens (in/out) |
|---:|---:|:-:|:-:|---|
| 1 | 5m 09s | 15/16 | 1 | 52,945 / 2,853 |
| 8 | 0m 52s | 15/16 | 1 | 52,945 / 2,548 |

**5.86× speedup** — beats the 4.18× from PR #10's synthetic bench because heterogeneous prompt sizes give vLLM's continuous batching better utilization (small responses don't block large ones, gaps fill naturally).

`planning.py` (56K chars) fails consistently in both runs — qwen2.5-14B-AWQ's 32K context limit. Pre-existing closet_llm scaling issue for huge files; not a parallelism bug. Same files succeed/fail in both runs; token counts identical; topic counts vary per file due to qwen non-determinism at temperature 0.1 (same characteristic as PR #10 bench, e.g. 130 vs 132 reclassifications).

## closet_llm full-palace regen (post-PR #13)

After fixing the 60s timeout, ran the full palace at workers=8:

| metric | value |
|---|---:|
| sources processed | 906 / 906 |
| ✓ successful | 863 (95.3%) |
| ✗ failed (real context overflow) | 43 (4.7%) |
| input tokens | 2,369,598 |
| output tokens | 153,184 |
| wallclock | 87m 33s |

**The fix delivered exactly the predicted result.** 78% (workers=16 + 60s timeout) → 4.7% (workers=8 + 600s timeout). The remaining 4.7% are real content-side overflows (files like `planning.py`, `mcp_server.py`, `narrative.py` whose joined drawer content > qwen's 32K context).

Live monitoring via the Monitor tool's 90s tick proved invaluable — we'd already wasted ~30 min on the broken workers=16 run before the cascade was visible. Going forward, **always wrap large LLM batch jobs in a Monitor that tracks rolling failure rate** so a cascade can be killed within 2 ticks (~3 min) instead of running to completion.

## Retrieval verification — the LLM closets do NOT improve search

This is the load-bearing empirical finding. After regenerating 1,302 LLM closets (96% of all closets in the palace), the same four test queries fail to surface their LLM-tagged target files:

| query | LLM-tagged target | rank in top-5 |
|---|---|:-:|
| `"truth of session"` | GMASSISTANT_PIPELINE.md | not present |
| `"authoritative source"` | GMASSISTANT_PIPELINE.md | not present |
| `"tiered retrieval pipeline"` | rpg_retriever.py | not present |
| `"black-box integration of external service"` | mempalace_client.py | not present |

**Diagnosis: the closet line format is the problem.** Current closet output is dense pipe-separated tag soup like `gmassistant-document|authoritative-source|truth-of-session|consistency-report|scene-plan|...`. This format:
- Embeds poorly — embedding models aren't trained on tag chains.
- Doesn't tokenize well for BM25 — `truth-of-session` is one token, not three.
- Loses to drawer-content cosine matches every time in the hybrid scorer.

**To actually get retrieval gain from LLM closets, the line format must change.** Natural-language sentences embed well and BM25-tokenize correctly:
```
Old: truth-of-session|authoritative-source|consistency-report|scene-plan
New: The GMASSISTANT pipeline output is the authoritative source and truth
     of the session, used for consistency-checking and scene planning.
```

This is a content-side fix in `closet_llm._parsed_to_closet_lines` (and possibly the LLM prompt asking for sentences instead of tag lists). Not a parallelism issue. Logged as deferred follow-up.

## Closet prose-format regen (PR #14, post-PR-#13 timeout fix)

**Done:** PR #14 changed PROMPT_TEMPLATE to request `index_sentences` (prose), changed `_parsed_to_closet_lines` to read them, added 7 tests, shipped on `kostadis-dev`. Full palace regen ran 129 min wallclock, 906/906 sources processed, 97% success / 2.8% real-failure (best run yet). 2,615 LLM closet rows generated. Token cost 2.63M in / 333K out (333K is 2× the previous tag-soup regen's 153K because prose is longer per row).

**The retrieval queries STILL fail in top-5** for the same reason as before — *but the architecture is correct*. Empirical proof: querying `"CampaignGenerator pipeline gmassistant structured recaps"` (matching the prose summary row qwen produced) surfaces GMASSISTANT_PIPELINE.md at rank 3. So prose rows DO compete in the hybrid scorer when they exist.

**The actual problem: qwen disobeyed the prompt.** Of 2,615 LLM rows, only ~51% are real prose (≥3 spaces in first column). ~20% are still hyphen-chains — qwen took the new instruction and pattern-matched on the prior format's shape, producing complete sentences with hyphens instead of spaces (e.g. `gmassistant-document-is-authoritative-source-of-truth`). The four validation queries happened to need rows that landed in the hyphen-chain bucket.

**This is a prompt-engineering problem, not an architecture problem.** Fix paths in order of cheapness: (1) iterate the prompt with few-shot examples against a fast Gemma — see `~/src/dgx/gemma-vs-qwen-ab.md` for the bench harness; (2) regenerate using a stronger model (Qwen2.5-32B exists on Spark per setup doc); (3) client-side reject hyphen-chain outputs in `_parsed_to_closet_lines`. **DO NOT do another Qwen-14B regen with a new prompt without testing the prompt on Gemma first** — each Qwen iteration is 129 min wasted.

Full report: `/tmp/closet-prose-result.md`.

## Open todo

- **Iterate closet_llm prompt** to push prose compliance above 90% before doing another production regen. Use Gemma (small, fast) for the prompt-iteration loop per `~/src/dgx/gemma-vs-qwen-ab.md`. Then re-run the production regen.
- (Alternative) Try Qwen2.5-32B as the closet generator — better instruction-following may produce more prose without prompt changes. ~3 hours per regen.
- Implement prefix-cache optimization per `~/src/dgx/closet-llm-prefix-cache.md` — small but free wallclock improvement.
- Retire `MEMPALACE_HTTP_KEEPALIVE` env shim by porting `test_embedding_openai.py` / `test_embedding_ollama.py` / `test_llm_client.py` to patch `urllib3.PoolManager.request`.
- Resolve issue #8 (6 pre-existing test failures).
- (Lower priority) Parallelize `dedup.py:184` and `repair.py:121`.

## Spec docs accumulated this session at ~/src/dgx/

- `tiered-llm-workflow.md` — operational framework for Opus / Qwen / Gemma
- `dnd-session-prep-with-opus.md` — concrete D&D use case using mempalace as retrieval
- `gemma-vs-qwen-ab.md` — A/B experiment for closet generator model choice
- `closet-llm-prefix-cache.md` — speed optimization
- `finetune-qwen-on-dnd-plan.md` — fine-tune Qwen on D&D summaries
- `spark-cli-design.md` — workstation CLI to manage all Spark vLLM containers
- `spin-up-vllm-gemma.sh` (script, not spec) — self-contained bash script for bringing up a vLLM container on a chosen port serving a chosen model

## SSH key auth: workstation → Spark (set up 2026-05-11)

Generated a passphraseless ed25519 keypair so the workstation can drive the Spark autonomously from auto mode:

- Private key: `~/.ssh/id_ed25519_spark` (mode 600)
- Public key: `~/.ssh/id_ed25519_spark.pub` (installed in `~/.ssh/authorized_keys` on the Spark)
- SSH config alias: `Host spark` → `kostadis@192.168.1.147`, identity-only auth

`ssh spark 'cmd'` is passwordless from the workstation. Use this for any future Spark management. The key is passphraseless because the workstation is a trusted LAN-only sandbox per `~/src/MACHINE.md`; if security posture changes, regenerate with `ssh-keygen -p -f ~/.ssh/id_ed25519_spark`.

## Spark vLLM containers (current state 2026-05-11)

| container | port | model | role |
|---|---:|---|---|
| `vllm-embed` | 8000 | nomic-ai/nomic-embed-text-v1.5 | embeddings (Tier 2) |
| `vllm-chat` | 8001 | Qwen/Qwen2.5-14B-Instruct-AWQ | quality LLM batch work (Tier 2) |
| **`vllm-gemma`** | **8002** | **Qwen/Qwen2.5-3B-Instruct** | **fast iteration (Tier 3 in framework terms)** |

**Important correction:** the container is named `vllm-gemma` for historical reasons but actually serves **Qwen2.5-3B**, not Gemma. Gemma is a gated HF repo and would require license acceptance + an HF access token. We swapped to the non-gated Qwen2.5-3B-Instruct as a fast alternative. The `~/src/dgx/spin-up-vllm-gemma.sh` script's `GEMMA_*` env vars are misnomers too.

Spec docs `~/src/dgx/gemma-vs-qwen-ab.md` and `~/src/dgx/tiered-llm-workflow.md` reference "Gemma" — the principle (fast model for iteration, bigger model for production) holds, but the concrete model swapped. Worth a global s/Gemma/Qwen-3B/ pass when next touched.

**To set up actual Gemma later:** accept license at https://huggingface.co/google/gemma-2-9b-it, create HF token at https://huggingface.co/settings/tokens, re-run the spin-up script with `HF_TOKEN=<tok>` and `GEMMA_MODEL=google/gemma-2-9b-it`.

**Verified performance:** ~32 token reply in 1.1s wallclock for a short prompt. Compared to Qwen2.5-14B's ~3-5s for similar prompts, this is ~3-4× faster — exactly the speed band needed for fast prompt-iteration cycles.

## SURPRISE: Qwen2.5-3B has BETTER prose compliance than Qwen2.5-14B (2026-05-11)

Same prompt, same task (closet_llm regen), 16-source bench:

| model | prose | hyphen-chain | other (quotes/short) |
|---|---:|---:|---:|
| Qwen2.5-**14B** @ workers=8 (production) | 51% | 20% | 29% |
| Qwen2.5-**3B** @ workers=16 (iteration tier) | **78%** | 20% | 2% |

Counterintuitive but explainable: the 3B has less capacity to "style" its output and sticks closer to plain English sentences — exactly what the prompt asked for. The 14B drifts into hyphen-glued summary patterns (its technical-writing stylistic prior) and emits more `[Speaker]` quote-formatted rows (29% vs 2%). On `planning.py` (56K chars), the 3B at 32K context **succeeded** — first time in this whole session that file got a non-failure outcome.

**Implication:** Qwen2.5-3B may be the better closet generator for this task — not just faster, but more prompt-compliant. Worth a full-palace regen + 4-validation-query test once prompt iteration pushes compliance to ≥90%.

## Bench harness (operational from this workstation 2026-05-11)

```bash
time MEMPALACE_WORKERS=16 /home/kroussos/src/mempalace-rlm/venv/bin/python \
  -m mempalace.closet_llm \
  --palace /home/kroussos/.mempalace/palaces/campaign-dev \
  --endpoint http://192.168.1.147:8002/v1 \
  --model Qwen/Qwen2.5-3B-Instruct \
  --sample 16
```

**~64s per cycle** at workers=16 with 32K context. 14/16 success rate typical (the 2 failures are usually JSON-parse hiccups, not context overflow). This is the fast-iteration loop the whole session has been building toward — finally operational.

Compliance measurement heuristic on closet rows: first-column ≥3 spaces = prose, ≥2 hyphens + ≤1 space = hyphen-chain, else other (quotes/short).

## Prompt-iteration session — closed 2026-05-11 (3B ceiling reached)

Goal was to push prose compliance ≥90% via prompt engineering against Qwen2.5-3B. Closed at iter 08 because the data showed the 3B is at its capacity ceiling for this task. Snapshots at `/tmp/prompt-iter/iter0*-prompt.txt`.

**3B output is non-deterministic and the metric variance straddles the threshold.** Same iter 06 prompt, same 16 files, three runs: 96%, 81%, 81% prose. Median ~86%. The "iter 06 hit 90%" result we celebrated was a single lucky sample. Diversity (distinct content tokens per file) varied 14-21; rows-per-file was stable at 3 regardless of asking for 10.

**Iter 07 (multi-framing prompt with worked example) regressed**: 82% prose, 13 diversity. The 3B parroted the example sentences verbatim because the example happened to be about `rpg_retriever.py`, which is in the bench set. **Rule: never include a worked example for a file that's in the bench corpus.**

**Iter 08 (abstract framing labels, no worked example, ask for 5 entries) collapsed**: 48% prose, 9 diversity, 2 rows/file. Stripping concrete examples and using abstract MECHANICAL/CONCEPTUAL/ROLE labels made the 3B fall back to single hyphen-glued tags. **Rule: 3B needs concrete imitation scaffolding; it cannot reason about abstract framing categories.**

**Conclusion: iter 06 (prose-format, 10 entries, anti-pattern examples, no per-file worked example) is the local maximum for Qwen2.5-3B on this task.** Further prompt tuning won't crack the noise floor. To get vocabulary-diverse multi-framing closets, the experiment to run is Qwen2.5-7B or 14B with a fresh prompt-tuning loop. Note that 14B at iter-04 produced 51% prose vs 3B's 78% — bigger model is not automatically better at instruction-following on this task; it would need its own tuning loop.

The iter 06 prompt and the list-shape parser tolerance were committed in `a9228ec feat(closet_llm): iter-06 prose prompt + list-shape parser tolerance`.

## Retrieval architecture win — closet_seed in search_within

Independent of closet content quality, the `search_within` hybrid scorer had a structural bug: closet hits could only *boost* drawers already in the top-(n*3) drawer-vector cut. If the closet ranked a file high but none of its drawers made the initial broad-net cut, the closet's vote was wasted and the file silently disappeared.

Fix (committed `781dc24 feat(searcher): seed drawer candidates from high-ranked closet matches`): for closet hits at rank < 5 with distance < 1.5 whose source has no drawer in the candidate pool, query the drawer collection scoped to that `source_file` and add up to 2 drawers. The same rank-based boost applies, so seeded entries compete on effective distance.

**Validated on the 4 original queries:**

| query | target | before fix | after fix |
|---|---|---|---|
| `"truth of session"` | GMASSISTANT_PIPELINE.md | not in top 10 | **rank 1** |
| `"authoritative source"` | GMASSISTANT_PIPELINE.md | not in top 10 | **rank 3** |
| `"tiered retrieval pipeline"` | rpg_retriever.py | not in top 10 | not in top 10 (RLM design docs surface — semantic match) |
| `"black-box integration of external service"` | mempalace_client.py | not in top 10 | not in top 10 (vocabulary gap) |

**The architecture fix and the closet-content quality are independent.** The fix pays off regardless of how the closets are generated; Q3/Q4 don't surface because the iter 06 closets simply don't contain the query's vocabulary (e.g., `rpg_retriever.py`'s closet says "defines retrieval modes for RPG resources" — never "tiered"). Bigger closets with multi-framing would close that gap; the fix is in place to consume them when they exist.

Additionally: `recursive_indexer.py` was clamping wing/room index documents to up to 100 closet lines, which overflowed nomic-embed-text-v1.5's hard 2048-token limit and silently produced zero-vectors. Committed `04232fc fix(recursive_indexer): cap index doc length to fit nomic 2048-token limit` — caps doc body at 3000 chars (env-override `MEMPALACE_INDEX_DOC_MAX_CHARS`).

## Vocabulary-gap fix: closet_taxonomy module (2026-05-11, commit `3378e86`)

The remaining 2/4 validation queries (`"tiered retrieval pipeline"` → rpg_retriever.py, `"black-box integration of external service"` → mempalace_client.py) missed because the iter 06 prose closets used content-grounded vocabulary that didn't overlap the abstract query phrasings. Both 3B and 14B picked the same vocabulary because the prompt asks for content-grounded sentences — bigger model didn't help (5-min experiment in this session showed 14B was worse: 50% success rate, 71% prose, same vocabulary register as 3B).

**Solution: classify each file into a FIXED TAXONOMY of abstract terms instead of generating from scratch.** The LLM doesn't have to invent vocabulary — it picks 2-4 labels per category from closed lists. Even 3B is reliable at small classification tasks where it can't do multi-framing prose generation (iter 07/08 lesson).

Shipped as `mempalace/closet_taxonomy.py` + 11 unit tests. Key design:

- **Closed vocabulary** in `TAXONOMY` dict (structural_role / function / abstraction lists). Adding to it when queries systematically miss their target is the curation path.
- **Specificity rule in the classifier prompt** pushes the model to pick `external_service`/`black_box`/`tiered_pipeline` over generic labels like `backend` when both apply. The v1 prompt without this rule picked `backend` for mempalace_client.py; v2 with the rule picked `wrapper`+`black_box`+`external_service`+`boundary`.
- **Worked example in the prompt** is for an imaginary "wraps an external service via subprocess" file, NOT a file in the bench corpus (iter 07 parroting lesson — never include an example for a file that's being processed).
- **4 natural-language sentences per file** using labels in human-readable phrasing ("X is a wrapper that operates as external service and boundary") not stiff list-style. Underscores humanized so `tiered_pipeline` matches "tiered pipeline" queries.
- **Additive to prose closets.** Taxonomy rows live alongside `closet_llm` rows; both contribute through the existing closet boost in `search_within`. Re-running replaces taxonomy rows (deterministic IDs via SHA hash of full source_file path).

**Validated end-to-end:**

| query | target | before module | after module |
|---|---|---|---|
| "tiered retrieval pipeline" | rpg_retriever.py | not in top 10 | **rank 3** |
| "black-box integration of external service" | mempalace_client.py | not in top 10 | **rank 1** |

Both wins are directly attributable to taxonomy rows containing vocabulary the prose closets did not (`tiered pipeline`, `black box`, `external service`, `boundary`).

**Notable Q1/Q2 outcome:** The classifier picked `design_doc`/`controller`/`backend` for GMASSISTANT_PIPELINE.md, NOT `source_of_truth`/`authoritative`. That's the right call — the doc *describes* the gmassistant pipeline, the implementation code *is* the source of truth. The user's original Q1/Q2 targets were arguably wrong.

**Cost:** ~10s for 4 files at workers=1; full-palace estimate ~15 min at workers=8 (~900 sources). An order of magnitude cheaper than a full prose-closet regen (87 min).

**Run on full palace via:** `python -m mempalace.closet_taxonomy --palace ~/.mempalace/palaces/campaign-dev --workers 8` against the 3B vLLM at port 8002. Not yet executed on the full campaign-dev palace — the validation result on the 4 targets is what's been measured.

## Bottleneck stack — current

- ✅ **Embedding**: parallel-capable, GPU-bound at single client on nomic-embed-text-v1.5. Confirmed at scale (24m to mine 906 files at workers=8, same band as workers=1 baseline). To push throughput: bigger model, multi-replica vLLM, different model architecture.
- ✅ **LLM refinement**: parallel-capable, **5.86× verified at scale** against vLLM chat (real corpus). Synthetic bench was 4.18×; heterogeneous prompts get better continuous-batching utilization.
- ✅ **closet_llm**: same code path as LLM refinement, same speedup.
- ✅ **convo_miner**: parallel-capable (PR #11). Same architecture as miner; embedding-saturation ceiling applies.
- 🟢 **dedup, repair**: still serial. Read-heavy chromadb queries; thread-pool friendly but lower priority.
- 🟢 **Cleanup**: `MEMPALACE_HTTP_KEEPALIVE` env shim retains the urlopen path for tests. Should be retired once all tests are ported to PoolManager-patching.

## Known content-side issue

`closet_llm` fails on source files whose total joined content exceeds qwen2.5-14B-AWQ's 32K context window (e.g., 56K-char `planning.py`). Pre-existing behavior, not a parallelism bug. To address: chunk the source content before sending, or pick a smaller model for huge files, or route long sources through a different prompt strategy.

## Pre-existing test failures (issue #8)

6 failures pre-date all this work: 4 in `test_corpus_origin_integration.py` (Namespace fixture missing `no_mempalaceignore`), 1 in `test_hnsw_capacity.py`, 1 in `test_save_hook_mines.py`.

## Open todo

- Retire `MEMPALACE_HTTP_KEEPALIVE` env shim by porting `test_embedding_openai.py` / `test_embedding_ollama.py` / `test_llm_client.py` to patch `urllib3.PoolManager.request` instead of `urlopen`.
- Resolve issue #8 (6 pre-existing test failures).
- (Optional, lower priority) Parallelize `dedup.py:184` and `repair.py:121` read-heavy chromadb query loops via `ParallelPipeline` with a multi-reader consumer.
