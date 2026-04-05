#!/bin/bash
SCAN_DIR="${1:-/mnt/g/My Drive/Kickstarter}"
DB_PATH="${2:-./rpg_library.db}"
SOURCE="${3:-kickstarter}"
shift 3 2>/dev/null
python3 "$(dirname "$0")/pdf_indexer.py" "$SCAN_DIR" "$DB_PATH" --source "$SOURCE" "$@"
