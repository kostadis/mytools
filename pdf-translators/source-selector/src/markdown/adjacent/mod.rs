//! Coordinator-only publication into the source tree. Directory manifests are
//! commit records; private receipts/intents establish ownership after a crash.
mod files;
mod state;
use super::worker::Engine;
use super::*;
use crate::{digest, digest_json, inventory::root_identity};
use state::{Ownership, Receipt};
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
}
pub struct Session {
    root: PathBuf,
    identity: Value,
    path: PathBuf,
    ownership: Ownership,
    directories: BTreeSet<PathBuf>,
    discovery_errors: Vec<String>,
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
impl Session {
    pub fn new(output: &Path, s: &Snapshot) -> Result<Self> {
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
        Ok(Self {
            root: s.source_root.clone(),
            identity: s.root_identity.clone(),
            path,
            ownership,
            directories,
            discovery_errors,
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
        let dir = match files::directory(&self.root, relative) {
            Err(SelectionError::Io(e)) if e.kind() == std::io::ErrorKind::NotFound => {
                return Ok(vec![]);
            }
            other => other?,
        };
        let path = dir.join(NAME);
        let original = files::read(&path)?;
        if members.is_empty() && original.is_none() {
            return Ok(vec![]);
        }
        if let Some(bytes) = &original {
            check_manifest(&serde_json::from_slice::<Value>(bytes)?)?;
        }
        files::read(&dir.join(".current-documents.lock"))?;
        let _guard = lock(&dir, ".current-documents.lock")?;
        if files::read(&path)? != original {
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
                && let Ok(Some(bytes)) = files::read(&self.root.join(&target))
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
                if !members
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
                let dest = dir.join(target.file_name().unwrap());
                let existing = files::read(&dest)?;
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
                if live_source_matches(&self.root, r)? != Some(true) {
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
                    if files::read(&dest)? != existing {
                        return Err(SelectionError::Invalid(
                            "Markdown changed concurrently; preserved".into(),
                        ));
                    }
                    atomic_write(&dest, bytes)?;
                }
                if live_source_matches(&self.root, r)? != Some(true) {
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
            if files::read(&path)? != original {
                return Err(SelectionError::Invalid(
                    "directory record changed concurrently; preserved".into(),
                ));
            }
            record["updated_at"] = Value::String(chrono::Utc::now().to_rfc3339());
            write_json(&path, &record)?;
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
        self.ownership.save(&self.path)?;
        Ok(results)
    }
}
