#!/usr/bin/env bash
# convert_t14.sh — Convert T1-4 PDF to 5etools JSON in one step.
#
# Usage:
#   ./convert_t14.sh <T1-4.pdf> [output.json] [extra converter options...]
#
# Defaults:
#   output  ~/adventure-t14-1e.json
#   model   claude-sonnet-4-6
#
# Examples:
#   ./convert_t14.sh "T1-4.pdf"
#   ./convert_t14.sh "T1-4.pdf" ~/output/t14.json --skip-pages 1-3 --debug-dir /tmp/dbg

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

PDF="${1:?Usage: $0 <T1-4.pdf> [output.json] [extra options...]}"
OUT="${2:-$HOME/adventure-t14-1e.json}"

# Remaining args (after PDF and OUT) are passed through to the converter
shift 2 2>/dev/null || shift $# 2>/dev/null || true

echo "=== Step 1/2: Converting PDF ==="
python3 "$SCRIPT_DIR/pdf_to_5etools_1e.py" "$PDF" \
    --module-code T1-4 \
    --author "Gary Gygax & Frank Mentzer" \
    --force-ocr \
    --model claude-sonnet-4-6 \
    --out "$OUT" \
    "$@"

echo
echo "=== Step 2/2: Applying T14 fixes ==="
python3 "$SCRIPT_DIR/fix_t14_1e.py" "$OUT"

echo
echo "Done: $OUT"
