use super::{
    inputs::{path_key, verify_snapshots},
    invalid,
    models::*,
    read_json,
};
use crate::{Result, digest_json};
use rusqlite::{Connection, OpenFlags, OptionalExtension};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
pub fn load(inputs: &FrozenInputs) -> Result<HistoricalView> {
    verify_snapshots(inputs, &inputs.snapshot_root)?;
    let status: Value = read_json(&inputs.snapshot_root.join("status.input"))?;
    let order = &inputs.config.historical_runs;
    if order.is_empty()
        || order.iter().collect::<BTreeSet<_>>().len() != order.len()
        || status["run_id"].as_str() != order.last().map(String::as_str)
    {
        return Err(invalid(
            "historical run order must be unique and end in the recorded latest run",
        ));
    }
    let c = Connection::open_with_flags(
        inputs.snapshot_root.join("history.db"),
        OpenFlags::SQLITE_OPEN_READ_ONLY,
    )?;
    let mut stmt =
        c.prepare("SELECT id,body FROM records WHERE kind='continuous_groups' ORDER BY id")?;
    let rows = stmt.query_map([], |r| Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?)))?;
    let mut verified_hashes = BTreeMap::new();
    let inventory = Connection::open_with_flags(
        inputs.snapshot_root.join("old.db"),
        OpenFlags::SQLITE_OPEN_READ_ONLY,
    )?;
    let root: Option<String> = inventory
        .query_row("SELECT body FROM meta WHERE key='root'", [], |r| r.get(0))
        .optional()?;
    let root = root.and_then(|r| serde_json::from_str::<String>(&r).ok());
    for db in [&inventory, &c] {
        let has_cache: bool = db.query_row(
            "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type='table' AND name='cache')",
            [],
            |r| r.get(0),
        )?;
        if !has_cache {
            continue;
        }
        let mut query=db.prepare("SELECT body FROM cache WHERE id=?1 AND stage IN ('hash','verified_hash') AND cache_key=?2")?;
        for source in &inputs.old_sources {
            let key = digest_json(&(1, &source.fingerprint));
            let rows = query.query_map(rusqlite::params![source.source_id, key], |r| {
                r.get::<_, String>(0)
            })?;
            for row in rows {
                let hash: String = serde_json::from_str(&row?)?;
                if hash.len() != 64 || !hash.bytes().all(|b| b.is_ascii_hexdigit()) {
                    return Err(invalid("invalid cached full hash"));
                }
                if verified_hashes
                    .insert(source.source_id.clone(), hash.clone())
                    .is_some_and(|old| old != hash)
                {
                    return Err(invalid("conflicting current-fingerprint hash caches"));
                }
            }
        }
    }
    let mut ranked = BTreeMap::new();
    let mut warnings = vec![];
    let sources = inputs
        .old_sources
        .iter()
        .map(|s| (&s.source_id, s))
        .collect::<BTreeMap<_, _>>();
    for r in rows {
        let (id, body) = r?;
        let run = order
            .iter()
            .filter(|run| id.starts_with(&format!("{run}-")))
            .collect::<Vec<_>>();
        if run.len() != 1 {
            return Err(invalid(format!(
                "unlisted or ambiguous historical run: {id}"
            )));
        }
        let rank = order.iter().position(|x| x == run[0]).unwrap();
        let value: Value = serde_json::from_str(&body)?;
        let snap = &value["snapshot"];
        if path_key(snap["source_root"].as_str().unwrap_or("")).trim_end_matches('/')
            != path_key(&inputs.config.g_root).trim_end_matches('/')
        {
            // Older saved snapshots may use the POSIX mount path instead of the CSV Windows root.
            if root.as_deref() != snap["source_root"].as_str() {
                return Err(invalid(
                    "historical snapshot belongs to a different library root",
                ));
            }
        }
        let policy = snap["policy"].as_str().unwrap_or("unknown").to_owned();
        let scorable = policy == "internal-recency-v1";
        if !scorable {
            warnings.push(format!("unsupported policy {policy} in {id}; unscored"));
        }
        let records = snap["records"]
            .as_array()
            .ok_or_else(|| invalid("snapshot missing records"))?;
        for record in records {
            let gid = record["group_id"]
                .as_str()
                .ok_or_else(|| invalid("historical record lacks group ID"))?
                .to_owned();
            let mut hashes = BTreeMap::new();
            for candidate in record["candidates"].as_array().into_iter().flatten() {
                let sid = candidate["source"]["source_id"].as_str().unwrap_or("");
                let fresh = sources.get(&sid.to_owned()).is_some_and(|s| {
                    digest_json(&s.fingerprint) == digest_json(&candidate["source"]["fingerprint"])
                });
                if let Some(hash) = verified_hashes.get(sid) {
                    hashes.insert(sid.to_owned(), hash.clone());
                } else if fresh {
                    if let Some(hash) = candidate["sha256"].as_str() {
                        hashes.insert(sid.to_owned(), hash.to_owned());
                    }
                } else {
                    warnings.push(format!(
                        "stale or missing candidate {sid} in {id}; cached hash not reused"
                    ));
                }
            }
            let mut selected = vec![];
            for ready in snap["ready"].as_array().into_iter().flatten() {
                let sid = ready["source_id"].as_str().unwrap_or("");
                if ready["group_id"].as_str().is_some_and(|x| x != gid) {
                    continue;
                }
                if ready.get("group_id").is_none()
                    && !inputs
                        .groups
                        .iter()
                        .any(|g| g.group_id == gid && g.source_ids.iter().any(|x| x == sid))
                {
                    continue;
                }
                if !sources.contains_key(&sid.to_owned()) {
                    warnings.push(format!(
                        "selected source {sid} is absent from current old inventory"
                    ));
                }
                selected.push(HistoricalChoice {
                    source_id: sid.into(),
                    relative_path: ready["relative_path"].as_str().unwrap_or("").into(),
                    sha256: hashes.get(sid).cloned(),
                    detail: ready.clone(),
                });
            }
            let observation = HistoricalObservation {
                group_id: gid.clone(),
                run_id: run[0].clone(),
                policy: policy.clone(),
                status: record["status"].as_str().unwrap_or("unknown").into(),
                reason: record["reason"].as_str().unwrap_or("").into(),
                selected,
                hashes,
                scorable,
                record: record.clone(),
            };
            if ranked
                .get(&gid)
                .is_some_and(|(previous, _)| *previous == rank)
            {
                return Err(invalid(format!(
                    "duplicate historical group observation {gid} in one run"
                )));
            }
            if ranked
                .get(&gid)
                .is_none_or(|(previous, _)| *previous < rank)
            {
                ranked.insert(gid, (rank, observation));
            }
        }
    }
    let groups: BTreeMap<_, _> = ranked.into_iter().map(|(k, (_, v))| (k, v)).collect();
    let mut unprocessed_groups = inputs
        .groups
        .iter()
        .filter(|g| !groups.contains_key(&g.group_id))
        .map(|g| g.group_id.clone())
        .collect::<Vec<_>>();
    unprocessed_groups.sort();
    Ok(HistoricalView {
        verified_hashes,
        groups,
        unprocessed_groups,
        warnings,
    })
}
