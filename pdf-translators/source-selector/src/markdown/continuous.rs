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
    /// Maximum simultaneous PDF extraction workers.
    #[arg(long, default_value_t = 2)]
    pub workers: usize,
    #[arg(long, default_value_t = 300)]
    pub metadata_timeout_secs: u64,
    #[arg(long, hide = true)]
    pub metadata_worker: Option<PathBuf>,
    #[arg(long, hide = true)]
    pub publication_gate: Option<PathBuf>,
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
    pub publication_pending: usize,
    pub publication_active: bool,
    pub publication_queued: usize,
    pub unverified_manifests: usize,
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
pub(crate) struct Resolution {
    pub snapshot: Snapshot,
    pub publication: Option<publication::Publication>,
}
#[derive(Clone, Default, Serialize, Deserialize)]
struct JobState {
    attempts: usize,
    status: String,
    error: Option<String>,
}
struct PublicationTicket {
    group_id: Option<String>,
    revision: String,
    job_ids: Vec<String>,
    withdrawal: bool,
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
fn publication_factor(
    id: &str,
    resolutions: &BTreeMap<String, Resolution>,
    tickets: &BTreeMap<u64, PublicationTicket>,
    engine: &Engine,
) -> u64 {
    resolutions
        .values()
        .map(|r| {
            r.snapshot
                .ready
                .iter()
                .filter(|ready| job_id(ready, engine) == id)
                .count() as u64
        })
        .chain(
            tickets
                .values()
                .map(|t| t.job_ids.iter().filter(|job| job.as_str() == id).count() as u64),
        )
        .max()
        .unwrap_or(1)
        .max(1)
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
        Err(SelectionError::Io(e)) if e.kind() == std::io::ErrorKind::NotFound => {
            empty(&observed, format!("source_missing: {e}"))
        }
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
fn publication_conflicts(p: &publication::Publication) -> usize {
    p.adjacent.as_ref().map_or(0, |a| a.errors.len()).max(
        p.pending_works
            .iter()
            .filter(|w| w["status"] == "output_conflict")
            .count(),
    )
}
fn persist_status(out: &Path, status: &Status) -> Result<()> {
    write_json(&out.join("continuous-status.json"), status)
}
fn authority_token(db: &Store) -> Result<String> {
    Ok(digest_json(&db.meta("authority_revision")?))
}
fn graph_token(db: &Store) -> Result<String> {
    Ok(digest_json(&db.meta("graph_revision")?))
}
fn observations_current(candidates: &[Candidate], root: &Path) -> bool {
    candidates.iter().all(|c| {
        let observed = checked_path(root, &c.source.relative_path).and_then(|p| fingerprint(&p));
        match observed {
            Ok(fp) => fp == c.source.fingerprint,
            Err(_) => c.error.is_some(),
        }
    })
}
fn invalidate_revoked_current(
    out: &Path,
    resolutions: &BTreeMap<String, Resolution>,
) -> Result<bool> {
    let old = read_json::<Value>(&out.join("corpus/current/catalog.json")).unwrap_or(Value::Null);
    let revoked = old["books"].as_array().is_some_and(|books| {
        books.iter().any(|b| {
            b["work"]["group_id"]
                .as_str()
                .and_then(|g| resolutions.get(g))
                .is_some_and(|r| {
                    (r.snapshot.records.iter().any(|p| {
                        p.candidates.iter().any(|c| {
                            b["work"]["source_id"] == c.source.source_id
                                && c.error
                                    .as_deref()
                                    .is_some_and(|e| e.starts_with("source_missing:"))
                        })
                    }) || r.snapshot.records.iter().all(|p| {
                        p.status == "source_changed"
                            || p.candidates.iter().all(|c| c.error.is_none())
                    })) && !r.snapshot.ready.iter().any(|ready| {
                        b["work"]["work_id"] == ready.work_id && b["work"]["sha256"] == ready.sha256
                    })
                })
        })
    });
    if revoked {
        let pointer = out.join("corpus/current");
        match fs::remove_file(&pointer) {
            Ok(()) => {}
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
            Err(e) => {
                write_json(
                    &out.join("current-view-state.json"),
                    &serde_json::json!({"safe":false,"error":e.to_string()}),
                )?;
                return Err(e.into());
            }
        }
        write_json(
            &out.join("current-view-state.json"),
            &serde_json::json!({"safe":false,"reason":"confirmed revocation; replacement pending"}),
        )?;
    }
    Ok(revoked)
}
fn resolution_key(run: &str, group: &str) -> String {
    format!("{run}-{group}")
}
#[allow(clippy::too_many_arguments)]
fn commit_group(
    db: &Store,
    ledger: &mut Store,
    out: &Path,
    root: &Path,
    group: &Group,
    candidates: Vec<Candidate>,
    run: &str,
    graph: &str,
    prior: Option<&Resolution>,
) -> Result<Option<Resolution>> {
    let _gate = db.authority_guard()?;
    if graph_token(db)? != graph || !observations_current(&candidates, root) {
        return Ok(None);
    }
    let snapshot = selection::resolve_group(db, out, root, group, candidates, &Value::Null)?;
    let publication = prior
        .filter(|r| r.snapshot.snapshot_id == snapshot.snapshot_id)
        .and_then(|r| r.publication.clone());
    let resolution = Resolution {
        snapshot,
        publication,
    };
    ledger.put_record(
        "continuous_groups",
        &resolution_key(run, &group.group_id),
        &resolution,
    )?;
    Ok(Some(resolution))
}
#[allow(clippy::too_many_arguments)]
pub(crate) fn publish_group(
    db: &Store,
    out: &Path,
    group: &Group,
    resolution: &mut Resolution,
    engine: &Engine,
    session: &mut adjacent::Session,
    graph: &str,
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
        return Ok(());
    }
    session.set_authority_database(db.path());
    session.set_graph_token(graph);
    let p = publication::publish_snapshot(out, engine, &resolution.snapshot, Some(session), false)?;
    eprintln!(
        "group {}: {} sibling Markdown published, revision {}",
        group.group_id, p.books, resolution.snapshot.snapshot_id
    );
    if p.pending {
        let changed = {
            let _gate = db.authority_guard()?;
            if graph_token(db)? == graph {
                let final_authority = selection::resolve_group(
                    db,
                    out,
                    &resolution.snapshot.source_root,
                    group,
                    resolution.snapshot.records[0].candidates.clone(),
                    &Value::Null,
                )?;
                if final_authority.snapshot_id != resolution.snapshot.snapshot_id {
                    resolution.snapshot = final_authority;
                    true
                } else {
                    false
                }
            } else {
                false
            }
        };
        if changed {
            resolution.publication = None;
            return Ok(());
        }
    }
    resolution.publication = Some(p);
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
    {
        let _gate = db.authority_guard()?;
        invalidate_revoked_current(out, resolutions)?;
    }
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
    write_json(
        &out.join("current-view-state.json"),
        &serde_json::json!({"safe":true}),
    )?;
    Ok(true)
}

pub fn run(work: &Path, options: Options) -> Result<Status> {
    if options.workers == 0 {
        return Err(SelectionError::Usage(
            "positive worker count required".into(),
        ));
    }
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
    let run = digest_json(&(
        "continuous-v2",
        &inv.root,
        &identity,
        &groups,
        &inv.finished,
    ));
    let graph = graph_token(&db)?;
    let conversion_options = conversion::Options {
        output: out.clone(),
        expected_selection: None,
        publish_every: 100,
        publish_next_to_source: true,
        workers: options.workers,
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
    if ledger
        .meta("regroup_fence")?
        .is_some_and(|f| f["inventory_finished"] == inv.finished)
    {
        status.phase = "needs_regroup".into();
        persist_status(&out, &status)?;
        return Ok(status);
    }
    let group_by_source: BTreeMap<_, _> = groups
        .iter()
        .flat_map(|g| {
            g.source_ids
                .iter()
                .map(move |id| (id.clone(), g.group_id.clone()))
        })
        .collect();
    if db
        .records::<Hint>("hints")?
        .iter()
        .filter(|h| h.origin == "muse")
        .any(|h| {
            h.source_ids
                .iter()
                .filter_map(|id| group_by_source.get(id))
                .collect::<BTreeSet<_>>()
                .len()
                > 1
        })
    {
        ledger.set_meta("regroup_fence",&serde_json::json!({"inventory_finished":inv.finished,"reason":"grouping hints require graph refresh"}))?;
        status.phase = "needs_regroup".into();
        persist_status(&out, &status)?;
        return Ok(status);
    }
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
    use super::continuous_publication::{DiscoveryWorker, Outcome, PublishRequest, Publisher};
    let publisher = Publisher::start(
        &work,
        &out,
        &engine,
        &graph,
        options.publication_gate,
        _conversion.try_clone()?,
    )?;
    let discovery_worker = DiscoveryWorker::start(&inv.root, &identity)?;
    let mut discovery: Option<adjacent::Discovery> = None;
    let mut publication_sequence = 0u64;
    // Every request retains its allocation consumers until a result/supersession.
    let mut publication_tasks: BTreeMap<u64, PublicationTicket> = BTreeMap::new();
    let mut publication_latest: BTreeMap<String, u64> = BTreeMap::new();
    let mut reconciliation_pending: Option<u64> = None;
    let mut publication_retry = BTreeSet::new();
    let mut reservation_factors: BTreeMap<String, u64> = BTreeMap::new();

    let mut heartbeat = Instant::now();
    let mut reconciled = Instant::now();
    let mut token = authority_token(&db)?;
    let initial_hints = digest_json(&db.records::<Value>("hints")?);
    let mut dirty = 0usize;
    let mut catalog_time = Instant::now();
    let mut capacity_blocked = BTreeSet::new();
    let mut observation_cursor = 0usize;
    let mut states: BTreeMap<String, JobState> = BTreeMap::new();
    let mut last_logged = 0usize;
    let mut reconciled_directories = BTreeSet::new();
    let mut unresolved_manifests = 0usize;
    loop {
        if graph_token(&db)? != graph {
            status.phase = "needs_regroup".into();
        }
        while let Some(response) = publisher.poll()? {
            let Some(PublicationTicket {
                group_id,
                revision: expected_revision,
                ..
            }) = publication_tasks.remove(&response.sequence)
            else {
                continue;
            };
            match response.outcome {
                Outcome::Superseded => {
                    if let Some(id) = group_id
                        && publication_latest.get(&id) == Some(&response.sequence)
                    {
                        publication_latest.remove(&id);
                    }
                }
                Outcome::Published(result) => {
                    let Some(id) = group_id else { continue };
                    if publication_latest.get(&id) != Some(&response.sequence) {
                        continue;
                    }
                    publication_latest.remove(&id);
                    if let Some(r) = resolutions.get_mut(&id) {
                        if r.snapshot.snapshot_id != expected_revision {
                            continue;
                        }
                        match result {
                            Ok(done) => {
                                let changed = done.snapshot.snapshot_id != r.snapshot.snapshot_id;
                                *r = *done;
                                if r.publication.is_none() {
                                    publication_retry.insert(id.clone());
                                }
                                if changed {
                                    dirty = 100;
                                }
                            }
                            Err(error) => {
                                eprintln!("publication {id}: {error}");
                                r.publication = Some(publication::Publication {
                                    selection_id: r.snapshot.snapshot_id.clone(),
                                    generation: None,
                                    books: 0,
                                    pending: true,
                                    published_snapshot: None,
                                    pending_works: vec![],
                                    catalog: vec![],
                                    adjacent: Some(adjacent::AdjacentReport {
                                        errors: vec![error],
                                        ..Default::default()
                                    }),
                                });
                            }
                        }
                        ledger.put_record("continuous_groups", &resolution_key(&run, &id), r)?;
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
                    }
                }
                Outcome::Reconciled {
                    directory,
                    result,
                    stale,
                } => {
                    reconciliation_pending = None;
                    if !stale {
                        match result {
                            Ok(n) => unresolved_manifests += n,
                            Err(e) => {
                                eprintln!("manifest reconciliation {}: {e}", directory.display());
                                unresolved_manifests += 1;
                            }
                        }
                        reconciled_directories.insert(directory);
                    }
                }
            }
        }
        if status.phase == "needs_regroup" {
            let _gate = db.authority_guard()?;
            publisher.fence();
        }
        let capacity_jobs: BTreeSet<_> = active
            .iter()
            .map(|a| a.job.id.clone())
            .chain(
                reservations
                    .jobs
                    .keys()
                    .filter(|id| id.as_str() != "metadata")
                    .cloned(),
            )
            .collect();
        for id in capacity_jobs {
            if let Ok(request) = read_json::<capacity::Request>(
                &out.join("capacity-requests").join(format!("{}.json", id)),
            ) {
                let prior = read_json::<capacity::Grant>(
                    &out.join("capacity-grants").join(format!("{}.json", id)),
                )
                .ok();
                if prior.as_ref().is_none_or(|g| g.nonce != request.nonce) {
                    let factor = publication_factor(&id, &resolutions, &publication_tasks, &engine);
                    let allowed = reservations.reserve(
                        &id,
                        request.bytes.saturating_mul(factor),
                        capacity::free(&out)?,
                    );
                    if allowed {
                        reservation_factors.insert(id.clone(), factor);
                    }
                    write_json(&out.join("reservations.json"), &reservations)?;
                    write_json(
                        &out.join("capacity-grants").join(format!("{}.json", id)),
                        &capacity::Grant {
                            nonce: request.nonce,
                            allowed,
                        },
                    )?;
                }
            }
        }
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
                        if c.error
                            .as_deref()
                            .is_some_and(|e| e.starts_with("needs_regroup:"))
                        {
                            status.phase = "needs_regroup".into();
                        }
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
                if !observations_current(std::slice::from_ref(&c), &inv.root) {
                    pending.insert(c.source.source_id.clone());
                    reservations.release("metadata");
                    continue;
                }
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
                            policy: selection::policy(&db)?,
                            created: String::new(),
                            source_root: inv.root.clone(),
                            root_identity: identity.clone(),
                            coverage_errors: vec!["needs_regroup".into()],
                            archives: 0,
                            ready: vec![],
                            records: vec![PolicyRecord {
                                selection_revision: None,
                                work_id: format!("w{}", &digest_json(&group.group_id)[..24]),
                                group_id: group.group_id.clone(),
                                status: "source_changed".into(),
                                reason: "verified bytes changed; prior claim withdrawn".into(),
                                selected_source_id: None,
                                candidates: vec![c.clone()],
                            }],
                        };
                        withdrawal.snapshot_id = digest_json(&withdrawal);
                        {
                            let _gate = db.authority_guard()?;
                            publisher.fence();
                            resolutions.insert(
                                group.group_id.clone(),
                                Resolution {
                                    snapshot: withdrawal.clone(),
                                    publication: None,
                                },
                            );
                            invalidate_revoked_current(&out, &resolutions)?;
                        }
                        publication_sequence += 1;
                        let sequence = publication_sequence;
                        let resolution = resolutions[&group.group_id].clone();
                        publication_tasks.insert(
                            sequence,
                            PublicationTicket {
                                group_id: Some(group.group_id.clone()),
                                revision: resolution.snapshot.snapshot_id.clone(),
                                job_ids: vec![],
                                withdrawal: true,
                            },
                        );
                        publication_latest.insert(group.group_id.clone(), sequence);
                        publisher.submit(PublishRequest {
                            sequence,
                            group: group.clone(),
                            resolution,
                            priority: 0,
                            withdrawal: true,
                        })?;
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
        let mut publish_ids = std::mem::take(&mut publication_retry);
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
                    let complete: Vec<_> = group
                        .source_ids
                        .iter()
                        .map(|id| candidates[id].clone())
                        .collect();
                    if !observations_current(&complete, &inv.root) {
                        for c in complete {
                            if !observations_current(std::slice::from_ref(&c), &inv.root) {
                                candidates.remove(&c.source.source_id);
                                pending.insert(c.source.source_id);
                            }
                        }
                        continue;
                    }
                    if graph_token(&db)? != graph {
                        status.phase = "needs_regroup".into();
                        break;
                    }
                    let result = commit_group(
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
                        &graph,
                        None,
                    )?;
                    let Some(r) = result else {
                        for id in &group.source_ids {
                            candidates.remove(id);
                            pending.insert(id.clone());
                        }
                        if graph_token(&db)? != graph {
                            status.phase = "needs_regroup".into();
                        }
                        continue;
                    };
                    eprintln!(
                        "group {} eligible: {} work(s), {}",
                        group.group_id,
                        r.snapshot.ready.len(),
                        r.snapshot.records[0].reason
                    );
                    publish_ids.insert(group.group_id.clone());
                    let revocation = r.snapshot.ready.is_empty();
                    resolutions.insert(group.group_id.clone(), r);
                    if revocation {
                        let _gate = db.authority_guard()?;
                        if invalidate_revoked_current(&out, &resolutions)? {
                            dirty = 100;
                        }
                    }
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
                        let result = commit_group(
                            &db,
                            &mut ledger,
                            &out,
                            &inv.root,
                            group,
                            r.snapshot.records[0].candidates.clone(),
                            &run,
                            &graph,
                            Some(r),
                        )?;
                        let Some(current) = result else {
                            if graph_token(&db)? != graph {
                                status.phase = "needs_regroup".into();
                            }
                            continue;
                        };
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
                    if c.error.is_some() {
                        continue;
                    }
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
            let _ = fs::remove_file(out.join("capacity-jobs").join(&item.job.id));
            if state.status == "capacity_pending" {
                capacity_blocked.insert(item.job.id.clone());
                handled.remove(&item.job.id);
                reservations.release(&item.job.id);
            }
            state.error = result.error;
            if state.status == "failed" {
                state.attempts += 1;
            }
            if worker::all_chunks(&out, &item.job.ready, &engine).is_ok() {
                let factor =
                    publication_factor(&item.job.id, &resolutions, &publication_tasks, &engine);
                let required =
                    capacity::job_bytes(&out, &item.job.ready, &engine, 0).saturating_mul(factor);
                if let Some(held) = reservations.jobs.get_mut(&item.job.id) {
                    *held = (*held).min(required);
                }
                reservation_factors.insert(item.job.id.clone(), factor);
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
            // One SHA/engine job can serve several current PDFs at distinct
            // paths. Every consumer needs publication when that job finishes.
            for (group_id, r) in &resolutions {
                if r.snapshot
                    .ready
                    .iter()
                    .any(|ready| job_id(ready, &engine) == item.job.id)
                {
                    publish_ids.insert(group_id.clone());
                }
            }
            // Keep the reservation through source/artifact assembly and publication.
            dirty += 1;
        }
        if status.phase != "needs_regroup" {
            // Scan small in-memory Ready records; actual content is only rendered
            // for changed groups. OS leases prevent adopting orphaned writers.
            for r in resolutions.values() {
                for ready in &r.snapshot.ready {
                    if active.len() >= options.workers {
                        break;
                    }
                    let id = job_id(ready, &engine);
                    if handled.contains(&id) || active.iter().any(|a| a.job.id == id) {
                        continue;
                    }
                    let _authority = db.authority_guard()?;
                    if graph_token(&db)? != graph {
                        status.phase = "needs_regroup".into();
                        break;
                    }
                    if !observations_current(&r.snapshot.records[0].candidates, &inv.root) {
                        continue;
                    }
                    let fresh = selection::resolve_group(
                        &db,
                        &out,
                        &inv.root,
                        groups
                            .iter()
                            .find(|g| g.group_id == ready.group_id)
                            .unwrap(),
                        r.snapshot.records[0].candidates.clone(),
                        &Value::Null,
                    )?;
                    if fresh.snapshot_id != r.snapshot.snapshot_id {
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
                    let factor = publication_factor(&id, &resolutions, &publication_tasks, &engine);
                    let bytes = capacity::job_bytes(&out, ready, &engine, source.fingerprint.size)
                        .max(
                            read_json::<capacity::Request>(
                                &out.join("capacity-requests").join(format!("{id}.json")),
                            )
                            .map_or(0, |r| r.bytes),
                        )
                        .saturating_mul(factor);
                    if !reservations.reserve(&id, bytes, capacity::free(&out)?) {
                        capacity_blocked.insert(id);
                        continue;
                    }
                    capacity_blocked.remove(&id);
                    reservation_factors.insert(id.clone(), factor);
                    write_json(&out.join("reservations.json"), &reservations)?;
                    let job = Job {
                        id: id.clone(),
                        output: out.clone(),
                        source_root: inv.root.clone(),
                        snapshot_id: r.snapshot.snapshot_id.clone(),
                        ready: ready.clone(),
                        engine: engine.clone(),
                    };
                    atomic_write(
                        &out.join("capacity-jobs").join(&id),
                        b"continuous allocation grants",
                    )?;
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
            {
                let _gate = db.authority_guard()?;
                if invalidate_revoked_current(&out, &resolutions)? {
                    dirty = 100;
                }
            }
            for id in publish_ids {
                if graph_token(&db)? != graph {
                    status.phase = "needs_regroup".into();
                    break;
                }
                if let Some(r) = resolutions.get(&id) {
                    let mut fits = true;
                    let ids: BTreeSet<_> = r
                        .snapshot
                        .ready
                        .iter()
                        .map(|ready| job_id(ready, &engine))
                        .collect();
                    for job in ids {
                        let ready = r
                            .snapshot
                            .ready
                            .iter()
                            .find(|ready| job_id(ready, &engine) == job)
                            .unwrap();
                        let complete = worker::all_chunks(&out, ready, &engine).is_ok();
                        if complete || reservations.jobs.contains_key(&job) {
                            let factor =
                                publication_factor(&job, &resolutions, &publication_tasks, &engine);
                            let base = capacity::job_bytes(
                                &out,
                                ready,
                                &engine,
                                sources[&ready.source_id].fingerprint.size,
                            );
                            let prior_factor = reservation_factors.get(&job).copied().unwrap_or(1);
                            let prior_base = reservations
                                .jobs
                                .get(&job)
                                .copied()
                                .unwrap_or(0)
                                .div_ceil(prior_factor);
                            let bytes = if complete { base } else { base.max(prior_base) }
                                .saturating_mul(factor);
                            if reservations
                                .jobs
                                .get(&job)
                                .is_some_and(|held| *held >= bytes)
                            {
                                reservations.jobs.insert(job.clone(), bytes);
                                reservation_factors.insert(job.clone(), factor);
                            } else if reservations.reserve(&job, bytes, capacity::free(&out)?) {
                                reservation_factors.insert(job.clone(), factor);
                                capacity_blocked.remove(&job);
                            } else {
                                capacity_blocked.insert(job);
                                fits = false;
                            }
                        }
                    }
                    if !fits {
                        publication_retry.insert(id);
                        continue;
                    }
                    let group = groups.iter().find(|g| g.group_id == id).unwrap();
                    publication_sequence += 1;
                    let sequence = publication_sequence;
                    let ids: Vec<_> = r
                        .snapshot
                        .ready
                        .iter()
                        .map(|ready| job_id(ready, &engine))
                        .collect();
                    let priority = if r.snapshot.ready.is_empty()
                        && r.snapshot
                            .records
                            .iter()
                            .any(|record| record.reason.contains("adopted review"))
                    {
                        0
                    } else if ids
                        .iter()
                        .any(|id| states.get(id).is_some_and(|s| s.status == "complete"))
                    {
                        1
                    } else {
                        2
                    };
                    publication_tasks.insert(
                        sequence,
                        PublicationTicket {
                            group_id: Some(id.clone()),
                            revision: r.snapshot.snapshot_id.clone(),
                            job_ids: ids,
                            withdrawal: false,
                        },
                    );
                    publication_latest.insert(id.clone(), sequence);
                    publisher.submit(PublishRequest {
                        sequence,
                        group: group.clone(),
                        resolution: r.clone(),
                        priority,
                        withdrawal: false,
                    })?;
                }
            }
        }
        let consumers: BTreeSet<_> = active
            .iter()
            .map(|a| a.job.id.clone())
            .chain(
                publication_tasks
                    .values()
                    .flat_map(|ticket| ticket.job_ids.iter().cloned()),
            )
            .collect();
        reservations.jobs.retain(|id, _| {
            id == "metadata" || consumers.contains(id) || lock(&out.join("leases"), id).is_err()
        });
        write_json(&out.join("reservations.json"), &reservations)?;
        if discovery.is_none() {
            discovery = discovery_worker.poll()?;
        }
        status.manifest_discovery_complete = discovery.is_some();
        let active_publication = publisher.active_sequence();
        status.publication_active = active_publication != 0;
        status.publication_queued = publication_latest.len().saturating_sub(usize::from(
            publication_latest
                .values()
                .any(|s| *s == active_publication),
        ));
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
        status.publication_pending = 0;
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
                if p.pending {
                    status.publication_pending += 1;
                }
                status.output_conflicts += publication_conflicts(p);
            }
        }
        let eligible: BTreeSet<_> = resolutions
            .values()
            .flat_map(|r| r.snapshot.ready.iter().map(|ready| job_id(ready, &engine)))
            .collect();
        capacity_blocked.retain(|id| {
            if let Some(g) = id.strip_prefix("destination-") {
                resolutions
                    .get(g)
                    .is_some_and(|r| !r.snapshot.ready.is_empty())
            } else if id == "metadata" {
                !pending.is_empty() || metadata.is_some()
            } else {
                eligible.contains(id)
            }
        });
        status.capacity_pending = capacity_blocked.len();
        if status.manifest_discovery_complete
            && status.groups_pending == 0
            && active.is_empty()
            && publication_latest.is_empty()
            && reconciliation_pending.is_none()
            && let Some(relative) = discovery
                .as_ref()
                .unwrap()
                .found
                .iter()
                .find(|p| !reconciled_directories.contains(*p))
                .cloned()
        {
            let snapshot = Snapshot {
                schema_version: 1,
                snapshot_id: digest_json(&("reconcile", &run)),
                policy: selection::policy(&db)?,
                created: String::new(),
                source_root: inv.root.clone(),
                root_identity: identity.clone(),
                coverage_errors: if status.failures == 0
                    && inv.errors.is_empty()
                    && discovery.as_ref().unwrap().errors.is_empty()
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
            publication_sequence += 1;
            let sequence = publication_sequence;
            publication_tasks.insert(
                sequence,
                PublicationTicket {
                    group_id: None,
                    revision: String::new(),
                    job_ids: vec![],
                    withdrawal: false,
                },
            );
            reconciliation_pending = Some(sequence);
            publisher.reconcile(sequence, relative, snapshot, token.clone())?;
        }
        status.unverified_manifests = unresolved_manifests;
        persist_status(&out, &status)?;
        if dirty >= 100 || dirty > 0 && catalog_time.elapsed() > Duration::from_secs(30) {
            let installed = current_view(
                &db,
                &token,
                &out,
                &run,
                &resolutions,
                status.groups_pending > 0
                    || status.failures > 0
                    || status.publication_pending > 0
                    || status.unverified_manifests > 0
                    || !publication_tasks.is_empty(),
            )?;
            if installed {
                dirty = 0;
                catalog_time = Instant::now();
            } else {
                dirty = 100;
            }
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
        if status.phase == "needs_regroup"
            && active.is_empty()
            && !publication_tasks.values().any(|ticket| ticket.withdrawal)
        {
            break;
        }
        if scan_groups.is_empty()
            && metadata.is_none()
            && active.is_empty()
            && publication_tasks.is_empty()
        {
            if status.phase == "needs_regroup" {
                break;
            }
            if authority_token(&db)? != token {
                reconciled = Instant::now()
                    .checked_sub(Duration::from_secs(1))
                    .unwrap_or(reconciled);
                continue;
            }
            if !capacity_blocked.is_empty() {
                status.phase = "capacity_pending".into();
                break;
            }
            if pending.is_empty()
                && status.groups_pending == 0
                && status.queued == 0
                && publication_retry.is_empty()
                && resolutions.values().all(|r| r.publication.is_some())
                && status.manifest_discovery_complete
                && reconciled_directories.len() == discovery.as_ref().unwrap().found.len()
            {
                status.phase = if status.failures
                    + status.needs_ocr
                    + status.output_conflicts
                    + status.publication_pending
                    + discovery.as_ref().map_or(0, |d| d.errors.len())
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
    if status.phase == "needs_regroup" {
        ledger.set_meta("regroup_fence",&serde_json::json!({"inventory_finished":inv.finished,"graph":graph,"reason":"known input changed; refresh inventory/group graph"}))?;
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
            status.groups_pending > 0
                || status.failures > 0
                || status.publication_pending > 0
                || status.unverified_manifests > 0
                || !publication_tasks.is_empty(),
        )? && status.phase != "needs_regroup"
        {
            status.phase = "authority_pending".into();
        }
    }
    persist_status(&out, &status)?;
    Ok(status)
}

#[cfg(test)]
mod view_tests {
    use super::*;
    #[test]
    fn revoked_pointer_is_removed_before_a_failing_generation_stage() {
        let out = tempfile::tempdir().unwrap();
        let main = tempfile::tempdir().unwrap();
        let db = Store::open(&main.path().join("selection.db")).unwrap();
        let old = out.path().join("corpus/generations/old");
        fs::create_dir_all(&old).unwrap();
        write_json(&old.join("catalog.json"),&serde_json::json!({"books":[{"work":{"group_id":"held-group","work_id":"held-work","sha256":"old"}}]})).unwrap();
        std::os::unix::fs::symlink("generations/old", out.path().join("corpus/current")).unwrap();
        let snapshot = Snapshot {
            schema_version: 1,
            snapshot_id: "held".into(),
            policy: "internal-recency-v1".into(),
            created: String::new(),
            source_root: main.path().into(),
            root_identity: Value::Null,
            coverage_errors: vec![],
            archives: 0,
            ready: vec![],
            records: vec![PolicyRecord {
                selection_revision: Some("held".into()),
                work_id: "held-work".into(),
                group_id: "held-group".into(),
                status: "deferred_choice".into(),
                reason: "user hold".into(),
                selected_source_id: None,
                candidates: vec![],
            }],
        };
        let resolutions = BTreeMap::from([(
            "held-group".into(),
            Resolution {
                snapshot,
                publication: None,
            },
        )]);
        let id = digest_json(
            &serde_json::json!({"schema_version":2,"run_id":"run","pending":true,"books":[]}),
        );
        fs::write(
            out.path().join("corpus/generations").join(id),
            b"injected stage conflict",
        )
        .unwrap();
        let result = current_view(
            &db,
            &authority_token(&db).unwrap(),
            out.path(),
            "run",
            &resolutions,
            true,
        );
        assert!(result.is_err());
        assert!(
            fs::symlink_metadata(out.path().join("corpus/current")).is_err(),
            "revoked default view survived staging failure"
        );
        let state: Value = read_json(&out.path().join("current-view-state.json")).unwrap();
        assert_eq!(state["safe"], false);
    }
}

#[cfg(test)]
mod count_tests {
    use super::*;
    #[test]
    fn queued_publication_is_pending_but_not_an_output_conflict() {
        let mut p:publication::Publication=serde_json::from_value(serde_json::json!({"selection_id":"test","generation":null,"books":0,"pending":true,"published_snapshot":null,"pending_works":[{"work_id":"queued","status":"pending"}],"catalog":[],"adjacent":{"published":[],"errors":[],"directories":1,"complete":false,"states":{},"warnings":[]}})).unwrap();
        assert_eq!(publication_conflicts(&p), 0);
        p.adjacent
            .as_mut()
            .unwrap()
            .errors
            .push("foreign manifest".into());
        assert_eq!(publication_conflicts(&p), 1);
        p.pending_works[0]["status"] = "output_conflict".into();
        assert_eq!(publication_conflicts(&p), 1, "same failure counted twice");
    }
}
