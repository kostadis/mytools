#!/bin/bash
DB_PATH="${1:-./rpg_library.db}"
PORT="${2:-8000}"
shift 2 2>/dev/null
python3 "$(dirname "$0")/library_server.py" --db "$DB_PATH" --port "$PORT" "$@"
