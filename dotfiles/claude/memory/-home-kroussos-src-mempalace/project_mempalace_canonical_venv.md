---
name: project_mempalace_canonical_venv
description: Canonical mempalace venv is ~/.venvs/main; Claude Code hooks point there and the stray worldanvil_pipeline copy was removed
metadata: 
  node_type: memory
  type: project
  originSessionId: 32b9a252-5089-492a-91b5-38171b1fbccb
---

The single canonical mempalace install lives at `/home/kroussos/.venvs/main` — a real PEP 660 **editable** install pointing at `/home/kroussos/src/mempalace` (verified importable from a neutral cwd: `pip show` reports `Editable project location: /home/kroussos/src/mempalace`). Edits to the repo source are live; no reinstall needed. The Claude Code Stop + PreCompact hooks (in `~/.claude/settings.json`) inject `PATH=/home/kroussos/.venvs/main/bin:$PATH`, so the hooks, the `mempalace` console script, and `python3 -m mempalace` all resolve to this one venv and repo — from any cwd.

**Correction (2026-06-03):** `.venvs/main` did NOT have mempalace installed until 2026-06-03. Earlier checks that "passed" only did so because the shell cwd was the repo itself (Python puts cwd on `sys.path`, importing the package folder directly). The editable install into `.venvs/main` was created on 2026-06-03 via `pip install -e /home/kroussos/src/mempalace`. The `worldanvil_pipeline/venv` copy that was removed the same day had been the *real* (cwd-independent) editable install actually firing the hooks — so the venv repoint + removal had to be backfilled with a genuine install into `.venvs/main`. If diagnosing "hooks silently not saving," verify `~/.venvs/main/bin/python3 -c "import mempalace"` succeeds **from a non-repo cwd** (e.g. `/tmp`), not just from the repo dir.

**Why:** the hooks previously borrowed `/home/kroussos/worldanvil_pipeline/venv` (an unrelated project's venv). That was the "wrong path to mempalace": worldanvil's `mempalace` console script had a cross-wired shebang (`#!/home/kroussos/.venvs/main/bin/python3.12`) pointing at a *different* venv, so any bare-`mempalace` call silently jumped venvs. Same family of bug as [[mempalace-rlm-deletable]] — mempalace running off an incidental venv. Nothing in worldanvil_pipeline imported mempalace (0 references), so the editable install there was pure cruft.

**How to apply:**
- Use `~/.venvs/main` for mempalace work, hook config, and any new MCP-server registration. Do not reintroduce installs in `worldanvil_pipeline/venv` or other project venvs.
- The worldanvil_pipeline editable install was uninstalled 2026-06-03 (`pip uninstall mempalace` — editable, so the repo source was untouched). `import mempalace` in that venv now fails by design.
- settings.json hooks are read at session start, so PATH edits take effect on the next session.
