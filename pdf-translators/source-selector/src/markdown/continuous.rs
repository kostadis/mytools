//! A single authority owner consumes bounded metadata requests and extraction jobs.
use super::*;
use super::{
    capacity::{self, Reservations},
    conversion,
    worker::{Engine, Job, WorkerResult},
};
use crate::{
    digest_json,
    inventory::{checked_path, fingerprint},
    models::*,
    store::Store,
};
use clap::Args;
use std::{
    collections::{BTreeMap, BTreeSet, VecDeque},
    process::{Child, Command, Stdio},
    time::{Duration, Instant},
};
#[derive(Clone, Debug, Args)]
pub struct Options {
    #[arg(long)]
    pub output: PathBuf,
    #[arg(long, default_value_t = 300)]
    pub metadata_timeout_secs: u64,
    #[arg(long, hide = true)]
    pub metadata_worker: Option<PathBuf>,
    #[arg(long, default_value = "pdftotext")]
    pub pdftotext: PathBuf,
    #[arg(long)]
    pub retry_failed: bool,
}
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct Status {
    pub run_id: String,
    pub phase: String,
    pub metadata_checked: usize,
    pub metadata_total: usize,
    pub groups_total: usize,
    pub groups_resolved: usize,
    pub groups_deferred: usize,
    pub groups_pending: usize,
    pub queued: usize,
    pub active: usize,
    pub published: usize,
    pub needs_ocr: usize,
    pub failures: usize,
    pub output_conflicts: usize,
    pub capacity_pending: usize,
    pub manifest_discovery_complete: bool,
}
#[derive(Clone, Serialize, Deserialize)]
pub struct MetadataRequest {
    pub id: String,
    pub work: PathBuf,
    pub output: PathBuf,
    pub root: PathBuf,
    pub source: Source,
}
#[derive(Clone, Serialize, Deserialize)]
pub struct MetadataResult {
    pub id: String,
    pub candidate: Candidate,
}
#[derive(Clone, Serialize, Deserialize)]
struct Resolution {
    snapshot: Snapshot,
    publication: Option<publication::Publication>,
}
#[derive(Clone, Default, Serialize, Deserialize)]
struct JobState {
    attempts: usize,
    status: String,
    error: Option<String>,
}
struct MetadataRunning {
    child: Child,
    request: MetadataRequest,
    start: Instant,
}
struct Extracting {
    child: Child,
    job: Job,
    start: Instant,
}
fn empty(source: &Source, error: String) -> Candidate {
    Candidate {
        source: source.clone(),
        sha256: None,
        page_count: None,
        dates: dates::DateEvidence::default(),
        error: Some(error),
    }
}
fn job_id(r: &Ready, e: &Engine) -> String {
    digest_json(&(&r.sha256, &e.id, r.page_count))
}
fn spawn(program: &Path, command: &str, flag: &str, request: &Path, log: &Path) -> Result<Child> {
    fs::create_dir_all(log.parent().unwrap())?;
    let log = fs::OpenOptions::new().create(true).append(true).open(log)?;
    let mut cmd = Command::new(program);
    cmd.args([command, flag])
        .arg(request)
        .stdin(Stdio::null())
        .stdout(log.try_clone()?)
        .stderr(log);
    use std::os::unix::process::CommandExt;
    cmd.process_group(0);
    if command == "markdown-metadata-worker" {
        let parent = std::process::id();
        unsafe {
            cmd.pre_exec(move || {
                if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0 {
                    return Err(std::io::Error::last_os_error());
                }
                if libc::getppid() as u32 != parent {
                    return Err(std::io::Error::other(
                        "coordinator exited before metadata startup",
                    ));
                }
                Ok(())
            });
        }
    }
    Ok(cmd.spawn()?)
}
/// Only raw/hash caches and a request-bound result are written by this child.
pub fn metadata_worker(path: &Path) -> Result<()> {
    let r: MetadataRequest = read_json(path)?;
    let _lease = lock(&r.output, "metadata-worker.lock")?;
    let db = Store::open_readonly(&r.work.join("selection.db"))?;
    let mut cache = Store::open(&r.output.join("metadata.db"))?;
    let key = digest_json(&(1, &r.source.fingerprint));
    let prior = db
        .get_cached(&r.source.source_id, "hash", &key)?
        .or(cache.get_cached(&r.source.source_id, "verified_hash", &key)?)
        .and_then(|v| v.as_str().map(str::to_owned))
        .or(r.source.fingerprint.sha256.clone());
    let mut observed = r.source.clone();
    let changed = checked_path(&r.root, &observed.relative_path)
        .and_then(|p| fingerprint(&p))
        .map(|fp| {
            let different = fp != observed.fingerprint;
            observed.fingerprint = fp;
            different
        });
    let candidate = match changed {
        Err(e) => empty(&observed, e.to_string()),
        Ok(changed) => {
            let mut c = metadata::probe(&r.root, &observed, &db, &mut cache);
            if changed && (prior.is_none() || c.sha256 != prior) {
                c.error = Some(
                    "needs_regroup: known source observation changed without identical-byte proof"
                        .into(),
                );
            }
            c
        }
    };
    write_json(
        &r.output
            .join("metadata-results")
            .join(format!("{}.json", r.id)),
        &MetadataResult {
            id: r.id,
            candidate,
        },
    )
}
fn persist_status(out: &Path, status: &Status) -> Result<()> {
    write_json(&out.join("continuous-status.json"), status)
}
fn authority_token(db: &Store) -> Result<String> {
    Ok(digest_json(&(
        db.records::<Value>("decisions")?,
        db.records::<Value>("hints")?,
        db.records::<Value>("evidence")?,
    )))
}
fn resolution_key(run: &str, group: &str) -> String {
    format!("{run}-{group}")
}
fn commit_group(
    db: &Store,
    ledger: &mut Store,
    out: &Path,
    root: &Path,
    group: &Group,
    candidates: Vec<Candidate>,
    run: &str,
) -> Result<Resolution> {
    let _gate = db.authority_guard()?;
    let snapshot = selection::resolve_group(db, out, root, group, candidates, &Value::Null)?;
    let resolution = Resolution {
        snapshot,
        publication: None,
    };
    ledger.put_record(
        "continuous_groups",
        &resolution_key(run, &group.group_id),
        &resolution,
    )?;
    Ok(resolution)
}
#[allow(clippy::too_many_arguments)]
fn publish_group(
    db: &Store,
    ledger: &mut Store,
    out: &Path,
    group: &Group,
    run: &str,
    resolution: &mut Resolution,
    engine: &Engine,
    session: &mut adjacent::Session,
) -> Result<()> {
    // Long parsing/staging happens outside the authority gate. The final pass is
    // observation-cached; reread authority under the gate before installing.
    let expected = resolution.snapshot.snapshot_id.clone();
    let fresh = selection::resolve_group(
        db,
        out,
        &resolution.snapshot.source_root,
        group,
        resolution.snapshot.records[0].candidates.clone(),
        &Value::Null,
    )?;
    if fresh.snapshot_id != expected {
        resolution.snapshot = fresh;
        resolution.publication = None;
    }
    session.set_authority_database(db.path());
    let p = publication::publish_snapshot(out, engine, &resolution.snapshot, Some(session), false)?;
    eprintln!(
        "group {}: {} sibling Markdown published, revision {}",
        group.group_id, p.books, resolution.snapshot.snapshot_id
    );
    resolution.publication = Some(p);
    ledger.put_record(
        "continuous_groups",
        &resolution_key(run, &group.group_id),
        resolution,
    )?;
    Ok(())
}
fn current_view(
    db: &Store,
    expected_authority: &str,
    out: &Path,
    run: &str,
    resolutions: &BTreeMap<String, Resolution>,
    pending: bool,
) -> Result<bool> {
    let entries: Vec<_> = resolutions
        .values()
        .filter_map(|r| r.publication.as_ref())
        .flat_map(|p| p.catalog.iter())
        .filter(|e| e["status"] == "searchable_with_flags")
        .cloned()
        .collect();
    let catalog =
        serde_json::json!({"schema_version":2,"run_id":run,"pending":pending,"books":entries});
    let id = digest_json(&catalog);
    let dir = out.join("corpus/generations").join(&id);
    fs::create_dir_all(dir.join("books"))?;
    for entry in &entries {
        let work = entry["work"]["work_id"].as_str().unwrap();
        safe_id(work)?;
        let artifact = entry["artifact"].as_str().unwrap();
        safe_id(artifact)?;
        for ext in ["md", "json"] {
            let target = dir.join("books").join(format!("{work}.{ext}"));
            if !target.exists() {
                fs::hard_link(
                    out.join("artifacts")
                        .join(artifact)
                        .join(format!("book.{ext}")),
                    target,
                )?;
            }
        }
    }
    write_json(&dir.join("catalog.json"), &catalog)?;
    let _gate = db.authority_guard()?;
    if authority_token(db)? != expected_authority {
        let _ = fs::remove_file(out.join("corpus/current"));
        return Ok(false);
    }
    let tmp = out
        .join("corpus")
        .join(format!(".current-{}", std::process::id()));
    let _ = fs::remove_file(&tmp);
    std::os::unix::fs::symlink(Path::new("generations").join(id), &tmp)?;
    if let Err(e) = fs::rename(&tmp, out.join("corpus/current")) {
        let _ = fs::remove_file(out.join("corpus/current"));
        return Err(e.into());
    }
    File::open(out.join("corpus"))?.sync_all()?;
    Ok(true)
}

pub fn run(work: &Path, options: Options) -> Result<Status> {
    if options.metadata_timeout_secs == 0 {
        return Err(SelectionError::Usage(
            "positive metadata timeout required".into(),
        ));
    }
    let db = Store::open_readonly(&work.join("selection.db"))?;
    let inv: InventoryResult = serde_json::from_value(
        db.meta("inventory")?
            .ok_or_else(|| SelectionError::Invalid("scan first".into()))?,
    )?;
    crate::export::validate_work_dir(&inv.root, &options.output)?;
    validate_output(&options.output)?;
    fs::create_dir_all(&options.output)?;
    let out = options.output.canonicalize()?;
    let work = work.canonicalize()?;
    let _owner = lock(&out, "rollout.lock")?;
    let _conversion = lock(&out, "conversion.lock")?;
    let _selection = lock(&out, "selection.lock")?;
    drop(_selection);
    publication::protect_existing_artifacts(&out)?;
    let groups: Vec<Group> = db.records("groups")?;
    let sources: BTreeMap<_, _> = db
        .sources()?
        .into_iter()
        .filter(|s| s.kind == SourceKind::Pdf)
        .map(|s| (s.source_id.clone(), s))
        .collect();
    let identity = crate::inventory::root_identity(&inv.root)?;
    if db.meta("root_identity")?.as_ref() != Some(&identity) {
        return Err(SelectionError::Invalid(
            "source root identity changed".into(),
        ));
    }
    let run = digest_json(&("continuous-v2", &inv.root, &identity, &groups));
    let conversion_options = conversion::Options {
        output: out.clone(),
        expected_selection: None,
        publish_every: 100,
        publish_next_to_source: true,
        workers: 2,
        chunk_pages: 20,
        timeout_secs: 120,
        job_timeout_secs: 1800,
        limit: usize::MAX,
        retry_failed: options.retry_failed,
        pdftotext: options.pdftotext,
    };
    let engine = conversion::engine(&conversion_options)?;
    let exe = std::env::current_exe()?;
    let mut ledger = Store::open(&out.join("continuous.db"))?;
    let mut jobs = Store::open(&out.join("markdown.db"))?;
    let cache = Store::open(&out.join("metadata.db"))?;
    let mut candidates: BTreeMap<String, Candidate> = BTreeMap::new();
    let mut resolutions: BTreeMap<String, Resolution> = BTreeMap::new();
    let mut status = Status {
        run_id: run.clone(),
        phase: "running".into(),
        metadata_total: sources.len(),
        groups_total: groups.len(),
        ..Status::default()
    };
    persist_status(&out, &status)?;
    let mut scan_groups: VecDeque<_> = groups.iter().collect();
    let mut pending: BTreeSet<String> = BTreeSet::new();
    let mut metadata: Option<MetadataRunning> = None;
    let mut active: Vec<Extracting> = vec![];
    let mut handled: BTreeSet<String> = BTreeSet::new();
    let mut reservations: Reservations =
        read_json(&out.join("reservations.json")).unwrap_or_default();
    reservations
        .jobs
        .retain(|id, _| id != "metadata" && lock(&out.join("leases"), id).is_err());
    let mut session: Option<adjacent::Session> = None;
    let mut heartbeat = Instant::now();
    let mut reconciled = Instant::now();
    let mut token = authority_token(&db)?;
    let initial_hints = digest_json(&db.records::<Value>("hints")?);
    let mut dirty = 0usize;
    let mut catalog_time = Instant::now();
    let mut capacity_blocked = BTreeSet::new();
    let mut observation_cursor = 0usize;
    let mut discovery = adjacent::Discovery::new(&inv.root, &identity);
    let mut states: BTreeMap<String, JobState> = BTreeMap::new();
    let mut last_logged = 0usize;
    let mut reconciled_directories = BTreeSet::new();
    let mut unresolved_manifests = 0usize;
    loop {
        // Inspect only one component per turn; an early cached group can dispatch
        // before the remaining cache census or metadata requests have completed.
        if status.phase != "needs_regroup"
            && let Some(group) = scan_groups.pop_front()
        {
            for id in &group.source_ids {
                if candidates.contains_key(id) {
                    continue;
                }
                if let Some(s) = sources.get(id) {
                    let checkpoint: Option<Candidate> = ledger
                        .get_cached(id, "continuous_metadata", &run)?
                        .map(serde_json::from_value)
                        .transpose()?;
                    if let Some(c) = checkpoint
                        && (!options.retry_failed || c.error.is_none())
                        && checked_path(&inv.root, &c.source.relative_path)
                            .and_then(|p| fingerprint(&p))
                            .ok()
                            .as_ref()
                            == Some(&c.source.fingerprint)
                    {
                        candidates.insert(id.clone(), c);
                        continue;
                    }
                    match metadata::cached(&inv.root, s, &db, &cache) {
                        Ok(Some(c)) => {
                            candidates.insert(id.clone(), c);
                        }
                        _ => {
                            pending.insert(id.clone());
                        }
                    }
                }
            }
        }
        if let Some(m) = metadata.as_mut() {
            let timeout = m.start.elapsed() >= Duration::from_secs(options.metadata_timeout_secs);
            let exit = m.child.try_wait()?;
            if timeout || exit.is_some() {
                let m = metadata.take().unwrap();
                let c = if timeout {
                    conversion::stop(m.child);
                    empty(
                        &m.request.source,
                        "metadata deadline exceeded; unresolved competitor".into(),
                    )
                } else {
                    read_json::<MetadataResult>(
                        &out.join("metadata-results")
                            .join(format!("{}.json", m.request.id)),
                    )
                    .ok()
                    .filter(|r| {
                        r.id == m.request.id
                            && r.candidate.source.source_id == m.request.source.source_id
                    })
                    .map(|r| r.candidate)
                    .unwrap_or_else(|| {
                        empty(
                            &m.request.source,
                            format!("metadata worker failed: {exit:?}"),
                        )
                    })
                };
                if c.error
                    .as_deref()
                    .is_some_and(|e| e.starts_with("needs_regroup:"))
                {
                    status.phase = "needs_regroup".into();
                    if let Some(group) = groups
                        .iter()
                        .find(|g| g.source_ids.contains(&c.source.source_id))
                    {
                        resolutions.remove(&group.group_id);
                        let mut withdrawal = Snapshot {
                            schema_version: 1,
                            snapshot_id: digest_json(&("invalidated", &c)),
                            policy: "internal-recency-v1".into(),
                            created: String::new(),
                            source_root: inv.root.clone(),
                            root_identity: identity.clone(),
                            coverage_errors: vec!["needs_regroup".into()],
                            archives: 0,
                            ready: vec![],
                            records: vec![PolicyRecord {
                                work_id: format!("w{}", &digest_json(&group.group_id)[..24]),
                                group_id: group.group_id.clone(),
                                status: "source_changed".into(),
                                reason: "verified bytes changed; prior claim withdrawn".into(),
                                selected_source_id: None,
                                candidates: vec![c.clone()],
                            }],
                        };
                        withdrawal.snapshot_id = digest_json(&withdrawal);
                        if session.is_none() {
                            session = Some(adjacent::Session::new_scoped(&out, &withdrawal)?);
                        }
                        session.as_mut().unwrap().clear_authority_database();
                        let _gate = db.authority_guard()?;
                        publication::publish_snapshot(
                            &out,
                            &engine,
                            &withdrawal,
                            session.as_mut(),
                            false,
                        )?;
                        dirty = 100;
                    }
                }
                ledger.put_cached(
                    &c.source.source_id,
                    "continuous_metadata",
                    &run,
                    &serde_json::to_value(&c)?,
                )?;
                candidates.insert(c.source.source_id.clone(), c);
                reservations.release("metadata");
            }
        }
        if status.phase != "needs_regroup" && metadata.is_none() {
            let next = pending
                .iter()
                .find(|id| !candidates.contains_key(*id))
                .cloned();
            if let Some(id) = next {
                let source = sources[&id].clone();
                if reservations.reserve("metadata", 64 * 1024 * 1024, capacity::free(&out)?) {
                    capacity_blocked.remove("metadata");
                    let request = MetadataRequest {
                        id: digest_json(&(&run, &id, &source.fingerprint)),
                        work: work.clone(),
                        output: out.clone(),
                        root: inv.root.clone(),
                        source,
                    };
                    let path = out
                        .join("metadata-jobs")
                        .join(format!("{}.json", request.id));
                    write_json(&path, &request)?;
                    let result = out
                        .join("metadata-results")
                        .join(format!("{}.json", request.id));
                    if result.exists() {
                        fs::remove_file(result)?;
                    }
                    let child = spawn(
                        options.metadata_worker.as_deref().unwrap_or(&exe),
                        "markdown-metadata-worker",
                        "--request",
                        &path,
                        &out.join("logs/continuous-metadata.log"),
                    )?;
                    pending.remove(&id);
                    metadata = Some(MetadataRunning {
                        child,
                        request,
                        start: Instant::now(),
                    });
                } else {
                    capacity_blocked.insert("metadata".into());
                }
            }
        }
        // Resolve completed groups only. Persistent resolutions and their Ready
        // records are one SQLite write; queue eligibility is derived from them.
        let mut publish_ids = BTreeSet::new();
        if status.phase != "needs_regroup" {
            for group in &groups {
                if resolutions.contains_key(&group.group_id) {
                    continue;
                }
                if group
                    .source_ids
                    .iter()
                    .all(|id| candidates.contains_key(id))
                {
                    let r = commit_group(
                        &db,
                        &mut ledger,
                        &out,
                        &inv.root,
                        group,
                        group
                            .source_ids
                            .iter()
                            .map(|id| candidates[id].clone())
                            .collect(),
                        &run,
                    )?;
                    eprintln!(
                        "group {} eligible: {} work(s), {}",
                        group.group_id,
                        r.snapshot.ready.len(),
                        r.snapshot.records[0].reason
                    );
                    publish_ids.insert(group.group_id.clone());
                    resolutions.insert(group.group_id.clone(), r);
                }
            }
        }
        if reconciled.elapsed() >= Duration::from_secs(1) {
            if digest_json(&db.records::<Value>("hints")?) != initial_hints
                || digest_json(&db.records::<Group>("groups")?) != digest_json(&groups)
            {
                status.phase = "needs_regroup".into();
            }
            let fresh = authority_token(&db)?;
            if fresh != token {
                token = fresh;
                for group in &groups {
                    if let Some(r) = resolutions.get_mut(&group.group_id) {
                        let current = commit_group(
                            &db,
                            &mut ledger,
                            &out,
                            &inv.root,
                            group,
                            r.snapshot.records[0].candidates.clone(),
                            &run,
                        )?;
                        if current.snapshot.snapshot_id != r.snapshot.snapshot_id {
                            *r = current;
                            publish_ids.insert(group.group_id.clone());
                            dirty = 100;
                        }
                    }
                }
            }
            reconciled = Instant::now();
        }
        // Stable observations are cheap; a changed observation is delegated to
        // the isolated byte verifier. Do not grant new authority in the meantime.
        if !groups.is_empty() && status.phase != "needs_regroup" {
            let group = &groups[observation_cursor % groups.len()];
            observation_cursor += 1;
            if let Some(r) = resolutions.get(&group.group_id) {
                for c in &r.snapshot.records[0].candidates {
                    if checked_path(&inv.root, &c.source.relative_path)
                        .and_then(|p| fingerprint(&p))
                        .ok()
                        .as_ref()
                        != Some(&c.source.fingerprint)
                    {
                        pending.insert(c.source.source_id.clone());
                        candidates.remove(&c.source.source_id);
                        resolutions.remove(&group.group_id);
                        publish_ids.remove(&group.group_id);
                        dirty = 100;
                        break;
                    }
                }
            }
        }
        // Reap first; a finished job is reusable bytes, never durable authority.
        let mut i = 0;
        while i < active.len() {
            let timeout = active[i].start.elapsed() > Duration::from_secs(1800);
            let exit = active[i].child.try_wait()?;
            if !timeout && exit.is_none() {
                i += 1;
                continue;
            }
            let item = active.swap_remove(i);
            if timeout {
                conversion::stop(item.child);
            }
            let result = if timeout {
                WorkerResult {
                    status: "failed".into(),
                    error: Some("job wall time exceeded".into()),
                    ..WorkerResult::default()
                }
            } else {
                read_json::<WorkerResult>(
                    &out.join("results").join(format!("{}.json", item.job.id)),
                )
                .unwrap_or_else(|e| WorkerResult {
                    status: "failed".into(),
                    error: Some(e.to_string()),
                    ..WorkerResult::default()
                })
            };
            let mut state: JobState = jobs
                .get_cached(&item.job.id, "job", "v1")?
                .map(serde_json::from_value)
                .transpose()?
                .unwrap_or_default();
            state.status = result.status.clone();
            state.error = result.error;
            if state.status == "failed" {
                state.attempts += 1;
            }
            states.insert(item.job.id.clone(), state.clone());
            jobs.put_cached(&item.job.id, "job", "v1", &serde_json::to_value(state)?)?;
            eprintln!(
                "conversion {}: {} ({} reused, {} extracted)",
                item.job.ready.relative_path.display(),
                result.status,
                result.reused_ranges,
                result.extracted_ranges
            );
            if resolutions.get(&item.job.ready.group_id).is_some_and(|r| {
                r.snapshot
                    .ready
                    .iter()
                    .any(|ready| job_id(ready, &engine) == item.job.id)
            }) {
                publish_ids.insert(item.job.ready.group_id.clone());
            }
            // Keep the reservation through source/artifact assembly and publication.
            dirty += 1;
        }
        if status.phase != "needs_regroup" {
            // Scan small in-memory Ready records; actual content is only rendered
            // for changed groups. OS leases prevent adopting orphaned writers.
            for r in resolutions.values() {
                for ready in &r.snapshot.ready {
                    if active.len() >= 2 {
                        break;
                    }
                    let id = job_id(ready, &engine);
                    if handled.contains(&id) || active.iter().any(|a| a.job.id == id) {
                        continue;
                    }
                    let state: JobState = jobs
                        .get_cached(&id, "job", "v1")?
                        .map(serde_json::from_value)
                        .transpose()?
                        .unwrap_or_default();
                    states.insert(id.clone(), state.clone());
                    if state.status == "failed" && (!options.retry_failed || state.attempts >= 3) {
                        handled.insert(id);
                        continue;
                    }
                    if lock(&out.join("leases"), &id).is_err() {
                        continue;
                    }
                    let source = &sources[&ready.source_id];
                    let bytes = capacity::job_bytes(
                        source.fingerprint.size,
                        ready.page_count,
                        engine.chunk_pages,
                    );
                    if !reservations.reserve(&id, bytes, capacity::free(&out)?) {
                        capacity_blocked.insert(id);
                        continue;
                    }
                    capacity_blocked.remove(&id);
                    write_json(&out.join("reservations.json"), &reservations)?;
                    let job = Job {
                        id: id.clone(),
                        output: out.clone(),
                        source_root: inv.root.clone(),
                        snapshot_id: r.snapshot.snapshot_id.clone(),
                        ready: ready.clone(),
                        engine: engine.clone(),
                    };
                    let path = out.join("jobs").join(format!("{id}.json"));
                    write_json(&path, &job)?;
                    let result = out.join("results").join(format!("{id}.json"));
                    if result.exists() {
                        fs::remove_file(result)?;
                    }
                    let child = spawn(
                        &exe,
                        "markdown-worker",
                        "--job",
                        &path,
                        &out.join("logs").join(format!("{id}.log")),
                    )?;
                    eprintln!("conversion started: {}", ready.relative_path.display());
                    handled.insert(id);
                    active.push(Extracting {
                        child,
                        job,
                        start: Instant::now(),
                    });
                }
            }
            for id in publish_ids {
                if let Some(r) = resolutions.get_mut(&id) {
                    if r.snapshot.ready.iter().any(|ready| {
                        worker::all_chunks(&out, ready, &engine).is_ok()
                            && !reservations.jobs.contains_key(&job_id(ready, &engine))
                    }) {
                        continue;
                    }
                    if session.is_none() {
                        session = Some(adjacent::Session::new_scoped(&out, &r.snapshot)?);
                    }
                    let group = groups.iter().find(|g| g.group_id == id).unwrap();
                    publish_group(
                        &db,
                        &mut ledger,
                        &out,
                        group,
                        &run,
                        r,
                        &engine,
                        session.as_mut().unwrap(),
                    )?;
                    if r.publication.as_ref().is_some_and(|p| {
                        p.pending_works.iter().any(|w| {
                            w["error"]
                                .as_str()
                                .is_some_and(|e| e.contains("destination space"))
                        })
                    }) {
                        capacity_blocked.insert(format!("destination-{id}"));
                    } else {
                        capacity_blocked.remove(&format!("destination-{id}"));
                    }
                    dirty += 1;
                    for ready in &r.snapshot.ready {
                        let job = job_id(ready, &engine);
                        if !active.iter().any(|a| a.job.id == job) {
                            reservations.release(&job);
                        }
                    }
                }
            }
            write_json(&out.join("reservations.json"), &reservations)?;
        }
        status.manifest_discovery_complete = discovery.step();
        status.metadata_checked = candidates.len();
        status.groups_resolved = resolutions.len();
        status.groups_pending = groups.len() - resolutions.len();
        status.groups_deferred = resolutions
            .values()
            .filter(|r| r.snapshot.ready.is_empty())
            .count();
        status.active = active.len();
        status.published = resolutions
            .values()
            .filter_map(|r| r.publication.as_ref())
            .map(|p| p.books)
            .sum();
        status.needs_ocr = 0;
        status.failures = candidates.values().filter(|c| c.error.is_some()).count();
        status.output_conflicts = 0;
        status.queued = 0;
        for r in resolutions.values() {
            for ready in &r.snapshot.ready {
                let id = job_id(ready, &engine);
                let state = states.get(&id).map(|s| s.status.as_str()).unwrap_or("");
                match state {
                    "needs_ocr_or_visual_review" => status.needs_ocr += 1,
                    "failed" => status.failures += 1,
                    _ => {}
                }
                if !handled.contains(&id) {
                    status.queued += 1;
                }
            }
            if let Some(p) = &r.publication {
                status.output_conflicts += p
                    .pending_works
                    .iter()
                    .filter(|w| w["status"] == "output_conflict")
                    .count();
            }
        }
        status.capacity_pending = capacity_blocked.len();
        if status.manifest_discovery_complete
            && status.groups_pending == 0
            && active.is_empty()
            && let Some(relative) = discovery
                .found
                .iter()
                .find(|p| !reconciled_directories.contains(*p))
                .cloned()
        {
            let snapshot = Snapshot {
                schema_version: 1,
                snapshot_id: digest_json(&("reconcile", &run)),
                policy: "internal-recency-v1".into(),
                created: String::new(),
                source_root: inv.root.clone(),
                root_identity: identity.clone(),
                coverage_errors: if status.failures == 0
                    && inv.errors.is_empty()
                    && discovery.errors.is_empty()
                {
                    vec![]
                } else {
                    vec!["unresolved coverage".into()]
                },
                archives: 0,
                ready: resolutions
                    .values()
                    .flat_map(|r| r.snapshot.ready.clone())
                    .collect(),
                records: resolutions
                    .values()
                    .flat_map(|r| r.snapshot.records.clone())
                    .collect(),
            };
            if session.is_none() {
                session = Some(adjacent::Session::new_scoped(&out, &snapshot)?);
            }
            session.as_mut().unwrap().clear_authority_database();
            let _gate = db.authority_guard()?;
            match session
                .as_mut()
                .unwrap()
                .reconcile_discovered(&snapshot, &engine, &relative)
            {
                Ok(n) => unresolved_manifests += n,
                Err(e) => {
                    eprintln!("manifest reconciliation {}: {e}", relative.display());
                    unresolved_manifests += 1;
                }
            }
            reconciled_directories.insert(relative);
        }
        persist_status(&out, &status)?;
        if dirty >= 100 || dirty > 0 && catalog_time.elapsed() > Duration::from_secs(30) {
            current_view(
                &db,
                &token,
                &out,
                &run,
                &resolutions,
                status.groups_pending > 0,
            )?;
            dirty = 0;
            catalog_time = Instant::now();
        }
        if heartbeat.elapsed() >= Duration::from_secs(30)
            || status.metadata_checked >= last_logged + 100
        {
            eprintln!(
                "continuous: metadata {}/{}, groups {}/{} ({} deferred), {} queued, {} active, {} published, {} OCR, {} failed",
                status.metadata_checked,
                status.metadata_total,
                status.groups_resolved,
                status.groups_total,
                status.groups_deferred,
                status.queued,
                status.active,
                status.published,
                status.needs_ocr,
                status.failures
            );
            last_logged = status.metadata_checked;
            heartbeat = Instant::now();
        }
        if status.phase == "needs_regroup" && active.is_empty() {
            break;
        }
        if scan_groups.is_empty() && metadata.is_none() && active.is_empty() {
            if status.phase == "needs_regroup" {
                break;
            }
            if !capacity_blocked.is_empty() {
                status.phase = "capacity_pending".into();
                break;
            }
            if pending.is_empty()
                && status.groups_pending == 0
                && status.queued == 0
                && status.manifest_discovery_complete
                && reconciled_directories.len() == discovery.found.len()
            {
                status.phase = if status.failures
                    + status.needs_ocr
                    + status.output_conflicts
                    + discovery.errors.len()
                    + unresolved_manifests
                    > 0
                {
                    "completed_with_exceptions"
                } else {
                    "completed"
                }
                .into();
                break;
            }
        }
        std::thread::sleep(Duration::from_millis(25));
    }
    if let Some(m) = metadata {
        conversion::stop(m.child);
    }
    {
        if !current_view(
            &db,
            &token,
            &out,
            &run,
            &resolutions,
            status.groups_pending > 0,
        )? {
            status.phase = "authority_pending".into();
        }
    }
    persist_status(&out, &status)?;
    Ok(status)
}
