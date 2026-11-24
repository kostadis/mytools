//! Additive policy selection and native-text search artifacts.
pub mod adjacent;
pub mod capacity;
pub mod continuous;
mod continuous_publication;
pub mod conversion;
pub mod dates;
pub mod metadata;
pub mod progress;
pub mod publication;
pub mod render;
pub mod selection;
pub mod worker;
use crate::{
    Result, SelectionError,
    models::{Source, path_serde},
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    fs::{self, File},
    io::Write,
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Candidate {
    pub source: Source,
    pub sha256: Option<String>,
    pub page_count: Option<u32>,
    pub dates: dates::DateEvidence,
    pub error: Option<String>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PolicyRecord {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub selection_revision: Option<String>,
    pub work_id: String,
    pub group_id: String,
    pub status: String,
    pub reason: String,
    pub selected_source_id: Option<String>,
    pub candidates: Vec<Candidate>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Ready {
    pub work_id: String,
    pub group_id: String,
    pub source_id: String,
    #[serde(with = "path_serde")]
    pub relative_path: PathBuf,
    pub sha256: String,
    pub page_count: u32,
    pub title: String,
    pub publisher: String,
    pub selection_basis: String,
    pub date: Option<dates::Stamp>,
    pub alternatives: Vec<String>,
    pub provenance: Value,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Snapshot {
    pub schema_version: u32,
    pub snapshot_id: String,
    pub policy: String,
    pub created: String,
    #[serde(with = "path_serde")]
    pub source_root: PathBuf,
    pub root_identity: Value,
    pub coverage_errors: Vec<String>,
    pub archives: usize,
    pub ready: Vec<Ready>,
    pub records: Vec<PolicyRecord>,
}

pub fn atomic_write(path: &Path, bytes: &[u8]) -> Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| SelectionError::Invalid("artifact has no parent".into()))?;
    fs::create_dir_all(parent)?;
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    let tmp = parent.join(format!(".write-{}-{nonce}", std::process::id()));
    let result = (|| {
        let mut f = File::create_new(&tmp)?;
        f.write_all(bytes)?;
        f.sync_all()?;
        fs::rename(&tmp, path)?;
        File::open(parent)?.sync_all()?;
        Ok(())
    })();
    if result.is_err() {
        let _ = fs::remove_file(tmp);
    }
    result
}
pub fn write_json(path: &Path, value: &impl Serialize) -> Result<()> {
    atomic_write(path, &serde_json::to_vec_pretty(value)?)
}
pub fn read_json<T: serde::de::DeserializeOwned>(path: &Path) -> Result<T> {
    Ok(serde_json::from_slice(&fs::read(path)?)?)
}
pub fn lock(output: &Path, name: &str) -> Result<File> {
    fs::create_dir_all(output)?;
    let f = fs::OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(output.join(name))?;
    f.try_lock()
        .map_err(|e| SelectionError::Invalid(format!("another operation holds {name}: {e}")))?;
    Ok(f)
}
pub fn safe_id(id: &str) -> Result<()> {
    if id.is_empty()
        || !id
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
    {
        return Err(SelectionError::Invalid("unsafe artifact identifier".into()));
    }
    Ok(())
}

/// Managed state must not redirect writes through a symlink into the source
/// library. The one intentional link is the validated corpus view.
pub fn validate_output(output: &Path) -> Result<()> {
    fn walk(root: &Path, dir: &Path) -> Result<()> {
        for entry in fs::read_dir(dir)? {
            let entry = entry?;
            let path = entry.path();
            let ty = entry.file_type()?;
            if ty.is_symlink() {
                let target = fs::read_link(&path)?;
                let is_pointer = path == root.join("corpus/current")
                    || (path.parent() == Some(root.join("corpus").as_path())
                        && path
                            .file_name()
                            .and_then(|s| s.to_str())
                            .and_then(|s| s.strip_prefix(".current-"))
                            .is_some_and(|s| {
                                !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit())
                            }));
                let allowed = is_pointer
                    && target.parent() == Some(Path::new("generations"))
                    && target
                        .file_name()
                        .is_some_and(|n| n.to_str().is_some_and(|s| safe_id(s).is_ok()));
                if !allowed {
                    return Err(SelectionError::Invalid(format!(
                        "managed output contains a symlink: {}",
                        path.display()
                    )));
                }
            } else if ty.is_dir() {
                walk(root, &path)?;
            }
        }
        Ok(())
    }
    if output.exists() {
        walk(output, output)?;
    }
    Ok(())
}

/// None denotes an unavailable original; an observed mismatch must never be
/// masked by an otherwise usable offline source cache.
pub fn live_source_matches(root: &Path, ready: &Ready) -> Result<Option<bool>> {
    if !root.try_exists()? {
        return Ok(None);
    }
    let path = match crate::inventory::checked_path(root, &ready.relative_path) {
        Ok(p) => p,
        Err(SelectionError::Io(e)) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(e) => return Err(e),
    };
    match crate::grouping::hash_source(&path) {
        Ok(hash) => Ok(Some(hash == ready.sha256)),
        Err(SelectionError::Io(e)) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(e) => Err(e),
    }
}
