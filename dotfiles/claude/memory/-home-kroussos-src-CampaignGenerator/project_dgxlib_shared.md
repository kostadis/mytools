---
name: project_dgxlib_shared
description: dgxlib is a shared package (in dgx-fun) owning per-model DGX request config; CampaignGenerator and mytools consume it
metadata: 
  node_type: memory
  type: project
  originSessionId: 92578d7e-6da0-487e-8511-bad9334acb78
---

`dgxlib` is a standalone installable package living in the **dgx-fun** repo
(local `~/src/dgx`, remote github.com/kostadis/dgx-fun), editable-installed into
the shared venv `~/.venvs/main`. It is the single home for **DGX/Spark per-model
behavior** so swapping the served model is a one-line edit to
`dgxlib/models.yaml`, not code surgery.

Surface: `resolve_model_config(model_id, thinking=None, max_tokens=None)` →
`ModelConfig(extra_body, read_timeout, max_tokens)`; `discover_model(endpoint)`;
a plain `make_client`/`call_api` client; `RETRYABLE_STATUS`. Thinking is
**(model capability) × (call intent)**: the registry stores `can_think` +
`thinking_default`, the call site overrides per request (honored only when
`can_think`). Registry source overridable via `DGXLIB_REGISTRY` env var.

Consumers: **mytools** `rpg-lib/pdf_enricher.py` imports it directly (replaced
the old `lib/dgxlib.py`); **CampaignGenerator** `campaignlib/api/backends.py`
`_OpenAICompatClient` applies it and threads a per-call `thinking` flag through
`stream_api`/`call_api`. `DGX_NO_THINKING` / `DGX_READ_TIMEOUT` / `DGX_MODEL`
remain as back-compat overrides.

Landed via PRs (verify merged before relying on it): dgx-fun #20 (impl #18),
mytools #49 (#48), CampaignGenerator #97 (#94). Deferred: structured
endpoint/host resolution (dgx-fun #19). Merge order: dgx-fun #20 first.
Supersedes the per-repo `DGX_NO_THINKING` hack. Related: [[project_spark_llamacpp_setup]].
