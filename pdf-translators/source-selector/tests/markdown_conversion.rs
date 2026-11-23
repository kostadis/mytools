mod common;
use rpg_source_select::{markdown::selection, store::Store};
use serde_json::Value;
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
};
use tempfile::TempDir;
fn cli(args: &[&str]) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .args(args)
        .output()
        .unwrap()
}
fn fixture(text: &str, pages: usize) -> (TempDir, TempDir, TempDir) {
    let root = tempfile::tempdir().unwrap();
    let state = tempfile::tempdir().unwrap();
    let out = tempfile::tempdir().unwrap();
    fs::create_dir_all(root.path().join("Pub/Book")).unwrap();
    let pdf = root.path().join("Pub/Book/Book.pdf");
    common::pdf(&pdf, text, "D:20220101000000Z", false);
    common::pages(&pdf, pages);
    assert!(
        cli(&[
            "--work-dir",
            state.path().to_str().unwrap(),
            "scan",
            "--root",
            root.path().to_str().unwrap()
        ])
        .status
        .success()
    );
    selection::select(
        &Store::open_readonly(&state.path().join("selection.db")).unwrap(),
        out.path(),
        None,
    )
    .unwrap();
    (root, state, out)
}
fn convert(out: &Path, extra: &[&str]) -> Value {
    let mut args = vec![
        "markdown-convert",
        "--output",
        out.to_str().unwrap(),
        "--chunk-pages",
        "1",
    ];
    args.extend(extra);
    let r = cli(&args);
    assert!(r.status.success(), "{}", String::from_utf8_lossy(&r.stderr));
    serde_json::from_slice(&r.stdout).unwrap()
}
fn files(root: &Path, ext: &str) -> Vec<PathBuf> {
    let mut out = vec![];
    for f in fs::read_dir(root).unwrap() {
        let p = f.unwrap().path();
        if p.is_dir() {
            out.extend(files(&p, ext));
        } else if p.extension().is_some_and(|e| e == ext) {
            out.push(p);
        }
    }
    out
}
#[test]
fn full_pages_searchable_and_resume_repairs_corrupt_range() {
    let (root, _state, out) = fixture("Searchable amber dragon <b>literal</b> & # heading", 3);
    let before =
        rpg_source_select::grouping::hash_source(&root.path().join("Pub/Book/Book.pdf")).unwrap();
    let r = convert(out.path(), &[]);
    assert_eq!(r["published_books"], 1);
    assert_eq!(r["extracted_ranges"], 3);
    let books = files(&out.path().join("corpus/current/books"), "md");
    assert_eq!(books.len(), 1);
    let body = fs::read_to_string(&books[0]).unwrap();
    assert_eq!(body.matches("## PDF page ").count(), 3);
    assert!(body.contains("Searchable amber dragon"));
    assert!(body.contains("&lt;b&gt;literal&lt;/b&gt;"));
    assert!(body.contains(&before));
    let ranges = files(&out.path().join("cache/pages"), "json");
    let old = fs::read(&ranges[0]).unwrap();
    fs::remove_dir_all(root.path()).unwrap();
    let r = convert(out.path(), &[]);
    assert_eq!(r["extracted_ranges"], 0);
    assert_eq!(r["reused_ranges"], 3);
    assert_eq!(fs::read(&ranges[0]).unwrap(), old);
    fs::write(&ranges[0], "corrupt").unwrap();
    let r = convert(out.path(), &[]);
    assert_eq!(r["extracted_ranges"], 1);
    assert_eq!(r["reused_ranges"], 2);
}
#[test]
fn zero_text_does_not_publish_empty_markdown() {
    let (_root, _state, out) = fixture("", 2);
    let r = convert(out.path(), &[]);
    assert_eq!(r["published_books"], 0);
    assert_eq!(r["needs_ocr_or_visual_review"], 1);
    assert!(!out.path().join("corpus/current").exists());
}
#[test]
fn policy_refresh_reassembles_and_stale_worker_cannot_restore_old_source() {
    use rpg_source_select::markdown::{publication, worker::Engine};
    let (root, state, out) = fixture("Original amber dragon words for the first edition.", 2);
    convert(out.path(), &[]);
    let old_pointer = fs::read_link(out.path().join("corpus/current")).unwrap();
    let sidecar: Value = serde_json::from_slice(
        &fs::read(files(&out.path().join("corpus/current/books"), "json")[0].clone()).unwrap(),
    )
    .unwrap();
    let engine: Engine = serde_json::from_value(sidecar["engine"].clone()).unwrap();
    let request = files(&out.path().join("jobs"), "json")[0].clone();
    let old_job = fs::read(&request).unwrap();
    selection::select(
        &Store::open_readonly(&state.path().join("selection.db")).unwrap(),
        out.path(),
        None,
    )
    .unwrap();
    let r = convert(out.path(), &[]);
    assert_eq!(r["extracted_ranges"], 0);
    assert_ne!(
        fs::read_link(out.path().join("corpus/current")).unwrap(),
        old_pointer
    );
    common::pdf(
        &root.path().join("Pub/Book/Book.pdf"),
        "New silver dragon source, replacing the previously selected content.",
        "D:20230101000000Z",
        false,
    );
    assert!(
        cli(&[
            "--work-dir",
            state.path().to_str().unwrap(),
            "scan",
            "--root",
            root.path().to_str().unwrap()
        ])
        .status
        .success()
    );
    selection::select(
        &Store::open_readonly(&state.path().join("selection.db")).unwrap(),
        out.path(),
        None,
    )
    .unwrap();
    let pointer = fs::read_link(out.path().join("corpus/current")).unwrap();
    fs::write(&request, old_job).unwrap();
    assert!(
        cli(&["markdown-worker", "--job", request.to_str().unwrap()])
            .status
            .success()
    );
    let p = publication::publish(out.path(), &engine).unwrap();
    assert!(p.pending);
    assert_eq!(p.books, 0);
    assert_eq!(
        fs::read_link(out.path().join("corpus/current")).unwrap(),
        pointer
    );
    convert(out.path(), &[]);
    let book = fs::read_to_string(files(&out.path().join("corpus/current/books"), "md")[0].clone())
        .unwrap();
    assert!(book.contains("New silver dragon"));
    assert!(!book.contains("Original amber dragon"));
}
#[test]
fn changed_source_fails_hash_binding_and_source_root_output_is_rejected() {
    let (root, state, out) = fixture("Frozen source text.", 1);
    common::pdf(
        &root.path().join("Pub/Book/Book.pdf"),
        "Changed text.",
        "D:20230101000000Z",
        false,
    );
    let r = convert(out.path(), &[]);
    assert_eq!(r["failed"], 1);
    assert_eq!(r["published_books"], 0);
    let r = cli(&[
        "--work-dir",
        state.path().to_str().unwrap(),
        "markdown-select",
        "--output",
        root.path().join("bad-output").to_str().unwrap(),
    ]);
    assert!(!r.status.success());
    assert!(!root.path().join("bad-output").exists());
}
#[cfg(unix)]
#[test]
fn failed_range_resumes_and_other_worker_can_publish() {
    use std::os::unix::fs::PermissionsExt;
    let (root, state, out) = fixture(
        "A reference with several searchable words about an amber dragon.",
        3,
    );
    let dir = root.path().join("Pub/Other");
    fs::create_dir_all(&dir).unwrap();
    common::pdf(
        &dir.join("Other.pdf"),
        "Other useful book with many searchable words about silver dragons.",
        "D:20220101000000Z",
        false,
    );
    assert!(
        cli(&[
            "--work-dir",
            state.path().to_str().unwrap(),
            "scan",
            "--root",
            root.path().to_str().unwrap()
        ])
        .status
        .success()
    );
    selection::select(
        &Store::open_readonly(&state.path().join("selection.db")).unwrap(),
        out.path(),
        None,
    )
    .unwrap();
    let wrapper = out.path().join("extractor");
    let marker = out.path().join("allow");
    let script = format!(
        "#!/bin/sh\nif [ \"$1\" != '-v' ] && [ ! -f '{}' ]; then\n case \"$*\" in *'-f 2 '*) exit 17;; esac\nfi\nexec /usr/bin/pdftotext \"$@\"\n",
        marker.display()
    );
    fs::write(&wrapper, script).unwrap();
    fs::set_permissions(&wrapper, fs::Permissions::from_mode(0o755)).unwrap();
    let r = convert(out.path(), &["--pdftotext", wrapper.to_str().unwrap()]);
    assert_eq!(r["failed"], 1);
    assert_eq!(r["published_books"], 1);
    fs::write(marker, "").unwrap();
    let r = convert(
        out.path(),
        &["--pdftotext", wrapper.to_str().unwrap(), "--retry-failed"],
    );
    assert_eq!(r["published_books"], 2);
    assert!(r["reused_ranges"].as_u64().unwrap() >= 2);
}
