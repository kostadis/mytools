//! One source writer performs slow publication independently of selection/dispatch.
use super::*;
use super::{
    continuous::{Resolution, publish_group},
    worker::Engine,
};
use crate::{models::Group, store::Store};
use std::{
    collections::{BTreeMap, VecDeque},
    sync::{
        Arc,
        atomic::{AtomicBool, AtomicU64, Ordering},
        mpsc,
    },
    thread::{self, JoinHandle},
    time::Duration,
};

pub(crate) struct PublishRequest {
    pub sequence: u64,
    pub group: Group,
    pub resolution: Resolution,
    pub priority: u8,
    pub withdrawal: bool,
}
struct ReconcileRequest {
    sequence: u64,
    directory: PathBuf,
    snapshot: Snapshot,
    authority: String,
}
enum Command {
    Publish(Box<PublishRequest>),
    Reconcile(Box<ReconcileRequest>),
    Stop,
}
pub(crate) enum Outcome {
    Published(std::result::Result<Box<Resolution>, String>),
    Superseded,
    Reconciled {
        directory: PathBuf,
        result: std::result::Result<usize, String>,
        stale: bool,
    },
}
pub(crate) struct Response {
    pub sequence: u64,
    pub outcome: Outcome,
}
pub(crate) struct Publisher {
    sender: mpsc::Sender<Command>,
    receiver: mpsc::Receiver<Response>,
    stop: Arc<AtomicBool>,
    fence: Arc<AtomicBool>,
    active: Arc<AtomicU64>,
    handle: Option<JoinHandle<()>>,
}
impl Publisher {
    pub fn start(
        work: &Path,
        output: &Path,
        engine: &Engine,
        graph: &str,
        gate: Option<PathBuf>,
        conversion_lease: File,
    ) -> Result<Self> {
        let (tx, rx) = mpsc::channel();
        let (results, result_rx) = mpsc::channel();
        let (init, initialized) = mpsc::channel();
        let stop = Arc::new(AtomicBool::new(false));
        let fence = Arc::new(AtomicBool::new(false));
        let active = Arc::new(AtomicU64::new(0));
        let owner = Worker {
            _conversion_lease: conversion_lease,
            work: work.into(),
            output: output.into(),
            engine: engine.clone(),
            graph: graph.into(),
            gate,
            stop: stop.clone(),
            fence: fence.clone(),
            active: active.clone(),
        };
        let handle = thread::Builder::new()
            .name("rpg-publish".into())
            .spawn(move || {
                let startup = (|| -> Result<_> {
                    let lease = lock(&owner.output, "publication-worker.lock")?;
                    let db = Store::open_readonly(&owner.work.join("selection.db"))?;
                    Ok((lease, db))
                })();
                match startup {
                    Err(e) => {
                        let _ = init.send(Err(e.to_string()));
                    }
                    Ok((_lease, db)) => {
                        let _ = init.send(Ok(()));
                        owner.run(db, rx, results);
                    }
                }
            })?;
        initialized
            .recv()
            .map_err(|_| SelectionError::Invalid("publication worker failed to initialize".into()))?
            .map_err(SelectionError::Invalid)?;
        Ok(Self {
            sender: tx,
            receiver: result_rx,
            stop,
            fence,
            active,
            handle: Some(handle),
        })
    }
    pub fn submit(&self, request: PublishRequest) -> Result<()> {
        self.sender
            .send(Command::Publish(Box::new(request)))
            .map_err(|_| SelectionError::Invalid("publication worker disconnected".into()))
    }
    pub fn reconcile(
        &self,
        sequence: u64,
        directory: PathBuf,
        snapshot: Snapshot,
        authority: String,
    ) -> Result<()> {
        self.sender
            .send(Command::Reconcile(Box::new(ReconcileRequest {
                sequence,
                directory,
                snapshot,
                authority,
            })))
            .map_err(|_| SelectionError::Invalid("publication worker disconnected".into()))
    }
    pub fn poll(&self) -> Result<Option<Response>> {
        match self.receiver.try_recv() {
            Ok(r) => Ok(Some(r)),
            Err(mpsc::TryRecvError::Empty) => Ok(None),
            Err(mpsc::TryRecvError::Disconnected) => Err(SelectionError::Invalid(
                "publication worker exited unexpectedly".into(),
            )),
        }
    }
    pub fn active_sequence(&self) -> u64 {
        self.active.load(Ordering::Acquire)
    }
    pub fn fence(&self) {
        self.fence.store(true, Ordering::Release);
    }
}
impl Drop for Publisher {
    fn drop(&mut self) {
        self.fence.store(true, Ordering::Release);
        self.stop.store(true, Ordering::Release);
        let _ = self.sender.send(Command::Stop);
        if self.handle.as_ref().is_some_and(|h| h.is_finished()) {
            let _ = self.handle.take().unwrap().join();
        }
    }
}
struct Worker {
    _conversion_lease: File,
    work: PathBuf,
    output: PathBuf,
    engine: Engine,
    graph: String,
    gate: Option<PathBuf>,
    stop: Arc<AtomicBool>,
    fence: Arc<AtomicBool>,
    active: Arc<AtomicU64>,
}
impl Worker {
    fn run(self, db: Store, receiver: mpsc::Receiver<Command>, results: mpsc::Sender<Response>) {
        let mut pending: BTreeMap<String, Box<PublishRequest>> = BTreeMap::new();
        let mut reconcile = VecDeque::new();
        let mut session: Option<adjacent::Session> = None;
        while !self.stop.load(Ordering::Acquire) {
            let command = if pending.is_empty() && reconcile.is_empty() {
                match receiver.recv_timeout(Duration::from_millis(25)) {
                    Ok(c) => Some(c),
                    Err(mpsc::RecvTimeoutError::Timeout) => None,
                    Err(_) => break,
                }
            } else {
                None
            };
            let commands = command.into_iter().chain(receiver.try_iter());
            for command in commands {
                match command {
                    Command::Stop => return,
                    Command::Publish(request) => {
                        if let Some(old) = pending.insert(request.group.group_id.clone(), request) {
                            let _ = results.send(Response {
                                sequence: old.sequence,
                                outcome: Outcome::Superseded,
                            });
                        }
                    }
                    Command::Reconcile(r) => reconcile.push_back(r),
                }
            }
            if let Some(id) = pending
                .iter()
                .min_by_key(|(_, r)| (r.priority, r.sequence))
                .map(|(id, _)| id.clone())
            {
                let request = pending.remove(&id).unwrap();
                let sequence = request.sequence;
                if self.fence.load(Ordering::Acquire) && !request.withdrawal {
                    let _ = results.send(Response {
                        sequence,
                        outcome: Outcome::Superseded,
                    });
                    continue;
                }
                self.active.store(sequence, Ordering::Release);
                while self.gate.as_ref().is_some_and(|g| g.exists())
                    && !self.stop.load(Ordering::Acquire)
                {
                    thread::sleep(Duration::from_millis(25));
                }
                if self.stop.load(Ordering::Acquire) {
                    return;
                }
                let result = (|| -> Result<Resolution> {
                    if session.is_none() {
                        session = Some(adjacent::Session::new_scoped(
                            &self.output,
                            &request.resolution.snapshot,
                        )?);
                    }
                    let mut resolution = request.resolution;
                    let session = session.as_mut().unwrap();
                    if request.withdrawal {
                        session.clear_authority_database();
                        let revision = crate::digest_json(&db.meta("authority_revision")?);
                        session.set_commit_authority(db.path(), &revision);
                        resolution.publication = Some(publication::publish_snapshot(
                            &self.output,
                            &self.engine,
                            &resolution.snapshot,
                            Some(session),
                            false,
                        )?);
                    } else {
                        session.set_publication_fence(self.fence.clone());
                        publish_group(
                            &db,
                            &self.output,
                            &request.group,
                            &mut resolution,
                            &self.engine,
                            session,
                            &self.graph,
                        )?;
                    }
                    Ok(resolution)
                })();
                self.active.store(0, Ordering::Release);
                if results
                    .send(Response {
                        sequence,
                        outcome: Outcome::Published(
                            result.map(Box::new).map_err(|e| e.to_string()),
                        ),
                    })
                    .is_err()
                {
                    return;
                }
            } else if let Some(r) = reconcile.pop_front() {
                self.active.store(r.sequence, Ordering::Release);
                let mut stale = false;
                let result = (|| -> Result<usize> {
                    if session.is_none() {
                        session = Some(adjacent::Session::new_scoped(&self.output, &r.snapshot)?);
                    }
                    if crate::digest_json(&db.meta("authority_revision")?) != r.authority {
                        stale = true;
                        return Ok(0);
                    }
                    let session = session.as_mut().unwrap();
                    session.clear_authority_database();
                    session.set_commit_authority(db.path(), &r.authority);
                    session.set_publication_fence(self.fence.clone());
                    let result =
                        session.reconcile_discovered(&r.snapshot, &self.engine, &r.directory);
                    if crate::digest_json(&db.meta("authority_revision")?) != r.authority {
                        stale = true;
                    }
                    result
                })();
                self.active.store(0, Ordering::Release);
                if results
                    .send(Response {
                        sequence: r.sequence,
                        outcome: Outcome::Reconciled {
                            directory: r.directory,
                            result: result.map_err(|e| e.to_string()),
                            stale,
                        },
                    })
                    .is_err()
                {
                    return;
                }
            }
        }
    }
}

pub(crate) struct DiscoveryWorker {
    receiver: mpsc::Receiver<adjacent::Discovery>,
    stop: Arc<AtomicBool>,
    handle: Option<JoinHandle<()>>,
}
impl DiscoveryWorker {
    pub fn start(root: &Path, identity: &Value) -> Result<Self> {
        let (tx, receiver) = mpsc::channel();
        let stop = Arc::new(AtomicBool::new(false));
        let cancelled = stop.clone();
        let root = root.to_path_buf();
        let identity = identity.clone();
        let handle = thread::Builder::new()
            .name("rpg-discovery".into())
            .spawn(move || {
                let mut discovery = adjacent::Discovery::new(&root, &identity);
                while !cancelled.load(Ordering::Acquire) {
                    if discovery.step() {
                        let _ = tx.send(discovery);
                        return;
                    }
                    thread::sleep(Duration::from_millis(2));
                }
            })?;
        Ok(Self {
            receiver,
            stop,
            handle: Some(handle),
        })
    }
    pub fn poll(&self) -> Result<Option<adjacent::Discovery>> {
        match self.receiver.try_recv() {
            Ok(d) => Ok(Some(d)),
            Err(mpsc::TryRecvError::Empty) => Ok(None),
            Err(_) => Err(SelectionError::Invalid(
                "manifest discovery worker exited unexpectedly".into(),
            )),
        }
    }
}
impl Drop for DiscoveryWorker {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Release);
        if self.handle.as_ref().is_some_and(|h| h.is_finished()) {
            let _ = self.handle.take().unwrap().join();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn publisher_holds_shared_conversion_lease_without_its_coordinator() {
        let work = tempfile::tempdir().unwrap();
        let out = tempfile::tempdir().unwrap();
        let root = tempfile::tempdir().unwrap();
        Store::open(&work.path().join("selection.db")).unwrap();
        let original = lock(out.path(), "conversion.lock").unwrap();
        let engine = Engine {
            id: "test".into(),
            binary: "/bin/true".into(),
            binary_sha256: String::new(),
            provenance: Value::Null,
            chunk_pages: 20,
            timeout_secs: 120,
        };
        let gate = out.path().join("blocked");
        fs::write(&gate, "blocked").unwrap();
        let publisher = Publisher::start(
            work.path(),
            out.path(),
            &engine,
            "graph",
            Some(gate.clone()),
            original.try_clone().unwrap(),
        )
        .unwrap();
        let snapshot = Snapshot {
            schema_version: 1,
            snapshot_id: "snapshot".into(),
            policy: "test".into(),
            created: String::new(),
            source_root: root.path().into(),
            root_identity: crate::inventory::root_identity(root.path()).unwrap(),
            coverage_errors: vec![],
            archives: 0,
            ready: vec![],
            records: vec![],
        };
        publisher
            .submit(PublishRequest {
                sequence: 1,
                group: Group {
                    group_id: "group".into(),
                    source_ids: vec![],
                    membership_digest: String::new(),
                    reasons: vec![],
                },
                resolution: Resolution {
                    snapshot,
                    publication: None,
                },
                priority: 0,
                withdrawal: false,
            })
            .unwrap();
        let start = std::time::Instant::now();
        while publisher.active_sequence() == 0 && start.elapsed() < Duration::from_secs(2) {
            thread::sleep(Duration::from_millis(5));
        }
        drop(original);
        let overlaps = lock(out.path(), "conversion.lock").is_ok();
        drop(publisher);
        fs::remove_file(gate).unwrap();
        assert!(
            !overlaps,
            "a batch publisher could enter while the detached source writer was alive"
        );
    }
}
