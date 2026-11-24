mod common;
use rpg_source_select::{models::Group, store::Store};
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

#[test]
fn current_downloads_convert_each_variant_without_date_exclusion_and_resume() {
    let root = tempfile::tempdir().unwrap();
    let state = tempfile::tempdir().unwrap();
    let out = tempfile::tempdir().unwrap();
    let dir = root.path().join("Publisher/Book");
    fs::create_dir_all(&dir).unwrap();
    common::pdf(
        &dir.join("Book_v1.pdf"),
        "Searchable old-named publisher-delivered PDF.",
        "not a valid date",
        false,
    );
    common::pdf(
        &dir.join("Book_v2.pdf"),
        "Searchable other publisher-delivered PDF.",
        "D:20260101000000Z",
        false,
    );
    fs::copy(dir.join("Book_v2.pdf"), dir.join("Book_print.pdf")).unwrap();
    common::pdf(&dir.join("Book_maps.pdf"), "", "", false);
    run(
        state.path(),
        &[
            "scan",
            "--root",
            root.path().to_str().unwrap(),
            "--current-library",
        ],
    );
    let db = Store::open_readonly(&state.path().join("selection.db")).unwrap();
    let groups = db.records::<Group>("groups").unwrap();
    assert_eq!(groups.len(), 4);
    assert!(groups.iter().all(|g| g.source_ids.len() == 1));
    let r = run(
        state.path(),
        &[
            "markdown-continuous",
            "--output",
            out.path().to_str().unwrap(),
        ],
    );
    assert_eq!(r["published"], 3, "{r}");
    assert_eq!(r["needs_ocr"], 1);
    assert_eq!(r["groups_deferred"], 0);
    for name in ["Book_v1", "Book_v2", "Book_print"] {
        let md = fs::read_to_string(dir.join(format!("{name}.md"))).unwrap();
        assert!(md.contains(&format!("[Source PDF]({name}.pdf)")));
        assert!(md.contains("owner_confirmed_current_download"));
    }
    let saved = fs::read(dir.join("Book_v1.md")).unwrap();
    let m: Value =
        serde_json::from_slice(&fs::read(dir.join("current-documents.json")).unwrap()).unwrap();
    assert_eq!(m["documents"].as_array().unwrap().len(), 4);
    let again = run(
        state.path(),
        &[
            "markdown-continuous",
            "--output",
            out.path().to_str().unwrap(),
        ],
    );
    assert_eq!(again["published"], 3);
    assert_eq!(fs::read(dir.join("Book_v1.md")).unwrap(), saved);
}

#[test]
fn current_downloads_preserve_manual_markdown() {
    let root = tempfile::tempdir().unwrap();
    let state = tempfile::tempdir().unwrap();
    let out = tempfile::tempdir().unwrap();
    let dir = root.path().join("Publisher/Book");
    fs::create_dir_all(&dir).unwrap();
    common::pdf(
        &dir.join("Book.pdf"),
        "A useful searchable reference.",
        "",
        false,
    );
    fs::write(dir.join("Book.md"), "My manual notes").unwrap();
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
            "markdown-continuous",
            "--output",
            out.path().to_str().unwrap(),
        ],
    );
    assert_eq!(r["published"], 0);
    assert_eq!(r["output_conflicts"], 1);
    assert_eq!(
        fs::read_to_string(dir.join("Book.md")).unwrap(),
        "My manual notes"
    );
}

#[test]
fn current_library_keeps_explicit_holds_and_cannot_silently_change_policy() {
    let root = tempfile::tempdir().unwrap();
    let state = tempfile::tempdir().unwrap();
    let out = tempfile::tempdir().unwrap();
    let dir = root.path().join("Publisher/Book");
    fs::create_dir_all(&dir).unwrap();
    common::pdf(
        &dir.join("Book.pdf"),
        "Useful native reference text.",
        "",
        false,
    );
    run(
        state.path(),
        &[
            "scan",
            "--root",
            root.path().to_str().unwrap(),
            "--current-library",
        ],
    );
    let mut db = Store::open(&state.path().join("selection.db")).unwrap();
    let g = db.records::<Group>("groups").unwrap().remove(0);
    db.put_record("decisions",&g.group_id,&serde_json::json!({
        "group_id":g.group_id,"membership_digest":g.membership_digest,"evidence_digest":"",
        "actor":"user","actor_role":"user","outcomes":[{"source_id":g.source_ids[0],"status":"needs_review","work_id":null,"representative_id":null,"successor_id":null}],
        "rationale":"Hold this file","evidence_refs":[]
    })).unwrap();
    let r = run(
        state.path(),
        &[
            "markdown-continuous",
            "--output",
            out.path().to_str().unwrap(),
        ],
    );
    assert_eq!(r["published"], 0);
    assert_eq!(r["groups_deferred"], 1);
    assert!(!dir.join("Book.md").exists());
    let before = db.records::<Group>("groups").unwrap()[0]
        .membership_digest
        .clone();
    let r = Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .arg("--work-dir")
        .arg(state.path())
        .args(["scan", "--root"])
        .arg(root.path())
        .output()
        .unwrap();
    assert!(!r.status.success());
    assert!(String::from_utf8_lossy(&r.stderr).contains("library policy changed"));
    assert_eq!(
        db.meta("current_library").unwrap(),
        Some(serde_json::json!(true))
    );
    assert_eq!(
        db.records::<Group>("groups").unwrap()[0].membership_digest,
        before
    );
}

#[test]
fn colliding_sibling_targets_are_not_published_or_overwritten() {
    let root = tempfile::tempdir().unwrap();
    let state = tempfile::tempdir().unwrap();
    let out = tempfile::tempdir().unwrap();
    let dir = root.path().join("Publisher/Book");
    fs::create_dir_all(&dir).unwrap();
    common::pdf(&dir.join("Book.pdf"), "Amber reference.", "", false);
    common::pdf(&dir.join("Book.PDF"), "Silver reference.", "", false);
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
            "markdown-continuous",
            "--output",
            out.path().to_str().unwrap(),
        ],
    );
    assert_eq!(r["published"], 0);
    assert_eq!(r["groups_deferred"], 2);
    assert!(!dir.join("Book.md").exists());
}

#[test]
fn explicitly_confirmed_baselines_remain_protected_in_current_mode() {
    let root = tempfile::tempdir().unwrap();
    let state = tempfile::tempdir().unwrap();
    let out = tempfile::tempdir().unwrap();
    let dir = root.path().join("Publisher/Book");
    fs::create_dir_all(&dir).unwrap();
    let pdf = dir.join("Book.pdf");
    common::pdf(&pdf, "Protected explicit baseline.", "", false);
    let baseline = state.path().join("baseline.json");
    fs::write(&baseline,serde_json::to_vec(&serde_json::json!({"sources":[{"relative_path":"Publisher/Book/Book.pdf","sha256":rpg_source_select::grouping::hash_source(&pdf).unwrap()}]})).unwrap()).unwrap();
    run(
        state.path(),
        &[
            "scan",
            "--root",
            root.path().to_str().unwrap(),
            "--current-library",
            "--baseline-manifest",
            baseline.to_str().unwrap(),
        ],
    );
    let r = run(
        state.path(),
        &[
            "markdown-continuous",
            "--output",
            out.path().to_str().unwrap(),
        ],
    );
    assert_eq!(r["published"], 0);
    assert_eq!(r["groups_deferred"], 1);
    assert!(!dir.join("Book.md").exists());
}

#[test]
fn concurrent_scan_is_rejected_before_overwriting_progress_or_policy() {
    let root = tempfile::tempdir().unwrap();
    let state = tempfile::tempdir().unwrap();
    let dir = root.path().join("Publisher/Book");
    fs::create_dir_all(&dir).unwrap();
    common::pdf(&dir.join("Book.pdf"), "Native reference.", "", false);
    let _lease = rpg_source_select::markdown::lock(state.path(), "scan.lock").unwrap();
    let journal = state.path().join("inventory-progress.jsonl");
    fs::write(&journal, "active scan checkpoint\n").unwrap();
    let r = Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .arg("--work-dir")
        .arg(state.path())
        .args(["scan", "--root"])
        .arg(root.path())
        .arg("--current-library")
        .output()
        .unwrap();
    assert!(!r.status.success());
    assert!(String::from_utf8_lossy(&r.stderr).contains("scan.lock"));
    assert_eq!(
        fs::read_to_string(journal).unwrap(),
        "active scan checkpoint\n"
    );
}

#[cfg(unix)]
#[test]
fn continuous_conversion_can_run_four_isolated_workers() {
    use std::{
        os::unix::fs::PermissionsExt,
        process::Stdio,
        time::{Duration, Instant},
    };
    let root = tempfile::tempdir().unwrap();
    let state = tempfile::tempdir().unwrap();
    // /tmp is a small tmpfs; four extraction windows must preserve the real
    // 20 GiB floor. Use the same disk-backed location as the deployed cache.
    let out = tempfile::tempdir_in(Path::new(env!("CARGO_MANIFEST_DIR")).join("target")).unwrap();
    let dir = root.path().join("Publisher/Book");
    fs::create_dir_all(&dir).unwrap();
    for i in 0..4 {
        common::pdf(
            &dir.join(format!("Book_{i}.pdf")),
            &format!("Distinct native reference number {i}."),
            "",
            false,
        );
    }
    run(
        state.path(),
        &[
            "scan",
            "--root",
            root.path().to_str().unwrap(),
            "--current-library",
        ],
    );
    let gate = out.path().join("release");
    let wrapper = out.path().join("extractor");
    fs::write(&wrapper,format!("#!/bin/sh\nif [ \"$1\" = '-v' ]; then exec /usr/bin/pdftotext \"$@\"; fi\ntouch '{}/started-'$$\nwhile [ ! -e '{}' ]; do sleep 0.02; done\nexec /usr/bin/pdftotext \"$@\"\n",out.path().display(),gate.display())).unwrap();
    fs::set_permissions(&wrapper, fs::Permissions::from_mode(0o755)).unwrap();
    let log = fs::File::create(out.path().join("run.log")).unwrap();
    let mut child = Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .arg("--work-dir")
        .arg(state.path())
        .args(["markdown-continuous", "--workers", "4", "--output"])
        .arg(out.path())
        .arg("--pdftotext")
        .arg(wrapper)
        .stdout(Stdio::piped())
        .stderr(log)
        .spawn()
        .unwrap();
    let start = Instant::now();
    let mut count = 0;
    while start.elapsed() < Duration::from_secs(10) {
        count = fs::read_dir(out.path())
            .unwrap()
            .filter_map(Result::ok)
            .filter(|e| e.file_name().to_string_lossy().starts_with("started-"))
            .count();
        if count == 4 || child.try_wait().unwrap().is_some() {
            break;
        }
        std::thread::sleep(Duration::from_millis(20));
    }
    fs::write(gate, "").unwrap();
    let result = child.wait_with_output().unwrap();
    assert!(
        result.status.success(),
        "{}",
        fs::read_to_string(out.path().join("run.log")).unwrap()
    );
    assert_eq!(
        count, 4,
        "four different extractors must be active before release"
    );
    let report: Value = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(report["published"], 4);
}
