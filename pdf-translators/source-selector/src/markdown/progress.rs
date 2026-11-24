use std::{
    sync::{
        Arc,
        atomic::{AtomicUsize, Ordering},
        mpsc,
    },
    thread,
    time::Duration,
};
pub struct Progress {
    label: String,
    count: Arc<AtomicUsize>,
    stop: Option<mpsc::Sender<()>>,
    thread: Option<thread::JoinHandle<()>>,
}
impl Progress {
    pub fn new(label: &str) -> Self {
        let count = Arc::new(AtomicUsize::new(0));
        let observed = count.clone();
        let (tx, rx) = mpsc::channel();
        let task = label.to_string();
        let thread = thread::spawn(move || {
            while rx.recv_timeout(Duration::from_secs(30)).is_err() {
                eprintln!(
                    "{task}: heartbeat, {} items processed",
                    observed.load(Ordering::Relaxed)
                );
            }
        });
        Self {
            label: label.into(),
            count,
            stop: Some(tx),
            thread: Some(thread),
        }
    }
    pub fn tick(&self) {
        let n = self.count.fetch_add(1, Ordering::Relaxed) + 1;
        if n.is_multiple_of(100) {
            eprintln!("{}: {n} items processed", self.label);
        }
    }
}
impl Drop for Progress {
    fn drop(&mut self) {
        if let Some(stop) = self.stop.take() {
            let _ = stop.send(());
        }
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}
