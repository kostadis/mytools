---
name: project_venv_console_scripts_install
description: "Web UI CLIs must be editable-installed into the venv the server runs under (.venv, uv-managed); \"Stream error — check terminal\" on a /run/* action usually means a missing console script."
metadata: 
  node_type: memory
  type: project
  originSessionId: e561915d-f79e-4659-aa54-3b5cb7a250eb
  modified: 2026-07-24T18:06:30.737Z
---

The web UI runs pipeline CLIs as subprocesses. `server/subprocess_runner.py` builds each command with `console_script(name)` = `Path(sys.executable).parent / name` — it looks for a `pyproject.toml [project.scripts]` console script installed in the **same venv as the running server**, NOT `$PATH`.

The production server (`startup` → `python -m server.main`, or `dev.sh`) runs under `/home/kroussos/.venv` (`VIRTUAL_ENV`), and `startup` sets `PYTHONPATH=/home/kroussos/src/CampaignGenerator` so `server.main` imports resolve WITHOUT the package being installed. So the server boots fine even when `campaigngenerator` is not installed — but the console scripts (`sd_narrate`, `scene_extract`, `enhance_summary`, `sd_plan`, `sd_consistency`, `assemble`, …) only exist if the package is editable-installed.

**Symptom:** any `/run/*` UI action fails and the Session Doc Editor shows `Stream error — check terminal.` because the subprocess spawn hits a non-existent `/home/kroussos/.venv/bin/<script>`.

**Fix (after a source-tree restructure, a `pyproject [project.scripts]` change, or a fresh venv):**
```
/home/kroussos/.venv/bin/uv pip install -e . --python /home/kroussos/.venv/bin/python
```
The venv is `uv`-managed (its `python` has no `pip`; claudelib/hypostasis/mempalace are editable there too). **No server restart needed** — `console_script()` resolves per-request, so the script just needs to exist on disk.

**Why:** the restructure moved flat `*.py` scripts into `pipelines/`, `session_doc/`, `entity_registry/` packages, so the old `python_exe() + SCRIPT_DIR/<name>.py` invocation was replaced by installed command names — which requires the editable install to be present.

Note: this contradicts [[reference_shared_venv]] (which names `~/.venvs/main`). The live web server actually runs under `~/.venv`; `~/.venvs/main` currently holds only a bare python3.12. Install into whichever venv the server process's `VIRTUAL_ENV` points at (verify via `/proc/<pid>/environ`).
