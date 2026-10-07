#!/usr/bin/env bash
# Keep the repository-owned entries in ~/.codex/skills linked to this checkout.
#
#   codex-links.sh           check only; exit 1 on missing or wrong links
#   codex-links.sh --apply   create missing links and repair wrong symlinks
#
# Real files and directories are never overwritten. Extra live entries are not
# managed: Codex system skills and separately installed personal skills coexist
# in the real ~/.codex/skills directory.
set -euo pipefail

REPO=${REPO_CODEX:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/codex}
LIVE=${CODEX_SKILLS_HOME:-${CODEX_HOME:-$HOME/.codex}/skills}

same_target() { [ "$(readlink -f "$1")" = "$(readlink -f "$2")" ]; }

state() {
  local dst=$LIVE/$1 want=$REPO/skills/$1
  if [ -L "$dst" ]; then
    if same_target "$dst" "$want"; then echo ok; else echo "wrong (-> $(readlink "$dst"))"; fi
  elif [ -e "$dst" ]; then
    echo real
  else
    echo missing
  fi
}

apply=false
[ "${1:-}" = "--apply" ] && apply=true
[ -d "$REPO/skills" ] || { echo "repo skills dir not found: $REPO/skills" >&2; exit 2; }
mkdir -p "$LIVE"

mapfile -t LINKS < <(find "$REPO/skills" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)
[ "${#LINKS[@]}" -gt 0 ] || { echo "no repository-owned Codex skills found" >&2; exit 2; }

drift=0
for p in "${LINKS[@]}"; do
  s=$(state "$p")
  if [ "$s" != ok ] && $apply; then
    case $s in
      missing) ln -s "$REPO/skills/$p" "$LIVE/$p" ;;
      wrong*) unlink "$LIVE/$p"; ln -s "$REPO/skills/$p" "$LIVE/$p" ;;
      real) echo "  refusing: $LIVE/$p is a real file or directory; move it aside or merge it first" ;;
    esac
    s=$(state "$p")
  fi
  printf '%-8s %s\n' "${s%% *}" "$p"
  if [ "$s" != ok ]; then drift=1; fi
done

if [ "$drift" = 0 ]; then
  echo "symmetric: repository-owned Codex skills point to this checkout"
elif $apply; then
  echo "still drifted: see the refusals above" >&2
  exit 1
else
  echo "drifted: run with --apply (it never overwrites a real file or directory)" >&2
  exit 1
fi
