mod analysis_support;
use analysis_support::*;
use serde_json::json;
use std::{path::Path, process::Command};
fn cli(args: &[&str]) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .args(args)
        .output()
        .unwrap()
}
fn run(config: &Path, out: &Path) -> std::process::Output {
    cli(&[
        "analysis",
        "run",
        "--config",
        config.to_str().unwrap(),
        "--output",
        out.to_str().unwrap(),
    ])
}
#[test]
fn analysis_does_not_touch_production_or_pdfs() {
    use std::os::unix::fs::PermissionsExt;
    let t = tempfile::tempdir().unwrap();
    let cfg = setup(t.path());
    let lib = t.path().join("pdfs");
    std::fs::create_dir(&lib).unwrap();
    let pdf = lib.join("unreadable.pdf");
    std::fs::write(&pdf, b"not a PDF; must never be opened").unwrap();
    std::fs::set_permissions(&pdf, std::fs::Permissions::from_mode(0)).unwrap();
    insert_source(&t.path().join("old.db"), source("a", "unreadable.pdf"));
    let c = rusqlite::Connection::open(t.path().join("old.db")).unwrap();
    c.execute(
        "INSERT INTO meta VALUES('root',?1)",
        [json!(lib).to_string()],
    )
    .unwrap();
    drop(c);
    let db = t.path().join("old.db");
    let before = std::fs::read(&db).unwrap();
    std::fs::set_permissions(&db, std::fs::Permissions::from_mode(0o444)).unwrap();
    write(&t.path().join("config.json"), &cfg);
    let result = run(&t.path().join("config.json"), &t.path().join("run"));
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert_eq!(std::fs::read(db).unwrap(), before);
    assert!(!lib.join("unreadable.md").exists());
    let denied = run(&t.path().join("config.json"), &lib.join("analysis"));
    assert!(!denied.status.success());
    assert!(!lib.join("analysis").exists());
}
#[test]
fn resume_preserves_completed_stages() {
    let t = tempfile::tempdir().unwrap();
    let cfg = setup(t.path());
    write(&t.path().join("config.json"), &cfg);
    let out = t.path().join("run");
    assert!(run(&t.path().join("config.json"), &out).status.success());
    let report = out.join("report/summary.json");
    let before = std::fs::metadata(&report).unwrap().modified().unwrap();
    assert!(run(&t.path().join("config.json"), &out).status.success());
    assert_eq!(
        before,
        std::fs::metadata(report).unwrap().modified().unwrap()
    );
}
#[test]
fn changed_inputs_require_new_run() {
    let t = tempfile::tempdir().unwrap();
    let cfg = setup(t.path());
    write(&t.path().join("config.json"), &cfg);
    let out = t.path().join("run");
    assert!(run(&t.path().join("config.json"), &out).status.success());
    std::fs::write(t.path().join("matches.csv"), "changed").unwrap();
    assert!(!run(&t.path().join("config.json"), &out).status.success());
}
#[test]
fn review_import_only_changes_derived_outputs() {
    let (t, a) = audit_fixture();
    let run = t.path().join("derived-run");
    std::fs::create_dir(&run).unwrap();
    std::fs::copy(t.path().join("run/inputs.json"), run.join("inputs.json")).unwrap();
    write(&run.join("audit.json"), &serde_json::to_value(&a).unwrap());
    write(
        &run.join("audit-receipt.json"),
        &json!({"audit_digest":rpg_source_select::digest_json(&a)}),
    );
    let sample = rpg_source_select::analysis::sampling::select(
        &a,
        &serde_json::from_value(setup(&tempfile::tempdir().unwrap().keep())).unwrap(),
    )
    .unwrap();
    write(
        &run.join("sample.json"),
        &serde_json::to_value(sample).unwrap(),
    );
    let export = t.path().join("review");
    let r = cli(&[
        "analysis",
        "review-export",
        "--run",
        run.to_str().unwrap(),
        "--output",
        export.to_str().unwrap(),
    ]);
    assert!(r.status.success(), "{}", String::from_utf8_lossy(&r.stderr));
    let m: rpg_source_select::analysis::models::ReviewManifest =
        serde_json::from_slice(&std::fs::read(export.join("review-manifest.json")).unwrap())
            .unwrap();
    let normalized = json!({"reviewId":m.review_id,"total":1,"scope_map":m.scope_map,"decisions":{},"picks":{},"notes":{},"unmarked":m.items["items"].as_array().unwrap().iter().map(|c|c["id"].clone()).collect::<Vec<_>>(),"discuss":[],"provenance":[]});
    write(&t.path().join("results.json"), &normalized);
    let before = std::fs::read(run.join("audit.json")).unwrap();
    let out = t.path().join("reviewed");
    let r = cli(&[
        "analysis",
        "review-import",
        "--run",
        run.to_str().unwrap(),
        "--manifest",
        export.join("review-manifest.json").to_str().unwrap(),
        "--results",
        t.path().join("results.json").to_str().unwrap(),
        "--output",
        out.to_str().unwrap(),
    ]);
    assert!(r.status.success(), "{}", String::from_utf8_lossy(&r.stderr));
    assert_eq!(before, std::fs::read(run.join("audit.json")).unwrap());
    assert!(out.join("report/summary.json").exists());
}
#[test]
fn progress_uses_count_and_elapsed_clock_without_sleep() {
    use rpg_source_select::analysis::progress::LogGate;
    let mut g = LogGate::default();
    assert!(g.due("audit", 0, 200, 0));
    assert!(!g.due("audit", 99, 200, 1));
    assert!(g.due("audit", 100, 200, 2));
    assert!(g.due("audit", 101, 200, 32));
    assert!(g.due("audit", 200, 200, 33));
}
#[test]
fn imported_evidence_is_visible_without_becoming_an_approval() {
    let t = tempfile::tempdir().unwrap();
    let mut cfg = setup(t.path());
    let s = source("a", "a.pdf");
    insert_source(&t.path().join("old.db"), s.clone());
    let evidence = t.path().join("evidence.json");
    write(
        &evidence,
        &json!([{"source_id":"a","fingerprint":s["fingerprint"],"method":"mystery","scope":"page one","provenance":"fixture comparison","actor":"operator","detail":"Evidence must be preserved"}]),
    );
    cfg["evidence_imports"] = json!([evidence]);
    write(&t.path().join("config.json"), &cfg);
    let out = t.path().join("run");
    let result = run(&t.path().join("config.json"), &out);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let audit: serde_json::Value =
        serde_json::from_slice(&std::fs::read(out.join("audit.json")).unwrap()).unwrap();
    assert_eq!(audit["supplemental_evidence"][0]["method"], "unconfirmed");
    assert_eq!(
        audit["supplemental_evidence"][0]["detail"],
        "Evidence must be preserved"
    );
    assert_eq!(audit["files"][0]["state"], "unresolved_retained");
}
