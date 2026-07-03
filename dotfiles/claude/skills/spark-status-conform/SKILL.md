---
name: spark-status-conform
description: Reconcile the live DGX Spark state against current-setup.md. Loads the doc (via spark-status), inspects the actual vllm-chat containers on both boxes, and reports the drift. On approval it conforms the BOXES to the doc (runs the documented spin-up commands); on rejection it conforms the DOC to reality instead. Invoke as /spark-status-conform.
---

# Spark Status Conform

Reconcile **what the doc says is running** (`~/src/dgx/current-setup.md`) with
**what is actually running** on the two DGX Sparks, then close the gap in
whichever direction the user chooses.

**The user is the arbiter of direction:**
- **YES / OK** → the doc is right, reality has drifted → **change the boxes** to match the doc.
- **NO** → reality is right, the doc is stale → **update the doc** to match reality.

Never pick the direction yourself. Draft the diff and the plan; the human decides.

## Boxes and access

| box | ssh alias | chat endpoint | embed endpoint |
|---|---|---|---|
| spark1 | `ssh spark` | `192.168.1.147:8001` | — |
| spark2 | `ssh spark2` | `192.168.1.121:8001` | `192.168.1.121:11434` |

- `ssh spark` / `ssh spark2` are configured aliases and **do** work for shell access.
- Endpoint URLs in any config use the **IPs**, never the hostnames (WSL2 can't resolve `spark`/`spark1`/`spark2`).
- **curl the endpoints from *inside* the box** (`ssh spark 'curl -sS localhost:8001/...'`),
  not from WSL — the boxes aren't always reachable on those ports from the workstation.

## Procedure

### 1. Load the intended state
Do the `spark-status` skill's job first: read `~/src/dgx/current-setup.md` in full.
From the **top copy-paste block** and the **topmost LIVE banner**, extract the
intended per-box chat config **and — importantly — the exact documented re-run /
revert commands** (the banners spell them out verbatim, e.g.
`PREFIX_CACHING=1 MAX_SEQS=3 GPU_UTIL=0.80 SPEC_TOKENS=2 bash ~/spin-up-vllm-qwen3-next-80b-mtp.sh`).
Also read the "Ports in use" and "VRAM budget" tables. Only the topmost LIVE
banner is current — ignore PREV banners.

### 2. Inspect live reality
For **each** box, over ssh:
```bash
ssh <alias> 'curl -sS --max-time 5 http://localhost:8001/v1/models | python3 -c "import sys,json;print(json.load(sys.stdin)[\"data\"][0][\"id\"])"'
ssh <alias> 'docker inspect vllm-chat --format "{{.Config.Image}}"'
ssh <alias> 'docker inspect vllm-chat --format "{{json .Args}}"'
ssh <alias> 'docker inspect vllm-chat --format "{{.HostConfig.RestartPolicy.Name}}"'
ssh <alias> 'docker ps --format "{{.Names}}\t{{.Status}}\t{{.Ports}}"'
ssh spark2 'curl -sS --max-time 5 http://localhost:11434/api/ps'   # embed (spark2 only)
```
If `vllm-chat` is missing or the endpoint doesn't answer, record that box as
**down / stopped** — that is itself a drift.

### 3. Diff, field by field, per box
Compare doc-intended vs live for at least:
- served model id
- image tag
- `--max-model-len`, `--max-num-seqs`, `--gpu-memory-utilization`, `--kv-cache-dtype`
- `--speculative-config` (MTP method + `num_speculative_tokens`)
- `--enable-prefix-caching` present / absent
- `--tool-call-parser` (+ reasoning parser if any)
- port, restart policy
- running containers; embed model / endpoint

Produce a compact **drift table**: `box | field | doc says | reality is`.
If there is **no drift**, say so plainly and stop — nothing to reconcile.

### 4. Present the plan and get the call
For each drift, show **both directions**:
- **Conform boxes → doc (YES):** the **exact spin-up command from the doc** that
  produces the intended state (lift it verbatim from the LIVE banner's "Re-run" /
  "Revert" line — do **not** synthesize a flag set). Warn that running it
  **restarts `vllm-chat` (~10 min, client-facing downtime)**.
- **Conform doc → reality (NO):** the `current-setup.md` edits that would record
  reality as the new truth.

Then ask: **"OK to conform the boxes to the doc, or should I fix the doc instead?"**

### 5a. On YES — do the work
- Run the documented spin-up command(s) on the affected box(es). Launch in the
  background and poll `docker logs vllm-chat` for `Application startup complete`
  (the boxes take ~10–15 min: weight load + torch.compile + graph capture + MTP
  drafter).
- Verify: served id, both intended flags at engine init (`enable_prefix_caching`,
  `speculative_config`), a coherence smoke test, and — if APC is intended — a
  prefix-cache-hit probe (`~/apc_probe.py` on the box: warm request should show
  `prefix_cache_hits_total > 0`).
- Then lightly touch the doc: bump the "Snapshot … as of" date and note the
  conform action. Reality now matches the doc, so no structural doc change.

### 5b. On NO — fix the doc
Update `current-setup.md` to reflect reality, per the repo's honesty rule
(`~/src/dgx/CLAUDE.md`): the top copy-paste block, a **new** LIVE banner (don't
rewrite history in PREV banners), the "Ports in use" table, the "VRAM budget"
table, and the snapshot date. Update `dgxlib/models.yaml` **only** if the served
*id* or *how the model is called* (thinking default / timeouts) changed — not for
flag-only drift.

## Safety rules
- **Never synthesize a spin-up command.** Only run the exact command documented in
  `current-setup.md` for the intended state. If the doc documents no command that
  produces the intended state, **STOP and ask** — do not guess flags onto a
  production box.
- **Never run a box-changing command without an explicit YES** for that box. The
  OK/no gate is the checkpoint; one YES covers the boxes named in the plan, not
  future runs.
- **If reality contains something the doc doesn't explain** (an undocumented model,
  a down box, a mystery container), surface it and ask — don't auto-remediate.
- If both boxes drift and both are client-facing, do them **one at a time** unless
  told otherwise, so there's always one endpoint up.
- This is the precision checkpoint from the global LLM-pipeline rule: the skill
  *drafts* the diff and the plan; the *human* decides direction before anything
  executes.
