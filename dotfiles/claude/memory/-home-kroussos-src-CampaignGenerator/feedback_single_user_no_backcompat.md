---
name: feedback-single-user-no-backcompat
description: "Kostadis is the only user of CampaignGenerator — don't build back-compat fallbacks, dual-location probes, or legacy shims; migrate and delete instead."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: feaa7733-d4a1-415e-9e68-4ad5a507344c
  modified: 2026-07-25T02:11:05.177Z
---

CampaignGenerator has exactly one user. When a design choice is "support both the
old and new location/shape" vs "migrate the data and delete the old path," pick
migrate-and-delete. Fallback probes, compatibility shims, and legacy branches buy
nothing here and actively cost correctness.

Stated directly on 2026-07-24: *"as the only user of this tool, i would like to have
one place for config files, in config."*

**Why:** the accumulated fallbacks had produced a live Split-Brain. Four code paths
probed for `party.yaml` across three locations (`docs/`, `config/`, campaign root) in
two different precedence orders — `campaignlib/party.py:44` checks `docs/` first, while
`platform_config_service.py:535` and `ensemble.py:195` check `config/` first and never
look in `docs/` at all. Result: the obelisk campaign's `docs/party.yaml` was visible to
PC-name filtering and invisible to the Party page and ensemble PC-exclusion,
simultaneously, with no error anywhere.

**How to apply:** declare one path, delete the probes, write a one-shot migration, and
add a boot check that names a stray file rather than silently loading defaults. When
removing a fallback, migrate the data *before* deleting the path that currently reaches
it — otherwise the removal silently orphans live data. The useful line for this repo:
`config/` = how a pipeline runs; `docs/` = what the pipelines operate on. Being YAML is
not the test — `docs/entity_registry.yaml` stays put.

Related: [[project_web_ui_usage_pattern]] (same single-user premise, applied to race
conditions), [[feedback_never_assume_answers]].
