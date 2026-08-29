---
name: project-speckit-worktree-feature-json
description: /speckit-* skills resolve the feature dir from the MAIN checkout's .specify/feature.json, ignoring a worktree's own copy; fix is an absolute path
metadata:
  type: project
---

The `/speckit-*` skills run as forked agents whose CWD is the session's primary
working directory — `/home/kroussos/src/CampaignGenerator` — **not** the worktree
you are working in. `get_repo_root()` (`.specify/scripts/bash/common.sh:56`)
walks up from there, so `check-prerequisites.sh` reads MAIN's
`.specify/feature.json` and a worktree's own (correct) copy is ignored. This bit
twice on the same day: `/speckit-analyze` analysed `013-batched-scene-extraction`
instead of the worktree's `014-thread-registry-ui`, and produced a plausible,
detailed, entirely off-target report both times.

**Why:** the resolution order is `SPECIFY_FEATURE_DIRECTORY` env var →
`$repo_root/.specify/feature.json` → error. Env vars do not persist between Bash
tool calls, and `repo_root` is main.

**How to apply:** put an **absolute** path in MAIN's `.specify/feature.json`.
Both resolution branches do `[[ "$feature_dir" != /* ]] && feature_dir="$repo_root/$feature_dir"`,
so an absolute value is used verbatim and works from either checkout:

```json
{ "feature_directory": "/home/kroussos/src/CampaignGenerator-worktrees/<wt>/specs/<NNN-feature>" }
```

Verify before trusting a report — the target is echoed:
`.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks`

Caveats: `REPO_ROOT` still resolves to main, so `.specify/memory/constitution.md`
and `.specify/templates/` come from main (same content in practice — but a
worktree that *changes* a template or the constitution will not see it).
Main's `feature.json` is tracked, so this dirties main; revert it to a relative
path when the worktree is done. Related: [[project-speckit-claude-gitignored]],
[[reference-worktree-editable-install-shadowing]].
