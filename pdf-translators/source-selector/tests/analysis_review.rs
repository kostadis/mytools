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
    assert!(review::load_results(&m, &p).is_err());
    let mut n = normalized(&m);
    let id = m.items["items"][0]["id"].as_str().unwrap();
    n["scope_map"][id]["evidence_digest"] = serde_json::json!("stale");
    write(&p, &n);
    assert!(review::load_results(&m, &p).is_err());
    let mut n = normalized(&m);
    n["decisions"][id] = serde_json::json!("approve");
    write(&p, &n);
    assert!(review::load_results(&m, &p).is_err());
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
    let results = review::load_results(&m, &p).unwrap();
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
    let results = review::load_results(&m, &p).unwrap();
    let next = rpg_source_select::analysis::audit::with_rulings(&a, &results).unwrap();
    assert!(next.files.iter().all(|f| f.ruling.is_some()));
    assert!(!next.relationships[0].needs_review);
    let mut changed = a.clone();
    changed.files[0].source.fingerprint.size += 1;
    assert!(rpg_source_select::analysis::audit::with_rulings(&changed, &results).is_err());
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
