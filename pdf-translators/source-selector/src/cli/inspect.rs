use super::*;
use crate::{
    evidence::{PopplerExtractor, inspect_pdf},
    grouping::cached_hash,
    inventory::checked_path,
    models::{Evidence, Group},
};
use std::{collections::BTreeSet, time::Duration};
pub(super) fn run(store: &mut Store, args: Inspect) -> Result<ExitCode> {
    if args.limit == 0 || args.timeout_secs == 0 {
        return Err(SelectionError::Usage(
            "--limit and --timeout-secs must be positive".into(),
        ));
    }
    let inventory: InventoryResult = serde_json::from_value(store.meta("inventory")?.unwrap())?;
    let sources = store.sources()?;
    let groups: Vec<Group> = store.records("groups")?;
    let requested = args.pages.as_deref().map(parse_pages).transpose()?;
    if args
        .group
        .as_ref()
        .is_some_and(|id| !groups.iter().any(|g| &g.group_id == id))
    {
        return Err(SelectionError::Usage("unknown group".into()));
    }
    let extractor = PopplerExtractor::new(args.pdftotext, Duration::from_secs(args.timeout_secs));
    let mut evidence = store.evidence()?;
    let mut inspected = 0;
    let mut reused = 0;
    let mut failed = 0;
    let mut worked_groups = 0;
    let mut remaining = 0;
    let mut bytes = 0u64;
    for group in groups
        .iter()
        .filter(|g| args.group.as_ref().is_none_or(|id| &g.group_id == id))
    {
        let complete = group.source_ids.iter().all(|id| {
            evidence.iter().any(|e| {
                &e.source_id == id
                    && requested
                        .as_ref()
                        .map(|ps| ps.iter().all(|p| e.pages.iter().any(|q| q.page == *p)))
                        .unwrap_or(
                            group.source_ids.len() == 1 || e.pages.len() == e.page_count as usize,
                        )
            })
        });
        if worked_groups >= args.limit && !complete {
            remaining += 1;
            continue;
        }
        let mut group_work = false;
        for id in &group.source_ids {
            let source = sources.iter().find(|s| &s.source_id == id).unwrap();
            let result = (|| -> Result<Option<Evidence>> {
                let path = checked_path(&inventory.root, &source.relative_path)?;
                let hash = cached_hash(&inventory.root, source, store)?;
                let prior = evidence.iter().find(|e| {
                    e.source_id == source.source_id && e.sha256 == hash && e.version == 1
                });
                let count = prior.map(|e| e.page_count).or_else(|| {
                    lopdf::Document::load(&path)
                        .ok()
                        .map(|d| d.get_pages().len() as u32)
                });
                let wanted = if let Some(ps) = &requested {
                    Some(ps.clone())
                } else if group.source_ids.len() == 1 {
                    count.map(sample_pages)
                } else {
                    None
                };
                if let Some(prior) = prior {
                    let satisfied = match &wanted {
                        Some(ps) => ps.iter().all(|p| prior.pages.iter().any(|q| q.page == *p)),
                        None => prior.pages.len() == prior.page_count as usize,
                    };
                    if satisfied {
                        return Ok(None);
                    }
                }
                let mut fresh = inspect_pdf(&path, source, wanted.as_deref(), &extractor)?;
                if let Some(prior) = prior {
                    for page in &prior.pages {
                        if !fresh.pages.iter().any(|p| p.page == page.page) {
                            fresh.pages.push(page.clone());
                        }
                    }
                    fresh.pages.sort_by_key(|p| p.page);
                    fresh.claims = prior.claims.clone();
                    if fresh
                        .pages
                        .iter()
                        .any(|p| p.text.chars().any(char::is_alphabetic))
                    {
                        fresh.text_quality = "text".into();
                    }
                }
                Ok(Some(fresh))
            })();
            match result {
                Ok(Some(e)) => {
                    store.save_evidence(&e)?;
                    store.delete_record("inspection_errors", id)?;
                    evidence.retain(|p| p.source_id != *id);
                    evidence.push(e);
                    inspected += 1;
                    bytes += source.fingerprint.size;
                    group_work = true;
                }
                Ok(None) => reused += 1,
                Err(e) => {
                    store.put_record(
                        "inspection_errors",
                        id,
                        &format!("{}: {e}", source.relative_path.display()),
                    )?;
                    eprintln!("inspect {}: {e}", source.relative_path.display());
                    failed += 1;
                    group_work = true;
                }
            }
        }
        if group_work {
            worked_groups += 1;
        }
    }
    print_json(
        &json!({"inspected_sources":inspected,"reused_sources":reused,"failed_sources":failed,"groups_remaining":remaining,"input_bytes_inspected":bytes,"model_calls":0}),
    )?;
    Ok(ExitCode::from(if failed > 0 { 1 } else { 0 }))
}
fn sample_pages(count: u32) -> Vec<u32> {
    let mut pages: BTreeSet<_> = (1..=count.min(3)).collect();
    let n = count.min(10);
    for i in 0..n {
        pages.insert(if n <= 1 {
            1
        } else {
            1 + (u64::from(i) * u64::from(count - 1) / u64::from(n - 1)) as u32
        });
    }
    pages.into_iter().collect()
}
fn parse_pages(text: &str) -> Result<Vec<u32>> {
    let bad = || SelectionError::Usage("--pages expects 1-based numbers/ranges, e.g. 1-3,5".into());
    let mut out = BTreeSet::new();
    for part in text.split(',') {
        let pair: Vec<_> = part.trim().split('-').collect();
        let a: u32 = pair.first().ok_or_else(bad)?.parse().map_err(|_| bad())?;
        let b = if pair.len() == 1 {
            a
        } else if pair.len() == 2 {
            pair[1].parse().map_err(|_| bad())?
        } else {
            return Err(bad());
        };
        if a == 0 || b < a || b - a > 100000 {
            return Err(bad());
        }
        out.extend(a..=b);
    }
    Ok(out.into_iter().collect())
}
