//! Coordinator-only publication into the source tree. Directory manifests are
//! commit records; private receipts/intents establish ownership after a crash.
mod files;
mod state;
use super::worker::Engine;
use super::*;
use crate::{digest, digest_json, inventory::root_identity};
use state::{Operation, Ownership, Receipt};
use std::collections::{BTreeMap, BTreeSet};
const NAME: &str = "current-documents.json";
const OWNER: &str = "rpg-source-select";
#[derive(Clone)]
pub struct Book {
    pub ready: Ready,
    pub markdown: String,
    pub metadata: Value,
}
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct AdjacentReport {
    pub published: Vec<String>,
    pub errors: Vec<String>,
    pub directories: usize,
    pub complete: bool,
    pub states: BTreeMap<String, Value>,
    pub warnings: Vec<String>,
}
pub struct Session {
    root: PathBuf,
    identity: Value,
    path: PathBuf,
    ownership: Ownership,
    directories: BTreeSet<PathBuf>,
    discovery_errors: Vec<String>,
    warnings: BTreeSet<String>,
}
fn owned(v: &Value) -> bool {
    v["generator"] == OWNER
}
fn check_manifest(v: &Value) -> Result<()> {
    if !owned(v) || v["schema_version"] != 1 || !v["documents"].is_array() {
        return Err(SelectionError::Invalid(
            "foreign, invalid or unsupported directory record".into(),
        ));
    }
    if v["selection_id"].as_str().is_none_or(str::is_empty) {
        return Err(SelectionError::Invalid(
            "directory record has no selection identity".into(),
        ));
    }
    let mut ids = BTreeSet::new();
    for d in v["documents"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|v| owned(v))
    {
        let valid_hash = |v: &Value| {
            v.as_str()
                .is_some_and(|s| s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit()))
        };
        if ["source_id", "selection_id", "selection_basis"]
            .iter()
            .any(|key| d[*key].as_str().is_none_or(str::is_empty))
            || !valid_hash(&d["pdf_sha256"])
            || !d["status"].as_str().is_some_and(|s| {
                [
                    "pending",
                    "published",
                    "needs_ocr_or_visual_review",
                    "failed",
                    "running",
                    "source_changed",
                    "source_unavailable",
                    "output_conflict",
                ]
                .contains(&s)
            })
            || (d["status"] == "published" && !valid_hash(&d["markdown_sha256"]))
        {
            return Err(SelectionError::Invalid(
                "incomplete or invalid owned manifest entry".into(),
            ));
        }
        let id = d["work_id"]
            .as_str()
            .ok_or_else(|| SelectionError::Invalid("manifest entry has no work ID".into()))?;
        safe_id(id)?;
        if !ids.insert(id) {
            return Err(SelectionError::Invalid("duplicate manifest work ID".into()));
        }
        let pdf = files::filename(&d["pdf"])?;
        let md = files::filename(&d["markdown"])?;
        if md.extension() != Some(std::ffi::OsStr::new("md")) || pdf == md {
            return Err(SelectionError::Invalid(
                "invalid manifest Markdown destination".into(),
            ));
        }
    }
    Ok(())
}
/// A generated sibling is not a preexisting Dungeon Masters Guild baseline.
/// The exact checksum/source identity is required; other artifacts stay protected.
pub fn managed_markdown(output: &Path, root: &Path, source: &crate::models::Source) -> bool {
    (|| -> Result<bool> {
        let identity = root_identity(root)?;
        let dir = files::Directory::open(
            root,
            &identity,
            source.relative_path.parent().unwrap_or(Path::new("")),
        )?;
        let target = source.relative_path.with_extension("md");
        if let Some(sha) = dir.hash(Path::new(target.file_name().unwrap()))? {
            let key = digest_json(&(&identity, crate::inventory::path_bytes(root)));
            if let Ok(state) =
                read_json::<Ownership>(&output.join("adjacent").join(format!("{key}.json")))
                && state.schema_version == 1
                && state.root == root
                && state.root_identity == identity
                && state.owns(&target, &sha)
            {
                return Ok(true);
            }
        }
        let Some(bytes) = dir.read(Path::new(NAME))? else {
            return Ok(false);
        };
        let manifest: Value = serde_json::from_slice(&bytes)?;
        check_manifest(&manifest)?;
        for entry in manifest["documents"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|e| {
                owned(e) && e["status"] == "published" && e["source_id"] == source.source_id
            })
        {
            if files::filename(&entry["pdf"])?
                == Path::new(source.relative_path.file_name().unwrap())
                && dir.hash(&files::filename(&entry["markdown"])?)?.as_deref()
                    == entry["markdown_sha256"].as_str()
            {
                return Ok(true);
            }
        }
        Ok(false)
    })()
    .unwrap_or(false)
}
impl Session {
    pub fn new(output: &Path, s: &Snapshot) -> Result<Self> {
        files::Directory::open(&s.source_root, &s.root_identity, Path::new(""))?;
        if root_identity(&s.source_root)? != s.root_identity {
            return Err(SelectionError::Invalid(
                "source root changed before adjacent publication".into(),
            ));
        }
        let key = digest_json(&(
            &s.root_identity,
            crate::inventory::path_bytes(&s.source_root),
        ));
        let path = output.join("adjacent").join(format!("{key}.json"));
        let ownership = Ownership::open(&path, s)?;
        let (dirs, discovery_errors) = files::discover(&s.source_root);
        let mut directories: BTreeSet<_> = dirs.into_iter().collect();
        for r in ownership.receipts.iter().chain(&ownership.intents) {
            if let Some(parent) = r.target.parent() {
                directories.insert(parent.to_path_buf());
            }
        }
        for operation in &ownership.operations {
            directories.insert(operation.directory.clone());
        }
        Ok(Self {
            root: s.source_root.clone(),
            identity: s.root_identity.clone(),
            path,
            ownership,
            directories,
            discovery_errors,
            warnings: BTreeSet::new(),
        })
    }
    pub fn sync(
        &mut self,
        s: &Snapshot,
        engine: &Engine,
        books: &[Book],
        states: &BTreeMap<String, Value>,
    ) -> AdjacentReport {
        let mut report = AdjacentReport {
            complete: s.coverage_errors.is_empty() && self.discovery_errors.is_empty(),
            errors: self.discovery_errors.clone(),
            ..AdjacentReport::default()
        };
        if self.root != s.source_root
            || self.identity != s.root_identity
            || root_identity(&self.root).ok().as_ref() != Some(&self.identity)
        {
            report.complete = false;
            report
                .errors
                .push("source root changed; adjacent publication refused".into());
            return report;
        }
        for ready in &s.ready {
            self.directories.insert(
                ready
                    .relative_path
                    .parent()
                    .unwrap_or(Path::new(""))
                    .to_path_buf(),
            );
        }
        let mut targets: BTreeMap<PathBuf, usize> = BTreeMap::new();
        for ready in &s.ready {
            *targets
                .entry(ready.relative_path.with_extension("md"))
                .or_default() += 1;
        }
        let coverage_complete = report.complete;
        let progress = super::progress::Progress::new("adjacent reconciliation");
        for relative in self.directories.clone() {
            let members: Vec<_> = s
                .ready
                .iter()
                .filter(|r| r.relative_path.parent().unwrap_or(Path::new("")) == relative)
                .collect();
            match self.sync_directory(
                &relative,
                s,
                engine,
                books,
                states,
                &members,
                &targets,
                coverage_complete,
            ) {
                Ok(entries) => {
                    report.directories += 1;
                    for entry in entries {
                        if let Some(id) = entry["work_id"].as_str() {
                            if entry["status"] == "published" {
                                report.published.push(id.to_string());
                            } else {
                                report.complete = false;
                                if let Some(e) = entry["error"].as_str() {
                                    report.errors.push(format!("{id}: {e}"));
                                }
                            }
                            report.states.insert(id.into(), entry);
                        }
                    }
                }
                Err(e) => {
                    report.complete = false;
                    report
                        .errors
                        .push(format!("{}: {e}", self.root.join(&relative).display()));
                    for r in members {
                        report.states.insert(r.work_id.clone(),serde_json::json!({"work_id":r.work_id,"status":"output_conflict","error":e.to_string()}));
                    }
                }
            }
            progress.tick();
        }
        // Full reconciliation coverage is independent of outstanding jobs, but
        // the overall report remains pending until every selected book publishes.
        report.published.sort();
        report.published.dedup();
        report.warnings = self.warnings.iter().cloned().collect();
        report
    }
    #[allow(clippy::too_many_arguments)]
    fn sync_directory(
        &mut self,
        relative: &Path,
        s: &Snapshot,
        engine: &Engine,
        books: &[Book],
        states: &BTreeMap<String, Value>,
        members: &[&Ready],
        targets: &BTreeMap<PathBuf, usize>,
        coverage_complete: bool,
    ) -> Result<Vec<Value>> {
        let dir = match files::Directory::open(&self.root, &self.identity, relative) {
            Err(SelectionError::Io(e)) if e.kind() == std::io::ErrorKind::NotFound => {
                return Ok(vec![]);
            }
            other => other?,
        };
        let _guard = dir.lock()?;
        let pending: Vec<_> = self
            .ownership
            .operations
            .iter()
            .filter(|o| o.directory == relative)
            .cloned()
            .collect();
        for operation in pending {
            dir.recover(&operation.plan)?;
            self.ownership.operations.retain(|o| o != &operation);
        }
        self.ownership.save(&self.path)?;
        let original = dir.read(Path::new(NAME))?;
        if members.is_empty() && original.is_none() {
            return Ok(vec![]);
        }
        if let Some(bytes) = &original {
            check_manifest(&serde_json::from_slice::<Value>(bytes)?)?;
        }
        if dir.read(Path::new(NAME))? != original {
            return Err(SelectionError::Invalid(
                "directory record changed concurrently; retry".into(),
            ));
        }
        let old: Value = original
            .as_ref()
            .map(|b| serde_json::from_slice(b))
            .transpose()?
            .unwrap_or_else(
                || serde_json::json!({"schema_version":1,"generator":OWNER,"documents":[]}),
            );
        // Rebuild ownership only from exact matching bytes, never from a name.
        for entry in old["documents"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|v| owned(v) && v["status"] == "published")
        {
            let target = relative.join(files::filename(&entry["markdown"])?);
            if let Some(sha) = entry["markdown_sha256"].as_str()
                && let Ok(Some(bytes)) = dir.read(target.file_name().unwrap().as_ref())
                && digest(&bytes) == sha
            {
                self.ownership.remember(Receipt {
                    target,
                    sha256: sha.into(),
                    work_id: entry["work_id"].as_str().unwrap().into(),
                    source_sha256: entry["pdf_sha256"].as_str().unwrap_or("").into(),
                });
            }
        }
        self.ownership.save(&self.path)?;
        let mut documents: Vec<Value> = old["documents"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|v| !owned(v))
            .cloned()
            .collect();
        let mut unresolved = vec![];
        if !coverage_complete {
            for entry in old["documents"]
                .as_array()
                .unwrap()
                .iter()
                .filter(|v| owned(v))
            {
                if !s
                    .ready
                    .iter()
                    .any(|r| Some(r.work_id.as_str()) == entry["work_id"].as_str())
                {
                    documents.push(entry.clone());
                    unresolved.push(entry["work_id"].clone());
                }
            }
        }
        let mut results = vec![];
        for r in members {
            let target = r.relative_path.with_extension("md");
            let mut entry = serde_json::json!({"generator":OWNER,"work_id":r.work_id,"source_id":r.source_id,"selection_id":s.snapshot_id,"pdf":files::path_value(Path::new(r.relative_path.file_name().unwrap())),"pdf_sha256":r.sha256,"markdown":files::path_value(Path::new(target.file_name().unwrap())),"selection_basis":r.selection_basis,"internal_date":r.date,"engine_id":engine.id,"status":states.get(&r.work_id).and_then(|v|v["status"].as_str()).unwrap_or("pending")});
            if let Some(error) = states.get(&r.work_id).and_then(|v| v.get("error")) {
                entry["error"] = error.clone();
            }
            let attempt = (|| -> Result<()> {
                if targets[&target] != 1 {
                    return Err(SelectionError::Invalid(
                        "multiple selected works target the same Markdown filename".into(),
                    ));
                }
                let dest = Path::new(target.file_name().unwrap());
                let existing = dir.read(dest)?;
                if let Some(bytes) = &existing
                    && !self.ownership.owns(&target, &digest(bytes))
                {
                    return Err(SelectionError::Invalid(
                        "existing Markdown is unowned or user-edited; preserved".into(),
                    ));
                }
                let Some(book) = books
                    .iter()
                    .find(|b| b.ready.work_id == r.work_id && b.ready.sha256 == r.sha256)
                else {
                    return Ok(());
                };
                if dir
                    .hash(Path::new(r.relative_path.file_name().unwrap()))?
                    .as_deref()
                    != Some(r.sha256.as_str())
                {
                    entry["status"] = Value::String("source_changed".into());
                    entry["error"] = Value::String("selected PDF changed or is unavailable".into());
                    return Ok(());
                }
                let markdown = super::render::sibling(&book.markdown, r, s);
                let bytes = markdown.as_bytes();
                let sha = digest(bytes);
                let receipt = Receipt {
                    target: target.clone(),
                    sha256: sha.clone(),
                    work_id: r.work_id.clone(),
                    source_sha256: r.sha256.clone(),
                };
                if existing.as_deref() != Some(bytes) {
                    if !self.ownership.intents.contains(&receipt) {
                        self.ownership.intents.push(receipt.clone());
                    }
                    self.ownership.save(&self.path)?;
                    if dir.read(dest)? != existing {
                        return Err(SelectionError::Invalid(
                            "Markdown changed concurrently; preserved".into(),
                        ));
                    }
                    let plan = dir.stage(dest, bytes, existing.as_deref())?;
                    let operation = Operation {
                        directory: relative.into(),
                        plan,
                    };
                    self.ownership.operations.push(operation.clone());
                    self.ownership.save(&self.path)?;
                    dir.install(&operation.plan)?;
                }
                if dir
                    .hash(Path::new(r.relative_path.file_name().unwrap()))?
                    .as_deref()
                    != Some(r.sha256.as_str())
                {
                    entry["status"] = Value::String("source_changed".into());
                    entry["error"] =
                        Value::String("selected PDF changed before record commit".into());
                    return Ok(());
                }
                entry["status"] = Value::String("published".into());
                entry["markdown_sha256"] = Value::String(sha);
                entry["quality"] = serde_json::json!({"empty_pages":book.metadata["empty_pages"],"sparse_pages":book.metadata["sparse_pages"],"warnings":book.metadata["warnings"]});
                Ok(())
            })();
            if let Err(e) = attempt {
                entry["status"] = Value::String("output_conflict".into());
                entry["error"] = Value::String(e.to_string());
            }
            documents.push(entry.clone());
            results.push(entry);
        }
        verify_pairs(&dir, &mut results);
        for result in &results {
            if let Some(entry) = documents
                .iter_mut()
                .find(|e| owned(e) && e["work_id"] == result["work_id"])
            {
                *entry = result.clone();
            }
        }
        documents.sort_by_key(|v| v["work_id"].as_str().unwrap_or("").to_string());
        let mut record = old.clone();
        record["schema_version"] = Value::from(1);
        record["generator"] = Value::String(OWNER.into());
        record["selection_id"] = Value::String(s.snapshot_id.clone());
        record["documents"] = Value::Array(documents);
        record["reconciliation_status"] = Value::String(
            if coverage_complete {
                "complete"
            } else {
                "partial"
            }
            .into(),
        );
        record["unverified_work_ids"] = Value::Array(unresolved);
        let mut comparable = record.clone();
        let mut prior = old.clone();
        comparable.as_object_mut().unwrap().remove("updated_at");
        prior.as_object_mut().unwrap().remove("updated_at");
        if comparable != prior {
            if dir.read(Path::new(NAME))? != original {
                return Err(SelectionError::Invalid(
                    "directory record changed concurrently; preserved".into(),
                ));
            }
            record["updated_at"] = Value::String(chrono::Utc::now().to_rfc3339());
            let mut committed = false;
            for _ in 0..3 {
                let plan = dir.stage(
                    Path::new(NAME),
                    &serde_json::to_vec_pretty(&record)?,
                    original.as_deref(),
                )?;
                let operation = Operation {
                    directory: relative.into(),
                    plan,
                };
                self.ownership.operations.push(operation.clone());
                self.ownership.save(&self.path)?;
                if verify_pairs(&dir, &mut results) {
                    dir.cleanup(&operation.plan)?;
                    self.ownership.operations.retain(|o| o != &operation);
                    self.ownership.save(&self.path)?;
                    for result in &results {
                        if let Some(entry) = record["documents"]
                            .as_array_mut()
                            .unwrap()
                            .iter_mut()
                            .find(|e| owned(e) && e["work_id"] == result["work_id"])
                        {
                            *entry = result.clone();
                        }
                    }
                    continue;
                }
                dir.install(&operation.plan)?;
                committed = true;
                break;
            }
            if !committed {
                return Err(SelectionError::Invalid(
                    "published files changed repeatedly before directory commit; retry".into(),
                ));
            }
        }
        // Only after the manifest commits is an intent promoted to a receipt.
        for e in &results {
            if e["status"] == "published" {
                let target = relative.join(files::filename(&e["markdown"])?);
                let receipt = Receipt {
                    target,
                    sha256: e["markdown_sha256"].as_str().unwrap().into(),
                    work_id: e["work_id"].as_str().unwrap().into(),
                    source_sha256: e["pdf_sha256"].as_str().unwrap().into(),
                };
                self.ownership.remember(receipt.clone());
                self.ownership.intents.retain(|r| r != &receipt);
            }
        }
        let committed: Vec<_> = self
            .ownership
            .operations
            .iter()
            .filter(|o| o.directory == relative)
            .cloned()
            .collect();
        for operation in committed {
            dir.cleanup(&operation.plan)?;
            self.ownership.operations.retain(|o| o != &operation);
        }
        if dir.sync_is_unsupported() {
            self.warnings.insert(format!("{}: directory fsync unsupported; file flushes and durable private recovery journal used",self.root.join(relative).display()));
        }
        self.ownership.save(&self.path)?;
        Ok(results)
    }
}

fn verify_pairs(dir: &files::Directory, entries: &mut [Value]) -> bool {
    let mut changed = false;
    for entry in entries.iter_mut().filter(|e| e["status"] == "published") {
        let check = (|| -> Result<Option<&str>> {
            let pdf = files::filename(&entry["pdf"])?;
            let md = files::filename(&entry["markdown"])?;
            if dir.hash(&pdf)?.as_deref() != entry["pdf_sha256"].as_str() {
                return Ok(Some("source_changed"));
            }
            if dir.hash(&md)?.as_deref() != entry["markdown_sha256"].as_str() {
                return Ok(Some("output_conflict"));
            }
            Ok(None)
        })();
        if let Some(status) = match check {
            Ok(s) => s,
            Err(_) => Some("output_conflict"),
        } {
            changed = true;
            entry["status"] = Value::String(status.into());
            entry["error"] = Value::String(
                "source or Markdown changed before directory commit; preserved".into(),
            );
            entry.as_object_mut().unwrap().remove("markdown_sha256");
        }
    }
    changed
}

#[cfg(test)]
mod commit_tests {
    use super::*;
    #[test]
    fn final_pair_check_rejects_earlier_source_or_markdown_changes_after_staging() {
        for source in [true, false] {
            let root = tempfile::tempdir().unwrap();
            fs::write(root.path().join("A.pdf"), b"pdf").unwrap();
            fs::write(root.path().join("A.md"), b"markdown").unwrap();
            let id = root_identity(root.path()).unwrap();
            let dir = files::Directory::open(root.path(), &id, Path::new("")).unwrap();
            let mut entries = vec![
                serde_json::json!({"status":"published","pdf":"A.pdf","pdf_sha256":digest(b"pdf"),"markdown":"A.md","markdown_sha256":digest(b"markdown")}),
            ];
            let staged = dir.stage(Path::new(NAME), b"new manifest", None).unwrap();
            fs::write(
                root.path().join(if source { "A.pdf" } else { "A.md" }),
                b"changed",
            )
            .unwrap();
            assert!(verify_pairs(&dir, &mut entries));
            assert_ne!(entries[0]["status"], "published");
            dir.cleanup(&staged).unwrap();
        }
    }
}
