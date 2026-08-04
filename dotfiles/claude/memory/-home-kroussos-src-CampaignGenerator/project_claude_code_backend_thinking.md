---
name: project-claude-code-backend-thinking
description: "The claude-code backend is ~4.5x slower than the anthropic backend because `claude -p` runs extended thinking that eats CLAUDE_CODE_MAX_OUTPUT_TOKENS; MAX_THINKING_TOKENS=0 closes the gap"
metadata: 
  node_type: memory
  type: project
  originSessionId: 7a8eadea-7c7d-458a-a0be-08623b6aad0f
  modified: 2026-08-03T04:50:59.954Z
---

`--backend claude-code` runs `claude -p`, which does **extended thinking by
default**. The Anthropic SDK path does not — `stream_api` only forwards
`thinking` to `_THINKING_EXTRA_CLIENTS` (DGX/OpenRouter), never to the real
Anthropic client (`campaignlib/api/client.py:290`). So the two backends are not
doing the same work, and the claude-code path silently burns ~5x the output
tokens on a thinking trace for pure-render tasks.

Worse: `_claude_code_generate` forwards the caller's `max_tokens` as
`CLAUDE_CODE_MAX_OUTPUT_TOKENS` (`campaignlib/api/backends.py:379`). When the
thinking trace (~14K tokens) nearly fills that ceiling, the CLI **auto-continues**
into a fresh turn and thinks another ~14K — the runaway that looks like a hang.

Measured 2026-08-02, identical `enhance_summary` call (130,412-char Phandalin
VTT, ch03), same box, concurrent:

| Config | Wall | Output tokens |
|---|---|---|
| `--backend anthropic` | 3m23s | ~9K |
| `--backend claude-code` (default `--max-tokens 16384`) | 17m43s | 53,387 (+ continuation seam) |
| `--backend claude-code --max-tokens 32000` | 10m54s | clean, no seam |
| ... plus `MAX_THINKING_TOKENS=0` | **3m57s** | 10,100 |

**Why:** thinking is the entire gap. Raising `--max-tokens` only stops the
auto-continue loop; it does not stop the trace.

**How to apply:** for render pipelines (`enhance_summary`, `scene_extract`,
`sd_narrate`) set `MAX_THINKING_TOKENS=0` in the `claude -p` env. Keep it
available for judgement passes (`sd_consistency`) where a trace may earn its
cost. This mirrors the guard the repo already documents for the other backends
at `campaignlib/api/client.py:25` (`DGX_NO_THINKING=1` / `OPENROUTER_NO_THINKING=1`)
— claude-code has no equivalent escape hatch yet.

Secondary, not a latency cause: every `claude -p` spawns 7 MCP servers
(codebase-memory, headroom, uvx mcp-server-git, campaign mcp_server,
mempalace-mcp, 5etools node, registry_mcp). `--disallowed-tools '*'` stops them
being *used*, not *spawned*; they cost 0 tokens (13,399-token cached prefix with
and without `--strict-mcp-config`) but ~300MB each. `scene_extract` pays this
per scene because `run_scene_extraction` (`campaignlib/scenes.py:149`) is a
serial loop — and each fresh CLI session also loses the `cache_system=True` VTT
prefix reuse the anthropic backend gets.

Related: [[project-venv-console-scripts-install]], [[project-web-ui-usage-pattern]]
