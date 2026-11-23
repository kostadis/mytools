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
fn force_corrupt(path: impl AsRef<Path>, text: &str) {
    use std::os::unix::fs::PermissionsExt;
    let path = path.as_ref();
    let mode = fs::metadata(path).unwrap().permissions().mode();
    fs::set_permissions(path, fs::Permissions::from_mode(mode | 0o200)).unwrap();
    fs::write(path, text).unwrap();
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
fn interrupted_or_corrupt_artifacts_rebuild_from_verified_ranges() {
    let (_root, _state, out) = fixture("Verified amber dragon text.", 2);
    convert(out.path(), &[]);
    let catalog: Value =
        serde_json::from_slice(&fs::read(out.path().join("corpus/current/catalog.json")).unwrap())
            .unwrap();
    let artifact = out
        .path()
        .join("artifacts")
        .join(catalog["books"][0]["artifact"].as_str().unwrap());
    fs::remove_file(artifact.join("book.json")).unwrap();
    fs::remove_dir_all(out.path().join("corpus")).unwrap();
    let r = convert(out.path(), &[]);
    assert_eq!(r["extracted_ranges"], 0);
    assert_eq!(r["published_books"], 1);
    force_corrupt(artifact.join("book.md"), "corrupt artifact");
    let current = files(&out.path().join("corpus/current/books"), "md")[0].clone();
    force_corrupt(&current, "corrupt generation");
    let r = convert(out.path(), &[]);
    assert_eq!(r["extracted_ranges"], 0);
    assert!(
        fs::read_to_string(current)
            .unwrap()
            .contains("Verified amber dragon")
    );
}
#[cfg(unix)]
#[test]
fn source_mutation_during_extraction_never_publishes_or_caches_invalid_ranges() {
    use std::os::unix::fs::PermissionsExt;
    let (_root, _state, out) = fixture("Frozen searchable amber dragon words.", 2);
    let wrapper = out.path().join("extractor");
    fs::write(&wrapper,"#!/bin/sh\n/usr/bin/pdftotext \"$@\" || exit $?\nif [ \"$1\" != '-v' ]; then for arg do case \"$arg\" in *.pdf) printf '\\n' >> \"$arg\";; esac; done; fi\n").unwrap();
    fs::set_permissions(&wrapper, fs::Permissions::from_mode(0o755)).unwrap();
    let r = convert(out.path(), &["--pdftotext", wrapper.to_str().unwrap()]);
    assert_eq!(r["failed"], 1);
    assert_eq!(r["published_books"], 0);
    let cache = out.path().join("cache/pages");
    assert!(!cache.exists() || files(&cache, "json").is_empty());
}
#[cfg(target_os = "linux")]
#[test]
fn job_deadline_terminates_the_separate_extractor_process_group() {
    use std::os::unix::fs::PermissionsExt;
    let (_root, _state, out) = fixture("Frozen searchable amber dragon words.", 1);
    let wrapper = out.path().join("extractor");
    let marker = out.path().join("extractor.pid");
    fs::write(&wrapper,format!("#!/bin/sh\nif [ \"$1\" = '-v' ]; then exec /usr/bin/pdftotext \"$@\"; fi\necho $$ > '{}'\nsleep 60\n",marker.display())).unwrap();
    fs::set_permissions(&wrapper, fs::Permissions::from_mode(0o755)).unwrap();
    let r = convert(
        out.path(),
        &[
            "--pdftotext",
            wrapper.to_str().unwrap(),
            "--timeout-secs",
            "30",
            "--job-timeout-secs",
            "1",
        ],
    );
    assert_eq!(r["failed"], 1);
    let pid = fs::read_to_string(marker).unwrap().trim().to_string();
    std::thread::sleep(std::time::Duration::from_millis(100));
    let alive = fs::read_to_string(format!("/proc/{pid}/stat"))
        .is_ok_and(|s| !s.rsplit_once(") ").unwrap().1.starts_with("Z "));
    let _ = Command::new("/bin/kill")
        .args(["-KILL", "--", &format!("-{pid}")])
        .output();
    assert!(!alive, "extractor outlived job deadline");
}
#[test]
fn bounded_batches_reach_unfinished_books_and_cached_original_changes_defer() {
    let (root, state, out) = fixture("Original amber dragon reference.", 1);
    let dir = root.path().join("Pub/Other");
    fs::create_dir_all(&dir).unwrap();
    common::pdf(
        &dir.join("Other.pdf"),
        "Independent silver dragon reference.",
        "D:20210101000000Z",
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
    assert_eq!(convert(out.path(), &["--limit", "1"])["published_books"], 1);
    assert_eq!(convert(out.path(), &["--limit", "1"])["published_books"], 2);
    common::pdf(
        &root.path().join("Pub/Book/Book.pdf"),
        "Changed original after successful cache",
        "D:20230101000000Z",
        false,
    );
    let r = convert(out.path(), &[]);
    assert_eq!(r["failed"], 1);
    assert_eq!(r["published_books"], 1);
    assert_eq!(
        r["publication"]["pending_works"][0]["status"],
        "source_changed"
    );
}
#[test]
fn cached_source_cannot_mask_accessible_original_change_and_old_view_is_explicit() {
    let (root, _state, out) = fixture("Original amber dragon.", 1);
    let first = convert(out.path(), &[]);
    let pointer = fs::read_link(out.path().join("corpus/current")).unwrap();
    common::pdf(
        &root.path().join("Pub/Book/Book.pdf"),
        "Changed original after cache exists.",
        "D:20230101000000Z",
        false,
    );
    let r = convert(out.path(), &[]);
    assert_eq!(r["failed"], 1);
    assert_eq!(r["published_books"], 0);
    assert_eq!(
        r["publication"]["published_snapshot"],
        first["selection_id"]
    );
    assert_eq!(
        r["publication"]["pending_works"][0]["status"],
        "source_changed"
    );
    assert_eq!(
        fs::read_link(out.path().join("corpus/current")).unwrap(),
        pointer
    );
}
#[test]
fn existing_artifact_and_generation_bytes_are_checked_before_reuse() {
    let (_root, _state, out) = fixture("Verified amber dragon.", 1);
    convert(out.path(), &[]);
    let catalog: Value =
        serde_json::from_slice(&fs::read(out.path().join("corpus/current/catalog.json")).unwrap())
            .unwrap();
    let artifact = out
        .path()
        .join("artifacts")
        .join(catalog["books"][0]["artifact"].as_str().unwrap());
    let book = files(&out.path().join("corpus/current/books"), "md")[0].clone();
    force_corrupt(artifact.join("book.md"), "damaged artifact");
    force_corrupt(&book, "damaged generation");
    convert(out.path(), &[]);
    assert!(
        fs::read_to_string(book)
            .unwrap()
            .contains("Verified amber dragon")
    );
}
#[cfg(unix)]
#[test]
fn non_utf8_path_preserves_byte_safe_front_matter() {
    use std::os::unix::ffi::OsStringExt;
    let (root, state, out) = fixture("Amber dragon.", 1);
    let dir = root.path().join("Pub/Other");
    fs::create_dir_all(&dir).unwrap();
    common::pdf(
        &dir.join(std::ffi::OsString::from_vec(b"other\xff.pdf".to_vec())),
        "Silver dragon.",
        "D:20210101000000Z",
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
    let r = convert(out.path(), &[]);
    assert_eq!(r["published_books"], 2);
    assert!(
        files(&out.path().join("corpus/current/books"), "md")
            .iter()
            .any(|f| fs::read_to_string(f).unwrap().contains("unix_bytes"))
    );
}
#[cfg(unix)]
#[test]
fn abandoned_pointer_is_recovered_and_non_utf8_book_does_not_abort_batch() {
    use std::os::unix::ffi::OsStringExt;
    let (root, state, out) = fixture("Amber dragon.", 1);
    let dir = root.path().join("Pub/Other");
    fs::create_dir_all(&dir).unwrap();
    common::pdf(
        &dir.join(std::ffi::OsString::from_vec(b"other\xff.pdf".to_vec())),
        "Silver dragon.",
        "D:20210101000000Z",
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
    fs::create_dir_all(out.path().join("corpus")).unwrap();
    let abandoned = out.path().join("corpus/.current-999999");
    std::os::unix::fs::symlink("generations/abc", &abandoned).unwrap();
    let r = convert(out.path(), &[]);
    assert_eq!(r["published_books"], 2);
    assert!(abandoned.symlink_metadata().is_err());
}
#[cfg(unix)]
#[test]
fn range_delimiters_prove_empty_pages_and_reject_truncated_output() {
    use std::os::unix::fs::PermissionsExt;
    for good in [false, true] {
        let (_root, _state, out) = fixture("Actual PDF reference.", 2);
        let wrapper = out.path().join("extractor");
        let text = if good {
            "Readable reference words\\f\\f"
        } else {
            "Readable reference words\\f"
        };
        fs::write(&wrapper,format!("#!/bin/sh\nif [ \"$1\" = '-v' ]; then exec /usr/bin/pdftotext \"$@\"; fi\nprintf '{text}'\n")).unwrap();
        fs::set_permissions(&wrapper, fs::Permissions::from_mode(0o755)).unwrap();
        let r = cli(&[
            "markdown-convert",
            "--output",
            out.path().to_str().unwrap(),
            "--pdftotext",
            wrapper.to_str().unwrap(),
            "--chunk-pages",
            "2",
        ]);
        assert!(r.status.success(), "{}", String::from_utf8_lossy(&r.stderr));
        let r: Value = serde_json::from_slice(&r.stdout).unwrap();
        if good {
            assert_eq!(r["published_books"], 1);
            assert!(
                fs::read_to_string(
                    files(&out.path().join("corpus/current/books"), "md")[0].clone()
                )
                .unwrap()
                .contains("No native text extracted for this page.")
            );
        } else {
            assert_eq!(r["failed"], 1);
            assert_eq!(r["published_books"], 0);
            assert_eq!(r["publication"]["pending_works"][0]["status"], "failed");
            assert_eq!(
                r["publication"]["pending_works"][0]["missing_ranges"][0]["last"],
                2
            );
        }
    }
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
    assert_eq!(r["publication"]["pending_works"][0]["status"], "failed");
    assert_eq!(
        r["publication"]["pending_works"][0]["missing_ranges"]
            .as_array()
            .unwrap()
            .len(),
        2
    );
    fs::write(marker, "").unwrap();
    let r = convert(
        out.path(),
        &["--pdftotext", wrapper.to_str().unwrap(), "--retry-failed"],
    );
    assert_eq!(r["published_books"], 2);
    assert!(r["reused_ranges"].as_u64().unwrap() >= 2);
}
