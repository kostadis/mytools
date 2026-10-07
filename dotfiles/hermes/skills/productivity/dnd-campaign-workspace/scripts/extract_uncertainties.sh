#!/usr/bin/env bash
# extract_uncertainties.sh — pull every "## Uncertainty" open question from a
# merged_dossiers directory (from CampaignGenerator ensemble output).
#
# Usage:  bash extract_uncertainties.sh <merged_dossiers_dir> [out_file]
#
# Output: one line per question, formatted "<filename>: <question text>".
# Block-scoped: only "- " bullets that fall INSIDE a "## Uncertainty" block
# are captured. Other "- " bullets (facts, statuses) are ignored. Because a
# single file can stack multiple entity-type blocks (e.g. faction+monster+
# object), each "## Uncertainty" block is treated independently and its
# questions carry the same filename but are kept separate.
#
# Caveat: the final block in a file has no closing "---", so we also end the
# capture window at end-of-file (loop naturally does this).

set -euo pipefail

DIR="${1:?Usage: extract_uncertainties.sh <merged_dossiers_dir> [out_file]}"
OUT="${2:-/dev/stdout}"

if [[ ! -d "$DIR" ]]; then
  echo "ERROR: not a directory: $DIR" >&2
  exit 1
fi

awk '
  /^## Uncertainty/ { inblock=1; next }
  # Any other H2 ends the uncertainty window (covers "## " sections).
  /^## / && !/Uncertainty/ { inblock=0 }
  # YAML frontmatter / source dividers also end a block.
  /^---/ { inblock=0 }
  # A non-bullet, non-heading, non-empty line with prose also ends the window
  # (questions are always "- " bullets, so this keeps capture tight).
  inblock && /^- / { print FILENAME ": " substr($0, 3) }
' "$DIR"/*.md > "$OUT"

echo "Extracted $(wc -l < "$OUT") uncertainty questions from $DIR" >&2
