---
name: reference-spark2-nemotron-extraction
description: "spark2's Nemotron reasoning model is unsuitable for bulk fact extraction — keep extraction on spark1's Qwen3-Next Instruct"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 374c07c8-3825-4bfe-9ecf-1596ac85bef3
---

spark2 (`192.168.1.69:8001`) serves `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16`, a reasoning model that **always emits a `<think>` trace** (routed to a non-standard `reasoning` JSON field by the `nano_v3` parser). The trace cannot be disabled — tested `/no_think` and `detailed thinking off` as system messages on 2026-05-28; both left reasoning length unchanged (~620–660 chars).

The trace length scales with input/task complexity. On the `extract_facts.py` ensemble (full chapter ~10K chars, `max_tokens=16000`) the reasoning trace **consumes the entire output budget before any JSON answer is emitted** — `content` comes back empty, the call generates for >400s and hits the `max_tokens` ceiling mid-`<think>`. A tiny one-sentence prompt works fine (~150 reasoning tokens, clean JSON), so it's a budget-burn failure mode, not a capability gap.

**Lesson:** fact extraction is a mechanical task, not a reasoning task — a reasoning model deliberates about work it could just do. Keep the [[project-local-extraction-pipeline]] ensemble on spark1's Qwen3-Next **Instruct** (non-reasoning) model. This means CONTINUE.md task #2 (two-Spark parallel ensemble) can't simply offload extraction agents to the spark2 Nemotron box — would need a non-reasoning model swapped onto spark2 first, or much smaller chunks + a far larger `max_tokens` + client timeout (slow, token-expensive, unproven).
