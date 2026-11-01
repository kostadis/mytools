#!/usr/bin/env bash
# Back up the rpg-lib SQLite databases to the backup folder.
# Uses `sqlite3 .backup` for consistent snapshots (safe to run while the
# read-only API server is up). Dated filenames keep one backup per day;
# same-day runs overwrite that day's files.
#
# Usage: ./backup_db.sh [dest_dir]
#   dest_dir defaults to $RPG_LIB_BACKUP_DIR; there is no built-in default.
set -euo pipefail

cd "$(dirname "$0")"

DEST="${1:-${RPG_LIB_BACKUP_DIR:-}}"
if [[ -z "$DEST" ]]; then
  echo "error: no backup folder: pass one or set RPG_LIB_BACKUP_DIR" >&2
  exit 1
fi
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
