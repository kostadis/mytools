#!/usr/bin/env bash
# Usage: run_source_selection_pilot.sh [SOURCE_FOLDER] [WORK_FOLDER]
# Optional: SELECTOR_BIN=/path/to/rpg-source-select
set -euo pipefail

if [[ ${1:-} == --help ]]; then
    echo "Usage: $0 [SOURCE_FOLDER] [WORK_FOLDER]"
    echo 'Override the selector executable with SELECTOR_BIN.'
    exit 0
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=${1:-"/mnt/g/My Drive/DriveThru/Dungeon Masters Guild/10 New Feats for 5th Edition D&D"}
work=${2:-/tmp/dmsguild-source-pilot}
selector=${SELECTOR_BIN:-"$script_dir/../source-selector/target/debug/rpg-source-select"}
# The implementation currently lives in a separate development checkout.
if [[ -z ${SELECTOR_BIN:-} && ! -x $selector ]]; then
    selector=/tmp/rpg-source-selection/pdf-translators/source-selector/target/debug/rpg-source-select
fi
if [[ ! -x $selector ]]; then
    printf 'Selector executable missing. Set SELECTOR_BIN to its full path.\n' >&2
    exit 1
fi
if [[ ! -d $root ]]; then
    printf 'Source folder not found: %s\n' "$root" >&2
    exit 1
fi
if ! command -v pdftotext >/dev/null 2>&1; then
    printf 'pdftotext is required; install Poppler before running the pilot.\n' >&2
    exit 1
fi

printf 'Source: %s\nWorking data: %s\nSelector: %s\n' "$root" "$work" "$selector"
"$selector" --work-dir "$work" scan --root "$root"
inspection_status=0
"$selector" --work-dir "$work" inspect --limit 1 --retry-failed || inspection_status=$?
# Export diagnostics even if a PDF could not be inspected.
"$selector" --work-dir "$work" export
if (( inspection_status != 0 )); then
    printf 'Inspection reported errors; export contains the diagnostics.\n' >&2
fi
exit "$inspection_status"
