use crate::{Result, SelectionError, inventory::checked_path};
use std::{
    fs,
    path::{Component, Path, PathBuf},
};
pub fn sibling(path: &Path) -> Result<()> {
    if path.components().count() != 1
        || !matches!(path.components().next(), Some(Component::Normal(_)))
    {
        return Err(SelectionError::Invalid(
            "manifest filename must be a sibling".into(),
        ));
    }
    Ok(())
}
pub fn directory(root: &Path, relative: &Path) -> Result<PathBuf> {
    if relative.as_os_str().is_empty() {
        Ok(root.to_path_buf())
    } else {
        checked_path(root, relative)
    }
}
pub fn read(path: &Path) -> Result<Option<Vec<u8>>> {
    match fs::symlink_metadata(path) {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(e) => Err(e.into()),
        Ok(m) => {
            if !m.is_file() || m.file_type().is_symlink() {
                return Err(SelectionError::Invalid(format!(
                    "redirected or non-file output refused: {}",
                    path.display()
                )));
            }
            Ok(Some(fs::read(path)?))
        }
    }
}
pub fn filename(value: &serde_json::Value) -> Result<PathBuf> {
    let path: PathBuf = crate::models::path_serde::deserialize(value.clone())
        .map_err(|e| SelectionError::Invalid(e.to_string()))?;
    sibling(&path)?;
    Ok(path)
}
pub fn path_value(path: &Path) -> serde_json::Value {
    #[derive(serde::Serialize)]
    struct P<'a> {
        #[serde(with = "crate::models::path_serde")]
        path: &'a Path,
    }
    serde_json::to_value(P { path }).expect("byte-safe path")["path"].clone()
}
pub fn discover(root: &Path) -> (Vec<PathBuf>, Vec<String>) {
    let mut dirs = vec![];
    let mut errors = vec![];
    let mut pending = vec![PathBuf::new()];
    let progress = crate::markdown::progress::Progress::new("manifest discovery");
    while let Some(relative) = pending.pop() {
        let path = root.join(&relative);
        match fs::read_dir(&path) {
            Err(e) => errors.push(format!("{}: {e}", path.display())),
            Ok(entries) => {
                for entry in entries {
                    match entry {
                        Err(e) => errors.push(format!("{}: {e}", path.display())),
                        Ok(entry) => match entry.file_type() {
                            Err(e) => errors.push(e.to_string()),
                            Ok(t) if t.is_dir() => pending.push(relative.join(entry.file_name())),
                            Ok(_) if entry.file_name() == "current-documents.json" => {
                                dirs.push(relative.clone())
                            }
                            _ => {}
                        },
                    }
                }
            }
        }
        progress.tick();
    }
    dirs.sort();
    dirs.dedup();
    (dirs, errors)
}
