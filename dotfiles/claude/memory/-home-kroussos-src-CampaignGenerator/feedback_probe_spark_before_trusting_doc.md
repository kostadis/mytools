---
name: feedback-probe-spark-before-trusting-doc
description: "~/src/dgx/current-setup.md lags real Spark swaps — probe /v1/models before relying on its model id; a 'verified live, no drift' note is not proof."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 1d9a0cda-e7bf-463a-a9a8-4a161baf615b
  modified: 2026-08-04T04:22:03.698Z
---

`/spark-status` says the inventory file *is* the answer and not to ask the user.
That is right about **not asking the user** — it is not proof the file is current.

**Measured 2026-08-03.** `~/src/dgx/current-setup.md`'s newest LIVE banner was
2026-07-04 and carried an explicit *"Verified live 2026-07-12: both boxes match
this snapshot exactly — no drift."* Live probe that day:

- **spark1 `192.168.1.147:8001`** served **`deepseek-ai/DeepSeek-V4-Flash-0731`**,
  not the documented `Qwen/Qwen3-Next-80B-A3B-Instruct-FP8`.
- **spark2 `192.168.1.121:8001`** did not answer at all (box pinged at ~0.9 ms,
  Ollama on 11434 answered) — despite `--restart unless-stopped` being applied
  to both boxes specifically to prevent that.

Two config files drift with it and are easy to miss: `config/wiring.yaml`'s
`dgx_model` (rendered, do-not-edit — override per-run with `--model`, don't edit
it), and `dgxlib/models.yaml`, which had **no entry** for the served model, so it
silently fell through to `default` (`max_tokens 16384`, thinking off, 120 s idle
timeout). A model can therefore be served, reachable, and running on
request settings nobody chose.

**Why:** the doc is hand-maintained and a swap is a `ssh spark …` one-liner, so
the box changes in seconds and the banner changes when someone remembers. The
"no drift" line records that a check *once passed*, not that it still holds.

**How to apply:** read the file for context (configs, revert commands, the
reasoning behind a config — none of that is on the wire), then confirm the model
id with `curl -s -m 8 http://192.168.1.147:8001/v1/models` before wiring anything
to it or reporting what is live. Probe **both** boxes — a down chat slot is
invisible from the doc. Report drift; don't silently rewrite the user's inventory
banner, which needs the swap rationale and restart command only they have. Use IPs,
never `spark`/`spark2` (see [[feedback-host-aliases-not-ips]] for the naming rule
and why the hostnames don't resolve in WSL2).

Related: [[project-spark-llamacpp-setup]], [[reference-enhance-summary-spark-test]],
[[reference-spark2-nemotron-extraction]].
