#!/bin/bash
# Backup enrichment data to enrichment.json and commit to git.
# Run this after any enrichment session to protect Claude API work.
#
# Usage: ./backup_enrichment.sh [db_path]
#   db_path  — path to database (default: rpg_library.db)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DB_PATH="${1:-$SCRIPT_DIR/rpg_library.db}"
OUTPUT="$SCRIPT_DIR/enrichment.json"

if [[ ! -f "$DB_PATH" ]]; then
    echo "Error: database not found: $DB_PATH"
    exit 1
fi

echo "=== Exporting enrichment from $DB_PATH ==="
python3 "$SCRIPT_DIR/export_enrichment.py" "$DB_PATH" --output "$OUTPUT"

cd "$SCRIPT_DIR"

if ! git diff --quiet "$OUTPUT" 2>/dev/null || ! git ls-files --error-unmatch "$OUTPUT" 2>/dev/null; then
    echo ""
    echo "=== Committing enrichment.json ==="
    git add "$OUTPUT"
    git commit -m "backup: update enrichment snapshot"
    echo "Committed."
    echo ""
    echo "=== Pushing to GitHub ==="
    git push
    echo "Pushed."
else
    echo ""
    echo "No changes to enrichment.json — nothing to commit."
fi
