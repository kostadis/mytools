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
fn long_document_uses_bounded_growth_instead_of_whole_document_reservation() {
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
        Some(0),
        "{}",
        String::from_utf8_lossy(&r.stderr)
    );
    let s: serde_json::Value =
        serde_json::from_slice(&fs::read(out.path().join("continuous-status.json")).unwrap())
            .unwrap();
    assert_eq!(s["phase"], "completed");
    assert_eq!(s["failures"], 0);
    assert!(root.path().join("Pub/Book/Chronicle.md").exists());
}
#[test]
fn missing_source_settles_once_instead_of_requeuing_forever() {
    use std::time::{Duration, Instant};
    let (root, state, out) = fixture();
    fs::remove_file(root.path().join("Pub/Book/Chronicle.pdf")).unwrap();
    let log = fs::File::create(out.path().join("missing.log")).unwrap();
    let mut c = Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .arg("--work-dir")
        .arg(state.path())
        .arg("markdown-continuous")
        .arg("--output")
        .arg(out.path())
        .stdout(log.try_clone().unwrap())
        .stderr(log)
        .spawn()
        .unwrap();
    let start = Instant::now();
    let mut exit = None;
    while start.elapsed() < Duration::from_secs(3) {
        exit = c.try_wait().unwrap();
        if exit.is_some() {
            break;
        }
        std::thread::sleep(Duration::from_millis(50));
    }
    if exit.is_none() {
        c.kill().unwrap();
    }
    c.wait().unwrap();
    assert!(exit.is_some(), "missing source was retried indefinitely");
    let s: serde_json::Value =
        serde_json::from_slice(&fs::read(out.path().join("continuous-status.json")).unwrap())
            .unwrap();
    assert_eq!(s["phase"], "completed_with_exceptions");
}
#[test]
fn regroup_fence_survives_two_restarts_until_inventory_is_refreshed() {
    let (root, state, out) = fixture();
    let db = Store::open_readonly(&state.path().join("selection.db")).unwrap();
    selection::select(&db, out.path(), None).unwrap();
    drop(db);
    common::pdf(
        &root.path().join("Pub/Book/Chronicle.pdf"),
        "Changed bytes require new graph",
        "D:20250101000000Z",
        false,
    );
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
    for _ in 0..3 {
        let r = run();
        assert_eq!(
            r.status.code(),
            Some(75),
            "{}",
            String::from_utf8_lossy(&r.stderr)
        );
        assert!(!root.path().join("Pub/Book/Chronicle.md").exists());
    }
    scan(root.path(), state.path());
    let r = run();
    assert!(r.status.success(), "{}", String::from_utf8_lossy(&r.stderr));
    assert!(root.path().join("Pub/Book/Chronicle.md").exists());
}
#[test]
fn record_only_publication_conflict_is_not_reported_clean() {
    let (root, state, out) = fixture();
    let mut db = Store::open(&state.path().join("selection.db")).unwrap();
    let g = db.records::<Group>("groups").unwrap().remove(0);
    let d = Decision {
        packet_ids: vec![],
        source_hashes: Default::default(),
        group_id: g.group_id.clone(),
        membership_digest: g.membership_digest,
        evidence_digest: String::new(),
        actor: "user".into(),
        actor_role: ActorRole::User,
        outcomes: g
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
        rationale: "hold".into(),
        evidence_refs: vec![],
    };
    db.put_record("decisions", &d.group_id, &d).unwrap();
    drop(db);
    fs::write(
        root.path().join("Pub/Book/current-documents.json"),
        "{foreign}",
    )
    .unwrap();
    let r = Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .arg("--work-dir")
        .arg(state.path())
        .arg("markdown-continuous")
        .arg("--output")
        .arg(out.path())
        .output()
        .unwrap();
    assert!(r.status.success());
    let s: serde_json::Value =
        serde_json::from_slice(&fs::read(out.path().join("continuous-status.json")).unwrap())
            .unwrap();
    assert!(s["output_conflicts"].as_u64().unwrap() > 0, "{s}");
    assert_eq!(s["phase"], "completed_with_exceptions");
}
#[test]
fn late_join_hint_fences_old_graph_before_dispatch_and_on_restart() {
    use std::{
        os::unix::fs::PermissionsExt,
        time::{Duration, Instant},
    };
    let (root, state, out) = fixture();
    fs::create_dir_all(root.path().join("Other/Atlas")).unwrap();
    common::pdf(
        &root.path().join("Other/Atlas/Atlas.pdf"),
        "Other work",
        "D:20200101000000Z",
        false,
    );
    scan(root.path(), state.path());
    let captured = out.path().join("captured");
    let gate = out.path().join("release");
    let wrapper = out.path().join("capture-metadata");
    fs::write(
        &wrapper,
        format!(
            "#!/bin/sh\n'{}' \"$@\"\ntouch '{}'\nwhile [ ! -e '{}' ]; do sleep 0.05; done\n",
            env!("CARGO_BIN_EXE_rpg-source-select"),
            captured.display(),
            gate.display()
        ),
    )
    .unwrap();
    fs::set_permissions(&wrapper, fs::Permissions::from_mode(0o755)).unwrap();
    let log = fs::File::create(out.path().join("late.log")).unwrap();
    let mut c = Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
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
    let start = Instant::now();
    while !captured.exists() && start.elapsed() < Duration::from_secs(3) {
        std::thread::sleep(Duration::from_millis(10));
    }
    assert!(captured.exists());
    let mut db = Store::open(&state.path().join("selection.db")).unwrap();
    let sources = db.sources().unwrap();
    let hint = Hint {
        origin: "muse".into(),
        source_ids: sources.iter().map(|s| s.source_id.clone()).collect(),
        payload: serde_json::json!({}),
        unmatched_references: vec![],
    };
    db.put_record("hints", "new-join", &hint).unwrap();
    drop(db);
    fs::write(gate, "go").unwrap();
    let exit = c.wait().unwrap();
    assert_eq!(
        exit.code(),
        Some(75),
        "{}",
        fs::read_to_string(out.path().join("late.log")).unwrap()
    );
    assert!(
        !out.path().join("jobs").exists(),
        "stale graph dispatched extraction"
    );
    let r = Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .arg("--work-dir")
        .arg(state.path())
        .arg("markdown-continuous")
        .arg("--output")
        .arg(out.path())
        .output()
        .unwrap();
    assert_eq!(r.status.code(), Some(75));
}
#[test]
fn review_committed_before_sibling_install_preserves_absent_target() {
    use rpg_source_select::markdown::{adjacent, conversion, publication};
    let (root, state, out) = fixture();
    let db = Store::open_readonly(&state.path().join("selection.db")).unwrap();
    selection::select(&db, out.path(), None).unwrap();
    let r = Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .arg("markdown-convert")
        .arg("--output")
        .arg(out.path())
        .output()
        .unwrap();
    assert!(r.status.success());
    let g = db.records::<Group>("groups").unwrap().remove(0);
    let source = db.sources().unwrap().remove(0);
    let cache = Store::open_readonly(&out.path().join("metadata.db")).unwrap();
    let c = metadata::cached(root.path(), &source, &db, &cache)
        .unwrap()
        .unwrap();
    let old = selection::resolve_group(
        &db,
        out.path(),
        root.path(),
        &g,
        vec![c],
        &serde_json::Value::Null,
    )
    .unwrap();
    let mut session = adjacent::Session::new_scoped(out.path(), &old).unwrap();
    session.set_authority_database(&state.path().join("selection.db"));
    let mut writer = Store::open(&state.path().join("selection.db")).unwrap();
    let d = Decision {
        packet_ids: vec![],
        source_hashes: Default::default(),
        group_id: g.group_id.clone(),
        membership_digest: g.membership_digest,
        evidence_digest: String::new(),
        actor: "user".into(),
        actor_role: ActorRole::User,
        outcomes: g
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
        rationale: "late hold".into(),
        evidence_refs: vec![],
    };
    writer.put_record("decisions", &d.group_id, &d).unwrap();
    let mut opt = options(out.path());
    opt.timeout_secs = 120;
    let e = conversion::engine(&opt).unwrap();
    let p = publication::publish_snapshot(out.path(), &e, &old, Some(&mut session), false).unwrap();
    assert!(p.pending);
    assert!(
        !root.path().join("Pub/Book/Chronicle.md").exists(),
        "revoked bytes installed before authority gate"
    );
}
#[test]
fn mixed_directory_retains_unmatched_entry_as_unverified_and_counts_it() {
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
    assert!(run().status.success());
    let path = root.path().join("Pub/Book/current-documents.json");
    let mut m: serde_json::Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
    let mut unknown = m["documents"][0].clone();
    unknown["work_id"] = "unmatched-work".into();
    unknown["source_id"] = "unknown-source".into();
    unknown["group_id"] = "unknown-group".into();
    unknown["pdf"] = "Untracked.pdf".into();
    unknown["markdown"] = "Untracked.md".into();
    fs::copy(
        root.path().join("Pub/Book/Chronicle.pdf"),
        root.path().join("Pub/Book/Untracked.pdf"),
    )
    .unwrap();
    fs::copy(
        root.path().join("Pub/Book/Chronicle.md"),
        root.path().join("Pub/Book/Untracked.md"),
    )
    .unwrap();
    m["documents"].as_array_mut().unwrap().push(unknown);
    fs::write(&path, serde_json::to_vec_pretty(&m).unwrap()).unwrap();
    let r = run();
    assert!(r.status.success());
    let s: serde_json::Value =
        serde_json::from_slice(&fs::read(out.path().join("continuous-status.json")).unwrap())
            .unwrap();
    assert_eq!(s["phase"], "completed_with_exceptions");
    let after: serde_json::Value = serde_json::from_slice(&fs::read(path).unwrap()).unwrap();
    assert!(
        after["unverified_work_ids"]
            .as_array()
            .unwrap()
            .contains(&serde_json::json!("unmatched-work"))
    );
    assert!(root.path().join("Pub/Book/Chronicle.md").exists());
}
#[test]
fn proven_missing_current_pdf_withdraws_directory_claim_and_search_pointer() {
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
    assert!(run().status.success());
    fs::remove_file(root.path().join("Pub/Book/Chronicle.pdf")).unwrap();
    let r = run();
    assert!(r.status.success(), "{}", String::from_utf8_lossy(&r.stderr));
    let m: serde_json::Value = serde_json::from_slice(
        &fs::read(root.path().join("Pub/Book/current-documents.json")).unwrap(),
    )
    .unwrap();
    assert!(
        m["documents"].as_array().unwrap().is_empty(),
        "missing PDF kept its current claim: {m}"
    );
    let c: serde_json::Value =
        serde_json::from_slice(&fs::read(out.path().join("corpus/current/catalog.json")).unwrap())
            .unwrap();
    assert!(c["books"].as_array().unwrap().is_empty());
    assert_eq!(c["pending"], true);
    assert!(root.path().join("Pub/Book/Chronicle.md").exists());
}
#[test]
fn blocked_publication_does_not_block_resolution_or_extraction() {
    use std::time::{Duration, Instant};
    let (root, state, out) = fixture();
    for name in ["Atlas", "Bestiary", "Gazetteer", "Manual", "Codex"] {
        let dir = root.path().join("Pub").join(name);
        fs::create_dir_all(&dir).unwrap();
        common::pdf(
            &dir.join(format!("{name}.pdf")),
            &format!("Independent searchable {name}"),
            "D:20220101000000Z",
            false,
        );
    }
    scan(root.path(), state.path());
    let db = Store::open_readonly(&state.path().join("selection.db")).unwrap();
    let selected = selection::select(&db, out.path(), None).unwrap();
    assert_eq!(selected.ready.len(), 6);
    drop(db);
    let gate = out.path().join("publication-blocked");
    fs::write(&gate, "blocked").unwrap();
    let log = fs::File::create(out.path().join("async-publication.log")).unwrap();
    let mut child = Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .arg("--work-dir")
        .arg(state.path())
        .arg("markdown-continuous")
        .arg("--output")
        .arg(out.path())
        .arg("--publication-gate")
        .arg(&gate)
        .stdout(log.try_clone().unwrap())
        .stderr(log)
        .spawn()
        .unwrap();
    let start = Instant::now();
    let mut before = serde_json::Value::Null;
    while start.elapsed() < Duration::from_secs(10) && child.try_wait().unwrap().is_none() {
        before = fs::read(out.path().join("continuous-status.json"))
            .ok()
            .and_then(|b| serde_json::from_slice(&b).ok())
            .unwrap_or_default();
        if before["groups_resolved"] == 6 && before["active"] == 0 && before["queued"] == 0 {
            break;
        }
        std::thread::sleep(Duration::from_millis(50));
    }
    let completed=rusqlite::Connection::open_with_flags(out.path().join("markdown.db"),rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY).ok().map(|db|db.query_row("SELECT count(*) FROM cache WHERE stage='job' AND json_extract(body,'$.status')='complete'",[],|r|r.get::<_,i64>(0)).unwrap());
    let still_running = child.try_wait().unwrap().is_none();
    let source_documents = selected
        .ready
        .iter()
        .filter(|r| {
            root.path()
                .join(&r.relative_path)
                .with_extension("md")
                .exists()
        })
        .count();
    fs::remove_file(&gate).unwrap();
    let exit = child.wait().unwrap();
    let log = fs::read_to_string(out.path().join("async-publication.log")).unwrap();
    assert_eq!(
        before["groups_resolved"], 6,
        "coordinator blocked on publisher: {before}; {log}"
    );
    assert_eq!(before["queued"], 0, "extraction dispatch blocked: {before}");
    assert_eq!(
        before["active"], 0,
        "extraction completion blocked: {before}"
    );
    assert!(still_running, "completed before publication drained: {log}");
    assert_eq!(source_documents, 0);
    assert_eq!(
        completed,
        Some(6),
        "jobs did not finish while publication was gated"
    );
    assert!(exit.success(), "{log}");
    let final_status: serde_json::Value =
        serde_json::from_slice(&fs::read(out.path().join("continuous-status.json")).unwrap())
            .unwrap();
    assert_eq!(final_status["published"], 6);
    assert_eq!(final_status["failures"], 0);
    assert!(
        log.matches(": complete (").count() >= 6,
        "not all extraction jobs finished: {log}"
    );
}
#[test]
fn cached_work_can_be_republished_after_a_review_without_another_extraction() {
    use std::{
        os::unix::fs::PermissionsExt,
        time::{Duration, Instant},
    };
    let (root, state, out) = fixture();
    let db = Store::open_readonly(&state.path().join("selection.db")).unwrap();
    let initial = selection::select(&db, out.path(), None).unwrap();
    drop(db);
    fs::create_dir_all(root.path().join("Other/Atlas")).unwrap();
    common::pdf(
        &root.path().join("Other/Atlas/Atlas.pdf"),
        "Uncached delayed atlas",
        "D:20250101000000Z",
        false,
    );
    scan(root.path(), state.path());
    let gate = out.path().join("release-metadata");
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
    let log = fs::File::create(out.path().join("review-republish.log")).unwrap();
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
    let start = Instant::now();
    while start.elapsed() < Duration::from_secs(5) {
        let s: serde_json::Value = fs::read(out.path().join("continuous-status.json"))
            .ok()
            .and_then(|b| serde_json::from_slice(&b).ok())
            .unwrap_or_default();
        if s["published"] == 1 && s["active"] == 0 {
            break;
        }
        std::thread::sleep(Duration::from_millis(25));
    }
    let mut db = Store::open(&state.path().join("selection.db")).unwrap();
    let group = db
        .records::<Group>("groups")
        .unwrap()
        .into_iter()
        .find(|g| g.group_id == initial.ready[0].group_id)
        .unwrap();
    let decision = Decision {
        packet_ids: vec![],
        source_hashes: Default::default(),
        group_id: group.group_id.clone(),
        membership_digest: group.membership_digest.clone(),
        evidence_digest: rpg_source_select::review::evidence_digest(&group, &[]),
        actor: "user".into(),
        actor_role: ActorRole::User,
        outcomes: group
            .source_ids
            .iter()
            .map(|id| Outcome {
                source_id: id.clone(),
                status: Status::Selected,
                work_id: Some("adopted-current-work".into()),
                representative_id: None,
                successor_id: None,
            })
            .collect(),
        rationale: "adopt named work".into(),
        evidence_refs: vec![],
    };
    db.put_record("decisions", &decision.group_id, &decision)
        .unwrap();
    let start = Instant::now();
    let mut republished = false;
    while start.elapsed() < Duration::from_secs(4) {
        let m: serde_json::Value = fs::read(root.path().join("Pub/Book/current-documents.json"))
            .ok()
            .and_then(|b| serde_json::from_slice(&b).ok())
            .unwrap_or_default();
        if m["documents"].as_array().is_some_and(|docs| {
            docs.iter()
                .any(|d| d["work_id"] == "adopted-current-work" && d["status"] == "published")
        }) {
            republished = true;
            break;
        }
        std::thread::sleep(Duration::from_millis(25));
    }
    fs::write(gate, "go").unwrap();
    let exit = child.wait().unwrap();
    let log = fs::read_to_string(out.path().join("review-republish.log")).unwrap();
    assert!(republished, "cached re-publication was dropped: {log}");
    assert!(exit.success());
    assert_eq!(
        log.matches("conversion started: Pub/Book/Chronicle.pdf")
            .count(),
        1,
        "review re-extracted completed work: {log}"
    );
}
#[test]
fn a_second_source_publisher_cannot_take_the_same_namespace() {
    let (root, state, out) = fixture();
    let lease = fs::OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .open(out.path().join("publication-worker.lock"))
        .unwrap();
    lease.lock().unwrap();
    let r = Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .arg("--work-dir")
        .arg(state.path())
        .arg("markdown-continuous")
        .arg("--output")
        .arg(out.path())
        .output()
        .unwrap();
    assert!(!r.status.success());
    assert!(String::from_utf8_lossy(&r.stderr).contains("publication-worker.lock"));
    assert!(!root.path().join("Pub/Book/Chronicle.md").exists());
}
#[test]
fn review_hold_supersedes_publication_while_publisher_is_blocked() {
    use std::time::{Duration, Instant};
    let (root, state, out) = fixture();
    let gate = out.path().join("publisher-blocked");
    fs::write(&gate, "wait").unwrap();
    let log = fs::File::create(out.path().join("queued-hold.log")).unwrap();
    let mut child = Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .arg("--work-dir")
        .arg(state.path())
        .arg("markdown-continuous")
        .arg("--output")
        .arg(out.path())
        .arg("--publication-gate")
        .arg(&gate)
        .stdout(log.try_clone().unwrap())
        .stderr(log)
        .spawn()
        .unwrap();
    let start = Instant::now();
    let mut status = serde_json::Value::Null;
    while start.elapsed() < Duration::from_secs(5) {
        status = fs::read(out.path().join("continuous-status.json"))
            .ok()
            .and_then(|b| serde_json::from_slice(&b).ok())
            .unwrap_or_default();
        if status["publication_active"] == true && status["queued"] == 0 && status["active"] == 0 {
            break;
        }
        std::thread::sleep(Duration::from_millis(25));
    }
    assert_eq!(status["publication_active"], true);
    let mut db = Store::open(&state.path().join("selection.db")).unwrap();
    let group = db.records::<Group>("groups").unwrap().remove(0);
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
            .iter()
            .map(|id| Outcome {
                source_id: id.clone(),
                status: Status::NeedsReview,
                work_id: None,
                representative_id: None,
                successor_id: None,
            })
            .collect(),
        rationale: "hold queued work".into(),
        evidence_refs: vec![],
    };
    db.put_record("decisions", &d.group_id, &d).unwrap();
    let start = Instant::now();
    let mut observed = false;
    while start.elapsed() < Duration::from_secs(3) {
        let s: serde_json::Value = fs::read(out.path().join("continuous-status.json"))
            .ok()
            .and_then(|b| serde_json::from_slice(&b).ok())
            .unwrap_or_default();
        if s["groups_deferred"] == 1 {
            observed = true;
            break;
        }
        std::thread::sleep(Duration::from_millis(25));
    }
    fs::remove_file(gate).unwrap();
    let exit = child.wait().unwrap();
    assert!(
        observed,
        "coordinator did not observe hold while publisher was blocked"
    );
    assert!(
        exit.success(),
        "{}",
        fs::read_to_string(out.path().join("queued-hold.log")).unwrap()
    );
    assert!(
        !root.path().join("Pub/Book/Chronicle.md").exists(),
        "stale queued publication was installed"
    );
    let catalog: serde_json::Value =
        serde_json::from_slice(&fs::read(out.path().join("corpus/current/catalog.json")).unwrap())
            .unwrap();
    assert!(catalog["books"].as_array().unwrap().is_empty());
    let reservations: serde_json::Value =
        serde_json::from_slice(&fs::read(out.path().join("reservations.json")).unwrap()).unwrap();
    assert!(
        reservations["jobs"].as_object().unwrap().is_empty(),
        "superseded publication stranded a reservation"
    );
}
#[test]
fn independent_works_sharing_extraction_keep_each_publications_space_reserved() {
    use std::time::{Duration, Instant};
    let (root, state, out) = fixture();
    fs::copy(
        root.path().join("Pub/Book/Chronicle.pdf"),
        root.path().join("Pub/Book/Cartography.pdf"),
    )
    .unwrap();
    scan(root.path(), state.path());
    let mut db = Store::open(&state.path().join("selection.db")).unwrap();
    let group = db.records::<Group>("groups").unwrap().remove(0);
    assert_eq!(group.source_ids.len(), 2);
    let d = Decision {
        packet_ids: vec![],
        source_hashes: Default::default(),
        group_id: group.group_id.clone(),
        membership_digest: group.membership_digest.clone(),
        evidence_digest: rpg_source_select::review::evidence_digest(&group, &[]),
        actor: "user".into(),
        actor_role: ActorRole::User,
        outcomes: group
            .source_ids
            .iter()
            .enumerate()
            .map(|(i, id)| Outcome {
                source_id: id.clone(),
                status: Status::DistinctWork,
                work_id: Some(format!("independent-{i}")),
                representative_id: None,
                successor_id: None,
            })
            .collect(),
        rationale: "two adopted independent presentations".into(),
        evidence_refs: vec![],
    };
    db.put_record("decisions", &d.group_id, &d).unwrap();
    assert_eq!(
        selection::select(&db, out.path(), None)
            .unwrap()
            .ready
            .len(),
        2
    );
    drop(db);
    let gate = out.path().join("publication-blocked");
    fs::write(&gate, "wait").unwrap();
    let log = fs::File::create(out.path().join("shared-extraction.log")).unwrap();
    let mut child = Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .arg("--work-dir")
        .arg(state.path())
        .arg("markdown-continuous")
        .arg("--output")
        .arg(out.path())
        .arg("--publication-gate")
        .arg(&gate)
        .stdout(log.try_clone().unwrap())
        .stderr(log)
        .spawn()
        .unwrap();
    let start = Instant::now();
    while start.elapsed() < Duration::from_secs(5) {
        let s: serde_json::Value = fs::read(out.path().join("continuous-status.json"))
            .ok()
            .and_then(|b| serde_json::from_slice(&b).ok())
            .unwrap_or_default();
        if s["groups_resolved"] == 1
            && s["active"] == 0
            && s["queued"] == 0
            && s["publication_active"] == true
        {
            break;
        }
        std::thread::sleep(Duration::from_millis(25));
    }
    let reserved: serde_json::Value =
        serde_json::from_slice(&fs::read(out.path().join("reservations.json")).unwrap()).unwrap();
    let held = reserved["jobs"]
        .as_object()
        .unwrap()
        .values()
        .map(|v| v.as_u64().unwrap())
        .sum::<u64>();
    fs::remove_file(gate).unwrap();
    let exit = child.wait().unwrap();
    assert!(
        exit.success(),
        "{}",
        fs::read_to_string(out.path().join("shared-extraction.log")).unwrap()
    );
    assert!(
        held >= 32 * 1024 * 1024,
        "shared extraction only reserved one work: {reserved}"
    );
    let s: serde_json::Value =
        serde_json::from_slice(&fs::read(out.path().join("continuous-status.json")).unwrap())
            .unwrap();
    assert_eq!(s["published"], 2);
    let log = fs::read_to_string(out.path().join("shared-extraction.log")).unwrap();
    assert_eq!(log.matches("conversion started:").count(), 1);
}
