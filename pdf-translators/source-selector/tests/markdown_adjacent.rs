mod common;
use rpg_source_select::{
    digest_json,
    grouping::hash_source,
    markdown::{Snapshot, selection},
    store::Store,
};
use serde_json::{Value, json};
use std::{fs, path::Path, process::Command};
use tempfile::TempDir;
fn cli(args: &[&str]) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .args(args)
        .output()
        .unwrap()
}
fn select(root: &Path, state: &Path, out: &Path) -> Snapshot {
    let r = cli(&[
        "--work-dir",
        state.to_str().unwrap(),
        "scan",
        "--root",
        root.to_str().unwrap(),
    ]);
    assert!(r.status.success(), "{}", String::from_utf8_lossy(&r.stderr));
    selection::select(
        &Store::open_readonly(&state.join("selection.db")).unwrap(),
        out,
        None,
    )
    .unwrap()
}
fn fixture() -> (TempDir, TempDir, TempDir) {
    let root = tempfile::tempdir().unwrap();
    let state = tempfile::tempdir().unwrap();
    let out = tempfile::tempdir().unwrap();
    fs::create_dir_all(root.path().join("Pub/Book")).unwrap();
    common::pdf(
        &root.path().join("Pub/Book/Amber Almanac.pdf"),
        "Searchable amber dragon and useful reference words.",
        "D:20210101000000Z",
        false,
    );
    select(root.path(), state.path(), out.path());
    (root, state, out)
}
fn convert(out: &Path, extra: &[&str]) -> Value {
    let mut args = vec![
        "markdown-convert",
        "--output",
        out.to_str().unwrap(),
        "--publish-next-to-source",
    ];
    args.extend(extra);
    let r = cli(&args);
    assert!(r.status.success(), "{}", String::from_utf8_lossy(&r.stderr));
    serde_json::from_slice(&r.stdout).unwrap()
}
fn manifest(dir: &Path) -> Value {
    serde_json::from_slice(&fs::read(dir.join("current-documents.json")).unwrap()).unwrap()
}
fn replace_snapshot(out: &Path, mut s: Snapshot) {
    s.snapshot_id.clear();
    s.snapshot_id = digest_json(&s);
    let dir = out.join("selection/generations").join(&s.snapshot_id);
    fs::create_dir_all(&dir).unwrap();
    fs::write(
        dir.join("markdown-selection.json"),
        serde_json::to_vec_pretty(&s).unwrap(),
    )
    .unwrap();
    fs::write(
        out.join("selection/current.json"),
        serde_json::to_vec(&s.snapshot_id).unwrap(),
    )
    .unwrap();
}
#[test]
fn selected_siblings_and_multiple_current_entries_publish_without_changing_pdfs() {
    let (root, state, out) = fixture();
    let dir = root.path().join("Pub/Book");
    fs::copy(
        dir.join("Amber Almanac.pdf"),
        dir.join("Amber Almanac.old-001.pdf"),
    )
    .unwrap();
    common::pdf(
        &dir.join("MapAtlas.pdf"),
        "Searchable silver dragon with readable reference words.",
        "D:20210101000000Z",
        false,
    );
    let s = select(root.path(), state.path(), out.path());
    assert_eq!(s.ready.len(), 2);
    let before = hash_source(&dir.join("Amber Almanac.pdf")).unwrap();
    let r = convert(out.path(), &[]);
    assert_eq!(r["published_books"], 2);
    let m = manifest(&dir);
    assert_eq!(m["documents"].as_array().unwrap().len(), 2);
    assert_eq!(m["reconciliation_status"], "complete");
    let entry = m["documents"]
        .as_array()
        .unwrap()
        .iter()
        .find(|v| v["pdf"] == "Amber Almanac.pdf")
        .unwrap();
    assert_eq!(entry["status"], "published");
    assert_eq!(entry["pdf_sha256"], before);
    assert_eq!(entry["markdown"], "Amber Almanac.md");
    let md = fs::read_to_string(dir.join("Amber Almanac.md")).unwrap();
    assert!(md.contains("[Source PDF](Amber%20Almanac.pdf)"));
    assert!(md.contains("Searchable amber dragon"));
    assert!(md.contains(&before));
    assert!(!dir.join("Amber Almanac.old-001.md").exists());
    assert_eq!(hash_source(&dir.join("Amber Almanac.pdf")).unwrap(), before);
    let mtime = fs::metadata(dir.join("Amber Almanac.md"))
        .unwrap()
        .modified()
        .unwrap();
    let old_record = fs::read(dir.join("current-documents.json")).unwrap();
    let r = convert(out.path(), &[]);
    assert_eq!(r["extracted_ranges"], 0);
    assert_eq!(
        fs::metadata(dir.join("Amber Almanac.md"))
            .unwrap()
            .modified()
            .unwrap(),
        mtime
    );
    assert_eq!(
        fs::read(dir.join("current-documents.json")).unwrap(),
        old_record
    );
}
#[test]
fn default_conversion_keeps_the_library_read_only() {
    let (root, _state, out) = fixture();
    let r = cli(&["markdown-convert", "--output", out.path().to_str().unwrap()]);
    assert!(r.status.success());
    assert!(!root.path().join("Pub/Book/Amber Almanac.md").exists());
    assert!(!root.path().join("Pub/Book/current-documents.json").exists());
}
#[test]
fn manual_and_edited_markdown_are_preserved_and_excluded_from_current_mirror() {
    for manual in [false, true] {
        let (root, _state, out) = fixture();
        let dir = root.path().join("Pub/Book");
        if !manual {
            convert(out.path(), &[]);
        }
        fs::write(dir.join("Amber Almanac.md"), "User authored notes").unwrap();
        let r = convert(out.path(), &[]);
        assert_eq!(r["published_books"], 0);
        assert_eq!(
            fs::read_to_string(dir.join("Amber Almanac.md")).unwrap(),
            "User authored notes"
        );
        assert_eq!(manifest(&dir)["documents"][0]["status"], "output_conflict");
        assert!(
            r["publication"]["adjacent"]["errors"]
                .as_array()
                .is_some_and(|v| !v.is_empty())
        );
    }
}
#[test]
fn foreign_directory_record_does_not_block_an_independent_directory() {
    let (root, state, out) = fixture();
    let dir = root.path().join("Pub/Other");
    fs::create_dir_all(&dir).unwrap();
    common::pdf(
        &dir.join("Silver.pdf"),
        "Useful silver dragon reference words.",
        "D:20210101000000Z",
        false,
    );
    select(root.path(), state.path(), out.path());
    let blocked = root.path().join("Pub/Book/current-documents.json");
    fs::write(&blocked, "{\"user\":\"record\"}").unwrap();
    let r = convert(out.path(), &[]);
    assert_eq!(r["published_books"], 1);
    assert_eq!(
        fs::read_to_string(blocked).unwrap(),
        "{\"user\":\"record\"}"
    );
    assert!(!root.path().join("Pub/Book/Amber Almanac.md").exists());
    assert!(dir.join("Silver.md").exists());
    assert_eq!(manifest(&dir)["reconciliation_status"], "complete");
}
#[test]
fn policy_refresh_reuses_text_and_unselected_files_stay_in_place() {
    let (root, _state, out) = fixture();
    let dir = root.path().join("Pub/Book");
    convert(out.path(), &[]);
    let mut s = selection::load_current(out.path()).unwrap();
    s.created = "2030-01-01T00:00:00Z".into();
    replace_snapshot(out.path(), s);
    let r = convert(out.path(), &[]);
    assert_eq!(r["extracted_ranges"], 0);
    let latest = selection::load_current(out.path()).unwrap();
    assert!(
        fs::read_to_string(dir.join("Amber Almanac.md"))
            .unwrap()
            .contains(&latest.snapshot_id)
    );
    let mut empty = latest;
    empty.ready.clear();
    empty.records.clear();
    replace_snapshot(out.path(), empty);
    convert(out.path(), &[]);
    assert!(dir.join("Amber Almanac.md").exists());
    assert!(manifest(&dir)["documents"].as_array().unwrap().is_empty());
}
#[cfg(unix)]
#[test]
fn redirected_markdown_cannot_overwrite_another_file() {
    let (root, _state, out) = fixture();
    let outside = tempfile::tempdir().unwrap();
    let target = outside.path().join("notes.md");
    fs::write(&target, "Keep these notes").unwrap();
    std::os::unix::fs::symlink(&target, root.path().join("Pub/Book/Amber Almanac.md")).unwrap();
    let r = convert(out.path(), &[]);
    assert_eq!(r["published_books"], 0);
    assert_eq!(fs::read_to_string(target).unwrap(), "Keep these notes");
}
#[test]
fn incomplete_coverage_keeps_old_authority_and_clean_coverage_clears_empty_directory() {
    let (root, _state, out) = fixture();
    let dir = root.path().join("Pub/Book");
    convert(out.path(), &[]);
    let old = manifest(&dir);
    let mut s = selection::load_current(out.path()).unwrap();
    s.ready.clear();
    s.records.clear();
    s.coverage_errors = vec!["unreadable subtree".into()];
    replace_snapshot(out.path(), s.clone());
    let r = convert(out.path(), &[]);
    let partial = manifest(&dir);
    assert_eq!(partial["reconciliation_status"], "partial");
    assert_eq!(
        partial["documents"][0]["selection_id"],
        old["documents"][0]["selection_id"]
    );
    assert!(r["publication"]["pending"].as_bool().unwrap());
    fs::remove_dir_all(out.path().join("adjacent")).unwrap();
    fs::remove_file(dir.join("Amber Almanac.pdf")).unwrap();
    s.coverage_errors.clear();
    replace_snapshot(out.path(), s);
    convert(out.path(), &[]);
    assert!(manifest(&dir)["documents"].as_array().unwrap().is_empty());
    assert!(dir.join("Amber Almanac.md").exists());
}
#[test]
fn published_checksum_receipts_survive_reselection_and_interrupted_record_commit() {
    let (root, _state, out) = fixture();
    let dir = root.path().join("Pub/Book");
    convert(out.path(), &[]);
    let original = selection::load_current(out.path()).unwrap();
    let mut none = original.clone();
    none.ready.clear();
    none.records.clear();
    replace_snapshot(out.path(), none);
    convert(out.path(), &[]);
    assert!(manifest(&dir)["documents"].as_array().unwrap().is_empty());
    replace_snapshot(out.path(), original.clone());
    assert_eq!(convert(out.path(), &[])["published_books"], 1);
    let registry = fs::read_dir(out.path().join("adjacent"))
        .unwrap()
        .next()
        .unwrap()
        .unwrap()
        .path();
    let mut state: Value = serde_json::from_slice(&fs::read(&registry).unwrap()).unwrap();
    state["intents"] = state["receipts"].clone();
    state["receipts"] = json!([]);
    fs::write(&registry, serde_json::to_vec(&state).unwrap()).unwrap();
    fs::remove_file(dir.join("current-documents.json")).unwrap();
    let r = convert(out.path(), &[]);
    assert_eq!(r["published_books"], 1);
    assert_eq!(r["extracted_ranges"], 0);
    assert!(
        serde_json::from_slice::<Value>(&fs::read(registry).unwrap()).unwrap()["intents"]
            .as_array()
            .unwrap()
            .is_empty()
    );
    fs::remove_dir_all(out.path().join("adjacent")).unwrap();
    assert_eq!(convert(out.path(), &[])["published_books"], 1); // ownership rebuilt from manifest
}
#[test]
fn bounded_conversion_writes_pending_entries_for_all_selected_works() {
    let (root, state, out) = fixture();
    let dir = root.path().join("Pub/Book");
    common::pdf(
        &dir.join("MapAtlas.pdf"),
        "Independent silver reference.",
        "D:20210101000000Z",
        false,
    );
    select(root.path(), state.path(), out.path());
    let r = convert(out.path(), &["--limit", "1"]);
    assert_eq!(r["published_books"], 1);
    let m = manifest(&dir);
    let docs = m["documents"].as_array().unwrap();
    assert_eq!(docs.len(), 2);
    assert_eq!(docs.iter().filter(|d| d["status"] == "pending").count(), 1);
    assert_eq!(convert(out.path(), &["--limit", "1"])["published_books"], 2);
}
#[cfg(unix)]
#[test]
fn non_utf8_filenames_keep_byte_identity_and_clickable_percent_encoded_links() {
    use std::os::unix::ffi::OsStringExt;
    let (root, state, out) = fixture();
    let dir = root.path().join("Pub/Book");
    let name = std::ffi::OsString::from_vec(b"Scarlet\xff #().pdf".to_vec());
    common::pdf(
        &dir.join(&name),
        "Readable scarlet reference.",
        "D:20210101000000Z",
        false,
    );
    select(root.path(), state.path(), out.path());
    assert_eq!(convert(out.path(), &[])["published_books"], 2);
    let md = fs::read_to_string(dir.join(name).with_extension("md")).unwrap();
    assert!(md.contains("[Source PDF](Scarlet%FF%20%23%28%29.pdf)"));
    assert!(
        manifest(&dir)["documents"]
            .as_array()
            .unwrap()
            .iter()
            .any(|d| d["pdf"].get("unix_bytes").is_some())
    );
}
#[test]
fn zero_text_and_sparse_text_have_truthful_directory_states() {
    let (root, state, out) = fixture();
    let dir = root.path().join("Pub/Book");
    common::pdf(&dir.join("Empty.pdf"), "", "D:20210101000000Z", false);
    common::pdf(&dir.join("Sparse.pdf"), "A", "D:20210101000000Z", false);
    select(root.path(), state.path(), out.path());
    let r = convert(out.path(), &[]);
    assert_eq!(r["published_books"], 2);
    let m = manifest(&dir);
    let docs = m["documents"].as_array().unwrap();
    assert_eq!(
        docs.iter().find(|d| d["pdf"] == "Empty.pdf").unwrap()["status"],
        "needs_ocr_or_visual_review"
    );
    assert!(!dir.join("Empty.md").exists());
    assert!(dir.join("Sparse.md").exists());
}
#[test]
fn revised_pdf_at_same_filename_replaces_only_unchanged_owned_markdown() {
    let (root, state, out) = fixture();
    let dir = root.path().join("Pub/Book");
    convert(out.path(), &[]);
    let old = fs::read(dir.join("Amber Almanac.md")).unwrap();
    common::pdf(
        &dir.join("Amber Almanac.pdf"),
        "New revised amber reference words.",
        "D:20220101000000Z",
        false,
    );
    select(root.path(), state.path(), out.path());
    let r = convert(out.path(), &[]);
    assert_eq!(r["published_books"], 1);
    assert_ne!(fs::read(dir.join("Amber Almanac.md")).unwrap(), old);
    assert!(
        fs::read_to_string(dir.join("Amber Almanac.md"))
            .unwrap()
            .contains("New revised amber reference")
    );
    assert_eq!(
        manifest(&dir)["documents"][0]["pdf_sha256"],
        hash_source(&dir.join("Amber Almanac.pdf")).unwrap()
    );
}
#[test]
fn lost_ownership_of_unlisted_markdown_is_a_conflict_and_unrelated_entries_survive() {
    let (root, _state, out) = fixture();
    let dir = root.path().join("Pub/Book");
    convert(out.path(), &[]);
    let original = selection::load_current(out.path()).unwrap();
    let mut none = original.clone();
    none.ready.clear();
    none.records.clear();
    replace_snapshot(out.path(), none);
    convert(out.path(), &[]);
    fs::remove_dir_all(out.path().join("adjacent")).unwrap();
    let mut m = manifest(&dir);
    m["documents"]
        .as_array_mut()
        .unwrap()
        .push(json!({"generator":"another-tool","work_id":"manual","note":"Keep me"}));
    fs::write(
        dir.join("current-documents.json"),
        serde_json::to_vec(&m).unwrap(),
    )
    .unwrap();
    replace_snapshot(out.path(), original);
    let r = convert(out.path(), &[]);
    assert_eq!(r["published_books"], 0);
    let m = manifest(&dir);
    assert!(
        m["documents"]
            .as_array()
            .unwrap()
            .iter()
            .any(|e| e["note"] == "Keep me")
    );
    assert!(
        m["documents"]
            .as_array()
            .unwrap()
            .iter()
            .any(|e| e["status"] == "output_conflict")
    );
}
#[test]
fn colliding_selected_destinations_do_not_silently_overwrite_each_other() {
    let (root, _state, out) = fixture();
    let mut s = selection::load_current(out.path()).unwrap();
    let mut other = s.ready[0].clone();
    other.work_id = "independent-work".into();
    s.ready.push(other);
    replace_snapshot(out.path(), s);
    let r = convert(out.path(), &[]);
    assert_eq!(r["published_books"], 0);
    assert!(!root.path().join("Pub/Book/Amber Almanac.md").exists());
    assert_eq!(
        manifest(&root.path().join("Pub/Book"))["documents"]
            .as_array()
            .unwrap()
            .len(),
        2
    );
}
#[test]
fn malformed_owned_record_is_preserved_instead_of_adopted() {
    let (root, _state, out) = fixture();
    let dir = root.path().join("Pub/Book");
    let bad = json!({"generator":"rpg-source-select","schema_version":1,"documents":[{"generator":"rpg-source-select","work_id":"x","pdf":"Amber Almanac.pdf","markdown":"Amber Almanac.md","status":"published"}]});
    let bytes = serde_json::to_vec(&bad).unwrap();
    fs::write(dir.join("current-documents.json"), &bytes).unwrap();
    let r = convert(out.path(), &[]);
    assert_eq!(r["published_books"], 0);
    assert_eq!(fs::read(dir.join("current-documents.json")).unwrap(), bytes);
    assert!(!dir.join("Amber Almanac.md").exists());
}
