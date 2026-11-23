use crate::{Result, SelectionError, digest_json, models::*};
use std::{
    collections::BTreeMap,
    fs,
    path::{Component, Path},
    time::UNIX_EPOCH,
};

pub fn fingerprint(path: &Path) -> Result<Fingerprint> {
    let meta = fs::symlink_metadata(path)?;
    if !meta.is_file() {
        return Err(SelectionError::Invalid(format!(
            "not a regular file: {}",
            path.display()
        )));
    }
    let mut fp = Fingerprint {
        size: meta.len(),
        mtime_ns: meta
            .modified()
            .ok()
            .and_then(|v| v.duration_since(UNIX_EPOCH).ok())
            .map(|v| v.as_nanos()),
        ctime_ns: None,
        device: None,
        inode: None,
        sha256: None,
    };
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        fp.ctime_ns = Some(meta.ctime() as i128 * 1_000_000_000 + meta.ctime_nsec() as i128);
        fp.device = Some(meta.dev());
        fp.inode = Some(meta.ino());
    }
    Ok(fp)
}

pub fn checked_path(root: &Path, relative: &Path) -> Result<std::path::PathBuf> {
    if relative.as_os_str().is_empty()
        || relative
            .components()
            .any(|c| !matches!(c, Component::Normal(_)))
    {
        return Err(SelectionError::Invalid(
            "source path must be relative without traversal".into(),
        ));
    }
    let mut path = root.to_path_buf();
    for part in relative.components() {
        path.push(part);
        if fs::symlink_metadata(&path)?.file_type().is_symlink() {
            return Err(SelectionError::Invalid(format!(
                "source symlink refused: {}",
                path.display()
            )));
        }
    }
    Ok(path)
}

pub fn scan_root(root: &Path) -> Result<InventoryResult> {
    scan_root_with_progress(root, |_| Ok(()))
}

pub fn scan_root_with_progress(
    root: &Path,
    mut progress: impl FnMut(&InventoryResult) -> Result<()>,
) -> Result<InventoryResult> {
    if !root.is_dir() {
        return Err(SelectionError::Invalid(format!(
            "root is not a readable directory: {}",
            root.display()
        )));
    }
    let root = root.canonicalize()?;
    // An unreadable root cannot replace an established inventory with an empty scan.
    drop(fs::read_dir(&root)?);
    let mut result = InventoryResult {
        root: root.clone(),
        started: chrono::Utc::now().to_rfc3339(),
        finished: String::new(),
        sources: vec![],
        errors: vec![],
    };
    walk(&root, &root, &mut result, &mut progress)?;
    result.finished = chrono::Utc::now().to_rfc3339();
    progress(&result)?;
    result
        .sources
        .sort_by(|a, b| a.relative_path.cmp(&b.relative_path));
    Ok(result)
}

fn walk(
    root: &Path,
    dir: &Path,
    result: &mut InventoryResult,
    progress: &mut dyn FnMut(&InventoryResult) -> Result<()>,
) -> Result<()> {
    let entries = match fs::read_dir(dir) {
        Ok(v) => v,
        Err(e) => {
            result.errors.push(format!("{}: {e}", dir.display()));
            return Ok(());
        }
    };
    for entry in entries {
        let entry = match entry {
            Ok(v) => v,
            Err(e) => {
                result.errors.push(e.to_string());
                continue;
            }
        };
        let path = entry.path();
        let kind = match entry.file_type() {
            Ok(v) => v,
            Err(e) => {
                result.errors.push(format!("{}: {e}", path.display()));
                continue;
            }
        };
        if kind.is_symlink() {
            result
                .errors
                .push(format!("symlink not followed: {}", path.display()));
            continue;
        }
        let name = entry.file_name().to_string_lossy().to_lowercase();
        if kind.is_dir() {
            if !name.ends_with("-responses") && ![".git", "_gsdata_"].contains(&name.as_str()) {
                walk(root, &path, result, progress)?;
            }
            continue;
        }
        if !kind.is_file() {
            continue;
        }
        let ext = path
            .extension()
            .and_then(|s| s.to_str())
            .unwrap_or("")
            .to_lowercase();
        let source_kind = match ext.as_str() {
            "pdf" => SourceKind::Pdf,
            "zip" | "rar" | "7z" | "tar" | "gz" => SourceKind::Archive,
            _ => continue,
        };
        let relative = path
            .strip_prefix(root)
            .expect("child of root")
            .to_path_buf();
        let fp = match fingerprint(&path) {
            Ok(v) => v,
            Err(e) => {
                result.errors.push(format!("{}: {e}", path.display()));
                continue;
            }
        };
        let parts: Vec<_> = relative
            .components()
            .map(|p| p.as_os_str().to_string_lossy().into_owned())
            .collect();
        let stem = path.file_stem().unwrap_or_default().to_string_lossy();
        let artifacts = [
            format!("{stem}.json"),
            format!("{stem}.md"),
            format!("{stem}-mistral.md"),
            format!("{stem}-extract.json"),
            format!("{stem}-mistral-raw.json"),
        ]
        .into_iter()
        .filter(|n| dir.join(n).is_file())
        .collect();
        let source_id = digest_json(&(path_bytes(root), path_bytes(&relative)));
        result.sources.push(Source {
            source_id,
            relative_path: relative,
            kind: source_kind,
            publisher: if parts.len() > 1 {
                parts[0].clone()
            } else {
                String::new()
            },
            product_folder: if parts.len() > 2 {
                parts[1].clone()
            } else {
                String::new()
            },
            fingerprint: fp,
            read_error: fs::File::open(&path).err().map(|e| e.to_string()),
            baseline_established: false,
            artifacts,
            metadata: BTreeMap::from([("inventory_root".into(), serde_json::json!(root.to_str()))]),
        });
        if result.sources.len().is_multiple_of(100) {
            progress(result)?;
        }
    }
    Ok(())
}

pub fn path_bytes(path: &Path) -> Vec<u8> {
    #[cfg(unix)]
    {
        use std::os::unix::ffi::OsStrExt;
        path.as_os_str().as_bytes().to_vec()
    }
    #[cfg(not(unix))]
    {
        path.as_os_str().as_encoded_bytes().to_vec()
    }
}

pub fn root_identity(root: &Path) -> Result<serde_json::Value> {
    let meta = fs::metadata(root)?;
    if !meta.is_dir() {
        return Err(SelectionError::Invalid(
            "library root is not a directory".into(),
        ));
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        Ok(serde_json::json!({"device":meta.dev(),"inode":meta.ino()}))
    }
    #[cfg(not(unix))]
    {
        Ok(
            serde_json::json!({"created":meta.created().ok().and_then(|v|v.duration_since(UNIX_EPOCH).ok()).map(|v|v.as_nanos())}),
        )
    }
}
