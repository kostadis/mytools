use super::*;
use crate::{
    evidence::{PopplerExtractor, inspect_pdf},
    grouping::cached_hash,
    inventory::checked_path,
    models::{Evidence, Group},
};
use std::{
    collections::{BTreeMap, BTreeSet},
    time::Duration,
};
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
    if requested.as_ref().is_some_and(|ps| ps.len() > 5) {
        return Err(SelectionError::Usage(
            "first pass has a five-page limit per PDF; additional reading is deferred".into(),
        ));
    }
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
    let mut reused_byte_samples = 0;
    let failures = store.keyed_records::<serde_json::Value>("inspection_errors")?;
    let failed_before = |id: &String| {
        sources
            .iter()
            .find(|s| &s.source_id == id)
            .is_some_and(|s| {
                failures.get(id).is_some_and(|f| {
                    f["fingerprint"] == serde_json::to_value(&s.fingerprint).unwrap()
                })
            })
    };
    let retry = args.retry_failed || args.group.is_some();
    let mut deferred = 0;
    for group in groups
        .iter()
        .filter(|g| args.group.as_ref().is_none_or(|id| &g.group_id == id))
    {
        if !retry && group.source_ids.iter().all(&failed_before) {
            deferred += group.source_ids.len();
            continue;
        }
        let complete = group.source_ids.iter().all(|id| {
            evidence.iter().any(|e| {
                &e.source_id == id
                    && requested
                        .as_ref()
                        .map(|ps| ps.iter().all(|p| e.pages.iter().any(|q| q.page == *p)))
                        .unwrap_or_else(|| {
                            e.pages.len() >= 5
                                || sample_pages(e.page_count)
                                    .iter()
                                    .all(|p| e.pages.iter().any(|q| q.page == *p))
                        })
            })
        });
        if worked_groups >= args.limit && !complete {
            remaining += 1;
            continue;
        }
        let mut group_work = false;
        for id in &group.source_ids {
            if !retry && failed_before(id) {
                deferred += 1;
                continue;
            }
            let source = sources.iter().find(|s| &s.source_id == id).unwrap();
            let result = (|| -> Result<Option<Evidence>> {
                let path = checked_path(&inventory.root, &source.relative_path)?;
                let hash = cached_hash(&inventory.root, source, store)?;
                let prior = evidence.iter().find(|e| {
                    e.source_id == source.source_id && e.sha256 == hash && e.version == 1
                });
                let peers: Vec<_> = evidence
                    .iter()
                    .filter(|e| e.sha256 == hash && e.version == 1)
                    .collect();
                let shared = peers.first().copied();
                let mut cached_pages = BTreeMap::new();
                for peer in &peers {
                    for page in &peer.pages {
                        cached_pages
                            .entry(page.page)
                            .or_insert_with(|| page.clone());
                    }
                }
                if let Some(prior) = prior {
                    for page in &prior.pages {
                        cached_pages.insert(page.page, page.clone());
                    }
                }
                let count = prior.or(shared).map(|e| e.page_count).or_else(|| {
                    lopdf::Document::load(&path)
                        .ok()
                        .map(|d| d.get_pages().len() as u32)
                });
                let count = count.ok_or_else(|| {
                    SelectionError::Invalid(
                        "cannot determine PDF page count; full extraction is deferred".into(),
                    )
                })?;
                let wanted = requested.clone().unwrap_or_else(|| {
                    let mut selected: BTreeSet<_> = prior
                        .map(|e| e.pages.iter().map(|p| p.page).collect())
                        .unwrap_or_default();
                    for page in cached_pages.keys() {
                        if selected.len() >= 5 {
                            break;
                        }
                        selected.insert(*page);
                    }
                    for page in sample_pages(count) {
                        if selected.len() >= 5 {
                            break;
                        }
                        selected.insert(page);
                    }
                    selected.into_iter().take(5).collect()
                });
                if let Some(prior) = prior {
                    let satisfied = wanted
                        .iter()
                        .all(|p| prior.pages.iter().any(|q| q.page == *p));
                    if satisfied {
                        return Ok(None);
                    }
                    let unique: BTreeSet<_> = prior
                        .pages
                        .iter()
                        .map(|p| p.page)
                        .chain(wanted.iter().copied())
                        .collect();
                    if unique.len() > 5 {
                        return Err(SelectionError::Usage(
                            "first pass has a five-page limit including cached pages; additional reading is deferred".into()
                        ));
                    }
                }
                let missing: Vec<_> = wanted
                    .iter()
                    .copied()
                    .filter(|p| !cached_pages.contains_key(p))
                    .collect();
                if !missing.is_empty() && cached_pages.len() + missing.len() > 5 {
                    return Err(SelectionError::Usage(
                        "first pass has a five-page limit across identical PDF copies; additional reading is deferred".into()
                    ));
                }
                let mut fresh = if missing.is_empty() {
                    reused_byte_samples += 1;
                    prior
                        .or(shared)
                        .expect("cached pages have evidence")
                        .clone()
                } else {
                    inspect_pdf(&path, source, Some(&missing), &extractor)?
                };
                fresh.source_id = source.source_id.clone();
                fresh.pages.retain(|p| wanted.contains(&p.page));
                for page in &wanted {
                    if !fresh.pages.iter().any(|p| p.page == *page)
                        && let Some(cached) = cached_pages.get(page)
                    {
                        fresh.pages.push(cached.clone());
                    }
                }
                fresh.pages.sort_by_key(|p| p.page);
                fresh.claims = prior.map(|e| e.claims.clone()).unwrap_or_default();
                merge_sample_provenance(&mut fresh, &peers, &wanted);
                fresh.text_quality =
                    crate::evidence::classify_text_quality(&fresh.pages, fresh.page_count).into();
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
                Err(e @ SelectionError::Usage(_)) => return Err(e),
                Err(e) => {
                    store.put_record(
                        "inspection_errors",
                        id,
                        &json!({"fingerprint":source.fingerprint,"error":format!("{}: {e}",source.relative_path.display()),"attempted_at":chrono::Utc::now().to_rfc3339()}),
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
        &json!({"inspected_sources":inspected,"reused_sources":reused,"reused_byte_samples":reused_byte_samples,"failed_sources":failed,"deferred_failures":deferred,"groups_remaining":remaining,"input_bytes_inspected":bytes,"page_limit_per_pdf":5,"model_calls":0}),
    )?;
    Ok(ExitCode::from(if failed > 0 { 1 } else { 0 }))
}

fn merge_sample_provenance(fresh: &mut Evidence, peers: &[&Evidence], wanted: &[u32]) {
    let mut batches = vec![];
    let mut reused_sources = BTreeSet::new();
    for evidence in std::iter::once(&*fresh).chain(peers.iter().copied()) {
        if !evidence.pages.iter().any(|p| wanted.contains(&p.page)) {
            continue;
        }
        if evidence.source_id != fresh.source_id {
            reused_sources.insert(evidence.source_id.clone());
        }
        let entries = evidence.pdf_metadata.get("_extraction_batches").and_then(|v| v.as_array()).cloned().unwrap_or_else(|| vec![json!({
            "pages":evidence.pages.iter().map(|p|p.page).collect::<Vec<_>>(),
            "extractor":evidence.pdf_metadata.get("_text_extractor").cloned().unwrap_or_else(||json!({"name":"unknown legacy extractor","version":null})),
            "warnings":evidence.errors,
        })]);
        for mut batch in entries {
            if let Some(pages) = batch.get_mut("pages").and_then(|v| v.as_array_mut()) {
                pages.retain(|p| p.as_u64().is_some_and(|n| wanted.contains(&(n as u32))));
                if pages.is_empty() {
                    continue;
                }
            }
            if !batches.contains(&batch) {
                batches.push(batch);
            }
        }
    }
    for peer in peers {
        if peer.pages.iter().any(|p| wanted.contains(&p.page)) {
            for warning in &peer.errors {
                if !fresh.errors.contains(warning) {
                    fresh.errors.push(warning.clone());
                }
            }
        }
    }
    if let Some(source) = reused_sources.first() {
        fresh
            .pdf_metadata
            .insert("_sample_reused_from_source".into(), json!(source));
        fresh
            .pdf_metadata
            .insert("_sample_reused_from_sources".into(), json!(reused_sources));
    }
    if batches.len() > 1 {
        fresh.pdf_metadata.insert(
            "_text_extractor".into(),
            json!({"mode":"multiple batches","details":"_extraction_batches"}),
        );
    }
    fresh
        .pdf_metadata
        .insert("_extraction_batches".into(), json!(batches));
}

fn sample_pages(count: u32) -> Vec<u32> {
    let mut pages: BTreeSet<_> = (1..=count.min(4)).collect();
    if count > 0 {
        pages.insert(count);
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
