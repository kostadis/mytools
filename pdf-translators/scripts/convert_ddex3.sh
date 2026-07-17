#!/usr/bin/env bash
#
# Batch-convert the DDEX3 (Rage of Demons) season of D&D Adventurers League
# modules to 5etools homebrew JSON via the DGX Spark.
#
# Targets the numbered DDEX3-NN adventure directories under $BASE. The
# "DDEX3 Rage of Demons Player's Pack" directory is intentionally NOT included:
# it holds player options / logsheets / character sheets, not an adventure, so
# `--type adventure` does not apply to it.
#
# Each module is run on its own, one at a time. `--concurrency 20` already fans
# every chunk of a single module at the Spark's one cross-box slot, so running
# modules in parallel would only oversubscribe the box and cause the request
# timeouts this exists to avoid. Sequential is deliberate.
#
# Output (homebrew mode, no --out) lands next to each PDF as <stem>.json. An
# existing <stem>.json is treated as "already done" and skipped unless --force.
#
# Usage:
#   ./convert_ddex3.sh                  # convert every not-yet-done module
#   ./convert_ddex3.sh --list           # show what would run, do nothing
#   ./convert_ddex3.sh --force          # reconvert even if <stem>.json exists
#   ./convert_ddex3.sh --skip 'DDEX3-07*'  # exclude module(s) by dir-name glob
#
# DDEX3-05 is skipped by default: it is being processed in another run and has
# no <stem>.json yet, so output-existence won't catch it. Edit SKIP_PATTERNS
# below (or pass more --skip globs) to adjust.
#
set -uo pipefail

BASE="/mnt/g/My Drive/DriveThru/Wizards of the Coast"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONVERTER="$SCRIPT_DIR/../converters/pdf_to_5etools_v2.py"
LOG_DIR="$SCRIPT_DIR/../ddex3-logs"

# Exact conversion parameters requested.
CONVERT_ARGS=(--reuse-responses --provider dgx --concurrency 20 --output-mode homebrew --type adventure)

# Module directories to exclude, matched against the dir basename as shell
# globs. DDEX3-05 is in progress elsewhere; --skip appends more at runtime.
SKIP_PATTERNS=("DDEX3-05*")

LIST_ONLY=0
FORCE=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --list)  LIST_ONLY=1 ;;
        --force) FORCE=1 ;;
        --skip)  shift; [[ $# -gt 0 ]] || { echo "--skip needs a glob" >&2; exit 2; }
                 SKIP_PATTERNS+=("$1") ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

mkdir -p "$LOG_DIR"

# Find the canonical PDF in a module directory: the single *.pdf that is not a
# *.old-001.pdf backup. Echoes the path, or nothing if none/ambiguous.
canonical_pdf() {
    local dir="$1" pdf found=""
    for pdf in "$dir"/*.pdf; do
        [[ -e "$pdf" ]] || continue
        case "$pdf" in
            *.old-001.pdf) continue ;;
        esac
        if [[ -n "$found" ]]; then
            echo "    [ambiguous] >1 canonical PDF in $(basename "$dir")" >&2
            return 1
        fi
        found="$pdf"
    done
    [[ -n "$found" ]] && printf '%s\n' "$found"
}

shopt -s nullglob
mapfile -t DIRS < <(printf '%s\n' "$BASE"/DDEX3-*/ | sort)
shopt -u nullglob

if [[ ${#DIRS[@]} -eq 0 ]]; then
    echo "No DDEX3-NN directories found under: $BASE" >&2
    exit 1
fi

ok=(); failed=(); skipped=()
echo "== DDEX3 batch: ${#DIRS[@]} module directories =="

for dir in "${DIRS[@]}"; do
    dir="${dir%/}"
    name="$(basename "$dir")"

    excluded=0
    for pat in "${SKIP_PATTERNS[@]}"; do
        # shellcheck disable=SC2053
        [[ "$name" == $pat ]] && { excluded=1; break; }
    done
    if [[ $excluded -eq 1 ]]; then
        echo "[skip] $name — excluded (--skip / SKIP_PATTERNS)"
        skipped+=("$name (excluded)")
        continue
    fi

    pdf="$(canonical_pdf "$dir")" || { failed+=("$name (ambiguous PDF)"); continue; }
    if [[ -z "$pdf" ]]; then
        echo "[skip] $name — no PDF found"
        skipped+=("$name (no PDF)")
        continue
    fi

    out="${pdf%.pdf}.json"
    if [[ $FORCE -eq 0 && -f "$out" ]]; then
        echo "[skip] $name — output exists: $(basename "$out")"
        skipped+=("$name (already done)")
        continue
    fi

    if [[ $LIST_ONLY -eq 1 ]]; then
        echo "[would run] $name"
        echo "            $(basename "$pdf") -> $(basename "$out")"
        continue
    fi

    log="$LOG_DIR/$(basename "${pdf%.pdf}").log"
    echo "----------------------------------------------------------------"
    echo "[run] $name"
    echo "      pdf: $pdf"
    echo "      log: $log"
    if python3 "$CONVERTER" "$pdf" "${CONVERT_ARGS[@]}" 2>&1 | tee "$log"; then
        echo "[ok]  $name"
        ok+=("$name")
    else
        echo "[FAIL] $name — see $log"
        failed+=("$name")
    fi
done

echo "================================================================"
echo "Summary: ${#ok[@]} ok, ${#failed[@]} failed, ${#skipped[@]} skipped"
[[ ${#ok[@]}      -gt 0 ]] && printf '  ok:      %s\n' "${ok[@]}"
[[ ${#skipped[@]} -gt 0 ]] && printf '  skipped: %s\n' "${skipped[@]}"
[[ ${#failed[@]}  -gt 0 ]] && printf '  FAILED:  %s\n' "${failed[@]}"
# Non-zero exit if anything failed, so callers / CI can detect it.
[[ ${#failed[@]} -eq 0 ]]
