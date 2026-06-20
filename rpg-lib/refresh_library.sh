#!/usr/bin/env bash
# Full library refresh: backup -> index both libraries -> enrich -> backup.
#
# Indexes the two PDF libraries I care about, enriches new books via the
# Claude API, and brackets the whole run with database backups so there's
# a snapshot both before (in case the run corrupts something) and after
# (the freshly-updated state).
#
# Usage: ./refresh_library.sh [db_path]
#   Pass extra enricher flags after the db path is NOT supported here;
#   edit the ENRICH_ARGS line below if you need --limit, --force, etc.
set -euo pipefail

cd "$(dirname "$0")"

DB_PATH="${1:-./rpg_library.db}"

# (scan_dir, source) pairs for the two libraries.
DRIVETHRU_DIR="/mnt/g/My Drive/DriveThru"
KICKSTARTER_DIR="/mnt/g/My Drive/Kickstarter"

ENRICH_ARGS=()   # e.g. (--limit 50) or (--force); empty = enrich all unenriched

banner() { echo; echo "==================== $* ===================="; echo; }

banner "BACKUP (before)"
./backup_db.sh

banner "INDEX: DriveThruRPG"
./index_rpgs.sh "$DRIVETHRU_DIR" "$DB_PATH" drivethrurpg

banner "INDEX: Kickstarter"
./index_rpgs.sh "$KICKSTARTER_DIR" "$DB_PATH" kickstarter

banner "ENRICH"
./enrich_rpgs.sh "$DB_PATH" "${ENRICH_ARGS[@]}"

banner "BACKUP (after)"
./backup_db.sh

banner "DONE"
echo "Library refreshed and backed up (before + after)."
