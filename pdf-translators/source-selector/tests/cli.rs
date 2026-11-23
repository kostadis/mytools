mod common;
use std::{fs, path::Path, process::Command};
use tempfile::tempdir;
fn run(args: &[&str]) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .args(args)
        .output()
        .unwrap()
}
fn cli(work: &Path, args: &[&str]) -> std::process::Output {
    let mut a = vec!["--work-dir", work.to_str().unwrap()];
    a.extend(args);
    run(&a)
}
#[test]
fn help_and_work_directory_guards_work_without_models() {
    assert!(run(&["--help"]).status.success());
    let root = tempdir().unwrap();
    common::pdf(
        &root.path().join("book.pdf"),
        "Reference",
        "D:20260101",
        false,
    );
    let out = cli(
        &root.path().join("state"),
        &["scan", "--root", root.path().to_str().unwrap()],
    );
    assert!(!out.status.success());
    assert!(!root.path().join("state").exists());
}
#[test]
fn miniature_library_inspect_export_and_resume_do_not_change_sources() {
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    let book = root.path().join("book.pdf");
    common::pdf(&book, "Useful GM reference.", "D:20260101", false);
    let before = fs::read(&book).unwrap();
    let scan = cli(
        work.path(),
        &["scan", "--root", root.path().to_str().unwrap()],
    );
    assert!(
        scan.status.success(),
        "{}",
        String::from_utf8_lossy(&scan.stderr)
    );
    let inspect = cli(work.path(), &["inspect", "--limit", "1"]);
    assert!(
        inspect.status.success(),
        "{}",
        String::from_utf8_lossy(&inspect.stderr)
    );
    let publish = cli(work.path(), &["export"]);
    assert!(
        publish.status.success(),
        "{}",
        String::from_utf8_lossy(&publish.stderr)
    );
    let result: serde_json::Value = serde_json::from_slice(&publish.stdout).unwrap();
    assert_eq!(result["counts"]["queue"], 1);
    let again = cli(work.path(), &["inspect", "--limit", "1"]);
    assert!(again.status.success());
    let result: serde_json::Value = serde_json::from_slice(&again.stdout).unwrap();
    assert_eq!(result["inspected_sources"], 0);
    assert_eq!(result["reused_sources"], 1);
    assert_eq!(fs::read(&book).unwrap(), before);
    assert!(
        cli(work.path(), &["inspect", "--group", "not-a-group"])
            .status
            .code()
            .is_some_and(|c| c != 0)
    );
    assert!(
        !cli(work.path(), &["inspect", "--pages", "99"])
            .status
            .success()
    );
    assert!(cli(work.path(), &["status"]).status.success());
}
#[test]
fn failed_reading_does_not_stop_other_books_and_missing_root_preserves_state() {
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    common::pdf(
        &root.path().join("good.pdf"),
        "good text",
        "D:20260101",
        false,
    );
    fs::write(root.path().join("bad.pdf"), b"broken").unwrap();
    assert!(
        cli(
            work.path(),
            &["scan", "--root", root.path().to_str().unwrap()]
        )
        .status
        .success()
    );
    let out = cli(work.path(), &["inspect", "--limit", "10"]);
    let result: serde_json::Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(result["inspected_sources"], 1);
    assert_eq!(result["failed_sources"], 1);
    assert!(!out.status.success());
    assert!(
        !cli(work.path(), &["scan", "--root", "/definitely/not/mounted"])
            .status
            .success()
    );
    assert!(cli(work.path(), &["export"]).status.success());
    let published = cli(work.path(), &["export"]);
    let result: serde_json::Value = serde_json::from_slice(&published.stdout).unwrap();
    let snapshot: serde_json::Value = serde_json::from_slice(
        &fs::read(result["files"]["selection.json"].as_str().unwrap()).unwrap(),
    )
    .unwrap();
    assert!(
        snapshot["errors"]
            .as_array()
            .unwrap()
            .iter()
            .any(|e| e.as_str().unwrap().contains("bad.pdf"))
    );
}

#[test]
fn issued_user_packets_can_record_distinct_works_but_unknown_sources_are_rejected() {
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    common::pdf(
        &root.path().join("book-v1.pdf"),
        "First work",
        "D:20200101",
        false,
    );
    common::pdf(
        &root.path().join("book-v3.pdf"),
        "Distinct work",
        "D:20260101",
        false,
    );
    assert!(
        cli(
            work.path(),
            &["scan", "--root", root.path().to_str().unwrap()]
        )
        .status
        .success()
    );
    assert!(cli(work.path(), &["inspect"]).status.success());
    let packets = work.path().join("review.jsonl");
    let out = cli(
        work.path(),
        &[
            "review",
            "export",
            "--role",
            "user",
            "--out",
            packets.to_str().unwrap(),
        ],
    );
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let row: serde_json::Value = serde_json::from_str(
        fs::read_to_string(&packets)
            .unwrap()
            .lines()
            .next()
            .unwrap(),
    )
    .unwrap();
    let mut response = row["response_template"].clone();
    response["decision"]["rationale"] = serde_json::json!("GM confirms these are separate works");
    for outcome in response["decision"]["outcomes"].as_array_mut().unwrap() {
        outcome["status"] = serde_json::json!("distinct_work");
    }
    let file = work.path().join("response.json");
    fs::write(&file, serde_json::to_vec(&response).unwrap()).unwrap();
    let imported = cli(
        work.path(),
        &["review", "import", "--file", file.to_str().unwrap()],
    );
    assert!(
        imported.status.success(),
        "{}",
        String::from_utf8_lossy(&imported.stderr)
    );
    let out = cli(work.path(), &["export"]);
    assert!(out.status.success());
    let value: serde_json::Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(value["counts"]["queue"], 2);
    response["decision"]["outcomes"][0]["source_id"] = serde_json::json!("../../outside.pdf");
    fs::write(&file, serde_json::to_vec(&response).unwrap()).unwrap();
    assert!(
        !cli(
            work.path(),
            &["review", "import", "--file", file.to_str().unwrap()]
        )
        .status
        .success()
    );
}
#[cfg(unix)]
#[test]
fn non_utf8_filenames_remain_lossless_in_the_json_manifest() {
    use std::os::unix::ffi::OsStringExt;
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    let p = root
        .path()
        .join(std::ffi::OsString::from_vec(b"book-\xff.pdf".to_vec()));
    common::pdf(
        &p,
        "Reference text for a searchable source document.",
        "D:20260101",
        false,
    );
    assert!(
        cli(
            work.path(),
            &["scan", "--root", root.path().to_str().unwrap()]
        )
        .status
        .success()
    );
    assert!(cli(work.path(), &["inspect"]).status.success());
    let out = cli(work.path(), &["export"]);
    assert!(out.status.success());
    let result: serde_json::Value = serde_json::from_slice(&out.stdout).unwrap();
    let manifest: serde_json::Value = serde_json::from_slice(
        &fs::read(result["files"]["selection.json"].as_str().unwrap()).unwrap(),
    )
    .unwrap();
    assert!(
        manifest["queue"][0]["relative_path"]["unix_bytes"]
            .as_array()
            .unwrap()
            .iter()
            .any(|v| v.as_u64() == Some(255))
    );
}
