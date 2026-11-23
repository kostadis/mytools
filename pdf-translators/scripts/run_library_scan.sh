#!/usr/bin/env bash
# Re-run this command after interruption; unchanged completed hashes are reused.
set -euo pipefail
if [[ ${1:-} == --help ]]; then
    echo "Usage: $0 [LIBRARY_ROOT] [WORK_FOLDER]"
    echo 'Set SELECTOR_BIN to override the Rust executable.'
    exit 0
fi
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=${1:-'/mnt/g/My Drive/DriveThru'}
work=${2:-"$script_dir/../source-selection-data"}
selector=${SELECTOR_BIN:-"$script_dir/../source-selector/target/debug/rpg-source-select"}
if [[ ! -x $selector ]]; then
    printf 'Selector executable missing: %s\n' "$selector" >&2
    exit 1
fi
mkdir -p -- "$work"
exec 9>"$work/scan.lock"
if ! flock -n 9; then
    printf 'Another library scan is already using %s\n' "$work" >&2
    exit 1
fi
log="$work/scan-progress.log"
printf '%s scan run started; root=%s\n' "$(date -Is)" "$root" | tee -a "$log"
if "$selector" --work-dir "$work" scan --root "$root" \
    > "$work/scan.next.json" 2> >(tee -a "$log" >&2); then
    mv -- "$work/scan.next.json" "$work/scan.json"
    printf '%s scan completed; summary=%s/scan.json\n' "$(date -Is)" "$work" | tee -a "$log"
    cat -- "$work/scan.json"
else
    status=$?
    printf '%s scan stopped (exit %s); rerun to reuse completed hashes\n' "$(date -Is)" "$status" | tee -a "$log" >&2
    exit "$status"
fi
