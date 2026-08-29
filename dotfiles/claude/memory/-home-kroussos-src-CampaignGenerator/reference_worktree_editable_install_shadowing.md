---
name: reference-worktree-editable-install-shadowing
description: "In a git worktree, `import campaignlib` can silently resolve to the MAIN checkout — the editable-install .pth puts /home/kroussos/src/CampaignGenerator on sys.path."
metadata: 
  node_type: memory
  type: reference
  originSessionId: feaa7733-d4a1-415e-9e68-4ad5a507344c
  modified: 2026-08-14T14:37:50.666Z
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

**Second mechanism, same symptom (2026-08-09, PR #246):** `tests/` has no
`__init__.py`, so a cross-file `from tests.test_roster import FIXTURE` imports the
module a *second time* under a second name and re-executes it; combined with WSL2's
coarse mtime granularity this produced intermittent stale-bytecode resolution of
`session_doc.roster` to the main checkout. Fix: keep a local fixture copy per test
file (the duplication is load-bearing — an in-file comment says so) and
`find <worktree> -name __pycache__ -exec rm -rf {} +` before trusting any run there.

**Also (2026-08-09):** with a `cd`-less Bash call the shell cwd resets to the MAIN
checkout, and `sys.path[0]=cwd` outranks `PYTHONPATH` — a worktree import check that
passed earlier can fail later in the same session. Always `cd <worktree>` first.

**Third mechanism — the *guard* is now the hazard (2026-08-12, PR #285 / issue #286):**
six test files defend themselves with a module-level
`pytest.skip(allow_module_level=True)` when `campaignlib` resolved outside their own
repo root — `test_verify_quotes.py`, `test_editor_verify_routes.py`,
`test_locate_quote_parity.py`, `test_sd_agent.py`, `test_transcript_corrections.py`,
`test_vtt_voice_compare_reader.py`. The skip is correct but **invisible in the totals**:
a module-level skip contributes exactly **one** entry to the skip count, not one per
test, so ~100 tests disappear behind a `+1`.

Measured: clean `origin/main` in a worktree = 3016 passed / 167 skipped; the same tree
plus a change adding 3 tests and deleting 1 = 3016 passed / **168** skipped. The
arithmetic should be +2; it was 0. This produced a false verification — a green
full-suite run was reported as evidence for PR #282, whose two edited test files
(97 tests) are both guarded and never ran.

**How to apply:** a full-suite pass/fail count from a worktree is not evidence for a
change. Always *also* run the specific test files the change touches, directly, and
report that number. Compare passed-count deltas against `git stash`ed clean base —
if the delta isn't what the diff implies, something skipped.

**Fourth mechanism, and the one that finally got fixed (2026-08-14, feature 008):**
the `python -m pytest` advice above does **not** hold in a Claude Code session — the
harness's rtk wrapper rewrites it to the venv's `pytest` entry point (probe printed
`sys.argv[0] = /home/kroussos/.venv/bin/pytest`). That entry point puts neither the cwd
nor `PYTHONPATH` on `sys.path`; under `prepend` import mode with no `tests/__init__.py`
pytest contributes only `tests/` and `tests/benchmarks/`. So the `.pth` wins outright,
`tests/benchmarks/test_rlm_benchmark_rpg_gate2.py` (collected first, does a bare
`from pipelines.rlm import rpg_retriever` with no repo-root insert) caches main's
`campaignlib` in `sys.modules`, and every module after it inherits it. Measured: a
worktree full-suite run reported **3178 passed against code the branch never touched**;
the two new test modules were the only thing that failed, and only because main's
`campaignlib` genuinely lacked the new files.

**Fix landed:** `tests/conftest.py` now does `sys.path.insert(0, REPO_ROOT)` at import
time — conftest is imported before any test module, so it closes this for the whole
suite instead of per-module. No-op in the main checkout (the `.pth` already put that
path there). If a worktree run still resolves to main, that insert is the first thing
to check.

**How to apply:** don't reach for `PYTHONPATH` — it is stripped twice over (mempalace's
`_strip_leaked_pythonpath_from_sys_path`, and the wrapper's entry point ignoring it).
Verify by probing inside the run, not before it: a throwaway test printing
`campaignlib.__path__` is the only reliable check.

Related: [[project_venv_console_scripts_install]] (the same venv, different failure),
[[reference_campaigns_repo_is_under_src]] (the sibling "wrong tree" trap).
