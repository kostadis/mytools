---
name: project-mempalace-skill-stale-registration
description: "mempalace-campaign skill's Phase 10 MCP registration instructions are stale — wrong binary path and wrong invocation form"
metadata: 
  node_type: memory
  type: project
  originSessionId: 1703ab1d-f43e-416e-b075-5980b9cf7df7
  modified: 2026-07-26T05:21:20.863Z
---

The `mempalace-campaign` skill (`~/.claude/skills/mempalace-campaign/SKILL.md`)
has stale registration instructions:

- **Prerequisites section** lists a fallback binary path
  `/home/kroussos/worldanvil_pipeline/venv/bin/mempalace` — this path no longer
  exists at all (the whole `worldanvil_pipeline/venv/` dir is gone, not just
  this binary). See [[reference-shared-venv]] — it was consolidated into
  `~/.venvs/main` on 2026-06-03.
- **Phase 10** says to register with
  `claude mcp add mempalace -- <venv_python> -m mempalace.mcp_server`. This is
  wrong. mempalace v3.3.5's own `mcp_server.py` documents (and real
  `.mcp.json` files use) the bare console script instead:
  `claude mcp add mempalace -- mempalace-mcp --palace /path/to/palace`.
  Real example from a live `.mcp.json`:
  ```json
  "mempalace": {
    "type": "stdio",
    "command": "mempalace-mcp",
    "args": ["--palace", "/home/kroussos/.mempalace/palaces/phandalin"]
  }
  ```
  Note this is single-palace (`--palace <path>`), not the multi-wing
  `-m mempalace.mcp_server` invocation the skill describes.

**Why:** mempalace has moved to a `--palace`-scoped console-script CLI since
the skill was written; the skill doc wasn't updated to match.

**How to apply:** Fixed directly in
`~/.claude/skills/mempalace-campaign/SKILL.md` on 2026-07-25 — Prerequisites
now points at `~/.venvs/main`, Phase 10 uses `mempalace-mcp --palace <path>`,
and the two `~/.mempalace/palace/` (singular, pre-rename) references in Key
Principles / Phase 13 were updated to `~/.mempalace/palaces/<campaign_name>/`.
Not re-verified end-to-end against a live campaign setup — if a future
`mempalace-campaign` run hits a mismatch, the skill's wing/`mempalace.yaml`
architecture sections (Phases 3–9) weren't audited in this pass and are the
next place to check.
