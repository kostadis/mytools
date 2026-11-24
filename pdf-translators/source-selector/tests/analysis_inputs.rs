mod analysis_support;
use analysis_support::*;
use rpg_source_select::analysis::{inputs::*, models::*};
#[test]
fn csv_paths_preserve_commas_and_newlines() {
    let t = tempfile::tempdir().unwrap();
    let cfg = setup(t.path());
    std::fs::write(t.path().join("matches.csv"),"\u{feff}D file,G file,Status,Evidence,Other matching G files\n\"D:\\Download\\Book, one.pdf\",G:\\Library\\Book.pdf,SHA-256 match,hash,\"G:\\Library\\copy.pdf\nG:\\Library\\copy2.pdf\"\n").unwrap();
    let f = freeze(&serde_json::from_value(cfg).unwrap(), &t.path().join("run")).unwrap();
    assert_eq!(f.reference.len(), 1);
    assert_eq!(f.reference[0].other_paths.len(), 2);
    assert_eq!(f.reference[0].method, EvidenceMethod::ExactBytes);
    assert_eq!(f.reference[0].d_path, "book, one.pdf");
}
#[test]
fn unicode_path_collisions_are_reported() {
    assert_eq!(
        normalize_windows_relative("G:/Library/Straße/Cafe\u{301}.pdf", "g:/library").unwrap(),
        "strasse/café.pdf"
    );
    assert!(normalize_windows_relative("G:/Library/../secret.pdf", "G:/Library").is_err());
    let t = tempfile::tempdir().unwrap();
    let cfg = setup(t.path());
    insert_source(&t.path().join("old.db"), source("a", "BOOK.pdf"));
    insert_source(&t.path().join("old.db"), source("b", "book.pdf"));
    assert!(freeze(&serde_json::from_value(cfg).unwrap(), &t.path().join("run")).is_err());
}
#[test]
fn unknown_and_partial_methods_do_not_confirm_full_match() {
    assert_eq!(
        classify_method("Mystery match", ""),
        EvidenceMethod::Unconfirmed
    );
    assert_eq!(
        classify_method("SHA-256 match", "readable portions of incomplete D: file"),
        EvidenceMethod::PartialReference
    );
    assert_eq!(
        classify_method("All rendered pages match", "all pages"),
        EvidenceMethod::AllRenderedPages
    );
}
#[test]
fn changed_or_interrupted_snapshot_is_not_committed() {
    let t = tempfile::tempdir().unwrap();
    let cfg: AnalysisConfig = serde_json::from_value(setup(t.path())).unwrap();
    let out = t.path().join("run");
    let first = freeze(&cfg, &out).unwrap();
    assert_eq!(first.receipt_id, freeze(&cfg, &out).unwrap().receipt_id);
    std::fs::write(
        &cfg.csv,
        "D file,G file,Status,Evidence,Other matching G files\nD:/Download/a.pdf,,unknown,,\n",
    )
    .unwrap();
    assert!(freeze(&cfg, &out).is_err());
    assert!(out.join("inputs.json").exists());
    let other = t.path().join("interrupted");
    std::fs::create_dir(&other).unwrap();
    std::fs::write(other.join("input.tmp"), "partial").unwrap();
    assert!(freeze(&cfg, &other).is_err());
}
#[test]
fn input_changed_during_read_is_rejected() {
    let t = tempfile::tempdir().unwrap();
    let p = t.path().join("data");
    std::fs::write(&p, b"before").unwrap();
    let result = read_unchanged(&p, |path| {
        let b = std::fs::read(path)?;
        std::fs::write(path, b"after, longer")?;
        Ok(b)
    });
    assert!(result.is_err());
}
#[test]
fn sqlite_wal_changes_are_detected_on_resume() {
    let t = tempfile::tempdir().unwrap();
    let cfg: AnalysisConfig = serde_json::from_value(setup(t.path())).unwrap();
    let run = t.path().join("run");
    let conn = rusqlite::Connection::open(&cfg.old_inventory).unwrap();
    conn.execute_batch("PRAGMA journal_mode=WAL").unwrap();
    freeze(&cfg, &run).unwrap();
    insert_source(&cfg.old_inventory, source("new", "new.pdf"));
    assert!(freeze(&cfg, &run).is_err());
}
#[test]
fn wal_cache_changes_are_detected_on_resume() {
    let t = tempfile::tempdir().unwrap();
    let cfg: AnalysisConfig = serde_json::from_value(setup(t.path())).unwrap();
    let conn = rusqlite::Connection::open(&cfg.old_inventory).unwrap();
    conn.execute_batch(
        "PRAGMA journal_mode=WAL;CREATE TABLE cache(id TEXT,stage TEXT,cache_key TEXT,body TEXT)",
    )
    .unwrap();
    let out = t.path().join("run");
    freeze(&cfg, &out).unwrap();
    conn.execute("INSERT INTO cache VALUES('s','hash','key','new hash')", [])
        .unwrap();
    assert!(freeze(&cfg, &out).is_err());
}
#[test]
fn unsupported_analysis_policy_is_rejected() {
    let t = tempfile::tempdir().unwrap();
    let mut c = setup(t.path());
    c["analysis_policy"] = serde_json::json!("future-policy");
    assert!(freeze(&serde_json::from_value(c).unwrap(), &t.path().join("run")).is_err());
}
#[test]
fn embedded_newline_in_a_windows_filename_is_not_silently_split() {
    assert!(normalize_windows_relative("G:/Library/name\nrest.pdf", "G:/Library").is_err());
    let t = tempfile::tempdir().unwrap();
    let c = setup(t.path());
    std::fs::write(t.path().join("matches.csv"),"D file,G file,Status,Evidence,Other matching G files\nD:/Download/a.pdf,,unknown,,\"G:/Library/name\nrest.pdf\"\n").unwrap();
    assert!(freeze(&serde_json::from_value(c).unwrap(), &t.path().join("run")).is_err());
}
