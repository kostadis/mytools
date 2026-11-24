mod common;
use rpg_source_select::{
    markdown::{adjacent, publication, selection},
    store::Store,
};
use serde_json::Value;
use std::{fs, process::Command};
static SERIAL: std::sync::Mutex<()> = std::sync::Mutex::new(());
fn cli(args: &[&str]) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .args(args)
        .output()
        .unwrap()
}
fn read_bytes() -> u64 {
    let s = fs::read_to_string("/proc/thread-self/io").unwrap();
    s.lines()
        .find_map(|v| v.strip_prefix("rchar: "))
        .unwrap()
        .trim()
        .parse()
        .unwrap()
}
fn fixture() -> (tempfile::TempDir, tempfile::TempDir, tempfile::TempDir) {
    let root = tempfile::tempdir().unwrap();
    let work = tempfile::tempdir().unwrap();
    let out = tempfile::tempdir().unwrap();
    fs::create_dir_all(root.path().join("Pub/Book")).unwrap();
    let pdf = root.path().join("Pub/Book/Book.pdf");
    common::pdf(
        &pdf,
        "A searchable amber dragon reference.",
        "D:20210101000000Z",
        false,
    );
    let mut doc = lopdf::Document::load(&pdf).unwrap();
    doc.add_object(lopdf::Stream::new(
        lopdf::Dictionary::new(),
        vec![b'x'; 8 * 1024 * 1024],
    ));
    doc.save(&pdf).unwrap();
    assert!(
        cli(&[
            "--work-dir",
            work.path().to_str().unwrap(),
            "scan",
            "--root",
            root.path().to_str().unwrap()
        ])
        .status
        .success()
    );
    (root, work, out)
}
#[test]
fn repeated_metadata_selection_reuses_verified_hash_for_unhashed_singleton() {
    let _serial = SERIAL.lock().unwrap_or_else(|p| p.into_inner());
    let (_root, work, out) = fixture();
    let store = Store::open_readonly(&work.path().join("selection.db")).unwrap();
    selection::select(&store, out.path(), None).unwrap();
    let before = read_bytes();
    let s = selection::select(&store, out.path(), None).unwrap();
    let read = read_bytes() - before;
    assert_eq!(s.ready.len(), 1);
    assert!(
        read < 1024 * 1024,
        "resume reread {read} bytes rather than using verified metadata/hash checkpoints"
    );
}
#[test]
fn unchanged_publication_avoids_rereading_large_pdf_but_detects_manual_edit() {
    let _serial = SERIAL.lock().unwrap_or_else(|p| p.into_inner());
    let (root, work, out) = fixture();
    selection::select(
        &Store::open_readonly(&work.path().join("selection.db")).unwrap(),
        out.path(),
        None,
    )
    .unwrap();
    let r = cli(&[
        "markdown-convert",
        "--output",
        out.path().to_str().unwrap(),
        "--publish-next-to-source",
    ]);
    assert!(r.status.success(), "{}", String::from_utf8_lossy(&r.stderr));
    let s = selection::load_current(out.path()).unwrap();
    let mut session = adjacent::Session::new(out.path(), &s).unwrap();
    let c: Value =
        serde_json::from_slice(&fs::read(out.path().join("corpus/current/catalog.json")).unwrap())
            .unwrap();
    let engine = serde_json::from_value(c["engine"].clone()).unwrap();
    publication::publish_with_destination(out.path(), &engine, Some(&mut session)).unwrap();
    let before = read_bytes();
    publication::publish_with_destination(out.path(), &engine, Some(&mut session)).unwrap();
    let read = read_bytes() - before;
    assert!(
        read < 2 * 1024 * 1024,
        "unchanged publication reread {read} bytes"
    );
    let pdf = root.path().join("Pub/Book/Book.pdf");
    let original = fs::read(&pdf).unwrap();
    let mut changed = original.clone();
    changed.extend_from_slice(b"\nsource changed\n");
    fs::write(&pdf, changed).unwrap();
    assert_eq!(
        publication::publish_with_destination(out.path(), &engine, Some(&mut session))
            .unwrap()
            .books,
        0
    );
    fs::write(&pdf, original).unwrap();
    assert_eq!(
        publication::publish_with_destination(out.path(), &engine, Some(&mut session))
            .unwrap()
            .books,
        1
    );
    fs::write(root.path().join("Pub/Book/Book.md"), "User notes").unwrap();
    assert_eq!(
        publication::publish_with_destination(out.path(), &engine, Some(&mut session))
            .unwrap()
            .books,
        0
    );
    assert_eq!(
        fs::read_to_string(root.path().join("Pub/Book/Book.md")).unwrap(),
        "User notes"
    );
}
#[test]
fn bulk_publication_interval_and_hardlinks_preserve_final_current_view() {
    let _serial = SERIAL.lock().unwrap_or_else(|p| p.into_inner());
    use std::os::unix::fs::MetadataExt;
    let (root, work, out) = fixture();
    for i in 0..3 {
        let folder = root.path().join(format!("Pub/Other{i}"));
        fs::create_dir_all(&folder).unwrap();
        common::pdf(
            &folder.join(format!("Other{i}.pdf")),
            &format!("Another useful searchable reference {i}."),
            "D:20210101000000Z",
            false,
        );
    }
    assert!(
        cli(&[
            "--work-dir",
            work.path().to_str().unwrap(),
            "scan",
            "--root",
            root.path().to_str().unwrap()
        ])
        .status
        .success()
    );
    selection::select(
        &Store::open_readonly(&work.path().join("selection.db")).unwrap(),
        out.path(),
        None,
    )
    .unwrap();
    let r = cli(&[
        "markdown-convert",
        "--output",
        out.path().to_str().unwrap(),
        "--publish-next-to-source",
        "--publish-every",
        "100",
    ]);
    assert!(r.status.success(), "{}", String::from_utf8_lossy(&r.stderr));
    let report: Value = serde_json::from_slice(&r.stdout).unwrap();
    assert_eq!(report["published_books"], 4);
    let c: Value =
        serde_json::from_slice(&fs::read(out.path().join("corpus/current/catalog.json")).unwrap())
            .unwrap();
    let b = &c["books"][0];
    let current = out
        .path()
        .join("corpus/current/books")
        .join(format!("{}.md", b["work"]["work_id"].as_str().unwrap()));
    let artifact = out
        .path()
        .join("artifacts")
        .join(b["artifact"].as_str().unwrap())
        .join("book.md");
    assert_eq!(
        fs::metadata(current).unwrap().ino(),
        fs::metadata(artifact).unwrap().ino()
    );
    let current = out
        .path()
        .join("corpus/current/books")
        .join(format!("{}.md", b["work"]["work_id"].as_str().unwrap()));
    assert!(
        fs::write(&current, "in-place edit").is_err(),
        "shared immutable payload must be read-only"
    );
}
#[cfg(unix)]
#[test]
fn rollout_checks_output_before_touching_control_files() {
    use std::os::unix::fs::symlink;
    let _serial = SERIAL.lock().unwrap_or_else(|p| p.into_inner());
    let (root, work, out) = fixture();
    let pdf = root.path().join("Pub/Book/Book.pdf");
    let before = fs::read(&pdf).unwrap();
    symlink(&pdf, out.path().join("rollout.lock")).unwrap();
    let r = cli(&[
        "--work-dir",
        work.path().to_str().unwrap(),
        "markdown-rollout",
        "--output",
        out.path().to_str().unwrap(),
    ]);
    assert!(!r.status.success());
    assert_eq!(fs::read(&pdf).unwrap(), before);
    assert!(String::from_utf8_lossy(&r.stderr).contains("symlink"));
    let bad = root.path().join("forbidden");
    let r = cli(&[
        "--work-dir",
        work.path().to_str().unwrap(),
        "markdown-rollout",
        "--output",
        bad.to_str().unwrap(),
    ]);
    assert!(!r.status.success());
    assert!(!bad.exists());
}
#[test]
fn conversion_refuses_a_selection_different_from_the_preflight_id() {
    let _serial = SERIAL.lock().unwrap_or_else(|p| p.into_inner());
    let (_root, work, out) = fixture();
    selection::select(
        &Store::open_readonly(&work.path().join("selection.db")).unwrap(),
        out.path(),
        None,
    )
    .unwrap();
    let r = cli(&[
        "markdown-convert",
        "--output",
        out.path().to_str().unwrap(),
        "--expected-selection",
        "wrong-selection",
    ]);
    assert!(!r.status.success());
    assert!(String::from_utf8_lossy(&r.stderr).contains("changed since preflight"));
}
#[test]
fn rollout_reselects_after_a_user_hold_without_a_new_scan() {
    use rpg_source_select::{models::*, review::evidence_digest};
    let _serial = SERIAL.lock().unwrap_or_else(|p| p.into_inner());
    let (root, work, out) = fixture();
    let mut db = Store::open(&work.path().join("selection.db")).unwrap();
    assert_eq!(
        selection::select(&db, out.path(), None)
            .unwrap()
            .ready
            .len(),
        1
    );
    let group = db.records::<Group>("groups").unwrap().remove(0);
    let decision = Decision {
        packet_ids: vec![],
        source_hashes: Default::default(),
        group_id: group.group_id.clone(),
        membership_digest: group.membership_digest.clone(),
        evidence_digest: evidence_digest(&group, &[]),
        actor: "user".into(),
        actor_role: ActorRole::User,
        outcomes: group
            .source_ids
            .iter()
            .map(|id| Outcome {
                source_id: id.clone(),
                status: Status::NeedsReview,
                work_id: None,
                representative_id: None,
                successor_id: None,
            })
            .collect(),
        rationale: "Hold this work".into(),
        evidence_refs: vec![],
    };
    db.save_decision(&decision).unwrap();
    drop(db);
    let r = cli(&[
        "--work-dir",
        work.path().to_str().unwrap(),
        "markdown-rollout",
        "--output",
        out.path().to_str().unwrap(),
    ]);
    assert!(r.status.success(), "{}", String::from_utf8_lossy(&r.stderr));
    assert!(
        selection::load_current(out.path())
            .unwrap()
            .ready
            .is_empty()
    );
    assert!(!root.path().join("Pub/Book/Book.md").exists());
}
#[test]
fn older_shared_artifact_payloads_are_made_read_only_before_rollout() {
    let _serial = SERIAL.lock().unwrap_or_else(|p| p.into_inner());
    let (_root, work, out) = fixture();
    selection::select(
        &Store::open_readonly(&work.path().join("selection.db")).unwrap(),
        out.path(),
        None,
    )
    .unwrap();
    let old = out.path().join("artifacts").join("a".repeat(64));
    fs::create_dir_all(&old).unwrap();
    fs::write(old.join("book.md"), "old generated text").unwrap();
    fs::write(old.join("book.json"), "{}").unwrap();
    let linked = out.path().join("old-generation.md");
    fs::hard_link(old.join("book.md"), &linked).unwrap();
    let r = cli(&["markdown-convert", "--output", out.path().to_str().unwrap()]);
    assert!(r.status.success());
    assert!(fs::write(linked, "in-place edit").is_err());
}
