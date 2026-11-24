//! Independent, read-only selection analysis; never applies production decisions.
pub mod audit;
pub mod history;
pub mod inputs;
pub mod models;
pub mod report;
pub mod review;
pub mod sampling;
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
