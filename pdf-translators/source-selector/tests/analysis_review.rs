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
