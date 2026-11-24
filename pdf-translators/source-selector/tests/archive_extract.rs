mod common;
use serde_json::Value;
use std::{fs, path::Path, process::Command};

fn run(state: &Path, args: &[&str]) -> Value {
    let r = Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .arg("--work-dir")
        .arg(state)
        .args(args)
        .output()
        .unwrap();
    assert!(r.status.success(), "{}", String::from_utf8_lossy(&r.stderr));
    serde_json::from_slice(&r.stdout).unwrap()
}
fn zip(path: &Path, nested: bool, bad: bool) {
    let code = "import sys,zipfile,io\np,n,b=sys.argv[1:]\nwith zipfile.ZipFile(p,'w') as z:\n z.writestr('../outside.txt' if b=='1' else 'book.txt','archive text')\n if n=='1':\n  x=io.BytesIO()\n  with zipfile.ZipFile(x,'w') as q:q.writestr('inside.pdf','pdf fixture bytes')\n  z.writestr('inner.zip',x.getvalue())\n";
    assert!(
        Command::new("python3")
            .args(["-c", code])
            .arg(path)
            .args([if nested { "1" } else { "0" }, if bad { "1" } else { "0" }])
            .status()
            .unwrap()
            .success()
    );
}
fn extractor() -> String {
    std::env::var("RPG_ARCHIVE_EXTRACTOR").expect("set RPG_ARCHIVE_EXTRACTOR to bsdtar")
}

#[test]
#[ignore = "requires explicit native bsdtar path"]
fn nested_archives_extract_and_resume_without_overwriting_user_edits() {
    let root = tempfile::tempdir().unwrap();
    let state = tempfile::tempdir().unwrap();
    let out = tempfile::tempdir().unwrap();
    zip(&root.path().join("books.zip"), true, false);
    run(
        state.path(),
        &[
            "scan",
            "--root",
            root.path().to_str().unwrap(),
            "--current-library",
        ],
    );
    let r = run(
        state.path(),
        &[
            "archive-extract",
            "--output",
            out.path().to_str().unwrap(),
            "--extractor",
            &extractor(),
        ],
    );
    assert_eq!(r["completed"], 2);
    assert_eq!(r["pdfs"], 1);
    assert_eq!(r["failed"], 0);
    let dest = root.path().join("books.zip.extracted");
    assert_eq!(
        fs::read_to_string(dest.join("book.txt")).unwrap(),
        "archive text"
    );
    assert!(dest.join("inner.zip.extracted/inside.pdf").exists());
    fs::write(dest.join("book.txt"), "user edit").unwrap();
    let again = run(
        state.path(),
        &[
            "archive-extract",
            "--output",
            out.path().to_str().unwrap(),
            "--extractor",
            &extractor(),
        ],
    );
    assert_eq!(again["reused"], 2);
    assert_eq!(
        fs::read_to_string(dest.join("book.txt")).unwrap(),
        "user edit"
    );
}

#[test]
#[ignore = "requires explicit native bsdtar path"]
fn existing_destination_is_preserved_and_bad_archive_is_individual_failure() {
    let root = tempfile::tempdir().unwrap();
    let state = tempfile::tempdir().unwrap();
    let out = tempfile::tempdir().unwrap();
    zip(&root.path().join("books.zip"), false, false);
    fs::write(root.path().join("bad.zip"), "not an archive").unwrap();
    fs::create_dir(root.path().join("books.zip.extracted")).unwrap();
    fs::write(root.path().join("books.zip.extracted/notes"), "manual").unwrap();
    run(
        state.path(),
        &[
            "scan",
            "--root",
            root.path().to_str().unwrap(),
            "--current-library",
        ],
    );
    let r = run(
        state.path(),
        &[
            "archive-extract",
            "--output",
            out.path().to_str().unwrap(),
            "--extractor",
            &extractor(),
        ],
    );
    assert_eq!(r["conflicts"], 1);
    assert_eq!(r["failed"], 1);
    assert_eq!(
        fs::read_to_string(root.path().join("books.zip.extracted/notes")).unwrap(),
        "manual"
    );
    assert!(!root.path().join("bad.zip.extracted").exists());
}

#[test]
#[ignore = "requires explicit native bsdtar path"]
fn traversal_archive_cannot_overwrite_files_outside_its_stage() {
    let root = tempfile::tempdir().unwrap();
    let state = tempfile::tempdir().unwrap();
    let out = tempfile::tempdir().unwrap();
    zip(&root.path().join("bad.zip"), false, true);
    fs::write(root.path().join("outside.txt"), "preserve me").unwrap();
    run(
        state.path(),
        &[
            "scan",
            "--root",
            root.path().to_str().unwrap(),
            "--current-library",
        ],
    );
    let r = run(
        state.path(),
        &[
            "archive-extract",
            "--output",
            out.path().to_str().unwrap(),
            "--extractor",
            &extractor(),
        ],
    );
    assert_eq!(r["failed"], 1);
    assert_eq!(
        fs::read_to_string(root.path().join("outside.txt")).unwrap(),
        "preserve me"
    );
    assert!(!root.path().join("bad.zip.extracted").exists());
}

#[test]
fn inventory_ignores_incomplete_archive_staging_but_reads_published_contents() {
    let root = tempfile::tempdir().unwrap();
    let state = tempfile::tempdir().unwrap();
    let partial = root.path().join(".rpg-archive-staging/job");
    let published = root.path().join("book.zip.extracted");
    fs::create_dir_all(&partial).unwrap();
    fs::create_dir(&published).unwrap();
    common::pdf(
        &partial.join("partial.pdf"),
        "Incomplete content.",
        "",
        false,
    );
    common::pdf(&published.join("book.pdf"), "Completed content.", "", false);
    let r = run(
        state.path(),
        &[
            "scan",
            "--root",
            root.path().to_str().unwrap(),
            "--current-library",
        ],
    );
    assert_eq!(r["sources"], 1);
    assert_eq!(r["groups"], 1);
}

#[test]
#[ignore = "requires explicit native bsdtar path"]
fn recovered_receipts_cannot_adopt_replaced_staging_or_destinations() {
    for phase in ["extracted", "complete"] {
        let root = tempfile::tempdir().unwrap();
        let state = tempfile::tempdir().unwrap();
        let out = tempfile::tempdir().unwrap();
        zip(&root.path().join("book.zip"), false, false);
        run(
            state.path(),
            &[
                "scan",
                "--root",
                root.path().to_str().unwrap(),
                "--current-library",
            ],
        );
        let args = [
            "archive-extract",
            "--output",
            out.path().to_str().unwrap(),
            "--extractor",
            &extractor(),
        ];
        run(state.path(), &args);
        let record = fs::read_dir(out.path().join("records"))
            .unwrap()
            .next()
            .unwrap()
            .unwrap()
            .path();
        let mut receipt: Value = serde_json::from_slice(&fs::read(&record).unwrap()).unwrap();
        let dest = root.path().join("book.zip.extracted");
        fs::rename(&dest, root.path().join("saved-original")).unwrap();
        if phase == "extracted" {
            let stage = Path::new(receipt["stage"].as_str().unwrap());
            fs::create_dir(stage).unwrap();
            fs::write(stage.join("manual"), "keep").unwrap();
        } else {
            fs::create_dir(&dest).unwrap();
            fs::write(dest.join("manual"), "keep").unwrap();
        }
        receipt["status"] = phase.into();
        fs::write(&record, serde_json::to_vec(&receipt).unwrap()).unwrap();
        let r = run(state.path(), &args);
        assert_eq!(r["completed"], 0, "{phase}: {r}");
        assert_eq!(
            r["failed"].as_u64().unwrap() + r["conflicts"].as_u64().unwrap(),
            1
        );
        assert_eq!(
            fs::read_to_string(root.path().join("saved-original/book.txt")).unwrap(),
            "archive text"
        );
    }
}

#[test]
#[ignore = "requires explicit native bsdtar path"]
fn interrupted_owned_stages_are_reclaimed_before_retry() {
    for phase in ["running", "capacity_pending"] {
        let root = tempfile::tempdir().unwrap();
        let state = tempfile::tempdir().unwrap();
        let out = tempfile::tempdir().unwrap();
        zip(&root.path().join("book.zip"), false, false);
        run(
            state.path(),
            &[
                "scan",
                "--root",
                root.path().to_str().unwrap(),
                "--current-library",
            ],
        );
        let args = [
            "archive-extract",
            "--output",
            out.path().to_str().unwrap(),
            "--extractor",
            &extractor(),
        ];
        run(state.path(), &args);
        let path = fs::read_dir(out.path().join("records"))
            .unwrap()
            .next()
            .unwrap()
            .unwrap()
            .path();
        let mut receipt: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        let stage = Path::new(receipt["stage"].as_str().unwrap()).to_path_buf();
        fs::rename(root.path().join("book.zip.extracted"), &stage).unwrap();
        receipt["status"] = phase.into();
        fs::write(&path, serde_json::to_vec(&receipt).unwrap()).unwrap();
        let r = run(state.path(), &args);
        assert_eq!(r["completed"], 1);
        assert!(!stage.exists(), "owned {phase} stage leaked");
    }
}

#[cfg(unix)]
#[test]
#[ignore = "requires explicit native bsdtar path"]
fn receipt_recovery_rejects_symlinks_to_genuine_owned_directories() {
    for phase in ["extracted", "complete"] {
        let root = tempfile::tempdir().unwrap();
        let state = tempfile::tempdir().unwrap();
        let out = tempfile::tempdir().unwrap();
        zip(&root.path().join("book.zip"), false, false);
        run(
            state.path(),
            &[
                "scan",
                "--root",
                root.path().to_str().unwrap(),
                "--current-library",
            ],
        );
        let args = [
            "archive-extract",
            "--output",
            out.path().to_str().unwrap(),
            "--extractor",
            &extractor(),
        ];
        run(state.path(), &args);
        let path = fs::read_dir(out.path().join("records"))
            .unwrap()
            .next()
            .unwrap()
            .unwrap()
            .path();
        let mut receipt: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        let saved = root.path().join("saved");
        let dest = root.path().join("book.zip.extracted");
        fs::rename(&dest, &saved).unwrap();
        let link = if phase == "extracted" {
            Path::new(receipt["stage"].as_str().unwrap()).to_path_buf()
        } else {
            dest.clone()
        };
        std::os::unix::fs::symlink(&saved, &link).unwrap();
        receipt["status"] = phase.into();
        fs::write(&path, serde_json::to_vec(&receipt).unwrap()).unwrap();
        let r = run(state.path(), &args);
        assert_eq!(r["completed"], 0, "{phase}: {r}");
        assert_eq!(
            fs::read_to_string(saved.join("book.txt")).unwrap(),
            "archive text"
        );
    }
}

#[test]
#[ignore = "requires RPG_ARCHIVE_LOW_SPACE_DIR pointing at a writable filesystem with under20GiB free"]
fn capacity_pause_returns_retryable_exit_and_keeps_queue() {
    let root = tempfile::tempdir().unwrap();
    let state = tempfile::tempdir().unwrap();
    let out = tempfile::tempdir_in(std::env::var_os("RPG_ARCHIVE_LOW_SPACE_DIR").unwrap()).unwrap();
    fs::write(root.path().join("book.zip"), "fixture archive").unwrap();
    run(
        state.path(),
        &[
            "scan",
            "--root",
            root.path().to_str().unwrap(),
            "--current-library",
        ],
    );
    let r = Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .arg("--work-dir")
        .arg(state.path())
        .arg("archive-extract")
        .arg("--output")
        .arg(out.path())
        .args(["--extractor", "/bin/true"])
        .output()
        .unwrap();
    let s: Value = serde_json::from_slice(&r.stdout).unwrap();
    assert_eq!(s["phase"], "capacity_pending");
    assert_eq!(s["queued"], 1);
    assert_eq!(r.status.code(), Some(75));
}
