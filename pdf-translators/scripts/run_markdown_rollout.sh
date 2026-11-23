#!/usr/bin/env bash
# Resume a completed inventory's metadata selection and full eligible conversion.
# No models, OCR, archives, historical index, or 5etools conversion are invoked.
set -euo pipefail
if [[ ${1:-} == --help ]]; then
    echo "Usage: $0 [COMPLETED_SCAN_STATE] [MARKDOWN_OUTPUT]"
    echo 'Set SELECTOR_BIN to a verified Rust executable; publication batches default to 100 completed jobs.'
    exit 0
fi
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
state=${1:-"$script_dir/../source-selection-data"}
out=${2:-"$script_dir/../source-selection-data/full-library-markdown"}
selector=${SELECTOR_BIN:-"$script_dir/../source-selector/target/release/rpg-source-select"}
if [[ ! -x $selector || ! -f $state/selection.db ]]; then
    echo 'A verified selector and completed scan database are required.' >&2
    exit 1
fi
mkdir -p -- "$out"
out=$(cd -- "$out" && pwd)
exec 9>"$out/rollout.lock"
flock -n 9 || { echo 'Another rollout already owns this output directory.' >&2; exit 1; }
exec >>"$out/rollout.log" 2>&1
phase() {
    printf '{"phase":"%s","at":"%s","pid":%s}\n' "$1" "$(date -u +%FT%TZ)" "$$" > "$out/.rollout-state-$$"
    mv -- "$out/.rollout-state-$$" "$out/rollout-state.json"
    printf '%s rollout: %s\n' "$(date -u +%FT%TZ)" "$1"
}
trap 'exit_status=$?; if ((exit_status)); then phase failed; printf "rollout stopped with exit %s; rerun to reuse checkpoints\n" "$exit_status"; fi' EXIT
phase metadata
# An already-running selection can finish first. The OS lock also releases on a crash.
until flock -n "$out/selection.lock" true; do
    printf '%s waiting for active metadata selection; see selection-progress.log\n' "$(date -u +%FT%TZ)"
    sleep 30
done
if ! python3 - "$state" "$out" <<'PY'
import sys,sqlite3,json,pathlib,datetime
try:
 state,out=map(pathlib.Path,sys.argv[1:]);c=sqlite3.connect(f'file:{state / "selection.db"}?mode=ro',uri=True)
 inv=json.loads(c.execute('select body from meta where key=?',('inventory',)).fetchone()[0]);sid=json.loads((out/'selection/current.json').read_text());s=json.loads((out/'selection/generations'/sid/'markdown-selection.json').read_text())
 assert s['source_root']==inv['root'] and datetime.datetime.fromisoformat(s['created'])>=datetime.datetime.fromisoformat(inv['finished'])
 print('Reusing completed metadata snapshot',sid)
except Exception:
 sys.exit(1)
PY
then
    "$selector" --work-dir "$state" markdown-select --output "$out" > "$out/selection-run.next.json" 2>> "$out/selection-progress.log"
    mv -- "$out/selection-run.next.json" "$out/selection-run.json"
fi
python3 - "$out" <<'PY'
import pathlib,json,shutil,sys
out=pathlib.Path(sys.argv[1]);sid=json.loads((out/'selection/current.json').read_text());s=json.loads((out/'selection/generations'/sid/'markdown-selection.json').read_text());sizes={c['sha256']:c['source']['fingerprint']['size'] for r in s['records'] for c in r['candidates'] if c.get('sha256')};unique={r['sha256'] for r in s['ready']};needed=sum(sizes[h] for h in unique if not (out/'cache/sources'/f'{h}.pdf').exists());free=shutil.disk_usage(out).free
summary={'selection_id':sid,'eligible_works':len(s['ready']),'physical_pages':sum(r['page_count'] for r in s['ready']),'deferred_or_baseline_groups':sum(r['status']!='ready' for r in s['records']),'archives':s['archives'],'new_source_cache_GiB':round(needed/2**30,2),'free_GiB':round(free/2**30,2),'publication_batch':100,'workers':2}
(out/'rollout-preflight.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2),flush=True)
if needed+20*2**30>free:raise SystemExit('Insufficient local space for selected source cache plus 20 GiB reserve; no conversion started.')
PY
phase conversion
"$selector" markdown-convert --output "$out" --publish-next-to-source --workers 2 --chunk-pages 20 --publish-every 100 --retry-failed > "$out/conversion-run.json"
python3 - "$out" <<'PY'
import json,pathlib,sys
out=pathlib.Path(sys.argv[1]);r=json.loads((out/'conversion-run.json').read_text());print(json.dumps({'published_books':r['published_books'],'failed':r['failed'],'needs_ocr_or_visual_review':r['needs_ocr_or_visual_review'],'publication_pending':r['publication']['pending']},indent=2),flush=True)
PY
if python3 - "$out" <<'PY'
import json,pathlib,sys
r=json.loads((pathlib.Path(sys.argv[1])/'conversion-run.json').read_text());sys.exit(0 if r['failed'] or r['publication']['pending'] else 1)
PY
then phase completed_with_exceptions; else phase completed; fi
