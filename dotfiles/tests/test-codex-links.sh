#!/usr/bin/env bash
set -euo pipefail

root=$(mktemp -d "${TMPDIR:-/tmp}/codex-links-test-XXXX")
trap 'rm -rf "$root"' EXIT
repo=$root/repo
live=$root/live
mkdir -p "$repo/skills/alpha" "$repo/skills/beta" "$live"

run() {
  REPO_CODEX=$repo CODEX_SKILLS_HOME=$live bash "$(dirname "$0")/../codex-links.sh" "$@"
}

# Missing links are reported and --apply creates them.
if run >"$root/out" 2>&1; then exit 1; fi
grep -q '^missing  alpha$' "$root/out"
run --apply >/dev/null
run >/dev/null
test "$(readlink -f "$live/alpha")" = "$(readlink -f "$repo/skills/alpha")"

# A wrong symlink is repaired.
unlink "$live/alpha"
ln -s "$repo/skills/beta" "$live/alpha"
if run >"$root/out" 2>&1; then exit 1; fi
grep -q '^wrong    alpha$' "$root/out"
run --apply >/dev/null
test "$(readlink -f "$live/alpha")" = "$(readlink -f "$repo/skills/alpha")"

# A real directory is preserved and keeps the run drifted.
unlink "$live/beta"
mkdir "$live/beta"
touch "$live/beta/keep-me"
if run --apply >"$root/out" 2>&1; then exit 1; fi
grep -q 'refusing: .*beta is a real file or directory' "$root/out"
test -f "$live/beta/keep-me"

echo "codex-links tests passed"
