#!/usr/bin/env bash
# Usage: check_pdf_access.sh [PDF_PATH]
set -euo pipefail

if [[ ${1:-} == --help ]]; then
    echo "Usage: $0 [PDF_PATH]"
    exit 0
fi

pdf=${1:-"/mnt/g/My Drive/DriveThru/Dungeon Masters Guild/10 New Feats for 5th Edition D&D/193137-Feats.pdf"}
printf 'Checking: %s\n' "$pdf"
if ! signature=$(head -c 5 -- "$pdf"); then
    printf 'Cannot read this PDF from the current terminal.\n' >&2
    exit 1
fi
if [[ $signature != '%PDF-' ]]; then
    printf 'File is readable, but does not start with a PDF header.\n' >&2
    exit 1
fi
printf 'Success: PDF content is readable (%%PDF-).\n'
