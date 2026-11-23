use super::*;
use crate::{
    digest_json,
    grouping::{build_groups, hash_source},
    hints::{legacy_hints, read_muse, read_rpglib},
    inventory::{checked_path, scan_root},
    models::{Hint, Source},
};
pub(super) fn run(work: &Path, args: Scan) -> Result<ExitCode> {
    let mut inventory = scan_root(&args.root)?;
    let work = validate_work_dir(&inventory.root, work)?;
    if args.twins_json.is_some() && args.muse_csv.is_none() {
        return Err(SelectionError::Usage(
            "--twins-json requires --muse-csv".into(),
        ));
    }
    let mut hints = legacy_hints(&inventory.root, &inventory.sources);
    if let Some(path) = &args.muse_csv {
        hints.extend(read_muse(
            path,
            &inventory.sources,
            args.twins_json.as_deref(),
        )?);
    }
    if let Some(path) = &args.rpglib_json {
        hints.extend(read_rpglib(path, &inventory.sources)?);
    }
    if let Some(path) = &args.baseline_manifest {
        hints.extend(baseline(path, &inventory.root, &mut inventory.sources)?);
    }
    fs::create_dir_all(&work)?;
    refuse_symlink_database(&work.join("selection.db"))?;
    let mut store = Store::open(&work.join("selection.db"))?;
    if let Some(previous) = store.meta("inventory")? {
        let previous: InventoryResult = serde_json::from_value(previous)?;
        for source in &mut inventory.sources {
            if previous.sources.iter().any(|p| {
                p.source_id == source.source_id
                    && p.fingerprint == source.fingerprint
                    && p.baseline_established
            }) {
                source.baseline_established = true;
            }
        }
    }
    for old in store.records::<Hint>("hints")? {
        if (old.origin == "muse" && args.muse_csv.is_none())
            || (old.origin == "rpglib" && args.rpglib_json.is_none())
            || (old.origin == "baseline" && args.baseline_manifest.is_none())
        {
            hints.push(old);
        }
    }
    let result = store.scan_transaction(|store| {
        store.upsert_inventory(&inventory)?;
        store.replace_records("grouping_errors", &[])?;
        store.replace_records(
            "hints",
            &hints
                .iter()
                .map(|h| Ok((digest_json(h), serde_json::to_value(h)?)))
                .collect::<Result<Vec<_>>>()?,
        )?;
        build_groups(&inventory.sources, &hints, store)
    })?;
    print_json(
        &json!({"sources":inventory.sources.len(),"groups":result.len(),"coverage_errors":inventory.errors,"hint_rows":hints.len(),"unmatched_hints":hints.iter().map(|h|h.unmatched_references.len()).sum::<usize>(),"model_calls":0}),
    )?;
    Ok(ExitCode::SUCCESS)
}
fn baseline(path: &Path, root: &Path, sources: &mut [Source]) -> Result<Vec<Hint>> {
    let value = read_json(path)?;
    let rows = value
        .get("sources")
        .and_then(|v| v.as_array())
        .ok_or_else(|| {
            SelectionError::Usage(
                "baseline manifest requires sources array with relative_path and sha256".into(),
            )
        })?;
    let mut hints = vec![];
    for row in rows {
        let relative = row["relative_path"].as_str().ok_or_else(|| {
            SelectionError::Usage("baseline relative_path must be UTF-8 string".into())
        })?;
        let sha = row["sha256"]
            .as_str()
            .or_else(|| row["fingerprint"]["sha256"].as_str())
            .ok_or_else(|| SelectionError::Usage("baseline source requires SHA-256".into()))?;
        let source = sources
            .iter_mut()
            .find(|s| s.relative_path == Path::new(relative))
            .ok_or_else(|| {
                SelectionError::Usage(format!("baseline source not in inventory: {relative}"))
            })?;
        if hash_source(&checked_path(root, &source.relative_path)?)? != sha {
            return Err(SelectionError::Invalid(format!(
                "baseline source hash mismatch: {relative}"
            )));
        }
        source.baseline_established = true;
        hints.push(Hint {
            origin: "baseline".into(),
            source_ids: vec![source.source_id.clone()],
            payload: row.clone(),
            unmatched_references: vec![],
        });
    }
    Ok(hints)
}
