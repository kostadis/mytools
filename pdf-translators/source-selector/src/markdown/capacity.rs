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
pub fn job_bytes(source_size: u64, pages: u32, chunk_pages: u32) -> u64 {
    source_size.saturating_mul(2).saturating_add(
        u64::from(pages.div_ceil(chunk_pages)).saturating_mul(4 * 1024 * 1024 * 1024),
    )
}
#[cfg(test)]
mod tests {
    use super::*;
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
