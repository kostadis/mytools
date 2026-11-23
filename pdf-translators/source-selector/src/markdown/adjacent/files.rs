use crate::{Result, SelectionError};
use serde::{Deserialize, Serialize};
use std::{
    cell::Cell,
    ffi::CString,
    fs::File,
    io::{Read, Write},
    os::{
        fd::{AsRawFd, FromRawFd},
        unix::{ffi::OsStrExt, fs::MetadataExt},
    },
};
use std::{
    fs,
    path::{Component, Path, PathBuf},
};

/// Every source-tree syscall is relative to this pinned, no-follow directory.
pub struct Directory {
    root: PathBuf,
    relative: PathBuf,
    identity: serde_json::Value,
    file: File,
    unsupported_sync: Cell<bool>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct Plan {
    #[serde(with = "crate::models::path_serde")]
    pub target: PathBuf,
    #[serde(with = "crate::models::path_serde")]
    pub temporary: PathBuf,
    pub before: Option<String>,
    pub after: String,
    #[serde(with = "crate::models::path_serde")]
    pub backup: PathBuf,
}
fn cstring(path: &Path) -> Result<CString> {
    CString::new(path.as_os_str().as_bytes())
        .map_err(|_| SelectionError::Invalid("NUL in filename".into()))
}
fn opened(fd: i32) -> Result<File> {
    if fd < 0 {
        Err(std::io::Error::last_os_error().into())
    } else {
        Ok(unsafe { File::from_raw_fd(fd) })
    }
}
fn child(parent: &File, name: &Path, flags: i32) -> Result<File> {
    let c = cstring(name)?;
    opened(unsafe {
        libc::openat(
            parent.as_raw_fd(),
            c.as_ptr(),
            flags | libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK,
            0o600,
        )
    })
}
fn chain(root: &Path, relative: &Path, identity: &serde_json::Value) -> Result<File> {
    if !root.is_absolute() {
        return Err(SelectionError::Invalid(
            "source root must be absolute".into(),
        ));
    }
    let mut dir = File::open("/")?;
    for part in root.components() {
        match part {
            Component::RootDir => {}
            Component::Normal(n) => {
                dir = child(&dir, Path::new(n), libc::O_RDONLY | libc::O_DIRECTORY)?
            }
            _ => return Err(SelectionError::Invalid("noncanonical source root".into())),
        }
    }
    let m = dir.metadata()?;
    if *identity != serde_json::json!({"device":m.dev(),"inode":m.ino()}) {
        return Err(SelectionError::Invalid(
            "source root identity changed".into(),
        ));
    }
    for part in relative.components() {
        match part {
            Component::Normal(n) => {
                dir = child(&dir, Path::new(n), libc::O_RDONLY | libc::O_DIRECTORY)?
            }
            _ => return Err(SelectionError::Invalid("invalid source directory".into())),
        }
    }
    Ok(dir)
}
impl Directory {
    pub fn open(root: &Path, identity: &serde_json::Value, relative: &Path) -> Result<Self> {
        Ok(Self {
            file: chain(root, relative, identity)?,
            root: root.into(),
            relative: relative.into(),
            identity: identity.clone(),
            unsupported_sync: Cell::new(false),
        })
    }
    fn validate(&self) -> Result<()> {
        let now = chain(&self.root, &self.relative, &self.identity)?;
        let a = now.metadata()?;
        let b = self.file.metadata()?;
        if (a.dev(), a.ino()) != (b.dev(), b.ino()) {
            return Err(SelectionError::Invalid(
                "source directory moved or redirected".into(),
            ));
        }
        Ok(())
    }
    fn open_file(&self, name: &Path, flags: i32) -> Result<Option<File>> {
        sibling(name)?;
        match child(&self.file, name, flags) {
            Err(SelectionError::Io(e)) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
            other => {
                let file = other?;
                if !file.metadata()?.is_file() {
                    return Err(SelectionError::Invalid(
                        "non-regular source/output file refused".into(),
                    ));
                }
                Ok(Some(file))
            }
        }
    }
    pub fn read(&self, name: &Path) -> Result<Option<Vec<u8>>> {
        let Some(mut f) = self.open_file(name, libc::O_RDONLY)? else {
            return Ok(None);
        };
        let mut bytes = vec![];
        f.read_to_end(&mut bytes)?;
        Ok(Some(bytes))
    }
    pub fn stamp(&self, name: &Path) -> Result<Option<serde_json::Value>> {
        let Some(f) = self.open_file(name, libc::O_RDONLY)? else {
            return Ok(None);
        };
        let m = f.metadata()?;
        Ok(Some(
            serde_json::json!({"device":m.dev(),"inode":m.ino(),"length":m.len(),"modified":m.mtime(),"modified_ns":m.mtime_nsec(),"changed":m.ctime(),"changed_ns":m.ctime_nsec()}),
        ))
    }
    pub fn hash(&self, name: &Path) -> Result<Option<String>> {
        use sha2::{Digest, Sha256};
        let Some(mut f) = self.open_file(name, libc::O_RDONLY)? else {
            return Ok(None);
        };
        let mut hash = Sha256::new();
        let mut buf = [0u8; 128 * 1024];
        loop {
            let n = f.read(&mut buf)?;
            if n == 0 {
                break;
            }
            hash.update(&buf[..n]);
        }
        Ok(Some(format!("{:x}", hash.finalize())))
    }
    pub fn lock(&self) -> Result<File> {
        let file = self
            .open_file(
                Path::new(".current-documents.lock"),
                libc::O_RDWR | libc::O_CREAT,
            )?
            .unwrap();
        file.try_lock().map_err(|e| {
            SelectionError::Invalid(format!("directory publication is locked: {e}"))
        })?;
        Ok(file)
    }
    pub fn stage(&self, target: &Path, bytes: &[u8], before: Option<&[u8]>) -> Result<Plan> {
        self.validate()?;
        sibling(target)?;
        let nonce = format!(
            "{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos()
        );
        let temporary = PathBuf::from(format!(".rpg-write-{nonce}"));
        let backup = PathBuf::from(format!(".rpg-previous-{nonce}"));
        let mut file = self
            .open_file(&temporary, libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL)?
            .unwrap();
        file.write_all(bytes)?;
        file.sync_all()?;
        Ok(Plan {
            target: target.into(),
            temporary,
            backup,
            before: before.map(crate::digest),
            after: crate::digest(bytes),
        })
    }
    fn rename(&self, from: &Path, to: &Path) -> Result<()> {
        sibling(from)?;
        sibling(to)?;
        let a = cstring(from)?;
        let b = cstring(to)?;
        if unsafe {
            libc::renameat2(
                self.file.as_raw_fd(),
                a.as_ptr(),
                self.file.as_raw_fd(),
                b.as_ptr(),
                libc::RENAME_NOREPLACE,
            )
        } != 0
        {
            return Err(std::io::Error::last_os_error().into());
        }
        Ok(())
    }
    fn flush(&self) -> Result<()> {
        match self.file.sync_all() {
            Err(e)
                if matches!(
                    e.raw_os_error(),
                    Some(libc::EINVAL) | Some(libc::EOPNOTSUPP) | Some(libc::ENOSYS)
                ) =>
            {
                self.unsupported_sync.set(true);
                Ok(())
            }
            other => Ok(other?),
        }
    }
    pub fn sync_is_unsupported(&self) -> bool {
        self.unsupported_sync.get()
    }
    pub fn install(&self, p: &Plan) -> Result<()> {
        self.validate()?;
        if self.hash(&p.target)? != p.before {
            return Err(SelectionError::Invalid(
                "destination changed after staging; preserved".into(),
            ));
        }
        if p.before.is_some() {
            self.rename(&p.target, &p.backup)?;
            if self.hash(&p.backup)? != p.before {
                let _ = self.rename(&p.backup, &p.target);
                return Err(SelectionError::Invalid(format!(
                    "concurrent edit preserved at {}",
                    self.root.join(&self.relative).join(&p.backup).display()
                )));
            }
        }
        if let Err(e) = self.rename(&p.temporary, &p.target) {
            if p.before.is_some() {
                let _ = self.rename(&p.backup, &p.target);
            }
            return Err(e);
        }
        self.flush()
    }
    fn remove_known(&self, name: &Path, sha: &str) -> Result<()> {
        match self.hash(name)? {
            None => Ok(()),
            Some(actual) if actual == sha => {
                let c = cstring(name)?;
                if unsafe { libc::unlinkat(self.file.as_raw_fd(), c.as_ptr(), 0) } != 0 {
                    return Err(std::io::Error::last_os_error().into());
                }
                Ok(())
            }
            _ => Err(SelectionError::Invalid(format!(
                "recovery file changed; preserved {}",
                self.root.join(&self.relative).join(name).display()
            ))),
        }
    }
    pub fn cleanup(&self, p: &Plan) -> Result<()> {
        self.validate()?;
        self.remove_known(&p.temporary, &p.after)?;
        if let Some(before) = &p.before {
            self.remove_known(&p.backup, before)?;
        }
        self.flush()
    }
    pub fn recover(&self, p: &Plan) -> Result<()> {
        self.validate()?;
        if self.hash(&p.target)?.is_none()
            && p.before.is_some()
            && self.hash(&p.backup)? == p.before
        {
            self.rename(&p.backup, &p.target)?;
        }
        self.cleanup(p)
    }
    pub fn entries(&self) -> Result<fs::ReadDir> {
        Ok(fs::read_dir(format!(
            "/proc/self/fd/{}",
            self.file.as_raw_fd()
        ))?)
    }
}
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
    let identity = match crate::inventory::root_identity(root) {
        Ok(i) => i,
        Err(e) => return (vec![], vec![e.to_string()]),
    };
    while let Some(relative) = pending.pop() {
        let path = root.join(&relative);
        let pinned = Directory::open(root, &identity, &relative);
        let entries = pinned
            .as_ref()
            .map_err(|e| SelectionError::Invalid(e.to_string()))
            .and_then(|d| d.entries());
        match entries {
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

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rename_aside_crash_restores_the_known_previous_file() {
        let root = tempfile::tempdir().unwrap();
        fs::write(root.path().join("notes.md"), b"old owned bytes").unwrap();
        let id = crate::inventory::root_identity(root.path()).unwrap();
        let dir = Directory::open(root.path(), &id, Path::new("")).unwrap();
        let staged = dir
            .stage(
                Path::new("notes.md"),
                b"new owned bytes",
                Some(b"old owned bytes"),
            )
            .unwrap();
        dir.rename(&staged.target, &staged.backup).unwrap();
        assert!(!root.path().join("notes.md").exists());
        dir.recover(&staged).unwrap();
        assert_eq!(
            fs::read(root.path().join("notes.md")).unwrap(),
            b"old owned bytes"
        );
        assert!(!root.path().join(staged.temporary).exists());
    }
    #[test]
    fn staged_install_preserves_a_file_created_or_edited_before_commit() {
        let root = tempfile::tempdir().unwrap();
        let id = crate::inventory::root_identity(root.path()).unwrap();
        let dir = Directory::open(root.path(), &id, Path::new("")).unwrap();
        let staged = dir
            .stage(Path::new("notes.md"), b"generated", None)
            .unwrap();
        std::fs::write(root.path().join("notes.md"), b"user notes").unwrap();
        assert!(dir.install(&staged).is_err());
        assert_eq!(
            std::fs::read(root.path().join("notes.md")).unwrap(),
            b"user notes"
        );
        let staged = dir
            .stage(Path::new("notes.md"), b"generated", Some(b"user notes"))
            .unwrap();
        std::fs::write(root.path().join("notes.md"), b"new user edits").unwrap();
        assert!(dir.install(&staged).is_err());
        assert_eq!(
            std::fs::read(root.path().join("notes.md")).unwrap(),
            b"new user edits"
        );
    }
    #[test]
    fn staged_directory_redirect_cannot_write_outside_the_frozen_root() {
        let root = tempfile::tempdir().unwrap();
        let outside = tempfile::tempdir().unwrap();
        std::fs::create_dir(root.path().join("Book")).unwrap();
        let id = crate::inventory::root_identity(root.path()).unwrap();
        let dir = Directory::open(root.path(), &id, Path::new("Book")).unwrap();
        let staged = dir
            .stage(Path::new("notes.md"), b"generated", None)
            .unwrap();
        std::fs::rename(root.path().join("Book"), root.path().join("Moved")).unwrap();
        std::os::unix::fs::symlink(outside.path(), root.path().join("Book")).unwrap();
        assert!(dir.install(&staged).is_err());
        assert!(!outside.path().join("notes.md").exists());
    }
}
