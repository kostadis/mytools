#!/bin/bash
# If first arg starts with -- it's a flag, not a db path; use default
if [[ "${1:-}" == --* ]] || [[ -z "$1" ]]; then
  DB_PATH="./rpg_library.db"
else
  DB_PATH="$1"
  shift
fi
python3 "$(dirname "$0")/pdf_enricher.py" "$DB_PATH" "$@"
