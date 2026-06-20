#!/usr/bin/env bash
# Back up the rpg-lib SQLite databases to Google Drive.
# Uses `sqlite3 .backup` for consistent snapshots (safe to run while the
# read-only API server is up). Dated filenames keep one backup per day;
# same-day runs overwrite that day's files.
#
# Usage: ./backup_db.sh [dest_dir]
set -euo pipefail

cd "$(dirname "$0")"

DEST="${1:-/mnt/g/My Drive/Kickstarter}"
STAMP="$(date +%Y-%m-%d)"
DBS=(rpg_library.db user_data.db)

if [[ ! -d "$DEST" ]]; then
  echo "error: destination not found: $DEST" >&2
  exit 1
fi

for db in "${DBS[@]}"; do
  if [[ ! -f "$db" ]]; then
    echo "warn: skipping missing $db" >&2
    continue
  fi
  out="$DEST/${db%.db}-$STAMP.db"
  sqlite3 "$db" ".backup '$out'"
  echo "backed up $db -> $out ($(du -h "$out" | cut -f1))"
done
