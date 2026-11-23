mod common;
use rpg_source_select::{
    markdown::{metadata, selection},
    models::*,
    store::Store,
};
use std::{fs, path::Path, process::Command};
use tempfile::{TempDir, tempdir};
fn scan(root: &Path, state: &Path) {
    let r = Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .arg("--work-dir")
        .arg(state)
        .args(["scan", "--root"])
        .arg(root)
        .output()
        .unwrap();
    assert!(r.status.success(), "{}", String::from_utf8_lossy(&r.stderr));
}
fn fixture() -> (TempDir, TempDir, TempDir) {
    let root = tempdir().unwrap();
    let state = tempdir().unwrap();
    let out = tempfile::tempdir_in(Path::new(env!("CARGO_MANIFEST_DIR")).join("target")).unwrap();
    fs::create_dir_all(root.path().join("Pub/Book")).unwrap();
    common::pdf(
        &root.path().join("Pub/Book/Chronicle.pdf"),
        "Searchable chronicle",
        "D:20220101000000Z",
        false,
    );
    scan(root.path(), state.path());
    (root, state, out)
}
#[test]
fn shared_group_policy_and_semantic_revision_survive_observation_changes() {
    let (root, state, out) = fixture();
    let db = Store::open_readonly(&state.path().join("selection.db")).unwrap();
    let group = db.records::<Group>("groups").unwrap().remove(0);
    let src = db.sources().unwrap().remove(0);
    let mut cache = Store::open(&out.path().join("metadata.db")).unwrap();
    assert!(
        metadata::cached(root.path(), &src, &db, &cache)
            .unwrap()
            .is_none()
    );
    let c = metadata::probe(root.path(), &src, &db, &mut cache);
    assert!(
        metadata::cached(root.path(), &src, &db, &cache)
            .unwrap()
            .is_some()
    );
    let s = selection::resolve_group(
        &db,
        out.path(),
        root.path(),
        &group,
        vec![c.clone()],
        &serde_json::Value::Null,
    )
    .unwrap();
    let batch = selection::select(&db, out.path(), None).unwrap();
    assert_eq!(s.ready[0].source_id, batch.ready[0].source_id);
    let mut changed = c;
    changed.source.fingerprint.mtime_ns = Some(123);
    let s2 = selection::resolve_group(
        &db,
        out.path(),
        root.path(),
        &group,
        vec![changed],
        &serde_json::Value::Null,
    )
    .unwrap();
    assert_eq!(s.snapshot_id, s2.snapshot_id);
    assert!(
        selection::resolve_group(
            &db,
            out.path(),
            root.path(),
            &group,
            vec![],
            &serde_json::Value::Null
        )
        .is_err()
    );
}
fn options(out: &Path) -> rpg_source_select::markdown::conversion::Options {
    rpg_source_select::markdown::conversion::Options {
        output: out.into(),
        expected_selection: None,
        publish_every: 1,
        publish_next_to_source: true,
        workers: 2,
        chunk_pages: 20,
        timeout_secs: 10,
        job_timeout_secs: 30,
        limit: usize::MAX,
        retry_failed: false,
        pdftotext: "pdftotext".into(),
    }
}
#[test]
fn scoped_manifest_preserves_unresolved_neighbor_and_retires_only_known_group() {
    use rpg_source_select::markdown::{adjacent, conversion, publication};
    let (root, state, out) = fixture();
    let db = Store::open_readonly(&state.path().join("selection.db")).unwrap();
    let s = selection::select(&db, out.path(), None).unwrap();
    let r = Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .arg("markdown-convert")
        .arg("--output")
        .arg(out.path())
        .arg("--publish-next-to-source")
        .output()
        .unwrap();
    assert!(r.status.success(), "{}", String::from_utf8_lossy(&r.stderr));
    let folder = root.path().join("Pub/Book");
    let before = fs::read(folder.join("Chronicle.md")).unwrap();
    let mut scoped = s.clone();
    scoped.ready.clear();
    scoped.records.clear();
    scoped.snapshot_id = "unrelated".into();
    let mut session = adjacent::Session::new_scoped(out.path(), &s).unwrap();
    let engine = conversion::engine(&options(out.path())).unwrap();
    publication::publish_snapshot(out.path(), &engine, &scoped, Some(&mut session), false).unwrap();
    let m: serde_json::Value =
        serde_json::from_slice(&fs::read(folder.join("current-documents.json")).unwrap()).unwrap();
    assert_eq!(m["documents"].as_array().unwrap().len(), 1);
    let mut revoked = s;
    revoked.ready.clear();
    revoked.records[0].status = "deferred_choice".into();
    revoked.records[0].reason = "user hold".into();
    revoked.snapshot_id = "held".into();
    publication::publish_snapshot(out.path(), &engine, &revoked, Some(&mut session), false)
        .unwrap();
    let m: serde_json::Value =
        serde_json::from_slice(&fs::read(folder.join("current-documents.json")).unwrap()).unwrap();
    assert_eq!(m["schema_version"], 2);
    assert!(m["documents"].as_array().unwrap().is_empty());
    assert_eq!(before, fs::read(folder.join("Chronicle.md")).unwrap());
}
#[test]
fn cached_group_publishes_while_uncached_metadata_is_gated_and_resumes_without_rewrite() {
    use std::os::unix::fs::PermissionsExt;
    use std::time::{Duration, Instant};
    let (root, state, out) = fixture();
    let db = Store::open_readonly(&state.path().join("selection.db")).unwrap();
    selection::select(&db, out.path(), None).unwrap();
    drop(db);
    fs::create_dir_all(root.path().join("Pub/Slow")).unwrap();
    common::pdf(
        &root.path().join("Pub/Slow/Atlas-v1.pdf"),
        "A different delayed atlas",
        "D:20200101000000Z",
        false,
    );
    common::pdf(
        &root.path().join("Pub/Slow/Atlas-v2.pdf"),
        "Newer delayed atlas",
        "D:20230101000000Z",
        false,
    );
    scan(root.path(), state.path());
    let db = Store::open_readonly(&state.path().join("selection.db")).unwrap();
    let source = db
        .sources()
        .unwrap()
        .into_iter()
        .find(|s| s.relative_path.ends_with("Atlas-v1.pdf"))
        .unwrap();
    let mut cache = Store::open(&out.path().join("metadata.db")).unwrap();
    assert!(
        metadata::probe(root.path(), &source, &db, &mut cache)
            .error
            .is_none()
    );
    drop(cache);
    drop(db);
    let gate = out.path().join("release");
    let wrapper = out.path().join("metadata-wrapper");
    fs::write(
        &wrapper,
        format!(
            "#!/bin/sh\nwhile [ ! -e '{}' ]; do sleep 0.05; done\nexec '{}' \"$@\"\n",
            gate.display(),
            env!("CARGO_BIN_EXE_rpg-source-select")
        ),
    )
    .unwrap();
    fs::set_permissions(&wrapper, fs::Permissions::from_mode(0o755)).unwrap();
    let log = fs::File::create(out.path().join("test.log")).unwrap();
    let mut child = Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .arg("--work-dir")
        .arg(state.path())
        .arg("markdown-continuous")
        .arg("--output")
        .arg(out.path())
        .arg("--metadata-worker")
        .arg(&wrapper)
        .stdout(log.try_clone().unwrap())
        .stderr(log)
        .spawn()
        .unwrap();
    let markdown = root.path().join("Pub/Book/Chronicle.md");
    let start = Instant::now();
    while !markdown.exists()
        && start.elapsed() < Duration::from_secs(15)
        && child.try_wait().unwrap().is_none()
    {
        std::thread::sleep(Duration::from_millis(50));
    }
    let early = markdown.exists();
    let partial_group_unpublished = !root.path().join("Pub/Slow/Atlas-v1.md").exists()
        && !root.path().join("Pub/Slow/Atlas-v2.md").exists();
    let status: serde_json::Value = fs::read(out.path().join("continuous-status.json"))
        .ok()
        .and_then(|b| serde_json::from_slice(&b).ok())
        .unwrap_or_default();
    let before = fs::read(&markdown).ok();
    let stamp = fs::metadata(&markdown).ok().and_then(|m| m.modified().ok());
    fs::write(gate, "go").unwrap();
    let exit = child.wait().unwrap();
    assert!(
        partial_group_unpublished,
        "half-read component acquired a winner"
    );
    let log = fs::read_to_string(out.path().join("test.log")).unwrap();
    assert!(
        early,
        "cached group did not publish before metadata gate opened: {log}"
    );
    assert!(
        status["metadata_checked"].as_u64().unwrap() < status["metadata_total"].as_u64().unwrap(),
        "{status}"
    );
    assert!(exit.success(), "{log}");
    assert_eq!(before.unwrap(), fs::read(&markdown).unwrap());
    assert_eq!(
        stamp.unwrap(),
        fs::metadata(&markdown).unwrap().modified().unwrap()
    );
    assert!(root.path().join("Pub/Slow/Atlas-v2.md").exists());
    let final_status: serde_json::Value =
        serde_json::from_slice(&fs::read(out.path().join("continuous-status.json")).unwrap())
            .unwrap();
    assert_eq!(final_status["manifest_discovery_complete"], true);
    let rerun = Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .arg("--work-dir")
        .arg(state.path())
        .arg("markdown-continuous")
        .arg("--output")
        .arg(out.path())
        .output()
        .unwrap();
    assert!(
        rerun.status.success(),
        "{}",
        String::from_utf8_lossy(&rerun.stderr)
    );
    assert_eq!(
        stamp.unwrap(),
        fs::metadata(markdown).unwrap().modified().unwrap()
    );
}
#[test]
fn confirmed_hold_with_pending_metadata_withdraws_manifest_and_current_view() {
    use std::{
        os::unix::fs::PermissionsExt,
        time::{Duration, Instant},
    };
    let (root, state, out) = fixture();
    let db = Store::open_readonly(&state.path().join("selection.db")).unwrap();
    let initial = selection::select(&db, out.path(), None).unwrap();
    drop(db);
    fs::create_dir_all(root.path().join("Pub/Slow")).unwrap();
    common::pdf(
        &root.path().join("Pub/Slow/Atlas.pdf"),
        "Delayed atlas",
        "D:20230101000000Z",
        false,
    );
    scan(root.path(), state.path());
    let gate = out.path().join("release");
    let wrapper = out.path().join("metadata-wrapper");
    fs::write(
        &wrapper,
        format!(
            "#!/bin/sh\nwhile [ ! -e '{}' ]; do sleep 0.05; done\nexec '{}' \"$@\"\n",
            gate.display(),
            env!("CARGO_BIN_EXE_rpg-source-select")
        ),
    )
    .unwrap();
    fs::set_permissions(&wrapper, fs::Permissions::from_mode(0o755)).unwrap();
    let log = fs::File::create(out.path().join("hold-test.log")).unwrap();
    let mut child = Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .arg("--work-dir")
        .arg(state.path())
        .arg("markdown-continuous")
        .arg("--output")
        .arg(out.path())
        .arg("--metadata-worker")
        .arg(wrapper)
        .stdout(log.try_clone().unwrap())
        .stderr(log)
        .spawn()
        .unwrap();
    let md = root.path().join("Pub/Book/Chronicle.md");
    let start = Instant::now();
    while !md.exists() && start.elapsed() < Duration::from_secs(10) {
        std::thread::sleep(Duration::from_millis(50));
    }
    assert!(md.exists());
    let mut db = Store::open(&state.path().join("selection.db")).unwrap();
    let group = db
        .records::<Group>("groups")
        .unwrap()
        .into_iter()
        .find(|g| g.group_id == initial.ready[0].group_id)
        .unwrap();
    let d = Decision {
        packet_ids: vec![],
        source_hashes: Default::default(),
        group_id: group.group_id.clone(),
        membership_digest: group.membership_digest,
        evidence_digest: String::new(),
        actor: "user".into(),
        actor_role: ActorRole::User,
        outcomes: group
            .source_ids
            .into_iter()
            .map(|source_id| Outcome {
                source_id,
                status: Status::NeedsReview,
                work_id: None,
                representative_id: None,
                successor_id: None,
            })
            .collect(),
        rationale: "Hold this book".into(),
        evidence_refs: vec![],
    };
    db.put_record("decisions", &d.group_id, &d).unwrap();
    let start = Instant::now();
    let mut withdrew = false;
    while start.elapsed() < Duration::from_secs(10) {
        let m: serde_json::Value = serde_json::from_slice(
            &fs::read(root.path().join("Pub/Book/current-documents.json")).unwrap(),
        )
        .unwrap();
        let c: serde_json::Value = fs::read(out.path().join("corpus/current/catalog.json"))
            .ok()
            .and_then(|v| serde_json::from_slice(&v).ok())
            .unwrap_or_default();
        if m["documents"].as_array().is_some_and(|v| v.is_empty())
            && c["books"].as_array().is_some_and(|v| v.is_empty())
            && c["pending"] == true
        {
            withdrew = true;
            break;
        }
        std::thread::sleep(Duration::from_millis(50));
    }
    fs::write(gate, "go").unwrap();
    let exit = child.wait().unwrap();
    assert!(
        withdrew,
        "{}",
        fs::read_to_string(out.path().join("hold-test.log")).unwrap()
    );
    assert!(exit.success());
    assert!(md.exists());
}
#[test]
fn changed_known_bytes_require_regroup_but_same_bytes_refresh_observation() {
    use std::os::unix::fs::PermissionsExt;
    for different in [false, true] {
        let (root, state, out) = fixture();
        let db = Store::open_readonly(&state.path().join("selection.db")).unwrap();
        selection::select(&db, out.path(), None).unwrap();
        drop(db);
        let pdf = root.path().join("Pub/Book/Chronicle.pdf");
        if different {
            common::pdf(&pdf, "New changed book bytes", "D:20240101000000Z", false)
        } else {
            fs::set_permissions(&pdf, fs::Permissions::from_mode(0o600)).unwrap();
        }
        let r = Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
            .arg("--work-dir")
            .arg(state.path())
            .arg("markdown-continuous")
            .arg("--output")
            .arg(out.path())
            .output()
            .unwrap();
        let s: serde_json::Value =
            serde_json::from_slice(&fs::read(out.path().join("continuous-status.json")).unwrap())
                .unwrap();
        if different {
            assert_eq!(r.status.code(), Some(75));
            assert_eq!(s["phase"], "needs_regroup");
            assert!(!pdf.with_extension("md").exists());
        } else {
            assert!(r.status.success(), "{}", String::from_utf8_lossy(&r.stderr));
            assert!(pdf.with_extension("md").exists());
        }
    }
}
#[test]
fn timed_out_metadata_is_terminal_for_pass_and_not_silently_retried_on_resume() {
    use std::{os::unix::fs::PermissionsExt, time::Instant};
    let (root, state, out) = fixture();
    let wrapper = out.path().join("never-metadata");
    fs::write(&wrapper, "#!/bin/sh\nsleep 60\n").unwrap();
    fs::set_permissions(&wrapper, fs::Permissions::from_mode(0o755)).unwrap();
    let run = || {
        Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
            .arg("--work-dir")
            .arg(state.path())
            .arg("markdown-continuous")
            .arg("--output")
            .arg(out.path())
            .arg("--metadata-worker")
            .arg(&wrapper)
            .args(["--metadata-timeout-secs", "1"])
            .output()
            .unwrap()
    };
    let first = run();
    assert!(first.status.success());
    let start = Instant::now();
    let second = run();
    assert!(second.status.success());
    assert!(
        start.elapsed().as_millis() < 800,
        "metadata failure retried on resume: {}",
        String::from_utf8_lossy(&second.stderr)
    );
    let s: serde_json::Value =
        serde_json::from_slice(&fs::read(out.path().join("continuous-status.json")).unwrap())
            .unwrap();
    assert_eq!(s["phase"], "completed_with_exceptions");
    assert!(!root.path().join("Pub/Book/Chronicle.md").exists());
}
#[test]
fn new_inventory_with_unrelated_work_preserves_markdown_and_manifest_bytes_and_mtimes() {
    let (root, state, out) = fixture();
    let run = || {
        Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
            .arg("--work-dir")
            .arg(state.path())
            .arg("markdown-continuous")
            .arg("--output")
            .arg(out.path())
            .output()
            .unwrap()
    };
    let r = run();
    assert!(r.status.success(), "{}", String::from_utf8_lossy(&r.stderr));
    let paths = [
        root.path().join("Pub/Book/Chronicle.md"),
        root.path().join("Pub/Book/current-documents.json"),
    ];
    let original: Vec<_> = paths
        .iter()
        .map(|p| {
            (
                fs::read(p).unwrap(),
                fs::metadata(p).unwrap().modified().unwrap(),
            )
        })
        .collect();
    fs::create_dir_all(root.path().join("Other/Independent")).unwrap();
    common::pdf(
        &root.path().join("Other/Independent/Bestiary.pdf"),
        "Entirely unrelated creatures",
        "D:20250101000000Z",
        false,
    );
    scan(root.path(), state.path());
    let r = run();
    assert!(r.status.success(), "{}", String::from_utf8_lossy(&r.stderr));
    for (p, (bytes, stamp)) in paths.iter().zip(original) {
        assert_eq!(bytes, fs::read(p).unwrap(), "{}", p.display());
        assert_eq!(
            stamp,
            fs::metadata(p).unwrap().modified().unwrap(),
            "{}",
            p.display()
        );
    }
}
#[test]
fn oversized_job_exits_capacity_pending_without_spending_an_extraction_attempt() {
    let (root, state, out) = fixture();
    common::pages(&root.path().join("Pub/Book/Chronicle.pdf"), 4000);
    scan(root.path(), state.path());
    let r = Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .arg("--work-dir")
        .arg(state.path())
        .arg("markdown-continuous")
        .arg("--output")
        .arg(out.path())
        .output()
        .unwrap();
    assert_eq!(
        r.status.code(),
        Some(75),
        "{}",
        String::from_utf8_lossy(&r.stderr)
    );
    let s: serde_json::Value =
        serde_json::from_slice(&fs::read(out.path().join("continuous-status.json")).unwrap())
            .unwrap();
    assert_eq!(s["phase"], "capacity_pending");
    assert_eq!(s["failures"], 0);
    assert!(!out.path().join("jobs").exists());
}
