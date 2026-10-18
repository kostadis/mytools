#!/bin/bash
DB_PATH="${1:-./rpg_library.db}"
PORT="${2:-8000}"
shift 2 2>/dev/null
"${PYTHON:-$HOME/.venv/bin/python}" "$(dirname "$0")/library_server.py" --db "$DB_PATH" --port "$PORT" "$@"
