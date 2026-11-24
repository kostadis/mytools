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
fn first_pass_caps_large_competing_pdfs_and_does_not_grow_on_rerun() {
    use rpg_source_select::store::Store;
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    for version in 1..=2 {
        let path = root.path().join(format!("Reference-v{version}.pdf"));
        common::pdf(
            &path,
            &format!("Edition {version}, useful reference text."),
            "D:20260101",
            false,
        );
        common::pages(&path, 100);
    }
    assert!(
        cli(
            work.path(),
            &["scan", "--root", root.path().to_str().unwrap()]
        )
        .status
        .success()
    );
    let first = cli(work.path(), &["inspect"]);
    assert!(
        first.status.success(),
        "{}",
        String::from_utf8_lossy(&first.stderr)
    );
    let db = Store::open_readonly(&work.path().join("selection.db")).unwrap();
    let evidence = db.evidence().unwrap();
    assert_eq!(evidence.len(), 2);
    for e in evidence {
        assert_eq!(
            e.pages.iter().map(|p| p.page).collect::<Vec<_>>(),
            vec![1, 2, 3, 4, 100]
        );
        assert_eq!(e.page_count, 100);
        assert!(e.pdf_metadata.contains_key("_text_extractor"));
    }
    let again = cli(work.path(), &["inspect"]);
    let v: serde_json::Value = serde_json::from_slice(&again.stdout).unwrap();
    assert_eq!(v["inspected_sources"], 0);
    assert_eq!(v["reused_sources"], 2);
    let more = cli(work.path(), &["inspect", "--pages", "5"]);
    assert!(!more.status.success());
    assert!(String::from_utf8_lossy(&more.stderr).contains("five-page"));
    for e in db.evidence().unwrap() {
        assert_eq!(e.pages.len(), 5);
    }
    let export = cli(work.path(), &["export"]);
    let v: serde_json::Value = serde_json::from_slice(&export.stdout).unwrap();
    assert_eq!(v["counts"]["needs_review"], 2);
    assert_eq!(v["counts"]["queue"], 0);
}

#[test]
fn first_pass_rejects_more_than_five_explicit_pages() {
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    let path = root.path().join("reference.pdf");
    common::pdf(&path, "reference text", "", false);
    common::pages(&path, 100);
    assert!(
        cli(
            work.path(),
            &["scan", "--root", root.path().to_str().unwrap()]
        )
        .status
        .success()
    );
    let out = cli(work.path(), &["inspect", "--pages", "1-6"]);
    assert_eq!(out.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&out.stderr).contains("five-page"));
}

#[test]
fn late_identical_copy_reuses_a_nondefault_sample_without_new_extraction() {
    use rpg_source_select::store::Store;
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    let path = root.path().join("reference.pdf");
    common::pdf(&path, "Useful edition reference.", "", false);
    common::pages(&path, 100);
    assert!(
        cli(
            work.path(),
            &["scan", "--root", root.path().to_str().unwrap()]
        )
        .status
        .success()
    );
    assert!(
        cli(work.path(), &["inspect", "--pages", "10-14"])
            .status
            .success()
    );
    fs::copy(&path, root.path().join("copy.pdf")).unwrap();
    assert!(
        cli(
            work.path(),
            &["scan", "--root", root.path().to_str().unwrap()]
        )
        .status
        .success()
    );
    let out = cli(
        work.path(),
        &["inspect", "--pdftotext", "/not/an/extractor"],
    );
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let db = Store::open_readonly(&work.path().join("selection.db")).unwrap();
    for e in db.evidence().unwrap() {
        assert_eq!(
            e.pages.iter().map(|p| p.page).collect::<Vec<_>>(),
            vec![10, 11, 12, 13, 14]
        );
    }
}

#[cfg(unix)]
#[test]
fn filling_a_sample_preserves_earlier_warnings_and_batch_attribution() {
    use rpg_source_select::store::Store;
    use std::os::unix::fs::PermissionsExt;
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    let path = root.path().join("reference.pdf");
    common::pdf(&path, "Useful edition reference.", "", false);
    common::pages(&path, 100);
    let extractor = work.path().join("extractor");
    fs::write(&extractor,"#!/bin/sh\nif [ \"$1\" != '-v' ]; then echo 'earlier sample warning' >&2; fi\nexec pdftotext \"$@\"\n").unwrap();
    fs::set_permissions(&extractor, fs::Permissions::from_mode(0o700)).unwrap();
    assert!(
        cli(
            work.path(),
            &["scan", "--root", root.path().to_str().unwrap()]
        )
        .status
        .success()
    );
    assert!(
        cli(
            work.path(),
            &[
                "inspect",
                "--pages",
                "1-2",
                "--pdftotext",
                extractor.to_str().unwrap()
            ]
        )
        .status
        .success()
    );
    assert!(cli(work.path(), &["inspect"]).status.success());
    let db = Store::open_readonly(&work.path().join("selection.db")).unwrap();
    let e = db.evidence().unwrap().remove(0);
    assert!(
        e.errors
            .iter()
            .any(|s| s.contains("earlier sample warning"))
    );
    let batches = e.pdf_metadata["_extraction_batches"].as_array().unwrap();
    assert!(
        batches
            .iter()
            .any(|b| b["pages"] == serde_json::json!([1, 2])
                && b["extractor"]["binary"] == extractor.to_str().unwrap())
    );
    assert!(
        batches
            .iter()
            .any(|b| b["pages"] == serde_json::json!([3, 4, 100])
                && b["extractor"]["binary"] == "pdftotext")
    );
}

#[test]
fn first_pass_fills_only_the_remaining_budget_of_an_earlier_sample() {
    use rpg_source_select::store::Store;
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    let path = root.path().join("reference.pdf");
    common::pdf(&path, "Useful reference text.", "", false);
    common::pages(&path, 100);
    assert!(
        cli(
            work.path(),
            &["scan", "--root", root.path().to_str().unwrap()]
        )
        .status
        .success()
    );
    assert!(
        cli(work.path(), &["inspect", "--pages", "1,50,100"])
            .status
            .success()
    );
    let default = cli(work.path(), &["inspect"]);
    assert!(
        default.status.success(),
        "{}",
        String::from_utf8_lossy(&default.stderr)
    );
    let db = Store::open_readonly(&work.path().join("selection.db")).unwrap();
    assert_eq!(
        db.evidence().unwrap()[0]
            .pages
            .iter()
            .map(|p| p.page)
            .collect::<Vec<_>>(),
        vec![1, 2, 3, 50, 100]
    );
    let again = cli(work.path(), &["inspect"]);
    let v: serde_json::Value = serde_json::from_slice(&again.stdout).unwrap();
    assert_eq!(v["inspected_sources"], 0);
    assert_eq!(v["reused_sources"], 1);
}

#[cfg(unix)]
#[test]
fn first_pass_keeps_successful_extraction_warnings() {
    use rpg_source_select::store::Store;
    use std::os::unix::fs::PermissionsExt;
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    common::pdf(
        &root.path().join("reference.pdf"),
        "Useful reference text.",
        "",
        false,
    );
    let extractor = work.path().join("extractor");
    fs::write(&extractor, "#!/bin/sh\nif [ \"$1\" != '-v' ]; then echo 'sample extraction warning' >&2; fi\nexec pdftotext \"$@\"\n").unwrap();
    fs::set_permissions(&extractor, fs::Permissions::from_mode(0o700)).unwrap();
    assert!(
        cli(
            work.path(),
            &["scan", "--root", root.path().to_str().unwrap()]
        )
        .status
        .success()
    );
    assert!(
        cli(
            work.path(),
            &["inspect", "--pdftotext", extractor.to_str().unwrap()]
        )
        .status
        .success()
    );
    let db = Store::open_readonly(&work.path().join("selection.db")).unwrap();
    assert!(
        db.evidence().unwrap()[0]
            .errors
            .iter()
            .any(|e| e.contains("sample extraction warning"))
    );
}

#[test]
fn first_pass_reuses_sample_for_identical_bytes_and_caps_singletons() {
    use rpg_source_select::store::Store;
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    let path = root.path().join("reference.pdf");
    common::pdf(
        &path,
        "Useful reference text and edition information.",
        "",
        false,
    );
    common::pages(&path, 100);
    assert!(
        cli(
            work.path(),
            &["scan", "--root", root.path().to_str().unwrap()]
        )
        .status
        .success()
    );
    assert!(cli(work.path(), &["inspect"]).status.success());
    let db = Store::open_readonly(&work.path().join("selection.db")).unwrap();
    let evidence = db.evidence().unwrap();
    assert_eq!(evidence[0].pages.len(), 5);
    let original_id = evidence[0].source_id.clone();
    let mut original = evidence[0].clone();
    original.claims.push(rpg_source_select::models::Claim {
        claim_id: "original-source-claim".into(),
        kind: "title".into(),
        value: "reference".into(),
        source_id: original_id.clone(),
        page: 1,
        quote: "Useful reference text".into(),
        actor: "test-reader".into(),
        role: rpg_source_select::models::ActorRole::Reader,
    });
    Store::open(&work.path().join("selection.db"))
        .unwrap()
        .save_evidence(&original)
        .unwrap();
    fs::copy(&path, root.path().join("copy.pdf")).unwrap();
    assert!(
        cli(
            work.path(),
            &["scan", "--root", root.path().to_str().unwrap()]
        )
        .status
        .success()
    );
    let out = cli(
        work.path(),
        &["inspect", "--pdftotext", "/not/an/extractor"],
    );
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let v: serde_json::Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(v["reused_byte_samples"], 1);
    let evidence = db.evidence().unwrap();
    assert_eq!(evidence.len(), 2);
    for e in evidence {
        assert_eq!(e.pages.len(), 5);
        if e.source_id == original_id {
            assert_eq!(e.claims.len(), 1);
        } else {
            assert!(e.claims.is_empty());
            assert_eq!(e.pdf_metadata["_sample_reused_from_source"], original_id);
        }
    }
}
#[test]
fn scan_logs_each_hundred_and_saves_a_complete_inventory_journal() {
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    for i in 0..201 {
        fs::write(root.path().join(format!("book-{i}.pdf")), b"same").unwrap();
    }
    let out = cli(
        work.path(),
        &["scan", "--root", root.path().to_str().unwrap()],
    );
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let log = String::from_utf8_lossy(&out.stderr);
    assert!(log.contains("inventory: 100 sources"));
    assert!(log.contains("inventory: 200 sources"));
    assert!(log.contains("hashes: 100/201"));
    assert!(log.contains("hashes: 200/201"));
    let journal = fs::read_to_string(work.path().join("inventory-progress.jsonl")).unwrap();
    let rows: Vec<serde_json::Value> = journal
        .lines()
        .map(|l| serde_json::from_str(l).unwrap())
        .collect();
    assert_eq!(rows.iter().filter(|r| r["type"] == "source").count(), 201);
    assert_eq!(rows.last().unwrap()["type"], "inventory-finished");
    let again = cli(
        work.path(),
        &["scan", "--root", root.path().to_str().unwrap()],
    );
    assert!(again.status.success());
    assert!(String::from_utf8_lossy(&again.stderr).contains("201 reused"));
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
