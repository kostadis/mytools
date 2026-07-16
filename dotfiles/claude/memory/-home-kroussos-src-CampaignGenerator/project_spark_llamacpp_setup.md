---
name: project-spark-local-llm-setup
description: Operational layout for Spark-hosted local LLMs backing CampaignGenerator (vLLM and llama.cpp paths)
metadata: 
  node_type: memory
  type: project
  originSessionId: e86ee47c-6b10-4ab8-88a0-8ddea332a573
---

CampaignGenerator's `_OpenAICompatClient` (`campaignlib.py:904`) talks to a local LLM on the Spark via SSH tunnel. Two backends coexist on `spark` — only one is "live" at a time. Last touched 2026-05-22.

**Hosts (refer by SSH alias, never IP — see [[feedback-host-aliases-not-ips]]):**
- `spark` — primary Spark (`gx10-46ea`, GB10, the host this whole setup lives on)
- `spark2` — secondary Spark (`gx10-3e5c`, GB10, added 2026-05-22, currently unused but reachable via `ssh spark2`)

**Why:** the user runs both vLLM (Docker containers, the long-standing path managed by scripts in `~/src/dgx/`) and llama.cpp (bare metal, set up 2026-05-22 to feel out the comparison) as part of local-LLM calibration on the DGX Spark. See `~/src/dgx/spark-llm-serving-learnings.md` for the running journal.

**How to apply:** when a task involves starting/stopping/debugging the local-model path, this memory tells you which backend is live and how to flip between them. Verify before acting — exact state may have moved on.

### Current live backend (as of 2026-05-22)

**vLLM, port 8001, Qwen3-Next-80B-A3B-Instruct-FP8 (128K ctx)**

- Container: `vllm-chat` on Spark (`docker ps`)
- Spin-up script: `~/spin-up-vllm-qwen3-next-80b.sh` on Spark (lives in `~/src/dgx/` locally); sources `~/lib-vllm-spinup.sh`.
- Other vLLM models available via sibling scripts in `~/src/dgx/`: Gemma 4 26B MoE (long-ctx + 32K variants), Llama 70B (+ spec-decode), Nemotron3-Nano 30B. All share the `vllm-chat` container slot — running a new spin-up replaces the previous.
- Tunnel: `rtk proxy ssh -fNL 8001:127.0.0.1:8001 spark` (RTK rewrites bare `ssh -fNL`; use `rtk proxy`).
- Env vars for CampaignGenerator: `DGX_ENDPOINT=http://localhost:8001`, `DGX_MODEL=Qwen/Qwen3-Next-80B-A3B-Instruct-FP8`.
- Tool calls and reasoning: Hermes parser; Instruct variant (no `<think>` blocks). FP8 weights + FP8 KV cache.
- Startup: ~13 min on warm HF cache (8 safetensors shards × ~100 s + ~1 min torch.compile + warmup). First-ever run pulls ~80 GB of FP8 weights.

### Dormant backend (paused, not deleted)

**llama.cpp, port 8000, Qwen2.5-32B-Instruct Q4_K_M (128K ctx via YaRN)**

- Binary: `~/llama.cpp/build/bin/llama-server` on Spark (CUDA 13.0, SM 12.1).
- Model: `~/models/qwen2.5-32b-q4_k_m/qwen2.5-32b-instruct-q4_k_m-{00001..00005}-of-00005.gguf` (~19 GB).
- HF download venv: `~/llm-venv/` (CLI is `hf`, not `huggingface-cli`).
- Launch command for restart:
  ```
  tmux new-session -d -s llamaserver "~/llama.cpp/build/bin/llama-server \
    -m ~/models/qwen2.5-32b-q4_k_m/qwen2.5-32b-instruct-q4_k_m-00001-of-00005.gguf \
    --host 127.0.0.1 --port 8000 -ngl 99 -c 131072 --parallel 1 -fa on \
    --rope-scaling yarn --rope-scale 4 --yarn-orig-ctx 32768 \
    --alias qwen2.5-32b-instruct 2>&1 | tee ~/llama-server.log"
  ```
- Env vars when active: `DGX_ENDPOINT=http://localhost:8000`, `DGX_MODEL=qwen2.5-32b-instruct`.

### Flipping backends

- llama.cpp → vLLM: `ssh spark tmux kill-session -t llamaserver` then `ssh spark 'bash ~/spin-up-vllm-qwen3-next-80b.sh'`. Update tunnel + env to port 8001.
- vLLM → llama.cpp: `ssh spark 'docker stop vllm-chat'` then re-run the tmux launch above. Update tunnel + env to port 8000.
- The two can technically coexist on different ports, but unified memory budget makes that pointless — pick one.

### Gotchas

- `rtk` (Rust Token Killer) intercepts and rewrites bare commands like `ssh -fNL`, `pkill -f ssh`, `curl`. When that gets in the way, prefix with `rtk proxy`. See `~/.claude/RTK.md`.
- llama.cpp's `-fa` now requires an explicit value (`on`/`off`/`auto`) — bare `-fa` errors out.
- `DGX_MODEL` is *cosmetic* under llama.cpp (the loaded model is returned regardless); under vLLM it must match the served model id exactly.
- The shim does not support tool use or vision (`_OpenAICompatClient.messages.create` raises `NotImplementedError` if `tools=...`). Paths needing those (`dnd_sheet.py`, `enhance_recap` with tools) must use Anthropic. vLLM *does* serve tool calls natively — the shim just doesn't plumb them through.
- The `DGX_*` env-var names are vestigial vLLM-era naming. Plan Phase 3.1 (`LOCAL_LLM_*` rename, not yet executed) is the cleanup path.
- `DGX_DEFAULT_MODEL` in `campaignlib.py:780` is still `"Qwen/Qwen2.5-14B-Instruct-AWQ"` — stale, only used when no `DGX_MODEL` env var is set and the caller passes a `claude-*` model id.
