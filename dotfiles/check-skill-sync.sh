#!/usr/bin/env bash
# Check that skill files shared by the Codex and Claude copies are still
# byte-identical. The list lives in skill-sync.txt.
#
#   check-skill-sync.sh      report; exit 1 if any listed file differs or is missing
#
# Each harness keeps its own copy (they install to different homes), so a fix
# made to one copy has to be ported to the other by hand. This catches the
# port that was forgotten.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
codex="$here/codex/skills"
claude="$here/claude/skills"
fail=0

while IFS= read -r path; do
  [[ -z "$path" || "$path" == \#* ]] && continue
  if [[ ! -f "$codex/$path" || ! -f "$claude/$path" ]]; then
    echo "MISSING  $path"
    fail=1
  elif ! cmp -s "$codex/$path" "$claude/$path"; then
    echo "DIFFERS  $path"
    fail=1
  fi
done < "$here/skill-sync.txt"

if (( fail )); then
  echo "shared skill files have drifted; port the change to both copies" >&2
  exit 1
fi
echo "shared skill files in sync ($(grep -cv '^\s*\(#\|$\)' "$here/skill-sync.txt") files)"
