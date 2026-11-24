use crate::Result;
use serde_json::{Value, json};
use std::{
    io::Write,
    path::{Path, PathBuf},
    sync::{Arc, Mutex, mpsc},
    thread::JoinHandle,
    time::{Duration, Instant},
};
#[derive(Default)]
pub struct LogGate {
    stage: String,
    last: usize,
    seconds: u64,
}
impl LogGate {
    pub fn due(&mut self, stage: &str, done: usize, total: usize, seconds: u64) -> bool {
        let yes = self.stage != stage
            || done.saturating_sub(self.last) >= 100
            || seconds.saturating_sub(self.seconds) >= 30
            || (done == total && self.last != done);
        if yes {
            self.stage = stage.into();
            self.last = done;
            self.seconds = seconds;
        }
        yes
    }
}
struct State {
    gate: LogGate,
    value: Value,
    start: Instant,
    root: PathBuf,
}
pub struct Reporter {
    state: Arc<Mutex<State>>,
    stop: mpsc::Sender<()>,
    thread: Option<JoinHandle<Result<()>>>,
}
fn emit(s: &State) -> Result<()> {
    super::write_json(&s.root.join("progress.json"), &s.value)?;
    let mut log = std::fs::OpenOptions::new()
        .append(true)
        .create(true)
        .open(s.root.join("progress.jsonl"))?;
    writeln!(log, "{}", s.value)?;
    eprintln!("{}", s.value);
    Ok(())
}
impl Reporter {
    pub fn start(root: &Path) -> Result<Self> {
        let state = Arc::new(Mutex::new(State {
            gate: LogGate::default(),
            value: json!({"stage":"ready","done":0,"total":0,"remaining":0,"errors":0}),
            start: Instant::now(),
            root: root.into(),
        }));
        let (stop, recv) = mpsc::channel();
        let copy = state.clone();
        let thread = std::thread::spawn(move || {
            loop {
                match recv.recv_timeout(Duration::from_secs(30)) {
                    Ok(()) | Err(mpsc::RecvTimeoutError::Disconnected) => break,
                    Err(mpsc::RecvTimeoutError::Timeout) => {
                        let mut s = copy.lock().unwrap();
                        let elapsed = s.start.elapsed().as_secs();
                        let stage = s.value["stage"].as_str().unwrap_or("working").to_owned();
                        let done = s.value["done"].as_u64().unwrap_or(0) as usize;
                        let total = s.value["total"].as_u64().unwrap_or(0) as usize;
                        if s.gate.due(&stage, done, total, elapsed) {
                            emit(&s)?;
                        }
                    }
                }
            }
            Ok(())
        });
        Ok(Self {
            state,
            stop,
            thread: Some(thread),
        })
    }
    pub fn record(&self, stage: &str, done: usize, total: usize, errors: usize) -> Result<()> {
        let mut s = self.state.lock().unwrap();
        s.value = json!({"stage":stage,"done":done,"total":total,"remaining":total.saturating_sub(done),"errors":errors,"updated_at":chrono::Utc::now().to_rfc3339()});
        let seconds = s.start.elapsed().as_secs();
        if s.gate.due(stage, done, total, seconds) {
            emit(&s)?;
        }
        Ok(())
    }
    pub fn finish(mut self) -> Result<()> {
        let _ = self.stop.send(());
        if let Some(thread) = self.thread.take() {
            thread
                .join()
                .map_err(|_| super::invalid("progress thread failed"))??;
        }
        Ok(())
    }
}
impl Drop for Reporter {
    fn drop(&mut self) {
        let _ = self.stop.send(());
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}
