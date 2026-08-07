#!/usr/bin/env bash
#
# Mine Claude Code's auto-recall memories into the `claude-memory` MemPalace.
#
# Claude Code keeps memories in one global dir plus one dir per project scope:
#
#   ~/.claude/memory/                      -> wing `global`
#   ~/.claude/projects/<slug>/memory/      -> wing derived from <slug>
#
# Only the *current* project's memories load into a session, so memories written
# in one project are invisible from another. Mining them all into a single palace
# gives cross-project recall through `mempalace search` / the MCP server.
#
# Mining is append-only and idempotent, so this script is safe to re-run — that
# is how the palace is kept fresh as new memories are written.
#
# Usage:
#   ./mine-claude-memories.sh              # mine for real
#   ./mine-claude-memories.sh --dry-run    # show what would be filed
#   ./mine-claude-memories.sh --dry-run --limit 5
#
# Any extra arguments are passed straight through to `mempalace mine`.

set -euo pipefail

MEMPALACE_REPO="${MEMPALACE_REPO:-$HOME/src/mempalace}"
PALACE="${MEMPALACE_PALACE:-claude-memory}"
BACKEND="${MEMPALACE_BACKEND:-turbovec}"
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"

if [ ! -d "$MEMPALACE_REPO" ]; then
  echo "error: mempalace checkout not found at $MEMPALACE_REPO" >&2
  echo "       set MEMPALACE_REPO to override" >&2
  exit 1
fi

# Claude Code slugifies a project path into a dir name by replacing `/` with `-`,
# e.g. /home/kroussos/src/CampaignGenerator -> -home-kroussos-src-CampaignGenerator.
# Stripping the home-dir portion leaves a readable wing (`src-CampaignGenerator`)
# that still maps 1:1 back to its project directory.
HOME_SLUG="$(printf '%s' "$HOME" | tr '/' '-')-"

wing_for_slug() {
  local slug="$1" wing="${1#"$HOME_SLUG"}"
  # A slug that doesn't sit under $HOME (or is exactly $HOME) keeps its raw form
  # rather than collapsing to an empty wing name.
  if [ -z "$wing" ]; then
    printf '%s' "$slug"
  else
    printf '%s' "$wing"
  fi
}

mine_dir() {
  local dir="$1" wing="$2"
  shift 2  # leaves only the caller's passthrough flags in "$@"
  local count
  count=$(find "$dir" -maxdepth 1 -name '*.md' -type f | wc -l)
  echo
  echo "=== $wing  ($count .md files)"
  echo "    $dir"
  # `mempalace mine` is run through `uv run` from the mempalace checkout so it
  # picks up that project's venv (where turbovecdb is installed), regardless of
  # which venv happens to be active in the calling shell.
  # `--palace` and `--backend` are GLOBAL flags and must precede the subcommand.
  (cd "$MEMPALACE_REPO" && uv run mempalace \
    --palace "$PALACE" \
    --backend "$BACKEND" \
    mine "$dir" \
    --wing "$wing" \
    --agent claude-memory \
    "$@")
}

total=0

# Global memories first — they are the ones that apply everywhere.
if [ -d "$CLAUDE_DIR/memory" ]; then
  mine_dir "$CLAUDE_DIR/memory" global "${@}"
  total=$((total + 1))
fi

# Per-project memories. Note `-d` also matches a symlinked dir: at least one of
# these is symlinked into the mytools dotfiles repo so the memories are
# git-tracked, and `os.walk` follows a symlinked top-level path just fine.
for memdir in "$CLAUDE_DIR"/projects/*/memory; do
  [ -d "$memdir" ] || continue
  slug=$(basename "$(dirname "$memdir")")
  mine_dir "$memdir" "$(wing_for_slug "$slug")" "${@}"
  total=$((total + 1))
done

echo
echo "=== done: $total memory director$([ "$total" -eq 1 ] && echo y || echo ies) processed"
