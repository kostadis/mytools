#!/bin/bash
# OCR "Ultimate Bestiary: The Dreaded Accursed" to Markdown via Mistral OCR.
# Needs MISTRAL_API_KEY in the environment. Cost: ~270 pages at $4/1000 ≈ $1.10.
set -euo pipefail

cd "$(dirname "$0")"
PY="$HOME/.venv/bin/python"
PDF="/mnt/g/My Drive/Kickstarter/NordGames/Ultimate Bestiary The Dreaded Accursed for 5th Edition!/Ultimate-Bestiary-The-Dreaded-Accursed-5E-hpdisb.pdf"
OUT="${1:-$HOME/src/mytools/pdf-translators/samples/ultimate-bestiary-dreaded-accursed.md}"

[ -n "${MISTRAL_API_KEY:-}" ] || { echo "Set MISTRAL_API_KEY first"; exit 1; }
[ -f "$PDF" ] || { echo "PDF not found: $PDF"; exit 1; }
[ -e "$OUT" ] && { echo "Refusing to overwrite $OUT (pass a different path as \$1)"; exit 1; }

# mistral_ocr.py imports from the mistralai 2.5.0 namespace layout.
"$PY" -c "from mistralai.client.sdk import Mistral" 2>/dev/null \
    || uv pip install --python "$PY" "mistralai==2.5.0"

"$PY" converters/extract_markdown.py "$PDF" --provider mistral --output "$OUT" --verbose
