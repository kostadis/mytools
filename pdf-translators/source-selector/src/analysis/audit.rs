use super::{inputs::path_key, models::*};
use crate::{Result, digest_json};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
pub fn compare(
    inputs: &FrozenInputs,
    history: &HistoricalView,
    rules: &[RetentionRule],
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
    let mut hashes = BTreeMap::new();
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
    let mut reference = vec![];
    for row in &inputs.reference {
        let confirmed = !matches!(
            row.method,
            EvidenceMethod::PartialReference | EvidenceMethod::Unconfirmed
        );
        let mut matches = BTreeMap::new();
        if confirmed {
            for (path, method) in row.g_path.iter().map(|p| (p, row.method.clone())).chain(
                row.other_paths
                    .iter()
                    .map(|p| (p, EvidenceMethod::UnspecifiedOtherCopy)),
            ) {
                if let Some(index) = by_path.get(path) {
                    let sid = files[*index].source.source_id.clone();
                    let mut ids = vec![sid.clone()];
                    if let Some(hash) = hashes.get(&sid) {
                        ids.extend(aliases[hash].clone());
                    }
                    for id in ids {
                        matches.entry(id).or_insert(method.clone());
                    }
                }
            }
        }
        let mut gids = BTreeSet::new();
        for (id, method) in &matches {
            let f = &mut files[by_id[id]];
            f.reference_rows.push(row.row);
            f.evidence.push(PairEvidence {
                old_source_id: id.clone(),
                reference_row: row.row,
                method: method.clone(),
                scope: match method {
                    EvidenceMethod::ExactBytes => "full file",
                    EvidenceMethod::AllRenderedPages => "all pages, visual only",
                    EvidenceMethod::UnspecifiedOtherCopy => {
                        "reported alternate match; per-copy method unspecified"
                    }
                    _ => "sampled portions only",
                }
                .into(),
                provenance: format!("CSV row {} from {}", row.row, inputs.receipt_id),
                raw_evidence: row.raw.get("Evidence").cloned().unwrap_or_default(),
            });
            for g in &inputs.groups {
                if g.source_ids.contains(id) {
                    gids.insert(g.group_id.clone());
                }
            }
        }
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
        } else if !selected_support_methods.is_empty() {
            "reference_supported_selection"
        } else if observed.is_empty() {
            "group_not_processed"
        } else if observed.iter().any(|h| !h.scorable) {
            "unsupported_historical_policy"
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
    let mut relationships = vec![];
    let mut covered = BTreeSet::new();
    for group in &inputs.groups {
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
    warnings.sort();
    warnings.dedup();
    Ok(AuditResult {
        schema_version: 1,
        input_receipt: inputs.receipt_id.clone(),
        provisional: !inputs.config.reference_complete,
        files,
        reference,
        relationships,
        protected,
        warnings,
        counts,
        review_notes: BTreeMap::new(),
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
    let flagged = historical.as_ref().is_some_and(|h| {
        !h.selected.is_empty()
            && h.selected.iter().all(|s| {
                candidates
                    .iter()
                    .filter(|f| !f.reference_rows.is_empty())
                    .all(|f| f.source.source_id != s.source_id)
            })
    });
    let evidence_digest = digest_json(&(id, &candidates, &historical));
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
    if results.manifest.audit_digest != digest_json(audit) {
        return Err(super::invalid(
            "audit changed since review; rebind affected cases in a new bundle",
        ));
    }
    let mut next = audit.clone();
    next.review_notes.extend(results.notes.clone());
    let mut applied: BTreeMap<String, (bool, String, String)> = BTreeMap::new();
    for (case, pick) in &results.picks {
        let scope = &results.manifest.scope_map[case];
        let relation = scope["relationship_id"]
            .as_str()
            .ok_or_else(|| super::invalid("review scope missing relationship"))?;
        let current = next
            .relationships
            .iter()
            .find(|g| g.id == relation)
            .ok_or_else(|| super::invalid("relationship removed since review"))?;
        if scope["evidence_digest"].as_str() != Some(&current.evidence_digest) {
            return Err(super::invalid("relationship evidence changed since review"));
        }
        let action = &scope["picks"][pick];
        let class = action["classification"]
            .as_str()
            .ok_or_else(|| super::invalid("missing named action"))?
            .to_owned();
        for (key, retain) in [("retain", true), ("omit", false)] {
            for id in action[key]
                .as_array()
                .ok_or_else(|| super::invalid("missing exact outcome list"))?
            {
                let id = id
                    .as_str()
                    .ok_or_else(|| super::invalid("invalid source ID in action"))?;
                if !current.source_ids.iter().any(|s| s == id) {
                    return Err(super::invalid("action outside relationship scope"));
                }
                if applied
                    .get(id)
                    .is_some_and(|(previous, _, _)| *previous != retain)
                {
                    return Err(super::invalid(
                        "conflicting rulings for overlapping candidate groups",
                    ));
                }
                applied.insert(id.into(), (retain, case.clone(), class.clone()));
            }
        }
        let g = next
            .relationships
            .iter_mut()
            .find(|g| g.id == relation)
            .unwrap();
        g.classification = class.clone();
        g.needs_review = class == "unresolved";
    }
    for f in &mut next.files {
        if let Some((retain, case, class)) = applied.get(&f.source.source_id) {
            if !retain
                && (f.state == ProposalState::ExplicitlyRetained
                    || audit
                        .protected
                        .iter()
                        .any(|p| p.bound && p.rule.source_id.as_ref() == Some(&f.source.source_id)))
            {
                return Err(super::invalid(
                    "ruling conflicts with explicit owner retention",
                ));
            }
            if *retain {
                f.state = if f.source.read_error.is_some() {
                    ProposalState::UnreadableRetained
                } else if class == "unresolved" {
                    ProposalState::UnresolvedRetained
                } else {
                    ProposalState::ExplicitlyRetained
                };
                f.representative = None;
            } else {
                let scope = &results.manifest.scope_map[case];
                let pick = &results.picks[case];
                let retain = scope["picks"][pick]["retain"].as_array().unwrap();
                let representative = retain
                    .iter()
                    .filter_map(Value::as_str)
                    .find(|id| next_source_readable(audit, id))
                    .ok_or_else(|| {
                        super::invalid("exclusion has no readable retained successor")
                    })?;
                f.state = ProposalState::Superseded;
                f.representative = Some(representative.into());
            }
            f.ruling = Some(case.clone());
            f.reason =
                format!("Owner Clef choice: {class}; exact scope recorded in review results");
        }
    }
    // A retained representative may not itself be omitted by a different group ruling.
    for f in &next.files {
        if let Some(rep) = &f.representative {
            if !next
                .files
                .iter()
                .any(|p| &p.source.source_id == rep && p.state.retained())
            {
                return Err(super::invalid(
                    "excluded source has no retained representative",
                ));
            }
        }
    }
    next.counts
        .insert("review_rulings_applied".into(), results.picks.len());
    next.counts
        .insert("review_cases_unresolved".into(), results.unresolved.len());
    Ok(next)
}
fn next_source_readable(audit: &AuditResult, id: &str) -> bool {
    audit
        .files
        .iter()
        .any(|f| f.source.source_id == id && f.source.read_error.is_none())
}
