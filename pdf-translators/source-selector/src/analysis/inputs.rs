use super::{invalid, models::*, read_json, write_json};
use crate::{
    Result, digest, digest_json,
    models::{Group, Source, SourceKind},
};
use rusqlite::{Connection, OpenFlags};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::{Path, PathBuf},
    time::UNIX_EPOCH,
};
use unicode_casefold::UnicodeCaseFold;
use unicode_normalization::UnicodeNormalization;

pub fn path_key(path: &str) -> String {
    path.replace('\\', "/").nfc().case_fold().nfc().collect()
}
pub fn normalize_windows_relative(path: &str, root: &str) -> Result<String> {
    let p = path_key(path);
    let r = path_key(root).trim_end_matches('/').to_owned();
    let parts = p.split('/').collect::<Vec<_>>();
    if parts.iter().any(|x| matches!(*x, "." | ".." | "")) {
        return Err(invalid(format!("unsafe Windows path: {path}")));
    }
    p.strip_prefix(&(r + "/"))
        .filter(|x| !x.is_empty())
        .map(str::to_owned)
        .ok_or_else(|| invalid(format!("path outside declared root: {path}")))
}
pub fn classify_method(status: &str, evidence: &str) -> EvidenceMethod {
    let text = format!("{status} {evidence}").to_lowercase();
    if ["incomplete", "readable portion", "partial", "truncat"]
        .iter()
        .any(|p| text.contains(p))
    {
        return EvidenceMethod::PartialReference;
    }
    match status {
        "SHA-256 match" => EvidenceMethod::ExactBytes,
        "All rendered pages match" => EvidenceMethod::AllRenderedPages,
        "Sampled byte match" => EvidenceMethod::SampledBytes,
        "Sampled PDF content match" | "Sampled PDF page match" => EvidenceMethod::SampledPages,
        _ => EvidenceMethod::Unconfirmed,
    }
}
pub fn parse_reference(bytes: &[u8], config: &AnalysisConfig) -> Result<Vec<ReferenceRow>> {
    let bytes = bytes.strip_prefix(&[239, 187, 191]).unwrap_or(bytes);
    let mut csv = csv::Reader::from_reader(bytes);
    let headers = csv.headers()?.clone();
    for field in [
        "D file",
        "G file",
        "Status",
        "Evidence",
        "Other matching G files",
    ] {
        if !headers.iter().any(|h| h == field) {
            return Err(invalid(format!("missing CSV header {field}")));
        }
    }
    let mut rows = vec![];
    let mut seen = BTreeSet::new();
    for (index, r) in csv.records().enumerate() {
        let raw: BTreeMap<String, String> = headers
            .iter()
            .zip(r?.iter())
            .map(|(a, b)| (a.into(), b.into()))
            .collect();
        let d = normalize_windows_relative(&raw["D file"], &config.d_root)?;
        if !d.ends_with(".pdf") {
            continue;
        }
        if !seen.insert(d.clone()) {
            return Err(invalid(format!("duplicate normalized reference path: {d}")));
        }
        let g = if raw["G file"].trim().is_empty() {
            None
        } else {
            Some(normalize_windows_relative(
                raw["G file"].trim(),
                &config.g_root,
            )?)
        };
        let others = raw["Other matching G files"]
            .lines()
            .filter(|s| !s.trim().is_empty())
            .map(|s| normalize_windows_relative(s.trim(), &config.g_root))
            .collect::<Result<Vec<_>>>()?;
        rows.push(ReferenceRow {
            row: index + 2,
            d_path: d,
            g_path: g,
            other_paths: others,
            method: classify_method(&raw["Status"], &raw["Evidence"]),
            raw,
        });
    }
    Ok(rows)
}
fn observed(path: &Path) -> Result<(u64, u128)> {
    let m = std::fs::metadata(path)?;
    Ok((
        m.len(),
        m.modified()?
            .duration_since(UNIX_EPOCH)
            .map_err(|_| invalid("input predates epoch"))?
            .as_nanos(),
    ))
}
fn files(config: &AnalysisConfig) -> Vec<(String, PathBuf, bool)> {
    let mut v = vec![
        ("reference".into(), config.csv.clone(), false),
        ("old".into(), config.old_inventory.clone(), true),
        ("current".into(), config.current_inventory.clone(), true),
        ("history".into(), config.history.clone(), true),
        ("status".into(), config.history_status.clone(), false),
        ("rulings".into(), config.owner_rulings.clone(), false),
    ];
    v.extend(
        config
            .evidence_imports
            .iter()
            .enumerate()
            .map(|(i, p)| (format!("evidence-{i}"), p.clone(), false)),
    );
    v
}
pub fn verify_snapshots(inputs: &FrozenInputs, run: &Path) -> Result<()> {
    if inputs.receipt_id != receipt_id(inputs) {
        return Err(invalid("input receipt binding changed"));
    }
    for r in &inputs.receipts {
        if digest(&std::fs::read(run.join(&r.snapshot))?) != r.sha256 {
            return Err(invalid(format!("snapshot changed: {}", r.label)));
        }
    }
    Ok(())
}
fn rows<T: serde::de::DeserializeOwned>(conn: &Connection, sql: &str) -> Result<Vec<T>> {
    let mut statement = conn.prepare(sql)?;
    let bodies = statement.query_map([], |r| r.get::<_, String>(0))?;
    bodies.map(|s| Ok(serde_json::from_str(&s?)?)).collect()
}
fn sources(db: &Path) -> Result<Vec<Source>> {
    let c = Connection::open_with_flags(db, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
    let v: Vec<Source> = rows(&c, "SELECT body FROM sources WHERE active=1 ORDER BY id")?;
    let mut seen = BTreeSet::new();
    for s in &v {
        let p = s.relative_path.to_string_lossy();
        let key = path_key(&p);
        if !seen.insert(key) {
            return Err(invalid(format!("inventory normalized-path collision: {p}")));
        }
    }
    Ok(v.into_iter()
        .filter(|s| s.kind == SourceKind::Pdf)
        .collect())
}
pub fn freeze(config: &AnalysisConfig, output: &Path) -> Result<FrozenInputs> {
    if config.schema_version != 1 || config.holdout_percent > 100 {
        return Err(invalid("unsupported config schema or holdout percentage"));
    }
    if config.reference_complete
        && config
            .completion_attestation
            .as_deref()
            .is_none_or(|s| s.trim().is_empty())
    {
        return Err(invalid("completed reference requires owner attestation"));
    }
    if output.exists() {
        let old: FrozenInputs = read_json(&output.join("inputs.json"))?;
        if digest_json(&old.config) != digest_json(config) {
            return Err(invalid("configuration changed; use a new run directory"));
        }
        verify_snapshots(&old, output)?;
        for r in &old.receipts {
            if observed(&r.original)? != (r.source_size, r.source_modified_ns) {
                return Err(invalid("source input changed; use a new run directory"));
            }
        }
        // Database WAL changes need logical comparison, not the main file's mtime alone.
        for (label, path, is_db) in files(config) {
            if is_db {
                let receipt = old.receipts.iter().find(|r| r.label == label).unwrap();
                let c = Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
                let snapshot = Connection::open_with_flags(
                    output.join(&receipt.snapshot),
                    OpenFlags::SQLITE_OPEN_READ_ONLY,
                )?;
                for table in ["meta", "sources", "records"] {
                    let sql = format!("SELECT * FROM {table} ORDER BY 1,2");
                    if db_values(&c, &sql)? != db_values(&snapshot, &sql)? {
                        return Err(invalid("database changed; use a new run directory"));
                    }
                }
            }
        }
        return Ok(old);
    }
    let parent = output
        .parent()
        .ok_or_else(|| invalid("output needs parent"))?;
    std::fs::create_dir_all(parent)?;
    let staging = parent.join(format!(".analysis-freeze-{}", std::process::id()));
    std::fs::create_dir(&staging)?;
    let result = (|| {
        let mut receipts = vec![];
        for (label, path, is_db) in files(config) {
            let before = observed(&path)?;
            let name = format!("{label}.{}", if is_db { "db" } else { "input" });
            let dest = staging.join(&name);
            if is_db {
                let conn = Connection::open_with_flags(&path, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
                conn.backup("main", &dest, None::<fn(rusqlite::backup::Progress)>)?;
            } else {
                std::fs::write(&dest, read_unchanged(&path, |p| Ok(std::fs::read(p)?))?)?;
            }
            if before != observed(&path)? {
                return Err(invalid("input changed while reading; retry"));
            }
            receipts.push(InputReceipt {
                label,
                original: path,
                snapshot: name,
                sha256: digest(&std::fs::read(&dest)?),
                source_size: before.0,
                source_modified_ns: before.1,
            });
        }
        let reference = parse_reference(&std::fs::read(staging.join("reference.input"))?, config)?;
        let old_sources = sources(&staging.join("old.db"))?;
        let current_sources = sources(&staging.join("current.db"))?;
        let c =
            Connection::open_with_flags(staging.join("old.db"), OpenFlags::SQLITE_OPEN_READ_ONLY)?;
        let groups: Vec<Group> = rows(
            &c,
            "SELECT body FROM records WHERE kind='groups' ORDER BY id",
        )?;
        let owner_rulings = read_json(&staging.join("rulings.input"))?;
        let imported_evidence = config
            .evidence_imports
            .iter()
            .enumerate()
            .map(|(i, _)| read_json(&staging.join(format!("evidence-{i}.input"))))
            .collect::<Result<Vec<_>>>()?;
        let mut frozen = FrozenInputs {
            schema_version: 1,
            snapshot_root: parent.canonicalize()?.join(
                output
                    .file_name()
                    .ok_or_else(|| invalid("output requires directory name"))?,
            ),
            receipt_id: String::new(),
            config: config.clone(),
            receipts,
            reference,
            old_sources,
            current_sources,
            groups,
            owner_rulings,
            imported_evidence,
        };
        frozen.receipt_id = receipt_id(&frozen);
        write_json(&staging.join("inputs.json"), &frozen)?;
        std::fs::rename(&staging, output)?;
        Ok(frozen)
    })();
    if result.is_err() {
        let _ = std::fs::remove_dir_all(&staging);
    }
    result
}
fn db_values(c: &Connection, sql: &str) -> Result<Vec<Vec<String>>> {
    let mut s = c.prepare(sql)?;
    let count = s.column_count();
    let rows = s.query_map([], |r| {
        (0..count)
            .map(|i| Ok(format!("{:?}", r.get_ref(i)?)))
            .collect::<rusqlite::Result<Vec<_>>>()
    })?;
    Ok(rows.collect::<std::result::Result<Vec<_>, _>>()?)
}

fn receipt_id(inputs: &FrozenInputs) -> String {
    let mut copy = inputs.clone();
    copy.receipt_id.clear();
    digest_json(&copy)
}

pub fn read_unchanged(
    path: &Path,
    reader: impl FnOnce(&Path) -> Result<Vec<u8>>,
) -> Result<Vec<u8>> {
    let before = observed(path)?;
    let bytes = reader(path)?;
    if before != observed(path)? {
        return Err(invalid("input changed while reading; retry"));
    }
    Ok(bytes)
}
