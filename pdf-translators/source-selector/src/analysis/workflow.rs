use super::{
    audit, history, inputs, invalid, models::*, progress::Reporter, read_json, report, review,
    sampling, write_json,
};
use crate::{Result, digest_json};
use rusqlite::{Connection, OpenFlags};
use serde_json::{Value, json};
use std::path::{Component, Path, PathBuf};
fn resolved(path: &Path) -> Result<PathBuf> {
    let absolute = std::path::absolute(path)?;
    let mut clean = PathBuf::new();
    for part in absolute.components() {
        match part {
            Component::ParentDir => {
                clean.pop();
            }
            Component::CurDir => {}
            other => clean.push(other),
        }
    }
    if clean.exists() {
        return Ok(clean.canonicalize()?);
    }
    let parent = clean
        .parent()
        .ok_or_else(|| invalid("invalid output path"))?;
    Ok(resolved(parent)?.join(
        clean
            .file_name()
            .ok_or_else(|| invalid("invalid output name"))?,
    ))
}
pub fn guard_output(config: &AnalysisConfig, out: &Path) -> Result<()> {
    let out = resolved(out)?;
    let paths = [
        &config.csv,
        &config.old_inventory,
        &config.current_inventory,
        &config.history,
        &config.history_status,
        &config.owner_rulings,
    ];
    for input in paths.into_iter().chain(config.evidence_imports.iter()) {
        let input = resolved(input)?;
        if input == out || input.starts_with(&out) {
            return Err(invalid("output overlaps an input path"));
        }
    }
    for db in [&config.old_inventory, &config.current_inventory] {
        let c = Connection::open_with_flags(db, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
        let root: Option<String> = c
            .query_row("SELECT body FROM meta WHERE key='root'", [], |r| r.get(0))
            .ok();
        if let Some(root) = root.and_then(|s| serde_json::from_str::<String>(&s).ok()) {
            let root = resolved(Path::new(&root))?;
            if out.starts_with(&root) || root.starts_with(&out) {
                return Err(invalid("analysis output overlaps a source library"));
            }
        }
    }
    Ok(())
}
fn validate_imports(f: &FrozenInputs) -> Result<Vec<Value>> {
    let ids = f
        .old_sources
        .iter()
        .map(|s| (&s.source_id, &s.fingerprint))
        .collect::<std::collections::BTreeMap<_, _>>();
    let mut normalized = vec![];
    for batch in &f.imported_evidence {
        for item in batch
            .as_array()
            .ok_or_else(|| invalid("evidence imports must be arrays of source-bound records"))?
        {
            let sid = item["source_id"].as_str().unwrap_or("");
            let method = item["method"].as_str().unwrap_or("unknown");
            let bound = ids.get(&sid.to_owned()).is_some_and(|fp| {
                serde_json::to_value(fp).ok().as_ref() == Some(&item["fingerprint"])
            });
            if !bound
                || item["scope"].as_str().is_none_or(str::is_empty)
                || item["provenance"].as_str().is_none_or(str::is_empty)
            {
                return Err(invalid(
                    "evidence import lacks verified source binding, scope, or provenance",
                ));
            }
            if item["actor"] == "model" {
                if item["model"].as_str().is_none_or(str::is_empty) {
                    return Err(invalid("model evidence lacks model ID"));
                }
                if item["kind"] == "judgment" && item["role"] != "sol" {
                    return Err(invalid("model judgments require Sol"));
                }
                if item["kind"] == "fact" {
                    let page = item["page"]
                        .as_u64()
                        .filter(|p| *p > 0)
                        .ok_or_else(|| invalid("fact needs page citation"))?;
                    let quote = item["quote"]
                        .as_str()
                        .filter(|s| !s.is_empty())
                        .ok_or_else(|| invalid("fact needs quotation"))?;
                    let db = Connection::open_with_flags(
                        f.snapshot_root.join("old.db"),
                        OpenFlags::SQLITE_OPEN_READ_ONLY,
                    )?;
                    let mut stmt = db.prepare("SELECT body FROM records WHERE kind='evidence'")?;
                    let bodies = stmt.query_map([], |r| r.get::<_, String>(0))?;
                    let mut checked = false;
                    for b in bodies {
                        let v: Value = serde_json::from_str(&b?)?;
                        if v["source_id"] == sid
                            && v["pages"].as_array().into_iter().flatten().any(|p| {
                                p["page"].as_u64() == Some(page)
                                    && p["text"].as_str().is_some_and(|t| t.contains(quote))
                            })
                        {
                            checked = true;
                            break;
                        }
                    }
                    if !checked {
                        return Err(invalid(
                            "model quote not verified against saved page evidence",
                        ));
                    }
                }
            }
            let mut entry = item.clone();
            if !matches!(
                method,
                "exact_bytes"
                    | "all_rendered_pages"
                    | "sampled_bytes"
                    | "sampled_pages"
                    | "partial_reference"
            ) {
                entry["method"] = json!("unconfirmed");
            }
            normalized.push(entry);
        }
    }
    // Imports remain attributed evidence only: they cannot become owner approvals or automatically exclude files.
    // Keep the immutable FrozenInputs receipt untouched; consumers use this validated view separately.
    Ok(normalized)
}
pub fn run(config: &AnalysisConfig, out: &Path) -> Result<AuditResult> {
    guard_output(config, out)?;
    eprintln!("Freezing read-only inputs; no PDFs are read.");
    let f = inputs::freeze(config, out)?;
    let lock = std::fs::OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(out.join(".analysis.lock"))?;
    lock.lock()?;
    for name in ["progress.json.tmp", "sample.json.tmp"] {
        let p = out.join(name);
        if p.exists() {
            std::fs::remove_file(p)?;
        }
    }
    let reporter = Reporter::start(out)?;
    reporter.record("history", 0, 1, 0)?;
    let result = (|| {
        let audit = if out.join("audit-receipt.json").exists() {
            read_audit(out)?
        } else {
            let imports = validate_imports(&f)?;
            let h = history::load(&f)?;
            reporter.record("audit", 0, f.reference.len(), 0)?;
            let mut audit =
                audit::compare_with_progress(&f, &h, &f.owner_rulings, |stage, done, total| {
                    reporter.record(stage, done, total, 0)
                })?;
            audit.supplemental_evidence = imports;
            for relation in &mut audit.relationships {
                let extra = audit
                    .supplemental_evidence
                    .iter()
                    .filter(|e| {
                        e["source_id"]
                            .as_str()
                            .is_some_and(|id| relation.source_ids.iter().any(|s| s == id))
                    })
                    .collect::<Vec<_>>();
                if !extra.is_empty() {
                    relation.evidence_digest = digest_json(&(&relation.evidence_digest, extra));
                }
            }
            for name in ["audit.json.tmp", "audit-receipt.json.tmp"] {
                let p = out.join(name);
                if p.exists() {
                    std::fs::remove_file(p)?;
                }
            }
            write_json(&out.join("audit.json"), &audit)?;
            write_json(
                &out.join("audit-receipt.json"),
                &json!({"audit_digest":digest_json(&audit)}),
            )?;
            audit
        };
        let sample = sampling::select(&audit, config)?;
        if !out.join("sample.json").exists() {
            write_json(&out.join("sample.json"), &sample)?;
        } else {
            let old: SampleManifest = read_json(&out.join("sample.json"))?;
            if digest_json(&old) != digest_json(&sample) {
                return Err(invalid("sample artifact changed"));
            }
        }
        reporter.record("report", 0, 1, 0)?;
        report::write(&audit, &sample, &out.join("report"))?;
        reporter.record("complete", 1, 1, 0)?;
        Ok(audit)
    })();
    if result.is_err() {
        let _ = reporter.record("failed", 0, 1, 1);
    }
    reporter.finish()?;
    result
}
pub fn read_audit(run: &Path) -> Result<AuditResult> {
    let audit: AuditResult = read_json(&run.join("audit.json"))?;
    let receipt: Value = read_json(&run.join("audit-receipt.json"))?;
    if audit.policy_version != super::POLICY_VERSION
        || receipt["audit_digest"] != digest_json(&audit)
    {
        return Err(invalid("saved audit changed"));
    }
    Ok(audit)
}
pub fn export(run: &Path, out: &Path) -> Result<ReviewManifest> {
    let f: FrozenInputs = read_json(&run.join("inputs.json"))?;
    guard_output(&f.config, out)?;
    inputs::verify_snapshots(&f, &f.snapshot_root)?;
    review::export_cases(&read_audit(run)?, out)
}
pub fn import(run: &Path, manifest: &Path, results: &Path, out: &Path) -> Result<AuditResult> {
    if out.exists() {
        return Err(invalid("review import needs a fresh derived run directory"));
    }
    let f: FrozenInputs = read_json(&run.join("inputs.json"))?;
    guard_output(&f.config, out)?;
    inputs::verify_snapshots(&f, &f.snapshot_root)?;
    let out_abs = resolved(out)?;
    let run_abs = resolved(run)?;
    if out_abs == run_abs || run_abs.starts_with(&out_abs) {
        return Err(invalid("derived output overlaps original run"));
    }
    let audit = read_audit(run)?;
    let m: ReviewManifest = read_json(manifest)?;
    let rulings = review::load_results(&m, results)?;
    let next = audit::with_rulings(&audit, &rulings)?;
    let sample: SampleManifest = read_json(&run.join("sample.json"))?;
    std::fs::create_dir_all(out)?;
    write_json(&out.join("inputs.json"), &f)?;
    write_json(&out.join("audit.json"), &next)?;
    write_json(
        &out.join("audit-receipt.json"),
        &json!({"audit_digest":digest_json(&next),"parent":run_abs}),
    )?;
    write_json(&out.join("sample.json"), &sample)?;
    write_json(&out.join("review-results.json"), &rulings)?;
    report::write(&next, &sample, &out.join("report"))?;
    Ok(next)
}
