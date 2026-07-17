#!/usr/bin/env bash
# start_editor.sh — Launch the unified Markdown/Adventure editor.
#
# Usage:
#   ./scripts/start_editor.sh [file.md|adventure.json] [--port N]

cd "$(dirname "$0")/.."
exec python3 editors/editor_server.py "$@"
