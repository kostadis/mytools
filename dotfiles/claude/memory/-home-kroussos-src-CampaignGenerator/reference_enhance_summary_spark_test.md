---
name: reference-enhance-summary-spark-test
description: Calibration test — enhance_summary.py on the Spark vs Sonnet; results + shareable report location
metadata: 
  node_type: memory
  type: reference
  originSessionId: c41a5943-b570-469e-bc22-7a81e279519d
---

2026-06-02 calibration test: ran CampaignGenerator's `enhance_summary.py` (Stage 1 recap enrichment) on `spark1` (`Qwen/Qwen3-Next-80B-A3B-Instruct-FP8`, via `DGX_ENDPOINT`) vs Anthropic Sonnet 4.6.

Key findings:
- Spark output passed the project's own `check_consistency.py` canon gate with **zero issues** — local 80B output is trustworthy for this workload.
- Spark ~1.6× slower than Sonnet (5:55 vs 3:41) and ~20% less detail-dense, but factually faithful; no quote fabrication detected.
- VTT tokenizes at **~7.4 chars/token** (vLLM count), so a single real D&D session is only ~12–15K tokens — nowhere near the 128K wall. Needs ~9 concatenated sessions to choke.
- Choke mode is clean: HTTP 400 "maximum context length 131072" in ~1.4s, no silent truncation; correctly NOT retried (400 ≠ 5xx).
- `cache_system=True` is silently dropped on the OpenAI-compat path (vLLM ignores `cache_control`) — every run pays full prefill.
- Gap: `enhance_summary.py` has no pre-flight token check, so over-window input dies with a raw `openai.BadRequestError` traceback.

Shareable writeup: `~/src/dgx/campaigngen-enhance-summary-spark-test.md`. See [[project_spark_llamacpp_setup]] for endpoint flip details.
