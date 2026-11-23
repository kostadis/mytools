use super::*;
use crate::{
    digest_json,
    export::validate_work_dir,
    grouping::{presentation_key, title_key},
    models::*,
    store::Store,
};
use std::collections::{BTreeMap, BTreeSet};

pub fn select(store: &Store, output: &Path, provenance: Option<&Path>) -> Result<Snapshot> {
    let inv: InventoryResult = serde_json::from_value(
        store
            .meta("inventory")?
            .ok_or_else(|| SelectionError::Invalid("scan first".into()))?,
    )?;
    validate_work_dir(&inv.root, output)?;
    validate_output(output)?;
    let _guard = lock(output, "selection.lock")?;
    let identity = crate::inventory::root_identity(&inv.root)?;
    if store.meta("root_identity")?.is_some_and(|v| v != identity) {
        return Err(SelectionError::Invalid(
            "source root identity changed".into(),
        ));
    }
    let mut cache = Store::open(&output.join("metadata.db"))?;
    let sources: BTreeMap<_, _> = store
        .sources()?
        .into_iter()
        .map(|s| (s.source_id.clone(), s))
        .collect();
    let decisions: Vec<Decision> = store.records("decisions")?;
    let adopted = store.current_decisions()?;
    let evidence = store.evidence()?;
    let hints: Vec<Hint> = store.records("hints")?;
    let provenance: Value = provenance
        .map(read_json)
        .transpose()?
        .unwrap_or(Value::Null);
    let mut snapshot = Snapshot {
        schema_version: 1,
        snapshot_id: String::new(),
        policy: "internal-recency-v1".into(),
        created: chrono::Utc::now().to_rfc3339(),
        source_root: inv.root.clone(),
        root_identity: identity,
        coverage_errors: inv.errors,
        archives: sources
            .values()
            .filter(|s| s.kind == SourceKind::Archive)
            .count(),
        ready: vec![],
        records: vec![],
    };
    for group in store.records::<Group>("groups")? {
        let members: Vec<_> = group
            .source_ids
            .iter()
            .filter_map(|id| sources.get(id))
            .filter(|s| s.kind == SourceKind::Pdf)
            .collect();
        if members.is_empty() {
            continue;
        }
        let work_id = format!("w{}", &digest_json(&group.group_id)[..24]);
        let mut record = PolicyRecord {
            work_id: work_id.clone(),
            group_id: group.group_id.clone(),
            status: "deferred_choice".into(),
            reason: String::new(),
            selected_source_id: None,
            candidates: members
                .iter()
                .map(|s| metadata::probe(&inv.root, s, store, &mut cache))
                .collect(),
        };
        let authority: Vec<_> = decisions
            .iter()
            .filter(|d| {
                matches!(d.actor_role, ActorRole::User | ActorRole::Sol)
                    && (d
                        .outcomes
                        .iter()
                        .any(|o| group.source_ids.contains(&o.source_id))
                        || record.candidates.iter().any(|c| {
                            c.sha256
                                .as_ref()
                                .is_some_and(|h| d.source_hashes.values().any(|v| v == h))
                        }))
            })
            .collect();
        let baseline = members.iter().any(|s| {
            s.baseline_established
                || (!s.artifacts.is_empty() && s.publisher.to_lowercase().contains("dungeon"))
        });
        let mut choices: Vec<(String, String, String)> = vec![];
        if baseline {
            record.status = "existing_or_baseline".into();
            record.reason =
                "baseline requires separate reconciliation; JSON is not Markdown coverage".into();
        } else if !authority.is_empty() {
            record.reason =
                "adopted review or hold preserved; changed membership requires review".into();
            if authority.len() == 1 {
                let d = authority[0];
                if adopted.iter().any(|a| {
                    a.group_id == d.group_id && a.membership_digest == group.membership_digest
                }) && d.membership_digest == group.membership_digest
                {
                    choices = d
                        .outcomes
                        .iter()
                        .filter(|o| matches!(o.status, Status::Selected | Status::DistinctWork))
                        .map(|o| {
                            (
                                o.source_id.clone(),
                                o.work_id.clone().unwrap_or_else(|| work_id.clone()),
                                "adopted_review".into(),
                            )
                        })
                        .collect();
                }
            }
        } else {
            let conflict = [
                "ruleset",
                "language",
                "document_role",
                "work_identity",
                "volume",
            ]
            .iter()
            .any(|kind| {
                let mut values = BTreeSet::new();
                for c in &record.candidates {
                    for e in evidence.iter().filter(|e| {
                        e.source_id == c.source.source_id
                            && Some(e.sha256.as_str()) == c.sha256.as_deref()
                    }) {
                        for claim in e.claims.iter().filter(|v| v.kind == *kind) {
                            values.insert(claim.value.trim().to_lowercase());
                        }
                    }
                    for h in hints
                        .iter()
                        .filter(|h| h.source_ids.contains(&c.source.source_id))
                    {
                        if let Some(v) = h.payload.get(*kind).and_then(Value::as_str) {
                            values.insert(v.trim().to_lowercase());
                        }
                    }
                }
                values.len() > 1
            });
            if conflict {
                record.reason =
                    "explicit content/hint qualifiers conflict; whole component deferred".into();
            } else {
                match automatic(&record.candidates) {
                    Ok(id) => {
                        choices.push((id, work_id.clone(), "most_recent_internal_date".into()))
                    }
                    Err(reason) => record.reason = reason,
                }
            }
        }
        for (id, work, basis) in choices {
            let c = record
                .candidates
                .iter()
                .find(|c| c.source.source_id == id)
                .unwrap();
            if c.error.is_some() || c.sha256.is_none() || c.page_count.is_none() {
                record.reason = "chosen source unavailable".into();
                continue;
            }
            safe_id(&work)?;
            let p = provenance
                .get("files")
                .and_then(Value::as_array)
                .and_then(|files| {
                    files.iter().find(|f| {
                        f["original_relative_path"]
                            == serde_json::to_value(&c.source.relative_path).unwrap_or(Value::Null)
                            && f["sha256"].as_str() == c.sha256.as_deref()
                    })
                });
            snapshot.ready.push(Ready{work_id:work,group_id:group.group_id.clone(),source_id:id.clone(),relative_path:c.source.relative_path.clone(),sha256:c.sha256.clone().unwrap(),page_count:c.page_count.unwrap(),title:c.source.product_folder.clone(),publisher:c.source.publisher.clone(),selection_basis:basis,date:c.dates.effective.clone(),alternatives:members.iter().filter(|s|s.source_id!=id).map(|s|s.relative_path.to_string_lossy().into_owned()).collect(),provenance:serde_json::json!({"original_source_root":provenance.get("source_root"),"original":p})});
            record.status = "ready".into();
            record.selected_source_id = Some(id);
            record.reason =
                "ready to attempt full native-text extraction; alternatives retained".into();
        }
        snapshot.records.push(record);
    }
    snapshot.snapshot_id = digest_json(&snapshot);
    let dir = output
        .join("selection/generations")
        .join(&snapshot.snapshot_id);
    write_json(&dir.join("markdown-selection.json"), &snapshot)?;
    let mut tsv = String::from("work_id\tsource_id\tsha256\tpages\tpath\n");
    for r in &snapshot.ready {
        tsv.push_str(&format!(
            "{}\t{}\t{}\t{}\t{}\n",
            r.work_id,
            r.source_id,
            r.sha256,
            r.page_count,
            r.relative_path
                .to_string_lossy()
                .replace(['\t', '\n', '\r'], " ")
        ));
    }
    atomic_write(&dir.join("markdown-queue.tsv"), tsv.as_bytes())?;
    let review = snapshot
        .records
        .iter()
        .map(serde_json::to_string)
        .collect::<std::result::Result<Vec<_>, _>>()?
        .join("\n");
    atomic_write(&dir.join("markdown-review.jsonl"), review.as_bytes())?;
    write_json(
        &output.join("selection/current.json"),
        &snapshot.snapshot_id,
    )?;
    Ok(snapshot)
}
pub fn load_current(output: &Path) -> Result<Snapshot> {
    let id: String = read_json(&output.join("selection/current.json"))?;
    safe_id(&id)?;
    let mut s: Snapshot = read_json(
        &output
            .join("selection/generations")
            .join(&id)
            .join("markdown-selection.json"),
    )?;
    if s.schema_version != 1 || s.snapshot_id != id {
        return Err(SelectionError::Invalid(
            "invalid selection version/id".into(),
        ));
    }
    s.snapshot_id.clear();
    if digest_json(&s) != id {
        return Err(SelectionError::Invalid(
            "selection checksum mismatch".into(),
        ));
    }
    s.snapshot_id = id;
    Ok(s)
}
fn automatic(candidates: &[Candidate]) -> std::result::Result<String, String> {
    if candidates
        .iter()
        .any(|c| c.error.is_some() || c.sha256.is_none())
    {
        return Err("unreadable or changed competitor".into());
    }
    let mut by_hash: BTreeMap<&str, Vec<&Candidate>> = BTreeMap::new();
    for c in candidates {
        by_hash
            .entry(c.sha256.as_deref().unwrap())
            .or_default()
            .push(c);
    }
    let mut reps = vec![];
    for aliases in by_hash.values_mut() {
        aliases.sort_by_key(|c| {
            (
                c.source
                    .relative_path
                    .to_string_lossy()
                    .to_lowercase()
                    .contains(".old"),
                crate::inventory::path_bytes(&c.source.relative_path),
            )
        });
        reps.push(aliases[0]);
    }
    if reps.len() == 1 {
        let c = reps[0];
        if c.dates.effective.is_none()
            && c.source
                .relative_path
                .to_string_lossy()
                .to_lowercase()
                .contains(".old")
        {
            return Err("undated old-only source".into());
        }
        return Ok(c.source.source_id.clone());
    }
    let family = |c: &&Candidate| {
        let key = title_key(&c.source.relative_path);
        presentation_key(Path::new(&format!("{key}.pdf")))
    };
    let folders: BTreeSet<_> = candidates
        .iter()
        .map(|c| (&c.source.publisher, &c.source.product_folder))
        .collect();
    let keys: BTreeSet<_> = candidates.iter().map(|c| family(&c)).collect();
    let qualifiers: BTreeSet<_> = candidates
        .iter()
        .map(|c| protected(&c.source.relative_path))
        .collect();
    if folders.len() != 1
        || reps[0].source.publisher.is_empty()
        || reps[0].source.product_folder.is_empty()
        || keys.len() != 1
        || keys.first().is_none_or(|s| {
            s.len() < 3
                || [
                    "map",
                    "maps",
                    "book",
                    "guide",
                    "character sheet",
                    "reference",
                    "readme",
                ]
                .contains(&s.as_str())
        })
        || qualifiers.len() != 1
    {
        return Err(
            "whole component is not a compatible product/version/presentation family".into(),
        );
    }
    if reps.iter().any(|c| c.dates.effective.is_none()) {
        return Err("missing, ambiguous or conflicting internal date on competitor".into());
    }
    reps.sort_by_key(|c| std::cmp::Reverse(c.dates.effective.as_ref().unwrap().start_ms));
    let best = reps[0];
    let date = best.dates.effective.as_ref().unwrap();
    if reps[1..]
        .iter()
        .any(|c| c.dates.effective.as_ref().unwrap().end_ms > date.start_ms)
    {
        return Err("tied or overlapping internal date intervals".into());
    }
    Ok(best.source.source_id.clone())
}
fn protected(path: &Path) -> Vec<String> {
    use std::sync::LazyLock;
    static Q: LazyLock<regex::Regex> = LazyLock::new(|| {
        regex::Regex::new(r"(?i)(?:d[&_ ]?d[ _-]*\d(?:\.\d)?|\b(?:vol(?:ume)?|book|part)[ _-]*\d+|\b\d+(?:e|nd[ _-]*edition|th[ _-]*edition)\b|\b(?:english|french|german|italian|spanish|fr|en|ita|pf2|pathfinder)\b)").unwrap()
    });
    let raw = path.to_string_lossy().replace('_', " ").to_lowercase();
    Q.find_iter(&raw)
        .map(|m| m.as_str().replace([' ', '-'], ""))
        .collect()
}
