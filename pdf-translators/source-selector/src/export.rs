use crate::{
    Result, SelectionError,
    grouping::hash_source,
    inventory::{checked_path, fingerprint},
    models::*,
    review::{accept_decision, propose_decision},
    store::Store,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::Write,
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct QueueItem {
    pub work_id: String,
    pub source_id: String,
    #[serde(with = "crate::models::path_serde")]
    pub relative_path: PathBuf,
    pub fingerprint: Fingerprint,
    pub title: String,
    pub publisher: String,
    pub book_ids: Vec<u64>,
    pub related_source_ids: Vec<String>,
    pub metadata: BTreeMap<String, Value>,
    pub artifact_references: Vec<String>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SelectionSnapshot {
    pub schema_version: u32,
    #[serde(with = "crate::models::path_serde")]
    pub root: PathBuf,
    pub scan_started: String,
    pub scan_finished: String,
    pub sources: Vec<Source>,
    pub groups: Vec<Group>,
    pub evidence_references: Vec<Value>,
    pub decisions: Vec<Decision>,
    pub decision_history: Vec<Decision>,
    pub hints: Vec<Hint>,
    pub works: Vec<QueueItem>,
    pub queue: Vec<QueueItem>,
    pub baseline_findings: Vec<Value>,
    pub errors: Vec<String>,
    pub counts: BTreeMap<String, usize>,
}

pub fn build_snapshot(store: &Store) -> Result<SelectionSnapshot> {
    let inventory: InventoryResult = serde_json::from_value(
        store
            .meta("inventory")?
            .ok_or_else(|| SelectionError::Invalid("scan first".into()))?,
    )?;
    if !inventory.root.is_dir() {
        return Err(SelectionError::Invalid(
            "library root unavailable; previous export retained".into(),
        ));
    }
    let sources = store.sources()?;
    let groups: Vec<Group> = store.records("groups")?;
    let evidence = store.evidence()?;
    let previous = store.current_decisions()?;
    let hints: Vec<Hint> = store.records("hints")?;
    let mut errors = inventory.errors.clone();
    for kind in ["grouping_errors", "inspection_errors"] {
        errors.extend(
            store
                .keyed_records::<String>(kind)?
                .into_iter()
                .filter(|(id, _)| sources.iter().any(|s| &s.source_id == id))
                .map(|(_, error)| error),
        );
    }
    let mut decisions = vec![];
    let mut counts = BTreeMap::new();
    let mut baseline = vec![];
    for group in &groups {
        let prior = previous.iter().find(|d| d.group_id == group.group_id);
        let mut decision = propose_decision(group, &evidence, &sources, prior);
        let mut stale = false;
        for id in &group.source_ids {
            let Some(source) = sources.iter().find(|s| &s.source_id == id) else {
                stale = true;
                continue;
            };
            if source.read_error.is_some() {
                continue;
            }
            let checked = checked_path(&inventory.root, &source.relative_path).and_then(|p| {
                if fingerprint(&p)? != source.fingerprint {
                    return Err(SelectionError::Invalid(
                        "source fingerprint changed; rescan".into(),
                    ));
                }
                if let Some(ev) = evidence.iter().find(|e| e.source_id == source.source_id)
                    && hash_source(&p)? != ev.sha256
                {
                    return Err(SelectionError::Invalid(
                        "source bytes changed; reinspect".into(),
                    ));
                }
                Ok(())
            });
            if let Err(e) = checked {
                stale = true;
                errors.push(format!("{}: {e}", source.relative_path.display()));
            }
        }
        if stale {
            increment(&mut counts, "stale_groups");
            for o in &mut decision.outcomes {
                o.status = Status::NeedsReview;
                o.work_id = None;
                o.representative_id = None;
                o.successor_id = None;
            }
            decision.actor_role = ActorRole::Deterministic;
            decision.rationale = "Source changed after inspection; rescan and inspect".into();
            if group.source_ids.iter().any(|id| {
                sources.iter().any(|s| {
                    &s.source_id == id
                        && (s.baseline_established || s.publisher == "Dungeon Masters Guild")
                })
            }) {
                baseline.push(
                    json!({"group_id":group.group_id,"reason":"baseline-related source changed"}),
                );
            }
        } else {
            decision = accept_decision(decision, group, &evidence, &sources)?;
        }
        decisions.push(decision);
    }
    let mut works = vec![];
    let mut queue = vec![];
    for decision in &decisions {
        for outcome in &decision.outcomes {
            increment(
                &mut counts,
                match outcome.status {
                    Status::Selected => "selected",
                    Status::DistinctWork => "distinct_work",
                    Status::ExactDuplicate => "exact_duplicates",
                    Status::EquivalentPresentation => "equivalent_presentations",
                    Status::Superseded => "superseded",
                    Status::NeedsReview => "needs_review",
                    Status::ExcludedAsset => "excluded_assets",
                    Status::Unreadable => "unreadable",
                },
            );
            if !matches!(outcome.status, Status::Selected | Status::DistinctWork) {
                continue;
            }
            let source = sources
                .iter()
                .find(|s| s.source_id == outcome.source_id)
                .expect("validated selected source");
            let related: Vec<_> = decision
                .outcomes
                .iter()
                .filter(|o| o.work_id == outcome.work_id)
                .map(|o| o.source_id.clone())
                .collect();
            let mut metadata = source.metadata.clone();
            let mut book_ids = BTreeSet::new();
            for hint in hints.iter().filter(|h| {
                h.origin == "rpglib" && h.source_ids.iter().any(|id| related.contains(id))
            }) {
                if let Some(id) = hint.payload["id"].as_u64() {
                    book_ids.insert(id);
                }
                metadata.insert(
                    format!("rpglib:{}", hint.payload["id"]),
                    hint.payload.clone(),
                );
            }
            let title = hints
                .iter()
                .filter(|h| h.origin == "rpglib" && h.source_ids.contains(&source.source_id))
                .find_map(|h| {
                    h.payload["display_title"]
                        .as_str()
                        .or(h.payload["pdf_title"].as_str())
                })
                .map(str::to_string)
                .unwrap_or_else(|| {
                    source
                        .relative_path
                        .file_stem()
                        .unwrap_or_default()
                        .to_string_lossy()
                        .into_owned()
                });
            let item = QueueItem {
                work_id: outcome.work_id.clone().expect("accepted work ID"),
                source_id: source.source_id.clone(),
                relative_path: source.relative_path.clone(),
                fingerprint: {
                    let mut fp = source.fingerprint.clone();
                    fp.sha256 = evidence
                        .iter()
                        .find(|e| e.source_id == source.source_id)
                        .map(|e| e.sha256.clone());
                    fp
                },
                title,
                publisher: source.publisher.clone(),
                book_ids: book_ids.into_iter().collect(),
                related_source_ids: related,
                metadata,
                artifact_references: source.artifacts.clone(),
            };
            if source.baseline_established {
                increment(&mut counts, "baseline_reuse");
                baseline.push(json!({"source_id":source.source_id,"work_id":item.work_id,"reason":"established baseline; preserved, not queued"}));
            } else if source.publisher == "Dungeon Masters Guild" && !source.artifacts.is_empty() {
                increment(&mut counts, "baseline_pending");
                baseline.push(json!({"source_id":source.source_id,"work_id":item.work_id,"reason":"artifact-bearing baseline candidate; confirm source identity before new conversion"}));
            } else {
                queue.push(item.clone());
            }
            works.push(item);
        }
    }
    works.sort_by(|a, b| a.work_id.cmp(&b.work_id));
    queue.sort_by(|a, b| a.relative_path.cmp(&b.relative_path));
    for key in [
        "selected",
        "distinct_work",
        "exact_duplicates",
        "equivalent_presentations",
        "superseded",
        "needs_review",
        "excluded_assets",
        "unreadable",
        "baseline_reuse",
        "baseline_pending",
        "stale_groups",
    ] {
        counts.entry(key.into()).or_default();
    }
    counts.insert("sources_total".into(), sources.len());
    counts.insert(
        "pdfs".into(),
        sources.iter().filter(|s| s.kind == SourceKind::Pdf).count(),
    );
    counts.insert(
        "archives".into(),
        sources
            .iter()
            .filter(|s| s.kind == SourceKind::Archive)
            .count(),
    );
    counts.insert("queue".into(), queue.len());
    counts.insert("works".into(), works.len());
    counts.insert("coverage_errors".into(), errors.len());
    counts.insert(
        "partial_inspection".into(),
        evidence
            .iter()
            .filter(|e| e.pages.len() != e.page_count as usize)
            .count(),
    );
    let refs=evidence.iter().filter(|e|sources.iter().any(|s|s.source_id==e.source_id)).map(|e|json!({"source_id":e.source_id,"sha256":e.sha256,"version":e.version,"page_count":e.page_count,"inspected_pages":e.pages.iter().map(|p|p.page).collect::<Vec<_>>(),"text_quality":e.text_quality,"errors":e.errors})).collect();
    Ok(SelectionSnapshot {
        schema_version: 1,
        root: inventory.root,
        scan_started: inventory.started,
        scan_finished: inventory.finished,
        sources,
        groups,
        evidence_references: refs,
        decisions,
        decision_history: store.records("decision_history")?,
        hints,
        works,
        queue,
        baseline_findings: baseline,
        errors,
        counts,
    })
}
fn increment(counts: &mut BTreeMap<String, usize>, key: &str) {
    *counts.entry(key.into()).or_default() += 1;
}

/// Resolve an existing ancestor, so an alias or a not-yet-created directory cannot enter the library.
pub fn validate_work_dir(root: &Path, out: &Path) -> Result<PathBuf> {
    let root = root.canonicalize()?;
    let absolute = if out.is_absolute() {
        out.to_path_buf()
    } else {
        std::env::current_dir()?.join(out)
    };
    let mut existing = absolute.as_path();
    let mut tail = vec![];
    while !existing.exists() {
        let name = existing.file_name().ok_or_else(|| {
            SelectionError::Invalid("work directory has no existing ancestor".into())
        })?;
        tail.push(name.to_os_string());
        existing = existing
            .parent()
            .ok_or_else(|| SelectionError::Invalid("invalid work directory".into()))?;
    }
    let mut resolved = existing.canonicalize()?;
    for name in tail.iter().rev() {
        if name == ".." {
            resolved.pop();
        } else if name != "." {
            resolved.push(name);
        }
    }
    if resolved.starts_with(root) {
        return Err(SelectionError::Invalid(
            "work directory must be outside the scanned root".into(),
        ));
    }
    Ok(resolved)
}

pub fn write_exports(
    snapshot: &SelectionSnapshot,
    out_dir: &Path,
) -> Result<BTreeMap<String, PathBuf>> {
    let out_dir = validate_work_dir(&snapshot.root, out_dir)?;
    let mut ids = BTreeSet::new();
    for item in &snapshot.queue {
        if !ids.insert(&item.work_id) {
            return Err(SelectionError::Invalid("duplicate work in queue".into()));
        }
    }
    let generations = out_dir.join("generations");
    if generations
        .symlink_metadata()
        .is_ok_and(|m| m.file_type().is_symlink())
    {
        return Err(SelectionError::Invalid(
            "generation directory must not be a symlink".into(),
        ));
    }
    fs::create_dir_all(&generations)?;
    let id = format!(
        "{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    );
    let staging = out_dir.join("generations").join(format!(".staging-{id}"));
    fs::create_dir(&staging)?;
    let mut bodies = BTreeMap::new();
    bodies.insert("selection.json", serde_json::to_vec_pretty(snapshot)?);
    let mut tsv = csv::WriterBuilder::new()
        .delimiter(b'\t')
        .from_writer(vec![]);
    tsv.write_record([
        "work_id",
        "source_id",
        "relative_path",
        "fingerprint_json",
        "title",
        "publisher",
        "book_ids_json",
    ])?;
    let mut non_utf8 = 0;
    for item in &snapshot.queue {
        let Some(path) = item.relative_path.to_str() else {
            non_utf8 += 1;
            continue;
        };
        tsv.write_record([
            item.work_id.as_str(),
            item.source_id.as_str(),
            path,
            &serde_json::to_string(&item.fingerprint)?,
            &item.title,
            &item.publisher,
            &serde_json::to_string(&item.book_ids)?,
        ])?;
    }
    bodies.insert(
        "queue.tsv",
        tsv.into_inner()
            .map_err(|e| SelectionError::Io(e.into_error()))?,
    );
    let mut review = String::new();
    for d in &snapshot.decisions {
        if d.outcomes
            .iter()
            .any(|o| matches!(o.status, Status::NeedsReview | Status::Unreadable))
        {
            review.push_str(&serde_json::to_string(d)?);
            review.push('\n');
        }
    }
    bodies.insert("review.jsonl", review.into_bytes());
    bodies.insert(
        "baseline-findings.json",
        serde_json::to_vec_pretty(&snapshot.baseline_findings)?,
    );
    let report = format!(
        "# Source selection coverage\n\nRoot: {}\nScan: {} — {}\n\n{}\n\nArchives are uninspected containers, not converted works. Page samples do not establish full content coverage. Existing sidecars are unverified references, not Markdown completion.\n\nTSV omitted {non_utf8} non-UTF-8 paths; selection.json preserves their raw bytes.\n\n## Errors\n\n{}\n",
        snapshot.root.display(),
        snapshot.scan_started,
        snapshot.scan_finished,
        snapshot
            .counts
            .iter()
            .map(|(k, v)| format!("- {k}: {v}"))
            .collect::<Vec<_>>()
            .join("\n"),
        snapshot.errors.join("\n")
    );
    bodies.insert("report.md", report.into_bytes());
    for (name, body) in &bodies {
        let mut file = fs::File::create(staging.join(name))?;
        file.write_all(body)?;
        file.sync_all()?;
    }
    let generation = format!("generations/{id}");
    let published = out_dir.join(&generation);
    fs::rename(&staging, &published)?;
    let pointer = out_dir.join(format!(".current-{id}"));
    let mut file = fs::File::create(&pointer)?;
    file.write_all(&serde_json::to_vec_pretty(
        &json!({"schema_version":1,"generation":generation}),
    )?)?;
    file.sync_all()?;
    fs::rename(pointer, out_dir.join("current.json"))?;
    Ok(bodies
        .keys()
        .map(|name| (name.to_string(), published.join(name)))
        .collect())
}
