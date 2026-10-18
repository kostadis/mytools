#!/bin/bash
# Restore rpg_library.db from the newest Google Drive backup (only if missing),
# install fastmcp, and register library_mcp.py with Claude Code as "rpg-library".
set -euo pipefail

cd "$(dirname "$0")"
LIB_DIR="$(pwd)"
BACKUP_DIR="/mnt/g/My Drive/Kickstarter"
PY="$HOME/.venv/bin/python"
DB="$LIB_DIR/rpg_library.db"

# 1. Database — never overwrite an existing one.
if [ -f "$DB" ]; then
    echo "DB already present: $DB (leaving it alone)"
else
    LATEST=$(ls -1 "$BACKUP_DIR"/rpg_library-*.db 2>/dev/null | sort | tail -1)
    [ -n "$LATEST" ] || { echo "No rpg_library-*.db backup in $BACKUP_DIR"; exit 1; }
    echo "Restoring $LATEST -> $DB"
    cp "$LATEST" "$DB"
fi

# 2. fastmcp in the same venv the server uses.
"$PY" -c "import fastmcp" 2>/dev/null || uv pip install --python "$PY" fastmcp

# 3. Register the MCP server (user scope, so every session sees it).
claude mcp remove rpg-library -s user 2>/dev/null || true
claude mcp add rpg-library -s user -- "$PY" "$LIB_DIR/library_mcp.py" --db "$DB"

# 4. Restart the web server so it picks up the DB.
if ./service.sh status | grep -qi "not running"; then
    if ss -ltn 2>/dev/null | grep -q ':8000 '; then
        echo "A server not managed by service.sh is holding port 8000."
        echo "Stop it (Ctrl-C in its terminal), then run: ./service.sh start"
    else
        ./service.sh start
    fi
else
    ./service.sh restart
fi

echo "Done. Restart Claude Code to load the rpg-library MCP."
