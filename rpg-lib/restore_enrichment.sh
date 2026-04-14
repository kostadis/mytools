#!/bin/bash
# Restore the RPG library database from scratch.
#
# Steps:
#   1. Re-index PDFs from disk (free, no API calls)
#   2. Import enrichment snapshot from enrichment.json (no API calls)
#
# Usage: ./restore_enrichment.sh [db_path]
#   db_path  — destination database (default: rpg_library.db)
#              WARNING: if the file exists it will be overwritten after confirmation.
#
# Scan roots are hardcoded below — update if your drive paths change.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DB_PATH="${1:-$SCRIPT_DIR/rpg_library.db}"
ENRICHMENT="$SCRIPT_DIR/enrichment.json"

DRIVETHRURPG_ROOT="/mnt/g/My Drive/DriveThru"
KICKSTARTER_ROOT="/mnt/g/My Drive/Kickstarter"

# ── Safety check ─────────────────────────────────────────────────────────────
if [[ -f "$DB_PATH" ]]; then
    echo "WARNING: $DB_PATH already exists."
    read -r -p "Overwrite it? This will delete all existing data. [y/N] " confirm
    if [[ "${confirm,,}" != "y" ]]; then
        echo "Aborted."
        exit 1
    fi
    rm "$DB_PATH"
fi

if [[ ! -f "$ENRICHMENT" ]]; then
    echo "Error: enrichment snapshot not found: $ENRICHMENT"
    echo "Cannot restore enrichment without it."
    exit 1
fi

# ── Phase 1: Index ────────────────────────────────────────────────────────────
echo ""
echo "=== Phase 1: Indexing DriveThruRPG PDFs ==="
if [[ -d "$DRIVETHRURPG_ROOT" ]]; then
    "$SCRIPT_DIR/index_rpgs.sh" "$DRIVETHRURPG_ROOT" "$DB_PATH" drivethrurpg
else
    echo "WARNING: DriveThruRPG root not found: $DRIVETHRURPG_ROOT — skipping"
fi

echo ""
echo "=== Phase 1: Indexing Kickstarter PDFs ==="
if [[ -d "$KICKSTARTER_ROOT" ]]; then
    "$SCRIPT_DIR/index_rpgs.sh" "$KICKSTARTER_ROOT" "$DB_PATH" kickstarter
else
    echo "WARNING: Kickstarter root not found: $KICKSTARTER_ROOT — skipping"
fi

# ── Phase 2: Restore enrichment ───────────────────────────────────────────────
echo ""
echo "=== Phase 2: Restoring enrichment from snapshot ==="
python3 "$SCRIPT_DIR/import_enrichment.py" "$DB_PATH" --input "$ENRICHMENT"

echo ""
echo "=== Restore complete ==="
echo "Database: $DB_PATH"
echo "Run './service.sh start' to bring the server back up."
