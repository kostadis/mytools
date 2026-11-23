use super::*;
use std::collections::VecDeque;
/// Resumable in bounded in-process steps; restarting is safe and read-only.
pub struct Discovery {
    root: PathBuf,
    identity: Value,
    pending: VecDeque<PathBuf>,
    active: Option<(PathBuf, files::Directory, fs::ReadDir)>,
    pub found: BTreeSet<PathBuf>,
    pub errors: Vec<String>,
}
impl Discovery {
    pub fn new(root: &Path, identity: &Value) -> Self {
        Self {
            root: root.into(),
            identity: identity.clone(),
            pending: VecDeque::from([PathBuf::new()]),
            active: None,
            found: BTreeSet::new(),
            errors: vec![],
        }
    }
    pub fn step(&mut self) -> bool {
        for _ in 0..64 {
            if self.active.is_none() {
                let Some(relative) = self.pending.pop_front() else {
                    return true;
                };
                match files::Directory::open(&self.root, &self.identity, &relative)
                    .and_then(|d| Ok((d.entries()?, d)))
                {
                    Ok((entries, dir)) => self.active = Some((relative, dir, entries)),
                    Err(e) => {
                        self.errors.push(e.to_string());
                        continue;
                    }
                }
            }
            let (relative, _, entries) = self.active.as_mut().unwrap();
            match entries.next() {
                None => self.active = None,
                Some(Err(e)) => self.errors.push(e.to_string()),
                Some(Ok(entry)) => match entry.file_type() {
                    Ok(t) if t.is_dir() => self.pending.push_back(relative.join(entry.file_name())),
                    Ok(t) if t.is_file() && entry.file_name() == NAME => {
                        self.found.insert(relative.clone());
                    }
                    Err(e) => self.errors.push(e.to_string()),
                    _ => {}
                },
            }
        }
        false
    }
}
