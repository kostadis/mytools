//! Archive-level checkpoints; native libarchive decodes inside private staging.
use crate::{
    Result, SelectionError, digest_json, inventory,
    markdown::{self, capacity},
    models::*,
    store::Store,
};
use clap::Args;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeSet, VecDeque},
    fs,
    io::{Read, Seek, SeekFrom},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::mpsc,
    time::{Duration, Instant},
};

pub const STAGING: &str = ".rpg-archive-staging";
#[derive(Args, Clone)]
pub struct Options {
    #[arg(long)]
    pub output: PathBuf,
    #[arg(long, default_value = "bsdtar")]
    pub extractor: PathBuf,
    #[arg(long, default_value_t = 4)]
    pub workers: usize,
    #[arg(long, default_value_t = 3600)]
    pub timeout_secs: u64,
    #[arg(long)]
    pub limit: Option<usize>,
    #[arg(long)]
    pub retry_failed: bool,
}
#[derive(Clone, Serialize, Deserialize)]
struct Job {
    source: Source,
    depth: usize,
}
#[derive(Serialize, Deserialize)]
struct Manifest {
    root: PathBuf,
    identity: Value,
    limit: Option<usize>,
    jobs: Vec<Job>,
}
#[derive(Clone, Default, Serialize, Deserialize)]
struct Stats {
    files: usize,
    pdfs: usize,
    bytes: u64,
}
#[derive(Clone, Serialize, Deserialize)]
struct Receipt {
    source: Source,
    depth: usize,
    status: String,
    error: Option<String>,
    destination: PathBuf,
    stage: PathBuf,
    stage_identity: Value,
    stats: Stats,
    children: Vec<Source>,
}
#[derive(Default, Serialize)]
pub struct Status {
    phase: String,
    total: usize,
    completed: usize,
    reused: usize,
    active: usize,
    queued: usize,
    failed: usize,
    conflicts: usize,
    capacity_pending: usize,
    nested_deferred: usize,
    files: usize,
    pdfs: usize,
    expanded_bytes: u64,
    last_archive: String,
}
impl Status {
    pub fn incomplete(&self) -> bool {
        self.capacity_pending > 0
    }
}
struct ExtractorChild(std::process::Child);
impl Drop for ExtractorChild {
    fn drop(&mut self) {
        if !matches!(self.0.try_wait(), Ok(Some(_))) {
            let _ = self.0.kill();
            let _ = self.0.wait();
        }
    }
}
fn real_directory_identity(path: &Path) -> Result<Value> {
    use std::os::unix::fs::MetadataExt;
    let m = fs::symlink_metadata(path)?;
    if !m.is_dir() {
        return Err(SelectionError::Invalid(
            "archive directory is not a real directory".into(),
        ));
    }
    Ok(json!({"device":m.dev(),"inode":m.ino()}))
}
fn reclaim_stage(root: &Path, record: &Receipt) -> Result<()> {
    let rel = record
        .stage
        .strip_prefix(root)
        .map_err(|_| SelectionError::Invalid("stage is outside archive root".into()))?;
    if rel.parent() != Some(Path::new(STAGING)) {
        return Err(SelectionError::Invalid(
            "stage is outside reserved directory".into(),
        ));
    }
    match fs::symlink_metadata(&record.stage) {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(e) => return Err(e.into()),
        Ok(_) => {}
    }
    let path = inventory::checked_path(root, rel)?;
    if real_directory_identity(&path)? != record.stage_identity {
        return Err(SelectionError::Invalid(
            "incomplete archive stage identity changed; preserved".into(),
        ));
    }
    fs::remove_dir_all(path)?;
    Ok(())
}
fn destination(root: &Path, s: &Source) -> PathBuf {
    let p = root.join(&s.relative_path);
    let mut name = p.file_name().unwrap().to_os_string();
    if inventory::path_bytes(Path::new(&name)).len() > 240 {
        name = format!("archive-{}", &s.source_id[..24]).into();
    }
    name.push(".extracted");
    p.with_file_name(name)
}
fn promote(from: &Path, to: &Path) -> Result<()> {
    use std::os::unix::ffi::OsStrExt;
    let a = std::ffi::CString::new(from.as_os_str().as_bytes())
        .map_err(|_| SelectionError::Invalid("NUL in stage".into()))?;
    let b = std::ffi::CString::new(to.as_os_str().as_bytes())
        .map_err(|_| SelectionError::Invalid("NUL in destination".into()))?;
    if unsafe {
        libc::renameat2(
            libc::AT_FDCWD,
            a.as_ptr(),
            libc::AT_FDCWD,
            b.as_ptr(),
            libc::RENAME_NOREPLACE,
        )
    } != 0
    {
        return Err(std::io::Error::last_os_error().into());
    }
    Ok(())
}
fn collect(root: &Path, dir: &Path, stats: &mut Stats, children: &mut Vec<Source>) -> Result<()> {
    for e in fs::read_dir(dir)? {
        let p = e?.path();
        let m = fs::symlink_metadata(&p)?;
        if m.is_dir() {
            collect(root, &p, stats, children)?;
        } else if m.is_file() {
            stats.files += 1;
            stats.bytes = stats.bytes.saturating_add(m.len());
            let ext = p
                .extension()
                .unwrap_or_default()
                .to_string_lossy()
                .to_lowercase();
            if ext == "pdf" {
                stats.pdfs += 1;
            }
            if matches!(ext.as_str(), "zip" | "rar" | "7z") {
                let rel = p
                    .strip_prefix(root)
                    .map_err(|_| SelectionError::Invalid("archive escaped library".into()))?
                    .to_path_buf();
                children.push(Source {
                    source_id: digest_json(&(
                        inventory::path_bytes(root),
                        inventory::path_bytes(&rel),
                    )),
                    relative_path: rel,
                    kind: SourceKind::Archive,
                    publisher: String::new(),
                    product_folder: String::new(),
                    fingerprint: inventory::fingerprint(&p)?,
                    read_error: None,
                    baseline_established: false,
                    artifacts: vec![],
                    metadata: Default::default(),
                });
            }
        } else {
            return Err(SelectionError::Invalid(format!(
                "link/special entry requires manual extraction: {}",
                p.display()
            )));
        }
    }
    Ok(())
}
fn tail(path: &Path) -> String {
    let attempt = (|| -> std::io::Result<String> {
        let mut f = fs::File::open(path)?;
        let n = f.metadata()?.len();
        f.seek(SeekFrom::Start(n.saturating_sub(4096)))?;
        let mut b = Vec::new();
        f.read_to_end(&mut b)?;
        Ok(String::from_utf8_lossy(&b).into_owned())
    })();
    attempt.unwrap_or_default()
}
fn extract(root: &Path, out: &Path, options: &Options, job: &Job) -> Result<(Receipt, bool)> {
    let source = inventory::checked_path(root, &job.source.relative_path)?;
    if inventory::fingerprint(&source)? != job.source.fingerprint {
        return Err(SelectionError::Invalid(
            "archive changed since inventory".into(),
        ));
    }
    let path = out
        .join("records")
        .join(format!("{}.json", job.source.source_id));
    if let Ok(mut prior) = markdown::read_json::<Receipt>(&path) {
        if prior.source.fingerprint != job.source.fingerprint
            || prior.source.source_id != job.source.source_id
            || prior.source.relative_path != job.source.relative_path
            || prior.destination != destination(root, &job.source)
        {
            return Err(SelectionError::Invalid(
                "archive changed since extraction receipt".into(),
            ));
        }
        if prior.status == "complete"
            && real_directory_identity(&prior.destination).ok().as_ref()
                == Some(&prior.stage_identity)
        {
            return Ok((prior, true));
        }
        if prior.status == "extracted" {
            let stage_exists = prior.stage.try_exists()?;
            if stage_exists {
                let rel = prior
                    .stage
                    .strip_prefix(root)
                    .map_err(|_| SelectionError::Invalid("extracted stage escaped root".into()))?;
                inventory::checked_path(root, rel)?;
                if real_directory_identity(&prior.stage)? != prior.stage_identity {
                    return Err(SelectionError::Invalid(
                        "extraction staging identity changed".into(),
                    ));
                }
                promote(&prior.stage, &prior.destination)?;
            }
            if !stage_exists
                && real_directory_identity(&prior.destination).ok().as_ref()
                    != Some(&prior.stage_identity)
            {
                return Err(SelectionError::Invalid(
                    "extraction intent cannot prove destination ownership".into(),
                ));
            }
            prior.status = "complete".into();
            markdown::write_json(&path, &prior)?;
            return Ok((prior, true));
        }
        if matches!(prior.status.as_str(), "failed" | "conflict") && !options.retry_failed {
            return Ok((prior, false));
        }
        if matches!(prior.status.as_str(), "running" | "capacity_pending") {
            reclaim_stage(root, &prior)?;
        } else if matches!(prior.status.as_str(), "failed" | "conflict") {
            markdown::write_json(
                &out.join("history").join(format!(
                    "{}-{}.json",
                    job.source.source_id,
                    chrono::Utc::now().timestamp_nanos_opt().unwrap_or_default()
                )),
                &prior,
            )?;
        }
    }
    let dest = destination(root, &job.source);
    let stage = root.join(STAGING).join(format!(
        "{}-{}-{}",
        &job.source.source_id[..24],
        std::process::id(),
        chrono::Utc::now().timestamp_nanos_opt().unwrap_or_default()
    ));
    let mut record = Receipt {
        source: job.source.clone(),
        depth: job.depth,
        status: "running".into(),
        error: None,
        destination: dest,
        stage,
        stage_identity: Value::Null,
        stats: Stats::default(),
        children: vec![],
    };
    if job.depth > 8 {
        record.status = "depth_limit".into();
        record.error = Some("nested archive depth exceeds eight".into());
        markdown::write_json(&path, &record)?;
        return Ok((record, false));
    }
    if record.destination.try_exists()? {
        record.status = "conflict".into();
        record.error = Some("existing destination preserved".into());
        markdown::write_json(&path, &record)?;
        return Ok((record, false));
    }
    fs::create_dir_all(root.join(STAGING))?;
    if fs::symlink_metadata(root.join(STAGING))?
        .file_type()
        .is_symlink()
    {
        return Err(SelectionError::Invalid("staging symlink refused".into()));
    }
    fs::create_dir(&record.stage)?;
    record.stage_identity = inventory::root_identity(&record.stage)?;
    markdown::write_json(&path, &record)?;
    let log = out
        .join("logs")
        .join(format!("{}.log", job.source.source_id));
    fs::create_dir_all(log.parent().unwrap())?;
    let attempt = (|| -> Result<()> {
        let mut command = Command::new(&options.extractor);
        command
            .args(["-xvf"])
            .arg(&source)
            .args([
                "--safe-writes",
                "--no-same-owner",
                "--no-same-permissions",
                "-C",
            ])
            .arg(&record.stage)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(fs::File::create(&log)?);
        use std::os::unix::process::CommandExt;
        let parent = std::process::id();
        unsafe {
            command.pre_exec(move || {
                if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0 {
                    return Err(std::io::Error::last_os_error());
                }
                if libc::getppid() as u32 != parent {
                    return Err(std::io::Error::other("archive owner exited"));
                }
                Ok(())
            });
        }
        let mut child = ExtractorChild(command.spawn()?);
        let start = Instant::now();
        let mut space = Instant::now();
        loop {
            if let Some(status) = child.0.try_wait()? {
                if !status.success() {
                    return Err(SelectionError::Invalid(format!(
                        "extractor {status}: {}",
                        tail(&log)
                    )));
                }
                break;
            }
            if start.elapsed() > Duration::from_secs(options.timeout_secs) {
                return Err(SelectionError::Invalid(
                    "archive extraction deadline exceeded".into(),
                ));
            }
            if space.elapsed() > Duration::from_secs(1) {
                if capacity::free(root)? < capacity::FLOOR || capacity::free(out)? < capacity::FLOOR
                {
                    return Err(SelectionError::Capacity("20 GiB free-space floor".into()));
                }
                space = Instant::now();
            }
            std::thread::sleep(Duration::from_millis(100));
        }
        let current_source = inventory::checked_path(root, &job.source.relative_path)?;
        if inventory::fingerprint(&current_source)? != job.source.fingerprint {
            return Err(SelectionError::Invalid(
                "archive changed during extraction".into(),
            ));
        }
        // Collect before promotion; remap nested source paths to their final location.
        collect(root, &record.stage, &mut record.stats, &mut record.children)?;
        for child in &mut record.children {
            let p = root.join(&child.relative_path);
            let suffix = p
                .strip_prefix(&record.stage)
                .map_err(|_| SelectionError::Invalid("nested path escaped stage".into()))?;
            child.relative_path = record
                .destination
                .join(suffix)
                .strip_prefix(root)
                .unwrap()
                .into();
            child.source_id = digest_json(&(
                inventory::path_bytes(root),
                inventory::path_bytes(&child.relative_path),
            ));
        }
        record.status = "extracted".into();
        markdown::write_json(&path, &record)?;
        promote(&record.stage, &record.destination)?;
        record.status = "complete".into();
        Ok(())
    })();
    if let Err(e) = attempt {
        if matches!(e, SelectionError::Capacity(_)) {
            reclaim_stage(root, &record)?;
        }
        record.status = if matches!(e, SelectionError::Capacity(_)) {
            "capacity_pending"
        } else {
            "failed"
        }
        .into();
        record.error = Some(e.to_string());
    }
    markdown::write_json(&path, &record)?;
    Ok((record, false))
}

pub fn run(work: &Path, options: Options) -> Result<Status> {
    if options.workers == 0 || options.timeout_secs == 0 || options.limit == Some(0) {
        return Err(SelectionError::Usage(
            "positive workers, timeout and limit required".into(),
        ));
    }
    let db = Store::open_readonly(&work.join("selection.db"))?;
    let inv: InventoryResult = serde_json::from_value(
        db.meta("inventory")?
            .ok_or_else(|| SelectionError::Usage("scan first".into()))?,
    )?;
    let identity = inventory::root_identity(&inv.root)?;
    if db.meta("root_identity")?.as_ref() != Some(&identity) {
        return Err(SelectionError::Invalid(
            "source root identity changed".into(),
        ));
    }
    crate::export::validate_work_dir(&inv.root, &options.output)?;
    markdown::validate_output(&options.output)?;
    fs::create_dir_all(&options.output)?;
    let out = options.output.canonicalize()?;
    let _lease = markdown::lock(&out, "archive-extraction.lock")?;
    let version = Command::new(&options.extractor).arg("--version").output()?;
    if !version.status.success() {
        return Err(SelectionError::Invalid(
            "archive extractor --version failed".into(),
        ));
    }
    let manifest_path = out.join("jobs.json");
    let mut manifest = if manifest_path.exists() {
        markdown::read_json::<Manifest>(&manifest_path)?
    } else {
        let mut jobs: Vec<_> = db
            .sources()?
            .into_iter()
            .filter(|s| s.kind == SourceKind::Archive)
            .map(|source| Job { source, depth: 0 })
            .collect();
        jobs.sort_by(|a, b| a.source.relative_path.cmp(&b.source.relative_path));
        if let Some(n) = options.limit {
            jobs.truncate(n);
        }
        Manifest {
            root: inv.root.clone(),
            identity: identity.clone(),
            limit: options.limit,
            jobs,
        }
    };
    if manifest.root != inv.root || manifest.identity != identity || manifest.limit != options.limit
    {
        return Err(SelectionError::Invalid(
            "archive scope/root changed; use separate output".into(),
        ));
    }
    markdown::write_json(&manifest_path, &manifest)?;
    let mut known: BTreeSet<_> = manifest
        .jobs
        .iter()
        .map(|j| j.source.source_id.clone())
        .collect();
    let mut queue: VecDeque<_> = manifest.jobs.clone().into();
    let (tx, rx) = mpsc::channel();
    let mut status = Status {
        phase: "running".into(),
        total: queue.len(),
        ..Status::default()
    };
    let mut beat = Instant::now();
    while !queue.is_empty() || status.active > 0 {
        while status.active < options.workers && !queue.is_empty() && status.capacity_pending == 0 {
            if capacity::free(&inv.root)? < capacity::FLOOR
                || capacity::free(&out)? < capacity::FLOOR
            {
                status.capacity_pending += 1;
                break;
            }
            if inventory::root_identity(&inv.root)? != identity {
                return Err(SelectionError::Invalid("archive root changed".into()));
            }
            let job = queue.pop_front().unwrap();
            let root = inv.root.clone();
            let out = out.clone();
            let opts = options.clone();
            let sender = tx.clone();
            eprintln!(
                "{} archive started: {}",
                chrono::Utc::now().to_rfc3339(),
                job.source.relative_path.display()
            );
            std::thread::spawn(move || {
                let result = extract(&root, &out, &opts, &job);
                let _ = sender.send((job, result));
            });
            status.active += 1;
        }
        if status.active == 0 && status.capacity_pending > 0 {
            break;
        }
        match rx.recv_timeout(Duration::from_secs(1)) {
            Ok((job, result)) => {
                status.active -= 1;
                status.last_archive = job.source.relative_path.to_string_lossy().into();
                match result {
                    Err(e) => {
                        status.failed += 1;
                        eprintln!("archive failed {}: {e}", job.source.relative_path.display());
                    }
                    Ok((r, reused)) => {
                        eprintln!(
                            "{} archive {}: {} ({} files, {} PDFs){}",
                            chrono::Utc::now().to_rfc3339(),
                            r.status,
                            job.source.relative_path.display(),
                            r.stats.files,
                            r.stats.pdfs,
                            if reused { " reused" } else { "" }
                        );
                        match r.status.as_str() {
                            "complete" => {
                                status.completed += 1;
                                status.reused += usize::from(reused);
                                status.files += r.stats.files;
                                status.pdfs += r.stats.pdfs;
                                status.expanded_bytes =
                                    status.expanded_bytes.saturating_add(r.stats.bytes);
                                for source in r.children {
                                    if known.insert(source.source_id.clone()) {
                                        let child = Job {
                                            source,
                                            depth: job.depth + 1,
                                        };
                                        queue.push_back(child.clone());
                                        manifest.jobs.push(child);
                                    }
                                }
                                markdown::write_json(&manifest_path, &manifest)?;
                            }
                            "conflict" => status.conflicts += 1,
                            "capacity_pending" => status.capacity_pending += 1,
                            "depth_limit" => status.nested_deferred += 1,
                            _ => status.failed += 1,
                        }
                    }
                }
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {}
            Err(e) => return Err(SelectionError::Invalid(e.to_string())),
        }
        status.total = manifest.jobs.len();
        status.queued = queue.len();
        markdown::write_json(&out.join("status.json"), &status)?;
        if beat.elapsed() > Duration::from_secs(30) {
            eprintln!(
                "archives: {} complete, {} active, {} queued, {} failed, {} conflicts, {} PDFs exposed",
                status.completed,
                status.active,
                status.queued,
                status.failed,
                status.conflicts,
                status.pdfs
            );
            beat = Instant::now();
        }
    }
    status.phase = if status.capacity_pending > 0 {
        "capacity_pending"
    } else if status.failed + status.conflicts + status.nested_deferred > 0 {
        "completed_with_exceptions"
    } else {
        "completed"
    }
    .into();
    status.queued = queue.len();
    markdown::write_json(&out.join("status.json"), &status)?;
    markdown::write_json(
        &out.join("extractor.json"),
        &json!({"program":options.extractor,"version":String::from_utf8_lossy(&version.stdout)}),
    )?;
    Ok(status)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    fn job(root: &Path, relative: &str) -> Job {
        let p = root.join(relative);
        fs::create_dir_all(p.parent().unwrap()).unwrap();
        fs::write(&p, "fixture").unwrap();
        Job {
            depth: 0,
            source: Source {
                source_id: digest_json(&relative),
                relative_path: relative.into(),
                kind: SourceKind::Archive,
                publisher: String::new(),
                product_folder: String::new(),
                fingerprint: inventory::fingerprint(&p).unwrap(),
                read_error: None,
                baseline_established: false,
                artifacts: vec![],
                metadata: Default::default(),
            },
        }
    }
    fn wait(path: &Path) {
        let start = Instant::now();
        while !path.exists() {
            assert!(start.elapsed() < Duration::from_secs(5));
            std::thread::sleep(Duration::from_millis(10));
        }
    }
    #[test]
    fn free_space_probe_error_kills_and_reaps_running_extractor() {
        let root = tempfile::tempdir().unwrap();
        let out = tempfile::tempdir().unwrap();
        let j = job(root.path(), "book.zip");
        let marker = root.path().join("pid");
        let program = root.path().join("extractor");
        fs::write(
            &program,
            format!(
                "#!/bin/sh\necho $$ > '{}'\nexec sleep 60\n",
                marker.display()
            ),
        )
        .unwrap();
        fs::set_permissions(&program, fs::Permissions::from_mode(0o755)).unwrap();
        let opts = Options {
            output: out.path().into(),
            extractor: program,
            workers: 1,
            timeout_secs: 10,
            limit: None,
            retry_failed: false,
        };
        let a = root.path().to_path_buf();
        let b = out.path().to_path_buf();
        let worker = std::thread::spawn(move || extract(&a, &b, &opts, &j));
        wait(&marker);
        let pid: i32 = fs::read_to_string(marker).unwrap().trim().parse().unwrap();
        fs::remove_dir_all(out.path()).unwrap();
        worker.join().unwrap().unwrap();
        let alive = unsafe { libc::kill(pid, 0) } == 0;
        if alive {
            unsafe {
                libc::kill(pid, libc::SIGKILL);
                libc::waitpid(pid, std::ptr::null_mut(), 0);
            }
        }
        assert!(
            !alive,
            "extractor survived its worker's failed free-space query"
        );
    }
    #[test]
    fn moved_source_parent_cannot_redirect_archive_publication() {
        let root = tempfile::tempdir().unwrap();
        let out = tempfile::tempdir().unwrap();
        let saved = tempfile::tempdir().unwrap();
        let j = job(root.path(), "Folder/book.zip");
        let marker = root.path().join("ready");
        let gate = root.path().join("release");
        let program = root.path().join("extractor");
        fs::write(
            &program,
            format!(
                "#!/bin/sh\ntouch '{}'\nwhile [ ! -e '{}' ]; do sleep 0.02; done\n",
                marker.display(),
                gate.display()
            ),
        )
        .unwrap();
        fs::set_permissions(&program, fs::Permissions::from_mode(0o755)).unwrap();
        let opts = Options {
            output: out.path().into(),
            extractor: program,
            workers: 1,
            timeout_secs: 10,
            limit: None,
            retry_failed: false,
        };
        let a = root.path().to_path_buf();
        let b = out.path().to_path_buf();
        let worker = std::thread::spawn(move || extract(&a, &b, &opts, &j));
        wait(&marker);
        let moved = saved.path().join("Folder");
        fs::rename(root.path().join("Folder"), &moved).unwrap();
        std::os::unix::fs::symlink(&moved, root.path().join("Folder")).unwrap();
        fs::write(gate, "").unwrap();
        let (r, _) = worker.join().unwrap().unwrap();
        assert_ne!(r.status, "complete");
        assert!(!moved.join("book.zip.extracted").exists());
    }
}
