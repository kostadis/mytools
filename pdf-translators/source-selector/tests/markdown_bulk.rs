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
    let _serial = SERIAL.lock().unwrap();
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
    let _serial = SERIAL.lock().unwrap();
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
    let _serial = SERIAL.lock().unwrap();
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
}
