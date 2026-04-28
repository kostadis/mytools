#!/usr/bin/env bash
# start_editor.sh — Launch the adventure block editor.
#
# Usage:
#   ./start_editor.sh [adventure.json] [--port N]

cd "$(dirname "$0")"
exec python3 adventure_editor.py "$@"
