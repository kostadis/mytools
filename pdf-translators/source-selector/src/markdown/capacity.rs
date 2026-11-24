//! Conservative per-job bounds include escaping, checkpoints, assembly and artifacts.
use super::*;
use std::collections::BTreeMap;
pub const FLOOR: u64 = 20 * 1024 * 1024 * 1024;
pub fn free(path: &Path) -> Result<u64> {
    use std::os::unix::ffi::OsStrExt;
    let path = std::ffi::CString::new(path.as_os_str().as_bytes())
        .map_err(|_| SelectionError::Invalid("NUL in capacity path".into()))?;
    let mut info = std::mem::MaybeUninit::<libc::statvfs>::uninit();
    if unsafe { libc::statvfs(path.as_ptr(), info.as_mut_ptr()) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    let info = unsafe { info.assume_init() };
    Ok((u128::from(info.f_bavail) * u128::from(info.f_frsize)).min(u128::from(u64::MAX)) as u64)
}
#[derive(Default, Serialize, Deserialize)]
pub struct Reservations {
    pub jobs: BTreeMap<String, u64>,
}
impl Reservations {
    pub fn reserve(&mut self, id: &str, bytes: u64, available: u64) -> bool {
        let held = self
            .jobs
            .iter()
            .filter(|(k, _)| k.as_str() != id)
            .map(|(_, v)| *v)
            .fold(0u64, u64::saturating_add);
        if available.saturating_sub(held).saturating_sub(FLOOR) < bytes {
            return false;
        }
        self.jobs.insert(id.into(), bytes);
        true
    }
    pub fn release(&mut self, id: &str) {
        self.jobs.remove(id);
    }
}
pub const WINDOW: u64 = 1024 * 1024 * 1024;
pub fn reservation_bytes(missing_source: u64, cached_bytes: u64, complete: bool) -> u64 {
    missing_source
        .saturating_mul(2)
        .saturating_add(cached_bytes.saturating_mul(16))
        .saturating_add(if complete { 16 * 1024 * 1024 } else { WINDOW })
}
pub fn job_bytes(output: &Path, ready: &Ready, engine: &worker::Engine, source_size: u64) -> u64 {
    let mut cached = 0u64;
    for first in (1..=ready.page_count).step_by(engine.chunk_pages as usize) {
        let last = ready.page_count.min(first + engine.chunk_pages - 1);
        cached = cached.saturating_add(
            fs::metadata(worker::range_path(
                output,
                &ready.sha256,
                engine,
                first,
                last,
            ))
            .map_or(0, |m| m.len()),
        );
    }
    let missing = if output
        .join("cache/sources")
        .join(format!("{}.pdf", ready.sha256))
        .exists()
    {
        0
    } else {
        source_size
    };
    reservation_bytes(
        missing,
        cached,
        worker::all_chunks(output, ready, engine).is_ok(),
    )
}
#[derive(Serialize, Deserialize)]
pub struct Request {
    pub nonce: String,
    pub bytes: u64,
}
#[derive(Serialize, Deserialize)]
pub struct Grant {
    pub nonce: String,
    pub allowed: bool,
}
/// Workers request allocation growth; only the coordinator owns reservations.
pub fn request(output: &Path, id: &str, bytes: u64) -> Result<()> {
    if !output.join("capacity-jobs").join(id).exists() {
        return Ok(());
    }
    let nonce = crate::digest_json(&(
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos(),
    ));
    write_json(
        &output.join("capacity-requests").join(format!("{id}.json")),
        &Request {
            nonce: nonce.clone(),
            bytes,
        },
    )?;
    let start = std::time::Instant::now();
    while start.elapsed() < std::time::Duration::from_secs(120) {
        if let Ok(grant) =
            read_json::<Grant>(&output.join("capacity-grants").join(format!("{id}.json")))
            && grant.nonce == nonce
        {
            return if grant.allowed {
                Ok(())
            } else {
                Err(SelectionError::Capacity(
                    "local allocation growth pending".into(),
                ))
            };
        }
        std::thread::sleep(std::time::Duration::from_millis(25));
    }
    Err(SelectionError::Capacity(
        "coordinator capacity grant unavailable".into(),
    ))
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn cached_assembly_fits_a_small_budget_and_uncached_growth_is_bounded() {
        let mut r = Reservations::default();
        let cached = reservation_bytes(0, 1024 * 1024, true);
        assert!(r.reserve("cached", cached, FLOOR + 64 * 1024 * 1024));
        let growth = reservation_bytes(0, 1024 * 1024, false);
        assert!(!r.reserve("growing", growth, FLOOR + 64 * 1024 * 1024));
        assert!(growth < 2 * 1024 * 1024 * 1024);
    }
    #[test]
    fn reservations_do_not_double_spend_and_smaller_jobs_fit() {
        let mut r = Reservations::default();
        assert!(r.reserve("one", 100, FLOOR + 150));
        assert!(!r.reserve("two", 100, FLOOR + 150));
        assert!(r.reserve("small", 40, FLOOR + 150));
        r.release("one");
        assert!(r.reserve("two", 100, FLOOR + 150));
        assert!(!r.reserve("none", 1, FLOOR));
    }
}
