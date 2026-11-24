#!/usr/bin/env bash
# Operational convenience wrapper; all validation, locking and I/O are Rust.
set -euo pipefail
if [[ ${1:-} == --help ]]; then
    echo "Usage: $0 [COMPLETED_SCAN_STATE] [MARKDOWN_OUTPUT]"
    echo 'Set SELECTOR_BIN to a verified Rust executable.'
    exit 0
fi
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
state=${1:-"$script_dir/../source-selection-data"}
out=${2:-"$script_dir/../source-selection-data/full-library-markdown"}
selector=${SELECTOR_BIN:-"$script_dir/../source-selector/target/release/rpg-source-select"}
exec "$selector" --work-dir "$state" markdown-rollout --output "$out"
