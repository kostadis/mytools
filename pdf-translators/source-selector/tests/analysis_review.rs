mod analysis_support;
use analysis_support::*;
use rpg_source_select::analysis::{models::*, review};
#[test]
fn named_choices_have_exact_non_destructive_outcomes() {
    let (t, a) = audit_fixture();
    let m = review::export_cases(&a, &t.path().join("review")).unwrap();
    assert_eq!(m.items["reviewKind"], "decision");
    let card = &m.items["items"][0];
    assert_eq!(card["choiceOnly"], true);
    let id = card["id"].as_str().unwrap();
    for choice in card["picks"].as_array().unwrap() {
        let key = choice.as_str().unwrap();
        assert!(card["pickTexts"][key].is_string());
        assert!(m.scope_map[id]["picks"][key].is_object());
    }
    assert!(card["ev"].as_str().unwrap().contains("&lt;v3&gt;"));
    let defer = &m.scope_map[id]["picks"]["Defer; retain all candidates"];
    assert_eq!(defer["retain"].as_array().unwrap().len(), 2);
    assert_eq!(defer["omit"].as_array().unwrap().len(), 0);
}
#[test]
fn known_owner_ruling_is_not_an_undecided_card() {
    let (t, mut a) = audit_fixture();
    for f in &mut a.files {
        f.state = ProposalState::ExplicitlyRetained;
        f.ruling = Some("owner".into());
    }
    for r in &mut a.relationships {
        r.needs_review = false;
    }
    let m = review::export_cases(&a, &t.path().join("review")).unwrap();
    assert_eq!(m.items["items"].as_array().unwrap().len(), 0);
}
#[test]
fn changed_case_cannot_overwrite_frozen_bundle() {
    let (t, mut a) = audit_fixture();
    let out = t.path().join("review");
    let first = review::export_cases(&a, &out).unwrap();
    assert_eq!(
        first.review_id,
        review::export_cases(&a, &out).unwrap().review_id
    );
    a.relationships[0].evidence_digest = "changed".into();
    assert!(review::export_cases(&a, &out).is_err());
}
#[test]
#[ignore = "requires installed review-pages skill"]
fn installed_builder_accepts_export_and_paginates() {
    let (t, mut a) = audit_fixture();
    let g = a.relationships[0].clone();
    a.relationships = (0..101)
        .map(|i| {
            let mut g = g.clone();
            g.id = format!("g{i}");
            g
        })
        .collect();
    let out = t.path().join("review");
    review::export_cases(&a, &out).unwrap();
    let script = std::path::PathBuf::from(std::env::var("HOME").unwrap())
        .join(".codex/skills/review-pages/scripts/build_pages.py");
    let result = std::process::Command::new("python3")
        .arg(script)
        .arg("--items")
        .arg(out.join("review_items.json"))
        .arg("--map")
        .arg(out.join("review_map.json"))
        .arg("--out")
        .arg(t.path().join("bundle"))
        .args(["--page-size", "100"])
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let bundle: serde_json::Value =
        serde_json::from_slice(&std::fs::read(t.path().join("bundle/bundle.json")).unwrap())
            .unwrap();
    assert_eq!(bundle["pages"].as_array().unwrap().len(), 2);
    for page in bundle["pages"].as_array().unwrap() {
        assert!(page["items"].as_array().unwrap().len() <= 100);
    }
}
fn normalized(m: &ReviewManifest) -> serde_json::Value {
    serde_json::json!({"reviewId":m.review_id,"total":m.items["items"].as_array().unwrap().len(),"scope_map":m.scope_map,"decisions":{},"picks":{},"notes":{},"unmarked":m.items["items"].as_array().unwrap().iter().map(|c|c["id"].clone()).collect::<Vec<_>>(),"discuss":[],"provenance":[]})
}
#[test]
fn foreign_or_stale_picks_are_rejected() {
    let (t, a) = audit_fixture();
    let m = review::export_cases(&a, &t.path().join("review")).unwrap();
    let p = t.path().join("results.json");
    let mut n = normalized(&m);
    n["reviewId"] = serde_json::json!("foreign");
    write(&p, &n);
    assert!(load_bound(&m, &p).is_err());
    let mut n = normalized(&m);
    let id = m.items["items"][0]["id"].as_str().unwrap();
    n["scope_map"][id]["evidence_digest"] = serde_json::json!("stale");
    write(&p, &n);
    assert!(load_bound(&m, &p).is_err());
    let mut n = normalized(&m);
    n["decisions"][id] = serde_json::json!("approve");
    write(&p, &n);
    assert!(load_bound(&m, &p).is_err());
}
#[test]
fn discuss_unmarked_and_notes_preserve_uncertainty() {
    let (t, a) = audit_fixture();
    let m = review::export_cases(&a, &t.path().join("review")).unwrap();
    let p = t.path().join("results.json");
    let mut n = normalized(&m);
    let id = m.items["items"][0]["id"].as_str().unwrap();
    n["notes"][id] = serde_json::json!("  Need to inspect the maps.\n");
    write(&p, &n);
    let results = load_bound(&m, &p).unwrap();
    let next = rpg_source_select::analysis::audit::with_rulings(&a, &results).unwrap();
    assert_eq!(next.review_notes[id], "  Need to inspect the maps.\n");
    assert!(next.files.iter().all(|f| f.state.retained()));
    assert!(next.relationships[0].needs_review);
}
#[test]
fn named_ruling_applies_only_to_unchanged_analysis() {
    let (t, a) = audit_fixture();
    let m = review::export_cases(&a, &t.path().join("review")).unwrap();
    let p = t.path().join("results.json");
    let mut n = normalized(&m);
    let id = m.items["items"][0]["id"].as_str().unwrap();
    n["decisions"][id] = serde_json::json!("pick");
    n["picks"][id] = serde_json::json!("Keep all listed editions");
    n["unmarked"] = serde_json::json!([]);
    n["provenance"] = serde_json::json!([{"page":"page-001","reviewId":"fixture-page","savedAt":"fixture","decisions_sha256":"fixture","frozen_files":{}}]);
    write(&p, &n);
    let results = load_bound(&m, &p).unwrap();
    let next = rpg_source_select::analysis::audit::with_rulings(&a, &results).unwrap();
    assert!(next.files.iter().all(|f| f.ruling.is_some()));
    assert!(!next.relationships[0].needs_review);
    let mut changed = a.clone();
    changed.files[0].source.fingerprint.size += 1;
    let reopened = rpg_source_select::analysis::audit::with_rulings(&changed, &results).unwrap();
    assert_eq!(reopened.counts["review_rulings_stale"], 1);
    assert!(reopened.files.iter().all(|f| f.ruling.is_none()));
}
#[test]
fn saved_chronology_is_presented_as_historical_evidence() {
    let (t, mut a) = audit_fixture();
    a.relationships[0].historical = Some(HistoricalObservation {
        group_id: "g".into(),
        run_id: "old".into(),
        policy: "internal-recency-v1".into(),
        status: "ready".into(),
        reason: "date fallback".into(),
        selected: vec![],
        hashes: Default::default(),
        scorable: true,
        record: serde_json::json!({"candidates":[{"source":{"source_id":"a"},"page_count":5,"dates":{"effective":{"field":"pdf_info.CreationDate","utc":"2023-03-16"},"fields":{"pdf_info.CreationDate":"D:20230316"}}}]}),
    });
    let m = review::export_cases(&a, &t.path().join("review")).unwrap();
    assert!(
        m.items["items"][0]["ev"]
            .as_str()
            .unwrap()
            .contains("pdf_info.CreationDate")
    );
}
#[test]
fn large_groups_keep_all_candidates_without_exceeding_pick_limit() {
    let (t, mut a) = audit_fixture();
    let source = a.files[0].clone();
    a.files.clear();
    a.relationships[0].source_ids.clear();
    for i in 0..25 {
        let mut f = source.clone();
        f.source.source_id = format!("s{i}");
        f.source.relative_path = format!("large/file-{i}.pdf").into();
        a.relationships[0]
            .source_ids
            .push(f.source.source_id.clone());
        a.files.push(f);
    }
    let m = review::export_cases(&a, &t.path().join("review")).unwrap();
    let card = &m.items["items"][0];
    assert!(card["picks"].as_array().unwrap().len() <= 12);
    let id = card["id"].as_str().unwrap();
    assert_eq!(
        m.scope_map[id]["picks"]["Defer; retain all candidates"]["retain"]
            .as_array()
            .unwrap()
            .len(),
        25
    );
    assert!(card["ev"].as_str().unwrap().contains("focused review"));
}

fn load_bound(m: &ReviewManifest, p: &std::path::Path) -> rpg_source_select::Result<ReviewResults> {
    let bundle = bundle_fixture(p.parent().unwrap(), m, p);
    review::load_results(m, &bundle, p)
}
#[test]
fn altered_displayed_card_and_fake_provenance_cannot_authorize_pick() {
    let (t, a) = audit_fixture();
    let m = review::export_cases(&a, &t.path().join("review")).unwrap();
    let p = t.path().join("results.json");
    let mut n = normalized(&m);
    let id = m.items["items"][0]["id"].as_str().unwrap();
    n["decisions"][id] = serde_json::json!("pick");
    n["picks"][id] = serde_json::json!("Keep all listed editions");
    n["unmarked"] = serde_json::json!([]);
    write(&p, &n);
    let bundle = bundle_fixture(t.path(), &m, &p);
    let mut n: serde_json::Value = serde_json::from_slice(&std::fs::read(&p).unwrap()).unwrap();
    n["provenance"] = serde_json::json!([null]);
    write(&p, &n);
    assert!(review::load_results(&m, &bundle, &p).is_err());
    let mut changed = m.clone();
    changed.items["items"][0]["pickTexts"]["Keep all listed editions"] =
        serde_json::json!("Omit every source instead");
    write(&p, &normalized(&changed));
    let bundle = bundle_fixture(t.path(), &changed, &p);
    assert!(review::load_results(&m, &bundle, &p).is_err());
}
#[test]
fn contradictory_unmarked_and_keep_both_in_large_group_stay_unresolved() {
    let (t, a) = audit_fixture();
    let m = review::export_cases(&a, &t.path().join("review")).unwrap();
    let p = t.path().join("results.json");
    let mut n = normalized(&m);
    let id = m.items["items"][0]["id"].as_str().unwrap();
    n["decisions"][id] = serde_json::json!("pick");
    n["picks"][id] = serde_json::json!("Keep all listed editions");
    write(&p, &n);
    assert!(load_bound(&m, &p).is_err());
}
fn protected_three() -> (
    tempfile::TempDir,
    rpg_source_select::analysis::models::AuditResult,
) {
    let (t, mut a) = audit_fixture();
    let mut third = a.files[1].clone();
    third.source.source_id = "c".into();
    third.source.relative_path = "Publisher/Old-draft.pdf".into();
    a.relationships[0].source_ids.push("c".into());
    a.files.push(third);
    a.files[0].state = ProposalState::ExplicitlyRetained;
    a.files[0].ruling = Some("nulb-owner".into());
    a.protected.push(ProtectedEdition {
        rule: RetentionRule {
            id: "nulb-owner".into(),
            wording: "Keep Nulb".into(),
            provenance: "owner".into(),
            source_id: Some("a".into()),
            fingerprint: Some(a.files[0].source.fingerprint.clone()),
            action: "keep_and_convert".into(),
        },
        bound: true,
        warning: None,
    });
    (t, a)
}
fn choose(m: &ReviewManifest, p: &std::path::Path, label: &str) -> ReviewResults {
    let mut n = normalized(m);
    let id = m.items["items"][0]["id"].as_str().unwrap();
    n["decisions"][id] = serde_json::json!("pick");
    n["picks"][id] = serde_json::json!(label);
    n["unmarked"] = serde_json::json!([]);
    write(p, &n);
    load_bound(m, p).unwrap()
}
#[test]
fn defer_preserves_permanent_owner_rule_and_later_choices() {
    let (t, a) = protected_three();
    let m = review::export_cases(&a, &t.path().join("review")).unwrap();
    let r = choose(
        &m,
        &t.path().join("results.json"),
        "Defer; retain all candidates",
    );
    let next = rpg_source_select::analysis::audit::with_rulings(&a, &r).unwrap();
    assert_eq!(next.files[0].state, ProposalState::ExplicitlyRetained);
    assert_eq!(next.files[0].ruling.as_deref(), Some("nulb-owner"));
    assert!(next.files[1].ruling.is_none());
    assert_eq!(next.counts["review_cases_unresolved"], 1);
    let m = review::export_cases(&next, &t.path().join("review-next")).unwrap();
    assert!(
        m.items["items"][0]["picks"]
            .as_array()
            .unwrap()
            .iter()
            .any(|p| p.as_str().unwrap().starts_with("Select "))
    );
}
#[test]
fn superseded_draft_links_to_selected_edition_not_protected_extra() {
    let (t, a) = protected_three();
    let m = review::export_cases(&a, &t.path().join("review")).unwrap();
    let label = m.items["items"][0]["picks"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(serde_json::Value::as_str)
        .find(|p| p.contains("Book&new.pdf"))
        .unwrap();
    let r = choose(&m, &t.path().join("results.json"), label);
    let next = rpg_source_select::analysis::audit::with_rulings(&a, &r).unwrap();
    assert_eq!(next.files[2].representative.as_deref(), Some("b"));
}
#[test]
fn unchanged_case_migrates_while_changed_case_and_notes_remain() {
    let (t, mut a) = audit_fixture();
    let mut g = a.relationships[0].clone();
    g.id = "other".into();
    g.source_ids = vec!["c".into(), "d".into()];
    g.product_folder = "Other".into();
    g.evidence_digest = "other".into();
    a.relationships.push(g);
    for id in ["c", "d"] {
        let mut f = a.files[0].clone();
        f.source.source_id = id.into();
        f.source.relative_path = format!("Other/{id}.pdf").into();
        a.files.push(f);
    }
    let m = review::export_cases(&a, &t.path().join("review")).unwrap();
    let mut n = normalized(&m);
    for card in m.items["items"].as_array().unwrap() {
        let id = card["id"].as_str().unwrap();
        n["decisions"][id] = serde_json::json!("pick");
        n["picks"][id] = serde_json::json!("Keep all listed editions");
    }
    let other = m
        .scope_map
        .as_object()
        .unwrap()
        .iter()
        .find(|(_, s)| s["relationship_id"] == "other")
        .unwrap()
        .0
        .clone();
    n["notes"][&other] = serde_json::json!("Keep all");
    n["unmarked"] = serde_json::json!([]);
    let p = t.path().join("results.json");
    write(&p, &n);
    let r = load_bound(&m, &p).unwrap();
    let mut changed = a.clone();
    changed.input_receipt = "unrelated new snapshot".into();
    changed.files[2].source.fingerprint.size += 1;
    changed.relationships[1].evidence_digest = "changed".into();
    let next = rpg_source_select::analysis::audit::with_rulings(&changed, &r).unwrap();
    assert!(next.files[0].ruling.is_some());
    assert!(next.files[2].ruling.is_none());
    assert_eq!(next.review_notes[&other], "Keep all");
    assert_eq!(next.counts["review_rulings_stale"], 1);
    assert_eq!(next.review_migrations.len(), 2);
}
#[test]
fn keep_both_note_is_ambiguous_for_three_candidates() {
    let (t, a) = protected_three();
    let m = review::export_cases(&a, &t.path().join("review")).unwrap();
    let mut n = normalized(&m);
    let id = m.items["items"][0]["id"].as_str().unwrap();
    n["notes"][id] = serde_json::json!("keep both");
    let p = t.path().join("results.json");
    write(&p, &n);
    let r = load_bound(&m, &p).unwrap();
    assert!(r.picks.is_empty());
    assert_eq!(r.notes[id], "keep both");
    assert!(r.unresolved.contains(&id.to_owned()));
}
#[test]
fn defer_scope_explicitly_preserves_existing_file_dispositions() {
    let (t, a) = audit_fixture();
    let m = review::export_cases(&a, &t.path().join("review")).unwrap();
    let id = m.items["items"][0]["id"].as_str().unwrap();
    assert_eq!(
        m.scope_map[id]["picks"]["Defer; retain all candidates"]["preserve_dispositions"],
        true
    );
}
