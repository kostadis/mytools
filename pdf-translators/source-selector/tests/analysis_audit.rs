mod analysis_support;
use analysis_support::*;
use rpg_source_select::analysis::{audit, inputs::freeze, models::*, sampling};
use serde_json::json;
fn fixture() -> (tempfile::TempDir, FrozenInputs, HistoricalView) {
    let t = tempfile::tempdir().unwrap();
    let c = setup(t.path());
    for (id, path) in [
        ("a", "Publisher/Nulb/Nulb_v3.pdf"),
        ("b", "Publisher/Nulb/Replacement.pdf"),
        ("c", "Other/Withdrawn.pdf"),
    ] {
        insert_source(&t.path().join("old.db"), source(id, path));
    }
    record(
        &t.path().join("old.db"),
        "groups",
        "g",
        json!({"group_id":"g","source_ids":["a","b"],"membership_digest":"m","reasons":[]}),
    );
    std::fs::write(t.path().join("matches.csv"),"D file,G file,Status,Evidence,Other matching G files\nD:/Download/Replacement.pdf,G:/Library/Publisher/Nulb/Replacement.pdf,Sampled byte match,samples,\n").unwrap();
    let f = freeze(&serde_json::from_value(c).unwrap(), &t.path().join("run")).unwrap();
    let h = HistoricalView {
        groups: Default::default(),
        unprocessed_groups: vec!["g".into()],
        warnings: vec![],
    };
    (t, f, h)
}
#[test]
fn old_only_sources_reconcile_to_inventory() {
    let (_t, f, h) = fixture();
    let a = audit::compare(&f, &h, &[]).unwrap();
    assert_eq!(a.files.len(), 3);
    assert_eq!(
        a.files
            .iter()
            .filter(|x| x.reference_rows.is_empty())
            .count(),
        2
    );
    assert!(a.files.iter().all(|x| x.state.eligible()));
}
#[test]
fn nulb_keep_overrides_replacement_without_reasking() {
    let (_t, f, h) = fixture();
    let rule = RetentionRule {
        id: "nulb".into(),
        wording: "Keep and convert Nulb v3".into(),
        provenance: "owner conversation".into(),
        source_id: Some("a".into()),
        fingerprint: Some(f.old_sources[0].fingerprint.clone()),
        action: "keep_and_convert".into(),
    };
    let a = audit::compare(&f, &h, &[rule]).unwrap();
    assert_eq!(
        a.files
            .iter()
            .find(|x| x.source.source_id == "a")
            .unwrap()
            .state,
        ProposalState::ExplicitlyRetained
    );
    assert!(a.protected[0].bound);
}
#[test]
fn unbound_nulb_rule_does_not_guess_by_name() {
    let (_t, f, h) = fixture();
    let rule = RetentionRule {
        id: "nulb".into(),
        wording: "Nulb v3".into(),
        provenance: "owner".into(),
        source_id: None,
        fingerprint: None,
        action: "keep_and_convert".into(),
    };
    let a = audit::compare(&f, &h, &[rule]).unwrap();
    assert!(!a.protected[0].bound);
    assert!(
        !a.files
            .iter()
            .any(|x| x.state == ProposalState::ExplicitlyRetained)
    );
}
#[test]
fn uncertainty_and_partial_matches_remain_retained() {
    let (_t, mut f, h) = fixture();
    f.reference[0].method = EvidenceMethod::PartialReference;
    let a = audit::compare(&f, &h, &[]).unwrap();
    assert!(a.files.iter().all(|x| x.state.eligible()));
    assert_eq!(a.reference[0].outcome, "reference_not_confirmed");
    assert!(a.files.iter().all(|x| x.reference_rows.is_empty()));
}
#[test]
fn multiple_current_variants_are_not_one_work() {
    let (_t, mut f, h) = fixture();
    let mut other = f.reference[0].clone();
    other.d_path = "other.pdf".into();
    other.g_path = Some("publisher/nulb/nulb_v3.pdf".into());
    other.row = 3;
    f.reference.push(other);
    let a = audit::compare(&f, &h, &[]).unwrap();
    assert_eq!(a.reference.len(), 2);
    let g = a.relationships.iter().find(|x| x.id == "g").unwrap();
    assert_eq!(g.reference_rows.len(), 2);
    assert!(g.needs_review);
    assert!(a.files.iter().all(|x| x.state.eligible()));
}
#[test]
fn sample_is_reproducible_and_publisher_holdouts_do_not_leak() {
    let (_t, f, h) = fixture();
    let mut a = audit::compare(&f, &h, &[]).unwrap();
    let base = a.relationships[0].clone();
    a.relationships.clear();
    for i in 0..100 {
        let mut g = base.clone();
        g.id = format!("g{i}");
        g.publisher = format!("publisher{}", i / 10);
        g.product_folder = format!("product{i}");
        g.flagged = false;
        a.relationships.push(g);
    }
    let first = sampling::select(&a, &f.config).unwrap();
    assert_eq!(
        serde_json::to_value(&first).unwrap(),
        serde_json::to_value(sampling::select(&a, &f.config).unwrap()).unwrap()
    );
    let mut partitions = std::collections::BTreeMap::new();
    for m in &first.membership {
        let old = partitions.insert(m.publisher.clone(), m.holdout);
        assert!(old.is_none_or(|x| x == m.holdout));
    }
    assert!(first.selected.len() <= 50);
    let mut cfg = f.config.clone();
    cfg.sample_seed = "different".into();
    assert_ne!(first.selected, sampling::select(&a, &cfg).unwrap().selected);
    a.relationships[99].flagged = true;
    assert!(
        sampling::select(&a, &f.config)
            .unwrap()
            .selected
            .contains(&"g99".into())
    );
}
#[test]
fn changed_binding_remains_policy_but_is_not_applied() {
    let (_t, f, h) = fixture();
    let mut fp = f.old_sources[0].fingerprint.clone();
    fp.size += 1;
    let r = RetentionRule {
        id: "keep".into(),
        wording: "keep".into(),
        provenance: "owner".into(),
        source_id: Some("a".into()),
        fingerprint: Some(fp),
        action: "keep_and_convert".into(),
    };
    let a = audit::compare(&f, &h, &[r]).unwrap();
    assert!(!a.protected[0].bound);
    assert_eq!(a.protected.len(), 1);
}
#[test]
fn conflicting_dates_and_companion_metadata_do_not_exclude_content() {
    let (_t, mut f, h) = fixture();
    f.old_sources[0]
        .metadata
        .insert("CreationDate".into(), json!("2023-03-16"));
    f.old_sources[1]
        .metadata
        .insert("ModDate".into(), json!("2017-08-27"));
    f.old_sources[0]
        .metadata
        .insert("language".into(), json!("English"));
    f.old_sources[1]
        .metadata
        .insert("language".into(), json!("French"));
    let a = audit::compare(&f, &h, &[]).unwrap();
    assert!(a.files.iter().all(|x| x.state.retained()));
    assert!(a.files.iter().all(|x| x.representative.is_none()));
}
#[test]
fn exact_duplicates_have_retained_representatives() {
    let (_t, mut f, h) = fixture();
    for s in &mut f.old_sources[..2] {
        s.fingerprint.sha256 = Some("a".repeat(64));
    }
    let a = audit::compare(&f, &h, &[]).unwrap();
    let duplicate = a
        .files
        .iter()
        .find(|x| x.state == ProposalState::Duplicate)
        .unwrap();
    let representative = a
        .files
        .iter()
        .find(|x| Some(&x.source.source_id) == duplicate.representative.as_ref())
        .unwrap();
    assert!(representative.state.retained());
    assert!(!duplicate.state.eligible());
}
#[test]
fn report_separates_files_groups_relationships_and_coverage() {
    let (t, f, h) = fixture();
    let a = audit::compare(&f, &h, &[]).unwrap();
    let sample = sampling::select(&a, &f.config).unwrap();
    let out = t.path().join("report");
    rpg_source_select::analysis::report::write(&a, &sample, &out).unwrap();
    let s: serde_json::Value =
        serde_json::from_slice(&std::fs::read(out.join("summary.json")).unwrap()).unwrap();
    assert_eq!(s["counts"]["old_pdf_files"], 3);
    assert_eq!(s["counts"]["reference_pdf_rows"], 1);
    assert_eq!(s["provisional"], true);
    assert!(s.get("accuracy").is_none());
    for name in [
        "report.md",
        "reference-rows.csv",
        "old-library-files.csv",
        "relationships.jsonl",
        "proposed-conversion-list.json",
        "protected-editions.json",
        "sample-manifest.json",
    ] {
        assert!(out.join(name).exists(), "{name}");
    }
}
