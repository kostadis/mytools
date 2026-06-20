#!/bin/bash
# Batch-convert all DDEX* PDFs via the two 80B Spark endpoints.
# Two parallel workers (one per endpoint) so both boxes stay busy and the
# endpoint alternates file-by-file. Options per the user's spec + --reuse-responses.
cd /home/kroussos/src/mytools/pdf-translators || exit 1

EP1=http://192.168.1.147:8001/v1   # spark1
EP2=http://192.168.1.121:8001/v1   # spark2
LOGDIR=/home/kroussos/src/mytools/pdf-translators/ddex3-logs
mkdir -p "$LOGDIR"

mapfile -t PDFS < <(find "/mnt/g/My Drive/DriveThru/Wizards of the Coast" -maxdepth 2 -iname "DDEX*.pdf" ! -iname "*.old-*.pdf" | sort)
echo "[$(date +%H:%M:%S)] batch start — ${#PDFS[@]} PDFs"

run_one() {
  local pdf="$1" ep="$2"
  local base; base=$(basename "$pdf" .pdf)
  echo "[$(date +%H:%M:%S)] START  $base   (ep=$ep)"
  python3 pdf_to_5etools_v2.py "$pdf" \
    --provider dgx --endpoint "$ep" \
    --concurrency 20 --output-mode homebrew --type adventure --reuse-responses \
    > "$LOGDIR/$base.log" 2>&1
  echo "[$(date +%H:%M:%S)] DONE   $base   exit=$?"
}

worker() { local ep="$1"; shift; for pdf in "$@"; do run_one "$pdf" "$ep"; done; }

A=(); B=()
for i in "${!PDFS[@]}"; do
  if (( i % 2 == 0 )); then A+=("${PDFS[$i]}"); else B+=("${PDFS[$i]}"); fi
done

worker "$EP1" "${A[@]}" &
p1=$!
worker "$EP2" "${B[@]}" &
p2=$!
wait $p1 $p2
echo "[$(date +%H:%M:%S)] ALL DONE"
