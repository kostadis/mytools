use super::{inputs::path_key, models::*};
use crate::{Result, digest_json};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
pub fn compare(
    inputs: &FrozenInputs,
    history: &HistoricalView,
    rules: &[RetentionRule],
) -> Result<AuditResult> {
    compare_with_progress(inputs, history, rules, |_, _, _| Ok(()))
}
pub fn compare_with_progress(
    inputs: &FrozenInputs,
    history: &HistoricalView,
    rules: &[RetentionRule],
    mut progress: impl FnMut(&str, usize, usize) -> Result<()>,
) -> Result<AuditResult> {
    let mut files: Vec<FileCoverage> = inputs
        .old_sources
        .iter()
        .cloned()
        .map(|s| FileCoverage {
            state: if s.read_error.is_some() {
                ProposalState::UnreadableRetained
            } else {
                ProposalState::UnresolvedRetained
            },
            source: s,
            reference_rows: vec![],
            reported_reference_rows: vec![],
            evidence: vec![],
            reason: "relationship unresolved; retained to avoid losing owned content".into(),
            representative: None,
            ruling: None,
        })
        .collect();
    let by_id: BTreeMap<_, _> = files
        .iter()
        .enumerate()
        .map(|(i, f)| (f.source.source_id.clone(), i))
        .collect();
    let by_path: BTreeMap<_, _> = files
        .iter()
        .enumerate()
        .map(|(i, f)| (path_key(&f.source.relative_path.to_string_lossy()), i))
        .collect();
    let mut warnings = history.warnings.clone();
    let mut protected = vec![];
    for rule in rules {
        let bound = rule.action == "keep_and_convert"
            && rule
                .source_id
                .as_ref()
                .and_then(|id| by_id.get(id))
                .is_some_and(|i| rule.fingerprint.as_ref() == Some(&files[*i].source.fingerprint));
        if bound {
            let f = &mut files[by_id[rule.source_id.as_ref().unwrap()]];
            if f.source.read_error.is_none() {
                f.state = ProposalState::ExplicitlyRetained;
            }
            f.reason = rule.wording.clone();
            f.ruling = Some(rule.id.clone());
        }
        protected.push(ProtectedEdition {
            rule: rule.clone(),
            bound,
            warning: if bound {
                None
            } else {
                Some("Owner policy preserved; actual source binding needs verification".into())
            },
        });
    }
    let mut hashes = history.verified_hashes.clone();
    for h in history.groups.values() {
        for (s, hash) in &h.hashes {
            if hash.len() == 64 && hash.bytes().all(|b| b.is_ascii_hexdigit()) {
                if let Some(previous) = hashes.insert(s.clone(), hash.clone()) {
                    if previous != *hash {
                        return Err(super::invalid("conflicting verified hashes for one source"));
                    }
                }
            }
        }
    }
    for f in &files {
        if let Some(hash) = &f.source.fingerprint.sha256 {
            if hash.len() == 64 && hash.bytes().all(|b| b.is_ascii_hexdigit()) {
                hashes
                    .entry(f.source.source_id.clone())
                    .or_insert(hash.clone());
            }
        }
    }
    let mut aliases: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for (s, h) in &hashes {
        aliases.entry(h.clone()).or_default().push(s.clone());
    }
    let reference_by_path = inputs
        .reference
        .iter()
        .map(|r| (r.d_path.clone(), r))
        .collect::<BTreeMap<_, _>>();
    let current_files=inputs.current_sources.iter().map(|source|{let path=path_key(&source.relative_path.to_string_lossy());let row=reference_by_path.get(&path);let bytes=row.and_then(|r|r.raw.get("D bytes")).and_then(|v|v.replace(',',"").parse::<u64>().ok());let size_agreement=bytes.map(|n|n==source.fingerprint.size);let archive=source.relative_path.components().any(|c|c.as_os_str().to_string_lossy().ends_with(".extracted"));CurrentCoverage{source:source.clone(),scope:if row.is_some(){"original_reference"}else if archive{"archive_expanded_path"}else{"current_only"}.into(),reference_rows:row.map(|r|vec![r.row]).unwrap_or_default(),size_agreement,provenance:if archive{"Archive scope inferred from extractor .extracted directory layout; receipt not independently reread"}else{"Current inventory relative path and available CSV D byte size"}.into()}}).collect::<Vec<_>>();
    let mut reference = vec![];
    for (row_index, row) in inputs.reference.iter().enumerate() {
        progress("reference", row_index, inputs.reference.len())?;
        let confirmed = !matches!(
            row.method,
            EvidenceMethod::PartialReference | EvidenceMethod::Unconfirmed
        );
        let mut matches = BTreeMap::new();
        let mut associations = BTreeMap::new();
        for (path, method) in row.g_path.iter().map(|p| (p, row.method.clone())).chain(
            row.other_paths
                .iter()
                .map(|p| (p, EvidenceMethod::UnspecifiedOtherCopy)),
        ) {
            if let Some(index) = by_path.get(path) {
                let sid = files[*index].source.source_id.clone();
                let mut ids = vec![sid.clone()];
                if confirmed {
                    if let Some(hash) = hashes.get(&sid) {
                        ids.extend(aliases[hash].clone());
                    }
                }
                for id in ids {
                    associations.entry(id.clone()).or_insert(method.clone());
                    if confirmed {
                        matches.entry(id).or_insert(method.clone());
                    }
                }
            }
        }
        let mut gids = BTreeSet::new();
        for (id, method) in &associations {
            let f = &mut files[by_id[id]];
            f.reported_reference_rows.push(row.row);
            if confirmed && *method != EvidenceMethod::UnspecifiedOtherCopy {
                f.reference_rows.push(row.row);
            }
            f.evidence.push(PairEvidence {
                old_source_id: id.clone(),
                reference_row: row.row,
                reference_path: row.d_path.clone(),
                method: method.clone(),
                scope: match method {
                    EvidenceMethod::ExactBytes => "full file",
                    EvidenceMethod::AllRenderedPages => "all pages, visual only",
                    EvidenceMethod::UnspecifiedOtherCopy => {
                        "reported alternate match; per-copy method unspecified"
                    }
                    EvidenceMethod::PartialReference => {
                        "readable portions only; incomplete reference"
                    }
                    EvidenceMethod::Unconfirmed => "candidate path only; method unconfirmed",
                    _ => "sampled portions only",
                }
                .into(),
                provenance: format!("CSV raw-row SHA-256 {}", digest_json(&row.raw)),
                raw_evidence: row.raw.get("Evidence").cloned().unwrap_or_default(),
            });
            if confirmed {
                for g in &inputs.groups {
                    if g.source_ids.contains(id) {
                        gids.insert(g.group_id.clone());
                    }
                }
            }
        }
        let current_matches = current_files
            .iter()
            .filter(|f| f.reference_rows.contains(&row.row))
            .collect::<Vec<_>>();
        let observed = gids
            .iter()
            .filter_map(|g| history.groups.get(g))
            .collect::<Vec<_>>();
        let selected = observed
            .iter()
            .filter(|h| h.scorable)
            .flat_map(|h| h.selected.iter())
            .collect::<Vec<_>>();
        let selected_support_methods = selected
            .iter()
            .filter_map(|s| matches.get(&s.source_id).cloned())
            .collect::<Vec<_>>();
        let outcome = if !confirmed || matches.is_empty() {
            "reference_not_confirmed"
        } else if current_matches.is_empty() {
            "reference_missing_from_current_inventory"
        } else if current_matches
            .iter()
            .any(|f| f.size_agreement == Some(false))
        {
            "current_inventory_size_mismatch"
        } else if !observed.is_empty()
            && observed
                .iter()
                .all(|h| matches.keys().all(|id| !historical_contains(h, id)))
        {
            "group_not_processed"
        } else if !selected_support_methods.is_empty()
            && selected_support_methods
                .iter()
                .all(|m| *m == EvidenceMethod::UnspecifiedOtherCopy)
        {
            "reported_alternate_selection_unverified"
        } else if !selected_support_methods.is_empty() {
            "reference_supported_selection"
        } else if observed.is_empty() {
            "group_not_processed"
        } else if observed.iter().any(|h| !h.scorable) {
            if observed.iter().any(|h| h.policy != "internal-recency-v1") {
                "unsupported_historical_policy"
            } else {
                "historical_source_unverified"
            }
        } else if selected.is_empty() {
            if observed.iter().any(|h| {
                h.reason.contains("baseline")
                    || h.status.contains("baseline")
                    || h.reason.contains("existing")
            }) {
                "baseline_or_existing_work_deferred"
            } else {
                "policy_deferred"
            }
        } else {
            // A different retained current variant is not necessarily a wrong edition.
            let current_paths = inputs
                .reference
                .iter()
                .filter(|r| {
                    !matches!(
                        r.method,
                        EvidenceMethod::PartialReference | EvidenceMethod::Unconfirmed
                    )
                })
                .flat_map(|r| r.g_path.iter().chain(r.other_paths.iter()))
                .collect::<BTreeSet<_>>();
            if selected
                .iter()
                .any(|s| current_paths.contains(&path_key(&s.relative_path)))
            {
                "different_current_variant_selected"
            } else {
                "selected_candidate_not_confirmed_by_reference"
            }
        };
        reference.push(ReferenceOutcome {
            row: row.row,
            d_path: row.d_path.clone(),
            method: row.method.clone(),
            matched_sources: matches.into_keys().collect(),
            reported_sources: associations.into_keys().collect(),
            current_source_ids: current_matches
                .iter()
                .map(|f| f.source.source_id.clone())
                .collect(),
            groups: gids.into_iter().collect(),
            outcome: outcome.into(),
            selected_support_methods,
        });
    }
    // Collapse only freshly verified byte identities; preserve explicit retention instructions.
    for copies in aliases.values() {
        let mut copies = copies
            .iter()
            .filter_map(|s| by_id.get(s).copied())
            .collect::<Vec<_>>();
        copies.sort_by_key(|i| {
            (
                files[*i].state != ProposalState::ExplicitlyRetained,
                files[*i].reference_rows.is_empty(),
                path_key(&files[*i].source.relative_path.to_string_lossy()),
            )
        });
        if let Some(rep) = copies.first().copied() {
            let representative = files[rep].source.source_id.clone();
            for i in copies.into_iter().skip(1) {
                if files[i].ruling.is_none() && files[rep].source.read_error.is_none() {
                    files[i].state = ProposalState::Duplicate;
                    files[i].representative = Some(representative.clone());
                    files[i].reason =
                        "verified full-file hash equality; representative retained".into();
                }
            }
        }
    }
    progress("reference", inputs.reference.len(), inputs.reference.len())?;
    let mut relationships = vec![];
    let mut covered = BTreeSet::new();
    for (group_index, group) in inputs.groups.iter().enumerate() {
        progress("relationships", group_index, inputs.groups.len())?;
        let ids = group
            .source_ids
            .iter()
            .filter(|id| by_id.contains_key(*id))
            .cloned()
            .collect::<Vec<_>>();
        if ids.is_empty() {
            continue;
        }
        covered.extend(ids.clone());
        relationships.push(make_relationship(
            &group.group_id,
            ids,
            &files,
            &by_id,
            history,
        ));
    }
    progress("relationships", inputs.groups.len(), inputs.groups.len())?;
    for f in &files {
        if !covered.contains(&f.source.source_id) {
            relationships.push(make_relationship(
                &format!("ungrouped-{}", f.source.source_id),
                vec![f.source.source_id.clone()],
                &files,
                &by_id,
                history,
            ));
        }
    }
    for relation in &relationships {
        if !relation.needs_review {
            for id in &relation.source_ids {
                let f = &mut files[by_id[id]];
                if f.state == ProposalState::UnresolvedRetained {
                    f.state = ProposalState::Selected;
                    f.reason = "sole distinct source in an accounted relationship".into();
                }
            }
        }
    }
    if inputs.current_sources.len() != inputs.reference.len() {
        warnings.push(format!("Current inventory contains {} PDFs; CSV contains {} original reference PDF rows. Archive expansion/unmatched coverage is reported separately.",inputs.current_sources.len(),inputs.reference.len()));
    }
    let mut counts = BTreeMap::from([
        ("old_pdf_files".into(), files.len()),
        ("reference_pdf_rows".into(), reference.len()),
        (
            "current_inventory_pdf_files".into(),
            inputs.current_sources.len(),
        ),
        ("candidate_relationships".into(), relationships.len()),
        (
            "historical_unprocessed_groups".into(),
            history.unprocessed_groups.len(),
        ),
    ]);
    for r in &reference {
        *counts.entry(r.outcome.clone()).or_default() += 1;
    }
    counts.insert(
        "old_only_or_unconfirmed_files".into(),
        files.iter().filter(|f| f.reference_rows.is_empty()).count(),
    );
    counts.insert(
        "protected_bound".into(),
        protected.iter().filter(|r| r.bound).count(),
    );
    let covered_rows = current_files
        .iter()
        .flat_map(|f| f.reference_rows.iter())
        .collect::<BTreeSet<_>>();
    counts.insert(
        "csv_paths_missing_current_inventory".into(),
        inputs
            .reference
            .iter()
            .filter(|r| !covered_rows.contains(&r.row))
            .count(),
    );
    for scope in [
        "original_reference",
        "archive_expanded_path",
        "current_only",
    ] {
        counts.insert(
            format!("current_{scope}_files"),
            current_files.iter().filter(|f| f.scope == scope).count(),
        );
    }
    counts.insert(
        "current_reference_size_mismatches".into(),
        current_files
            .iter()
            .filter(|f| f.size_agreement == Some(false))
            .count(),
    );
    warnings.sort();
    warnings.dedup();
    Ok(AuditResult {
        policy_version: super::POLICY_VERSION.into(),
        schema_version: 1,
        input_receipt: inputs.receipt_id.clone(),
        provisional: !inputs.config.reference_complete,
        files,
        current_files,
        review_migrations: vec![],
        reference,
        relationships,
        protected,
        warnings,
        counts,
        review_notes: BTreeMap::new(),
        supplemental_evidence: vec![],
    })
}
fn make_relationship(
    id: &str,
    ids: Vec<String>,
    files: &[FileCoverage],
    by_id: &BTreeMap<String, usize>,
    history: &HistoricalView,
) -> Relationship {
    let candidates = ids.iter().map(|id| &files[by_id[id]]).collect::<Vec<_>>();
    let rows = candidates
        .iter()
        .flat_map(|f| f.reference_rows.iter().copied())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    let retained = candidates.iter().filter(|f| f.state.retained()).count();
    let needs_review = (retained > 1 || rows.is_empty())
        && candidates
            .iter()
            .any(|f| f.ruling.is_none() && f.state == ProposalState::UnresolvedRetained);
    let historical = history.groups.get(id).cloned();
    let flagged = !rows.is_empty()
        && historical.as_ref().is_some_and(|h| {
            h.scorable
                && candidates.iter().any(|f| {
                    !f.reference_rows.is_empty() && historical_contains(h, &f.source.source_id)
                })
                && !h.selected.is_empty()
                && h.selected.iter().all(|s| {
                    candidates
                        .iter()
                        .filter(|f| !f.reference_rows.is_empty())
                        .all(|f| f.source.source_id != s.source_id)
                })
        });
    let stable=candidates.iter().map(|f|serde_json::json!({"source":f.source,"state":f.state,"reason":f.reason,"ruling":f.ruling,"representative":f.representative,"pairs":f.evidence.iter().map(stable_pair).collect::<Vec<_>>()})).collect::<Vec<_>>();
    let evidence_digest = digest_json(&(id, stable, &historical));
    Relationship {
        id: id.into(),
        source_ids: ids,
        reference_rows: rows.clone(),
        publisher: candidates[0].source.publisher.clone(),
        product_folder: candidates[0].source.product_folder.clone(),
        historical,
        needs_review,
        flagged,
        evidence_digest,
        reason: if rows.is_empty() {
            "Absent or unconfirmed in current reference; absence does not establish supersession"
        } else {
            "Establish whether variants are drafts, companions, or independently useful editions"
        }
        .into(),
        classification: if needs_review {
            "unresolved"
        } else {
            "accounted"
        }
        .into(),
    }
}
pub fn with_rulings(audit: &AuditResult, results: &ReviewResults) -> Result<AuditResult> {
    super::review::verify_manifest(&results.manifest)?;
    let current = super::review::prepare_cases(audit)?;
    let current_cards = current.items["items"]
        .as_array()
        .unwrap()
        .iter()
        .map(|c| (c["id"].as_str().unwrap(), c))
        .collect::<BTreeMap<_, _>>();
    let old_cards = results.manifest.items["items"]
        .as_array()
        .unwrap()
        .iter()
        .map(|c| (c["id"].as_str().unwrap(), c))
        .collect::<BTreeMap<_, _>>();
    let unchanged = |id: &str| {
        current.scope_map.get(id) == results.manifest.scope_map.get(id)
            && current_cards.get(id) == old_cards.get(id)
            && current.scope_map.get(id).is_some()
    };
    let mut next = audit.clone();
    next.review_notes.extend(results.notes.clone());
    let mut applied: BTreeMap<String, (bool, String, String, Option<String>)> = BTreeMap::new();
    let mut stale = 0;
    let mut deferred = 0;
    let mut reused = 0;
    for (case, pick) in &results.picks {
        let old_scope = results
            .manifest
            .scope_map
            .get(case)
            .ok_or_else(|| super::invalid("pick outside original scope"))?;
        if !unchanged(case) {
            stale += 1;
            next.review_migrations.push(serde_json::json!({"source_review":results.manifest.review_id,"target_review":current.review_id,"source_case":case,"relationship_id":old_scope["relationship_id"],"status":"stale","pick":pick,"note":results.notes.get(case),"old_scope":old_scope}));
            continue;
        }
        let scope = &current.scope_map[case];
        let relation = scope["relationship_id"]
            .as_str()
            .ok_or_else(|| super::invalid("missing relationship"))?;
        let action = &scope["picks"][pick];
        let class = action["classification"]
            .as_str()
            .ok_or_else(|| super::invalid("invalid named outcome"))?
            .to_owned();
        let g = next
            .relationships
            .iter_mut()
            .find(|g| g.id == relation)
            .ok_or_else(|| super::invalid("unknown relationship"))?;
        next.review_migrations.push(serde_json::json!({"source_review":results.manifest.review_id,"target_review":current.review_id,"source_case":case,"target_case":case,"relationship_id":relation,"status":if class=="unresolved"{"deferred"}else{"applied"},"pick":pick,"note":results.notes.get(case),"card_sha256":digest_json(old_cards[case.as_str()]),"scope_sha256":digest_json(scope)}));
        if class == "unresolved" {
            if action["preserve_dispositions"] != true {
                return Err(super::invalid("defer lacks explicit preservation scope"));
            }
            deferred += 1;
            g.classification = "unresolved".into();
            g.needs_review = true;
            continue;
        }
        reused += 1;
        g.classification = class.clone();
        g.needs_review = false;
        let successor = action["successor"].as_str().map(str::to_owned);
        if !action["omit"]
            .as_array()
            .ok_or_else(|| super::invalid("missing omissions"))?
            .is_empty()
        {
            let selected = successor
                .as_deref()
                .ok_or_else(|| super::invalid("omission lacks explicit selected successor"))?;
            if !action["retain"]
                .as_array()
                .unwrap()
                .iter()
                .any(|id| id.as_str() == Some(selected))
                || !next
                    .files
                    .iter()
                    .any(|f| f.source.source_id == selected && f.source.read_error.is_none())
            {
                return Err(super::invalid(
                    "selected successor is not a readable retained source",
                ));
            }
        }
        for (key, retain) in [("retain", true), ("omit", false)] {
            for id in action[key]
                .as_array()
                .ok_or_else(|| super::invalid("missing action sources"))?
            {
                let id = id
                    .as_str()
                    .ok_or_else(|| super::invalid("source ID must be text"))?;
                if !g.source_ids.iter().any(|s| s == id) {
                    return Err(super::invalid("action outside source scope"));
                }
                if applied
                    .get(id)
                    .is_some_and(|(previous, _, _, _)| *previous != retain)
                {
                    return Err(super::invalid("conflicting rulings for overlapping groups"));
                }
                applied.insert(
                    id.into(),
                    (retain, case.clone(), class.clone(), successor.clone()),
                );
            }
        }
    }
    for (case, note) in &results.notes {
        if !results.picks.contains_key(case) {
            next.review_migrations.push(serde_json::json!({"source_review":results.manifest.review_id,"target_review":current.review_id,"source_case":case,"relationship_id":results.manifest.scope_map[case]["relationship_id"],"status":if unchanged(case){"note_pending"}else{"stale_note"},"note":note,"old_scope":results.manifest.scope_map[case]}));
        }
    }
    for f in &mut next.files {
        if let Some((retain, case, class, successor)) = applied.get(&f.source.source_id) {
            let protected = audit
                .protected
                .iter()
                .any(|p| p.bound && p.rule.source_id.as_ref() == Some(&f.source.source_id));
            if protected {
                if !retain {
                    return Err(super::invalid(
                        "choice contradicts permanent owner retention",
                    ));
                }
                continue;
            }
            if *retain {
                f.state = if f.source.read_error.is_some() {
                    ProposalState::UnreadableRetained
                } else {
                    ProposalState::ExplicitlyRetained
                };
                f.representative = None;
            } else {
                f.state = ProposalState::Superseded;
                f.representative = successor.clone();
            }
            f.ruling = Some(case.clone());
            f.reason = format!("Owner Clef choice: {class}; exact scope saved in review results");
        }
    }
    for f in &next.files {
        if let Some(rep) = &f.representative {
            if !next
                .files
                .iter()
                .any(|p| &p.source.source_id == rep && p.state.retained())
            {
                return Err(super::invalid("exclusion lacks retained representative"));
            }
        }
    }
    next.counts.insert("review_rulings_applied".into(), reused);
    next.counts.insert("review_rulings_stale".into(), stale);
    next.counts.insert("review_cases_deferred".into(), deferred);
    next.counts.insert(
        "review_cases_unresolved".into(),
        next.relationships.iter().filter(|g| g.needs_review).count(),
    );
    Ok(next)
}
pub fn stable_pair(pair: &PairEvidence) -> Value {
    serde_json::json!({"source_id":pair.old_source_id,"reference_path":pair.reference_path,"method":pair.method,"scope":pair.scope,"provenance":pair.provenance,"raw_evidence":pair.raw_evidence})
}
fn historical_contains(h: &HistoricalObservation, id: &str) -> bool {
    h.selected.iter().any(|s| s.source_id == id)
        || h.record["candidates"]
            .as_array()
            .into_iter()
            .flatten()
            .any(|c| c["source"]["source_id"].as_str() == Some(id))
}
