#!/usr/bin/env bash
# Sequence existing Rust commands; all archive/PDF I/O stays in the selector.
set -euo pipefail
if [[ ${1:-} == --help ]]; then
    echo "Usage: $0 DATA_ROOT SELECTOR_BIN [LIBRARY_ROOT]"
    exit 0
fi
data_root=$(realpath -- "${1:?DATA_ROOT required}")
selector_bin=$(realpath -- "${2:?SELECTOR_BIN required}")
library_root=${3:-/mnt/winshare}
archive_out="$data_root/winshare-archive-extraction"
markdown_out="$data_root/winshare-current-markdown"
scan_state="$data_root/winshare-current-state"
archive_unit=rpg-archive-extraction.service
markdown_unit=rpg-markdown-winshare.service
workflow_path="$archive_out/markdown-followup.json"
exec {workflow_fd}>"$archive_out/markdown-followup.lock"
flock -n "$workflow_fd"

set_phase() {
    python3 - "$workflow_path" "$1" "${2:-}" <<'PY'
import datetime,json,os,sys
from pathlib import Path
p=Path(sys.argv[1]);t=p.with_suffix('.tmp')
with t.open('w') as f:
    json.dump({'phase':sys.argv[2],'detail':sys.argv[3],'updated_at':datetime.datetime.now(datetime.timezone.utc).isoformat()},f,indent=2)
    f.flush();os.fsync(f.fileno())
os.replace(t,p)
PY
    printf '%s %s %s\n' "$(date -u +%FT%TZ)" "$1" "${2:-}"
}
archive_ready() {
    python3 - "$archive_out/status.json" <<'PY'
import json,sys
try:
    s=json.load(open(sys.argv[1]));ready=s.get('phase') in ('completed','completed_with_exceptions') and s.get('active')==0 and s.get('queued')==0
except (OSError,ValueError):ready=False
sys.exit(0 if ready else 1)
PY
}
service_busy() {
    local state
    state=$(systemctl --user show "$1" -p ActiveState --value)
    [[ $state == active || $state == activating || $state == deactivating ]]
}
follow_conversion() {
    while service_busy "$markdown_unit"; do sleep 15; done
    python3 - "$markdown_out/continuous-status.json" <<'PY'
import json,sys
s=json.load(open(sys.argv[1]))
assert s.get('phase') in ('completed','completed_with_exceptions') and s.get('active')==0 and s.get('queued')==0,s
PY
    set_phase completed 'PDF conversion finished; inspect continuous-status.json for exceptions.'
}
previous_phase=$(python3 - "$workflow_path" <<'PY'
import json,sys
try:print(json.load(open(sys.argv[1])).get('phase',''))
except (OSError,ValueError):print('')
PY
)
trap 'rc=$?; if (( rc != 0 )); then set_phase failed "Workflow stopped with exit $rc; see markdown-followup.log." || true; fi' EXIT
if [[ $previous_phase == completed ]]; then exit 0; fi
if [[ $previous_phase == converting ]]; then follow_conversion; exit 0; fi

set_phase waiting_archives 'Waiting for all archive workers and nested jobs to finish.'
while :; do
    if archive_ready && ! service_busy "$archive_unit"; then
        exec {archive_fd}>"$archive_out/archive-extraction.lock"
        if flock -n "$archive_fd"; then
            if archive_ready; then break; fi
            flock -u "$archive_fd"
        fi
        exec {archive_fd}>&-
    fi
    sleep 15
done
# Hold the archive lease through scan/conversion so a retry cannot add PDFs mid-run.
while service_busy "$markdown_unit"; do
    set_phase waiting_existing_converter 'Waiting for the earlier converter to release its state.'
    sleep 15
done
set_phase scanning 'Refreshing the current-library inventory, including extracted PDFs.'
"$selector_bin" --work-dir "$scan_state" scan --root "$library_root" --current-library \
    >"$archive_out/post-extraction-scan.json" 2>"$archive_out/post-extraction-scan.log"
set_phase starting_conversion 'Starting four Rust PDF workers with existing extraction checkpoints.'
systemd-run --user --unit=rpg-markdown-winshare --collect \
    --property="WorkingDirectory=$(dirname -- "$data_root")" \
    --property=Restart=on-abnormal --property=RestartSec=30s \
    --property="StandardOutput=append:$markdown_out/continuous.log" \
    --property="StandardError=append:$markdown_out/continuous.log" \
    "$selector_bin" --work-dir "$scan_state" markdown-continuous --output "$markdown_out" --workers 4
python3 - "$markdown_out" "$scan_state" "$selector_bin" <<'PY'
import datetime,hashlib,json,shutil,sqlite3,subprocess,sys
from pathlib import Path
out,state,binary=map(Path,sys.argv[1:]);p=out/'deployment.json'
d=json.loads(p.read_text());backup=out/'deployment-before-archive-followup.json'
if not backup.exists():shutil.copy2(p,backup)
c=sqlite3.connect(f'file:{state}/selection.db?mode=ro',uri=True)
sources=[json.loads(b) for b, in c.execute('select body from sources where active=1')]
pid=int(subprocess.check_output(['systemctl','--user','show','rpg-markdown-winshare.service','-p','MainPID','--value'],text=True).strip())
d.update(binary=str(binary),binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),commit='53fbbe3',pid=pid,workers=4,tests_passed=167,started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),trigger='archive extraction completed',scope={'pdfs':sum(s['kind']=='pdf' for s in sources),'archives':sum(s['kind']=='archive' for s in sources),'pdf_bytes':sum(s['fingerprint']['size'] for s in sources if s['kind']=='pdf')})
p.write_text(json.dumps(d,indent=2))
PY
set_phase converting 'Four-worker Markdown conversion is running; prior outputs and caches are retained.'
follow_conversion
