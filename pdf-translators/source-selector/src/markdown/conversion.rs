use super::*;
use super::{
    publication::Publication,
    worker::{Engine, Job, WorkerResult},
};
use crate::{
    digest_json,
    evidence::{PopplerExtractor, TextExtractor},
    grouping::hash_source,
    store::Store,
};
use clap::Args;
use std::{
    collections::VecDeque,
    process::{Child, Command, Stdio},
    time::{Duration, Instant},
};

#[derive(Clone, Debug, Args)]
pub struct Options {
    #[arg(long)]
    pub output: PathBuf,
    #[arg(long, default_value_t = 2)]
    pub workers: usize,
    #[arg(long, default_value_t = 20)]
    pub chunk_pages: u32,
    #[arg(long, default_value_t = 120)]
    pub timeout_secs: u64,
    #[arg(long, default_value_t = 1800)]
    pub job_timeout_secs: u64,
    #[arg(long,default_value_t=usize::MAX)]
    pub limit: usize,
    #[arg(long)]
    pub retry_failed: bool,
    #[arg(long, default_value = "pdftotext")]
    pub pdftotext: PathBuf,
}
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct Report {
    pub selection_id: String,
    pub scheduled: usize,
    pub failed: usize,
    pub needs_ocr_or_visual_review: usize,
    pub reused_ranges: usize,
    pub extracted_ranges: usize,
    pub published_books: usize,
    pub publication: Option<Publication>,
    pub warnings: Vec<String>,
}
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
struct State {
    attempts: usize,
    status: String,
    heartbeat: String,
    error: Option<String>,
}
struct Running {
    child: Child,
    job: Job,
    start: Instant,
    state: State,
}
fn executable(path: &Path) -> Result<PathBuf> {
    if path.components().count() > 1 {
        return Ok(path.canonicalize()?);
    }
    for dir in std::env::split_paths(&std::env::var_os("PATH").unwrap_or_default()) {
        let p = dir.join(path);
        if p.is_file() {
            return Ok(p.canonicalize()?);
        }
    }
    Err(SelectionError::Invalid(
        "pdftotext executable not found".into(),
    ))
}
pub fn engine(options: &Options) -> Result<Engine> {
    let binary = executable(&options.pdftotext)?;
    let sha = hash_source(&binary)?;
    let extractor =
        PopplerExtractor::new(binary.clone(), Duration::from_secs(options.timeout_secs));
    let provenance = extractor.provenance();
    if provenance["version_output"]
        .as_str()
        .is_none_or(str::is_empty)
    {
        return Err(SelectionError::Invalid(format!(
            "cannot identify extractor: {provenance}"
        )));
    }
    let mut engine = Engine {
        id: String::new(),
        binary,
        binary_sha256: sha,
        provenance,
        chunk_pages: options.chunk_pages,
        timeout_secs: options.timeout_secs,
    };
    engine.id = digest_json(&(1, &engine));
    Ok(engine)
}
fn stop(child: &mut Child) {
    #[cfg(unix)]
    {
        let _ = Command::new("kill")
            .args(["-KILL", "--", &format!("-{}", child.id())])
            .status();
    }
    let _ = child.kill();
    let _ = child.wait();
}
pub fn run(options: Options) -> Result<Report> {
    if options.workers == 0
        || options.workers > 8
        || options.chunk_pages == 0
        || options.chunk_pages > 100
        || options.timeout_secs == 0
        || options.job_timeout_secs == 0
    {
        return Err(SelectionError::Usage(
            "workers 1..8, chunk pages 1..100 and positive timeouts required".into(),
        ));
    }
    let output = if options.output.exists() {
        options.output.canonicalize()?
    } else {
        return Err(SelectionError::Invalid(
            "select into output directory first".into(),
        ));
    };
    let snapshot = selection::load_current(&output)?;
    validate_output(&output)?;
    // Offline source caches are supported; canonicalize the frozen original root
    // when available and use lexical containment as a second independent guard.
    if output.starts_with(&snapshot.source_root) {
        return Err(SelectionError::Invalid(
            "output must be outside source library".into(),
        ));
    }
    if snapshot.source_root.exists() {
        crate::export::validate_work_dir(&snapshot.source_root, &output)?;
    }
    let _coordinator = lock(&output, "conversion.lock")?;
    let engine = engine(&options)?;
    let mut store = Store::open(&output.join("markdown.db"))?;
    let mut queue = VecDeque::new();
    let mut report = Report {
        selection_id: snapshot.snapshot_id.clone(),
        ..Report::default()
    };
    for ready in snapshot.ready.iter().take(options.limit) {
        let id = digest_json(&(&ready.sha256, &engine.id, ready.page_count));
        let state: State = store
            .get_cached(&id, "job", "v1")?
            .map(serde_json::from_value)
            .transpose()?
            .unwrap_or_default();
        if state.status == "failed" && (!options.retry_failed || state.attempts >= 3) {
            report.failed += 1;
            report.warnings.push(format!(
                "{id}: failed; explicit retry allowed up to three attempts"
            ));
            continue;
        }
        // Detect orphaned workers by their OS-held lease, never by wall time.
        match lock(&output.join("leases"), &id) {
            Ok(f) => drop(f),
            Err(_) => {
                report.warnings.push(format!(
                    "{id}: existing worker retains lease; retry coordinator after it exits"
                ));
                continue;
            }
        }
        queue.push_back((
            Job {
                id,
                output: output.clone(),
                source_root: snapshot.source_root.clone(),
                snapshot_id: snapshot.snapshot_id.clone(),
                ready: ready.clone(),
                engine: engine.clone(),
            },
            state,
        ));
    }
    let mut active: Vec<Running> = vec![];
    let mut heartbeat = Instant::now();
    while !queue.is_empty() || !active.is_empty() {
        while active.len() < options.workers && !queue.is_empty() {
            let (job, mut state) = queue.pop_front().unwrap();
            let request = output.join("jobs").join(format!("{}.json", job.id));
            write_json(&request, &job)?;
            let result_path = output.join("results").join(format!("{}.json", job.id));
            if result_path.exists() {
                fs::remove_file(&result_path)?;
            }
            fs::create_dir_all(output.join("logs"))?;
            let log = fs::OpenOptions::new()
                .create(true)
                .append(true)
                .open(output.join("logs").join(format!("{}.log", job.id)))?;
            let mut cmd = Command::new(std::env::current_exe()?);
            cmd.args(["markdown-worker", "--job"])
                .arg(&request)
                .stdin(Stdio::null())
                .stdout(Stdio::from(log.try_clone()?))
                .stderr(Stdio::from(log));
            #[cfg(unix)]
            {
                use std::os::unix::process::CommandExt;
                cmd.process_group(0);
            }
            state.status = "running".into();
            state.heartbeat = chrono::Utc::now().to_rfc3339();
            state.error = None;
            store.put_cached(&job.id, "job", "v1", &serde_json::to_value(&state)?)?;
            match cmd.spawn() {
                Ok(child) => {
                    report.scheduled += 1;
                    active.push(Running {
                        child,
                        job,
                        start: Instant::now(),
                        state,
                    });
                }
                Err(e) => {
                    state.status = "failed".into();
                    state.attempts += 1;
                    state.error = Some(e.to_string());
                    store.put_cached(&job.id, "job", "v1", &serde_json::to_value(state)?)?;
                    report.failed += 1;
                }
            }
        }
        let mut i = 0;
        while i < active.len() {
            let timeout = active[i].start.elapsed() > Duration::from_secs(options.job_timeout_secs);
            let exit = active[i].child.try_wait()?;
            if !timeout && exit.is_none() {
                i += 1;
                continue;
            }
            let mut item = active.swap_remove(i);
            if timeout {
                stop(&mut item.child);
            }
            let result: WorkerResult = if !timeout && exit.is_some_and(|s| s.success()) {
                read_json(&output.join("results").join(format!("{}.json", item.job.id)))
                    .unwrap_or_else(|e| WorkerResult {
                        status: "failed".into(),
                        error: Some(e.to_string()),
                        ..WorkerResult::default()
                    })
            } else {
                WorkerResult {
                    status: "failed".into(),
                    error: Some(if timeout {
                        "job wall time exceeded".into()
                    } else {
                        format!("worker exited {exit:?}")
                    }),
                    ..WorkerResult::default()
                }
            };
            item.state.status = result.status.clone();
            item.state.error = result.error.clone();
            item.state.heartbeat = chrono::Utc::now().to_rfc3339();
            if result.status == "failed" {
                item.state.attempts += 1;
                report.failed += 1;
            } else if result.status == "needs_ocr_or_visual_review" {
                report.needs_ocr_or_visual_review += 1;
            }
            report.reused_ranges += result.reused_ranges;
            report.extracted_ranges += result.extracted_ranges;
            store.put_cached(
                &item.job.id,
                "job",
                "v1",
                &serde_json::to_value(item.state)?,
            )?;
            eprintln!(
                "{}: {} ({} reused, {} extracted ranges)",
                item.job.ready.title, result.status, result.reused_ranges, result.extracted_ranges
            );
            report.publication = Some(publication::publish(&output, &engine)?);
        }
        if heartbeat.elapsed() >= Duration::from_secs(30) {
            eprintln!(
                "Markdown heartbeat: {} active, {} queued",
                active.len(),
                queue.len()
            );
            for item in &mut active {
                item.state.heartbeat = chrono::Utc::now().to_rfc3339();
                store.put_cached(
                    &item.job.id,
                    "job",
                    "v1",
                    &serde_json::to_value(&item.state)?,
                )?;
            }
            heartbeat = Instant::now();
        }
        if !active.is_empty() {
            std::thread::sleep(Duration::from_millis(50));
        }
    }
    report.publication = Some(publication::publish(&output, &engine)?);
    report.published_books = report.publication.as_ref().unwrap().books;
    write_json(&output.join("last-run.json"), &report)?;
    Ok(report)
}
