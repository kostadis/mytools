//! Independent, read-only selection analysis; never applies production decisions.
pub const POLICY_VERSION: &str = "library-selection-analysis-v2";
pub mod audit;
pub mod history;
pub mod inputs;
pub mod models;
pub mod progress;
pub mod report;
pub mod review;
pub mod sampling;
pub mod workflow;
use crate::{Result, SelectionError};
use serde::{Serialize, de::DeserializeOwned};
use std::path::Path;
pub(crate) fn invalid(message: impl Into<String>) -> SelectionError {
    SelectionError::Invalid(message.into())
}
pub fn read_json<T: DeserializeOwned>(path: &Path) -> Result<T> {
    Ok(serde_json::from_slice(&std::fs::read(path)?)?)
}
pub fn write_json(path: &Path, value: &impl Serialize) -> Result<()> {
    let bytes = serde_json::to_vec_pretty(value)?;
    let tmp = path.with_extension("json.tmp");
    let mut file = std::fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(&tmp)?;
    use std::io::Write;
    file.write_all(&bytes)?;
    file.sync_all()?;
    std::fs::rename(&tmp, path)?;
    Ok(())
}
pub(crate) fn new_stage(parent: &Path, kind: &str) -> Result<std::path::PathBuf> {
    let nonce = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|_| invalid("clock predates epoch"))?
        .as_nanos();
    let stage = parent.join(format!(".{kind}-{}-{nonce}", std::process::id()));
    std::fs::create_dir(&stage)?;
    Ok(stage)
}
