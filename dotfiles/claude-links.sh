#!/usr/bin/env bash
# Make ~/.claude match the link set documented in CLAUDE.md, so every machine
# runs the same skills, agents and global instructions.
#
#   claude-links.sh           check only; exit 1 if this machine has drifted
#   claude-links.sh --apply   create or repair the links
#
# --apply only ever fills a gap or replaces a symlink. A real file or directory
# where a link belongs is reported and left alone, because it may hold the only
# copy of something. The one exception is skills/, which is converted (below).
#
# CLAUDE_HOME and REPO_CLAUDE override the two roots so this can be tested
# against scratch directories.
set -euo pipefail

REPO=${REPO_CLAUDE:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/claude}
LIVE=${CLAUDE_HOME:-$HOME/.claude}

# The symmetric set. settings.json and plugins/known_marketplaces.json are left
# out on purpose: they hold per-machine hooks and per-user absolute paths, so a
# single shared copy could never be right on every machine.
LINKS=(CLAUDE.md skills agents plugins/blocklist.json)

same_target() { [ "$(readlink -f "$1")" = "$(readlink -f "$2")" ]; }

state() {
  local dst=$LIVE/$1 want=$REPO/$1
  if [ -L "$dst" ]; then
    if same_target "$dst" "$want"; then echo ok; else echo "wrong (-> $(readlink "$dst"))"; fi
  elif [ -e "$dst" ]; then
    echo real
  else
    echo missing
  fi
}

# skills/ is often a real directory because Claude Code writes its own
# skills/synced/ (claude.ai account skills) into it. Linking the whole directory
# means that state now lives in the repo tree, where claude/.gitignore hides it,
# so move it across rather than delete it. Anything else in there is refused.
convert_skills() {
  local live=$LIVE/skills e b
  while IFS= read -r e; do
    b=${e##*/}
    if [ "$b" = synced ] && [ -d "$e" ] && [ ! -L "$e" ]; then continue; fi
    if [ -L "$e" ] && [[ $(readlink -f "$e") == "$(readlink -f "$REPO/skills")"/* ]]; then continue; fi
    echo "  refusing: skills/$b is neither synced/ nor a link into this repo; move it aside and re-run"
    return 1
  done < <(find "$live" -mindepth 1 -maxdepth 1)
  if [ -e "$REPO/skills/synced" ]; then
    echo "  refusing: $REPO/skills/synced already exists"
    return 1
  fi
  if [ -d "$live/synced" ]; then mv "$live/synced" "$REPO/skills/synced"; fi
  find "$live" -mindepth 1 -maxdepth 1 -type l -exec unlink {} \;
  rmdir "$live"
  ln -s "$REPO/skills" "$live"
}

apply=false
[ "${1:-}" = "--apply" ] && apply=true
[ -d "$REPO" ] || { echo "repo dir not found: $REPO" >&2; exit 2; }

drift=0
for p in "${LINKS[@]}"; do
  s=$(state "$p")
  if [ "$s" != ok ] && $apply; then
    case $s in
      missing) mkdir -p "$(dirname "$LIVE/$p")"; ln -s "$REPO/$p" "$LIVE/$p" ;;
      wrong*)  unlink "$LIVE/$p"; ln -s "$REPO/$p" "$LIVE/$p" ;;
      real)
        if [ "$p" = skills ] && [ -d "$LIVE/$p" ]; then
          convert_skills || true
        else
          echo "  refusing: $LIVE/$p is a real file or directory; merge it into the repo or move it aside"
        fi ;;
    esac
    s=$(state "$p")
  fi
  printf '%-8s %s\n' "${s%% *}" "$p"
  if [ "$s" != ok ]; then drift=1; fi
done

if [ "$drift" = 0 ]; then
  echo "symmetric: $LIVE matches the repo link set"
elif $apply; then
  echo "still drifted: see the refusals above" >&2; exit 1
else
  echo "drifted: run with --apply (it never overwrites a real file)" >&2; exit 1
fi
