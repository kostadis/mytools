---
name: feedback-use-claude-p-not-api-key
description: "For Claude-model calls I orchestrate (synthesis, one-off LLM passes), use `claude -p` (subscription) instead of scripts that burn ANTHROPIC_API_KEY"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: c525383c-2dcc-432a-a02c-9483830bfed4
---

When I run Claude-model work on the user's behalf (e.g. `synthesise_world_state.py`-style synthesis passes, one-off render calls), the user wants it billed to their Claude subscription via `claude -p` (headless CLI), NOT to their metered `ANTHROPIC_API_KEY` through the anthropic SDK.

**Why:** the API key is pay-per-token; the Claude Code subscription is already paid. Given 2026-06-12 after I ran world_state synthesis (~$3 of Fable tokens) through campaignlib's SDK client.

**How to apply:** before launching any script that calls the Claude API via campaignlib/anthropic SDK, check whether the call can instead be expressed as `claude -p` with `--system-prompt`/stdin (e.g. use `synthesise_world_state.py --dump-input FILE` to assemble the input without calling the API, then pipe through `claude -p`). The CampaignGenerator scripts' own day-to-day use by the user is their business; this rule is about runs I initiate. Local-Spark (DGX) calls are unaffected.
