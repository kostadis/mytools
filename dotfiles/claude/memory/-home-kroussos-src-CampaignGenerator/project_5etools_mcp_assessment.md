---
name: 5etools-mcp-assessment
description: "Verdict on \"is the 5etools MCP helping or hurting\" + the 3-tier fix set (uncommitted in two repos as of 2026-07-13)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 21e9ca12-3af4-401d-85a6-cf597c3415fd
---

Transcript-mined verdict (2026-07-13): the 5etools MCP **helps** — 6/8 real calls
returned exact module text; zero campaign sessions ever found module content via file
tools alone. The damage came from plumbing: `rpg_search` 0/4 usable (NoneType.rstrip
crash when `rpg_library_url` unwired), `-32000` reconnect drops, query-shape friction
(AND-of-substrings matcher needs terse keywords; `get_section` needs numeric ids), and
a 21.5KB `list_sources` dump. Full assessment + plan:
`~/.claude/plans/peppy-beaming-harbor.md`.

Three approved fix tiers implemented by Sonnet subagents, verified, left
**uncommitted**: Tier 1 in CampaignGenerator `main` (rpglib tier soft-skips with
`expensive_fallback_reason` when URL is None; `suggest_conversion` returns a clear
error; 2 new tests in `tests/test_rpg_retriever.py`); Tiers 2–3 in 5etools-kostadis
`kostadis-dev` under `mcp/` only (query-rule tool descriptions, compact
`list_sources` + `verbose` flag, entity stores rekeyed name→entry[] per source with
get_monster/get_spell/get_item `source` disambiguation, entity search now respects
`source_ids`/`ref_name`).

**Why:** the uncommitted diffs in two repos are otherwise mystery state next session.
**How to apply:** if asked about mcp/ or rpg_retriever working-tree changes, this is
what they are; the deferred item is diagnosing the `-32000` reconnects (capture stderr
from `launch_5etools_mcp.py`'s exec'd node next time it drops). Related:
[[rlm-5etools-bridge]].
