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
    let mut current = PathBuf::new();
    for part in absolute.components() {
        match part {
            Component::ParentDir => {
                current.pop();
            }
            Component::CurDir => {}
            other => {
                current.push(other);
                if std::fs::symlink_metadata(&current).is_ok() {
                    current = current.canonicalize()?;
                }
            }
        }
    }
    Ok(current)
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
    let sources = f
        .old_sources
        .iter()
        .chain(f.current_sources.iter())
        .map(|s| (&s.source_id, s))
        .collect::<std::collections::BTreeMap<_, _>>();
    let mut normalized = vec![];
    for batch in &f.imported_evidence {
        for item in batch
            .as_array()
            .ok_or_else(|| invalid("evidence imports must be arrays"))?
        {
            let sid = item["source_id"].as_str().unwrap_or("");
            let source = sources
                .get(&sid.to_owned())
                .ok_or_else(|| invalid("unbound evidence source"))?;
            if serde_json::to_value(&source.fingerprint)? != item["fingerprint"]
                || item["scope"].as_str().is_none_or(str::is_empty)
                || item["provenance"].as_str().is_none_or(str::is_empty)
            {
                return Err(invalid(
                    "evidence lacks source fingerprint, scope or provenance",
                ));
            }
            let method = item["method"].as_str().unwrap_or("unknown");
            if item["kind"] == "comparison"
                || matches!(method, "exact_bytes" | "all_rendered_pages")
            {
                let other = item["other_source_id"].as_str().ok_or_else(|| {
                    invalid("pairwise comparisons require both source identities")
                })?;
                let second = sources
                    .get(&other.to_owned())
                    .ok_or_else(|| invalid("unbound comparison counterpart"))?;
                if serde_json::to_value(&second.fingerprint)? != item["other_fingerprint"]
                    || other == sid
                {
                    return Err(invalid("comparison counterpart fingerprint invalid"));
                }
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
                        .and_then(|p| u32::try_from(p).ok())
                        .filter(|p| *p > 0)
                        .ok_or_else(|| invalid("fact needs positive page citation"))?;
                    let quote = item["quote"]
                        .as_str()
                        .filter(|s| !s.trim().is_empty())
                        .ok_or_else(|| invalid("fact needs quotation"))?;
                    let db = if f.old_sources.iter().any(|s| s.source_id == sid) {
                        "old.db"
                    } else {
                        "current.db"
                    };
                    let store = crate::store::Store::open_readonly(&f.snapshot_root.join(db))?;
                    let key = digest_json(&(1, &source.fingerprint));
                    let current_hash = source.fingerprint.sha256.clone().or(store
                        .get_cached(sid, "hash", &key)?
                        .and_then(|v| v.as_str().map(str::to_owned)));
                    let current_hash = if current_hash.is_some() {
                        current_hash
                    } else {
                        let history = crate::store::Store::open_readonly(
                            &f.snapshot_root.join("history.db"),
                        )?;
                        history
                            .get_cached(sid, "verified_hash", &key)?
                            .and_then(|v| v.as_str().map(str::to_owned))
                    };
                    let current_hash = current_hash.ok_or_else(|| {
                        invalid("factual source has no current fingerprint-bound hash")
                    })?;
                    let claim = crate::models::Claim {
                        claim_id: "analysis-import".into(),
                        kind: "fact".into(),
                        value: quote.into(),
                        source_id: sid.into(),
                        page,
                        quote: quote.into(),
                        actor: item["model"].as_str().unwrap().into(),
                        role: crate::models::ActorRole::Reader,
                    };
                    let saved = store.group_evidence(&[sid.to_owned()])?;
                    if !saved.iter().any(|e| {
                        e.sha256 == current_hash && crate::evidence::validate_claim(&claim, e)
                    }) {
                        return Err(invalid(
                            "model quote not verified against current native page evidence",
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
    Ok(normalized)
}
pub fn run(config: &AnalysisConfig, out: &Path) -> Result<AuditResult> {
    let canonical_output = resolved(out)?;
    let out = canonical_output.as_path();
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
    let canonical_output = resolved(out)?;
    let out = canonical_output.as_path();
    let f: FrozenInputs = read_json(&run.join("inputs.json"))?;
    guard_output(&f.config, out)?;
    inputs::verify_snapshots(&f, &f.snapshot_root)?;
    review::export_cases(&read_audit(run)?, out)
}
pub fn import(
    run: &Path,
    manifest: &Path,
    bundle: &Path,
    results: &Path,
    out: &Path,
) -> Result<AuditResult> {
    let canonical_output = resolved(out)?;
    let out = canonical_output.as_path();
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
    let rulings = review::load_results(&m, bundle, results)?;
    let next = audit::with_rulings(&audit, &rulings)?;
    let sample: SampleManifest = read_json(&run.join("sample.json"))?;
    publish_derived(out, |stage| {
        write_json(&stage.join("inputs.json"), &f)?;
        write_json(&stage.join("audit.json"), &next)?;
        write_json(&stage.join("sample.json"), &sample)?;
        write_json(&stage.join("review-results.json"), &rulings)?;
        report::write(&next, &sample, &stage.join("report"))?;
        write_json(
            &stage.join("audit-receipt.json"),
            &json!({"audit_digest":digest_json(&next),"parent":run_abs}),
        )?;
        Ok(())
    })?;
    Ok(next)
}
pub fn publish_derived(out: &Path, build: impl FnOnce(&Path) -> Result<()>) -> Result<()> {
    if out.exists() {
        return Err(invalid("derived output already exists"));
    }
    let parent = out
        .parent()
        .ok_or_else(|| invalid("derived output needs parent"))?;
    std::fs::create_dir_all(parent)?;
    let stage = super::new_stage(parent, "analysis-import")?;
    let result = (|| {
        build(&stage)?;
        if out.exists() {
            return Err(invalid("derived output appeared during publication"));
        }
        std::fs::rename(&stage, out)?;
        Ok(())
    })();
    if result.is_err() {
        let _ = std::fs::remove_dir_all(stage);
    }
    result
}
