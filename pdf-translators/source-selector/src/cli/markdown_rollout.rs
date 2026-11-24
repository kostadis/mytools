use super::*;
use crate::{
    inventory::root_identity,
    markdown::{self, Snapshot, adjacent::ControlDirectory},
};
use std::{
    fs::File,
    io::Write,
    process::{Command, Stdio},
    time::Duration,
};

fn phase(dir: &ControlDirectory, log: &mut File, name: &str) -> Result<()> {
    let now = chrono::Utc::now().to_rfc3339();
    dir.write_control(
        Path::new("rollout-state.json"),
        &serde_json::to_vec_pretty(&json!({"phase":name,"at":now,"pid":std::process::id()}))?,
    )?;
    writeln!(log, "{now} rollout: {name}")?;
    log.sync_data()?;
    Ok(())
}
fn child(
    dir: &ControlDirectory,
    log: &File,
    args: &[OsString],
    report: &str,
) -> Result<serde_json::Value> {
    let (name, capture) = dir.create_capture()?;
    let sync = capture.try_clone()?;
    let status = Command::new(std::env::current_exe()?)
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::from(capture))
        .stderr(Stdio::from(log.try_clone()?))
        .status()?;
    sync.sync_all()?;
    if !status.success() {
        dir.commit_control(&name, Path::new("failed-command-output.json"))?;
        return Err(SelectionError::Invalid(format!(
            "rollout child failed ({status}); see rollout.log/selection-progress.log"
        )));
    }
    let value = serde_json::from_slice(
        &dir.read(&name)?
            .ok_or_else(|| SelectionError::Invalid("missing captured report".into()))?,
    )?;
    dir.commit_control(&name, Path::new(report))?;
    Ok(value)
}
pub(super) fn run(work: &Path, inventory: &InventoryResult, out: &Path) -> Result<ExitCode> {
    // No launcher-owned file or directory is written before both guards pass.
    let out = validate_work_dir(&inventory.root, out)?;
    markdown::validate_output(&out)?;
    fs::create_dir_all(&out)?;
    let out = validate_work_dir(&inventory.root, &out)?;
    markdown::validate_output(&out)?;
    let dir = ControlDirectory::open(&out, &root_identity(&out)?, Path::new(""))?;
    let _owner = dir.lock_named(Path::new("rollout.lock"))?;
    let mut log = dir.append_log(Path::new("rollout.log"))?;
    println!("Rollout log: {}", out.join("rollout.log").display());
    let result = (|| -> Result<()> {
        phase(&dir, &mut log, "metadata")?;
        loop {
            match dir.lock_named(Path::new("selection.lock")) {
                Ok(lock) => {
                    drop(lock);
                    break;
                }
                Err(SelectionError::Invalid(e)) if e.contains("locked") => {
                    writeln!(
                        log,
                        "waiting for active metadata selection; progress is checkpointed"
                    )?;
                    log.flush()?;
                    std::thread::sleep(Duration::from_secs(30));
                }
                Err(e) => return Err(e),
            }
        }
        // Always recalculate from current review/evidence/hints. Scan timestamps
        // alone cannot prove an existing Ready queue still honors user rulings.
        let selection_log = dir.append_log(Path::new("selection-progress.log"))?;
        child(
            &dir,
            &selection_log,
            &[
                "--work-dir".into(),
                work.as_os_str().to_owned(),
                "markdown-select".into(),
                "--output".into(),
                out.as_os_str().to_owned(),
            ],
            "selection-run.json",
        )?;
        let _selection = dir.lock_named(Path::new("selection.lock"))?;
        let s: Snapshot = markdown::selection::load_current(&out)?;
        let mut sizes = std::collections::BTreeMap::new();
        for c in s.records.iter().flat_map(|r| &r.candidates) {
            if let Some(h) = &c.sha256 {
                sizes.insert(h.clone(), c.source.fingerprint.size);
            }
        }
        let hashes: std::collections::BTreeSet<_> =
            s.ready.iter().map(|r| r.sha256.clone()).collect();
        let needed: u64 = hashes
            .iter()
            .filter(|h| !out.join("cache/sources").join(format!("{h}.pdf")).exists())
            .map(|h| sizes.get(h).copied().unwrap_or(0))
            .sum();
        use std::os::unix::ffi::OsStrExt;
        let path = std::ffi::CString::new(out.as_os_str().as_bytes())
            .map_err(|_| SelectionError::Invalid("invalid output path".into()))?;
        let mut info = std::mem::MaybeUninit::<libc::statvfs>::uninit();
        if unsafe { libc::statvfs(path.as_ptr(), info.as_mut_ptr()) } != 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        let info = unsafe { info.assume_init() };
        let free = (info.f_bavail as u128) * (info.f_frsize as u128);
        let preflight = json!({"selection_id":s.snapshot_id,"eligible_works":s.ready.len(),"physical_pages":s.ready.iter().map(|r|u64::from(r.page_count)).sum::<u64>(),"deferred_or_baseline_groups":s.records.iter().filter(|r|r.status!="ready").count(),"archives":s.archives,"new_source_cache_bytes":needed,"free_bytes":free,"workers":2,"publication_batch":100});
        dir.write_control(
            Path::new("rollout-preflight.json"),
            &serde_json::to_vec_pretty(&preflight)?,
        )?;
        writeln!(log, "{}", serde_json::to_string_pretty(&preflight)?)?;
        if u128::from(needed) + 20u128 * 1024 * 1024 * 1024 > free {
            return Err(SelectionError::Invalid(
                "insufficient local space for selected source cache plus 20 GiB reserve".into(),
            ));
        }
        drop(_selection);
        phase(&dir, &mut log, "conversion")?;
        writeln!(
            log,
            "starting eligible queue; failed jobs retry on explicit reruns, up to the three-failure ceiling"
        )?;
        let r = child(
            &dir,
            &log,
            &[
                "markdown-convert".into(),
                "--output".into(),
                out.as_os_str().to_owned(),
                "--publish-next-to-source".into(),
                "--workers".into(),
                "2".into(),
                "--chunk-pages".into(),
                "20".into(),
                "--publish-every".into(),
                "100".into(),
                "--expected-selection".into(),
                s.snapshot_id.clone().into(),
                "--retry-failed".into(),
            ],
            "conversion-run.json",
        )?;
        writeln!(
            log,
            "{}",
            serde_json::to_string(
                &json!({"published_books":r["published_books"],"failed":r["failed"],"needs_ocr_or_visual_review":r["needs_ocr_or_visual_review"],"publication_pending":r["publication"]["pending"]})
            )?
        )?;
        let exceptions = r["publication"]["pending"].as_bool().unwrap_or(true)
            || r["failed"].as_u64().unwrap_or(0) > 0;
        phase(
            &dir,
            &mut log,
            if exceptions {
                "completed_with_exceptions"
            } else {
                "completed"
            },
        )?;
        Ok(())
    })();
    if let Err(e) = result {
        let _ = phase(&dir, &mut log, "failed");
        let _ = writeln!(log, "{e}; rerun the same command to resume checkpoints");
        return Err(e);
    }
    Ok(ExitCode::SUCCESS)
}
