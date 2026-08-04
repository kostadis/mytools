---
name: reference-two-spark-ensemble-perf
description: Splitting the 5-pass fact-extraction ensemble across both DGX Sparks (Qwen3-Next 80B on each) ~halves wall-clock — measured ~2.4x
metadata: 
  node_type: memory
  type: reference
  originSessionId: 374c07c8-3825-4bfe-9ecf-1596ac85bef3
---

Measured 2026-05-28 on `chapter_03_escape.md` (~10K chars, 5-pass ensemble), with `Qwen/Qwen3-Next-80B-A3B-Instruct-FP8` running on **both** Sparks (swapped onto spark2 for this test, replacing Nemotron — see [[reference-spark2-nemotron-extraction]] for why the reasoning model was unfit).

| run | wall-clock | merged facts |
|---|---|---|
| baseline — full ensemble on spark1 solo (passes sequential) | **563s** (9:23) | 170 |
| split — both Sparks concurrent | **238s** (3:58) | 210 |

**Speedup ~2.4×.** Per-pass split: spark1 = small 172s + interiority 58s = 230s; spark2 = large 97s + sweep 127s + temporal 14s = 238s (long pole). Load balance was near-perfect (<4% imbalance) using a naive "3 chunk-calls per box" split. >2× partly because the split also produced more facts (226 raw vs 186) — extraction is nondeterministic run-to-run; the merge step is deterministic given its inputs.

Per-call latency is the bottleneck, not the split: `small` = 172s for 2 chunks ≈ 86s/call. That's the immature hybrid-attention kernel on sm_121 (per `~/src/dgx-fun/current-setup.md`), so parallelism is the cheapest available win.

**Validates CONTINUE.md task #2.** To productionize, `ensemble_extract.py` needs per-pass endpoint assignment — it currently loops all passes against one `DGX_ENDPOINT` in a serial `for` loop (`run_pass` builds the cmd with no endpoint forwarding). Working prototype: `scratch_output/split_run.sh` (shell-orchestrated pass-groups, per-pass `timeout 600` guard, concurrent boxes, then the deterministic merge). Relates to [[project-local-extraction-pipeline]].

Op note: spark2's Qwen pull ran **unauthenticated** (~48 min for 80GB) because `HF_TOKEN` didn't reach the nohup'd spin-up — the `.profile` export quirk the setup doc warns about. Pass the token explicitly for a faster authenticated pull.
