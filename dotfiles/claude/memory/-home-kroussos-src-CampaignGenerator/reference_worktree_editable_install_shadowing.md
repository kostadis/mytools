---
name: reference-worktree-editable-install-shadowing
description: "In a git worktree, `import campaignlib` can silently resolve to the MAIN checkout — the editable-install .pth puts /home/kroussos/src/CampaignGenerator on sys.path."
metadata: 
  node_type: memory
  type: reference
  originSessionId: feaa7733-d4a1-415e-9e68-4ad5a507344c
  modified: 2026-07-27T06:56:38.521Z
---

`~/.venv/lib/python3.12/site-packages/_editable_impl_campaigngenerator.pth` contains
the literal path `/home/kroussos/src/CampaignGenerator` (six times). That path is on
`sys.path` for **every** Python process using that venv — including ones run from
inside a `.claude/worktrees/*` worktree.

So in a worktree, `import campaignlib` (or `server`, `pipelines`, …) may resolve to the
**main checkout's** copy rather than the branch's, depending on import order and which
module got imported first in the process.

**Why it matters:** a green test run in a worktree is not automatically a run against
that branch's code. The failure mode is confusing — a test passes when run alone and
fails in a suite run, or vice versa, because the winner depends on import order.

**How it showed up (2026-07-25, PR #183):** a new `campaignlib/constants.py` symbol
existed in the worktree but the test importing it raised `ImportError`, because the
main checkout's `constants.py` (without the symbol) had already been imported.

**The `PYTHONPATH=<worktree>` guard is NOT safe (2026-07-26, PR #188):**
`mempalace/__init__.py` runs `_strip_leaked_pythonpath_from_sys_path()` at import
time, deleting every `sys.path` entry that string-matches a `PYTHONPATH` value.
`tests/benchmarks/test_rlm_benchmark_rpg_gate2.py` does
`pytest.importorskip("mempalace")` early in collection, so mid-suite the worktree
path vanishes from `sys.path` and later imports silently fall through to main.
Symptom: targeted runs pass, the full suite fails only in files whose code differs
from main.

**Reliable invocation instead:** `cd <worktree> && env -u PYTHONPATH ~/.venvs/main/bin/python -m pytest -q`
— `-m pytest` puts the cwd on `sys.path[0]` *not* via PYTHONPATH, so mempalace's
strip can't remove it and it outranks the `.pth` entry.

**How to apply:**
- Guard tests that assert on source structure should read files off a `REPO_ROOT`
  computed from `__file__`, not `import` the module.
- When a worktree test failure looks impossible, check
  `python -c "import campaignlib; print(campaignlib.__file__)"` first — and re-check
  *inside the failing suite run*, since the mempalace strip poisons mid-session.
- Re-running `uv pip install -e .` from the worktree would repoint the `.pth` at the
  worktree and break the main checkout the same way — don't.
- Worktrees don't carry untracked files: the gitignored `config/wiring.yaml` must be
  copied from the main checkout or `test_extract_facts::test_cli_parallel_fully_cached`
  fails.

Related: [[project_venv_console_scripts_install]] (the same venv, different failure).
