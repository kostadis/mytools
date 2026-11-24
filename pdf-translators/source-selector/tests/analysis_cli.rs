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
    let bundle = bundle_fixture(t.path(), &m, &t.path().join("results.json"));
    let before = std::fs::read(run.join("audit.json")).unwrap();
    let out = t.path().join("reviewed");
    let r = cli(&[
        "analysis",
        "review-import",
        "--run",
        run.to_str().unwrap(),
        "--manifest",
        export.join("review-manifest.json").to_str().unwrap(),
        "--bundle",
        bundle.to_str().unwrap(),
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
#[test]
fn symlink_parent_resolution_cannot_escape_output_guard() {
    use std::os::unix::fs::symlink;
    let t = tempfile::tempdir().unwrap();
    let cfg: rpg_source_select::analysis::models::AnalysisConfig =
        serde_json::from_value(setup(t.path())).unwrap();
    let library = t.path().join("library");
    std::fs::create_dir_all(library.join("child")).unwrap();
    std::fs::create_dir(t.path().join("outside")).unwrap();
    symlink(library.join("child"), t.path().join("outside/link")).unwrap();
    let c = rusqlite::Connection::open(&cfg.old_inventory).unwrap();
    c.execute(
        "INSERT INTO meta VALUES('root',?1)",
        [json!(library).to_string()],
    )
    .unwrap();
    drop(c);
    assert!(
        rpg_source_select::analysis::workflow::guard_output(
            &cfg,
            &t.path().join("outside/link/../analysis")
        )
        .is_err()
    );
}
#[test]
fn derived_publication_is_atomic_and_retryable_after_failure() {
    let t = tempfile::tempdir().unwrap();
    let out = t.path().join("derived");
    let r = rpg_source_select::analysis::workflow::publish_derived(&out, |stage| {
        std::fs::write(stage.join("partial"), "partial")?;
        Err(rpg_source_select::SelectionError::Invalid(
            "injected interruption".into(),
        ))
    });
    assert!(r.is_err());
    assert!(!out.exists());
    rpg_source_select::analysis::workflow::publish_derived(&out, |stage| {
        std::fs::write(stage.join("complete"), "complete")?;
        Ok(())
    })
    .unwrap();
    assert!(out.join("complete").exists());
    assert!(!out.join("partial").exists());
}
fn factual_fixture(stale: bool) -> (tempfile::TempDir, std::path::PathBuf) {
    use rpg_source_select::{
        models::{Evidence, PageText},
        store::Store,
    };
    let t = tempfile::tempdir().unwrap();
    let mut cfg = setup(t.path());
    let mut s = source("a", "a.pdf");
    s["fingerprint"]["sha256"] = json!("a".repeat(64));
    insert_source(&t.path().join("old.db"), s.clone());
    let mut store = Store::open(&t.path().join("old.db")).unwrap();
    store
        .save_evidence(&Evidence {
            source_id: "a".into(),
            sha256: if stale {
                "b".repeat(64)
            } else {
                "a".repeat(64)
            },
            version: 1,
            pdf_metadata: Default::default(),
            pages: vec![PageText {
                page: 1,
                text: "Verified edition statement".into(),
                images: None,
                annotations: None,
            }],
            page_count: 1,
            bookmarks: serde_json::Value::Null,
            errors: vec![],
            text_quality: "native".into(),
            claims: vec![],
        })
        .unwrap();
    drop(store);
    let evidence = t.path().join("facts.json");
    write(
        &evidence,
        &json!([{"source_id":"a","fingerprint":s["fingerprint"],"actor":"model","model":"reader-model","kind":"fact","method":"sampled_pages","scope":"page 1","provenance":"fixture native inspect","page":1,"quote":"Verified edition statement"}]),
    );
    cfg["evidence_imports"] = json!([evidence]);
    let config = t.path().join("config.json");
    write(&config, &cfg);
    (t, config)
}
#[test]
fn factual_import_reads_native_gzip_evidence_and_rejects_stale_hash() {
    let (t, c) = factual_fixture(false);
    let result = run(&c, &t.path().join("run"));
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let (t, c) = factual_fixture(true);
    assert!(!run(&c, &t.path().join("run")).status.success());
}
