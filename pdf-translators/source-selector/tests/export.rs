mod common;
use rpg_source_select::{
    Result,
    evidence::{TextExtractor, inspect_pdf},
    export::{build_snapshot, write_exports},
    grouping::build_groups,
    inventory::scan_root,
    models::*,
    store::Store,
};
use std::{fs, path::Path};
use tempfile::tempdir;

#[test]
fn a_user_chosen_equivalent_path_does_not_bypass_confirmed_baseline_protection() {
    let (root, _work, mut db) = library();
    fs::copy(
        root.path()
            .join("Dungeon Masters Guild/Book/guild-book.pdf"),
        root.path().join("Pub/Book/book.pdf"),
    )
    .unwrap();
    let mut inv = scan_root(root.path()).unwrap();
    inv.sources
        .iter_mut()
        .find(|s| s.publisher == "Dungeon Masters Guild")
        .unwrap()
        .baseline_established = true;
    db.upsert_inventory(&inv).unwrap();
    let group = build_groups(&inv.sources, &[], &mut db).unwrap().remove(0);
    for source in inv.sources.iter().filter(|s| s.kind == SourceKind::Pdf) {
        db.save_evidence(
            &inspect_pdf(
                &root.path().join(&source.relative_path),
                source,
                None,
                &Reader,
            )
            .unwrap(),
        )
        .unwrap();
    }
    let evidence = db.evidence().unwrap();
    let mut decision =
        rpg_source_select::review::propose_decision(&group, &evidence, &inv.sources, None);
    decision.actor_role = ActorRole::User;
    decision.actor = "gm".into();
    decision.rationale = "Choose the equivalent external path".into();
    let external = inv
        .sources
        .iter()
        .find(|s| s.publisher == "Pub")
        .unwrap()
        .source_id
        .clone();
    for outcome in &mut decision.outcomes {
        if outcome.source_id == external {
            outcome.status = Status::Selected;
            outcome.representative_id = None;
        } else {
            outcome.status = Status::EquivalentPresentation;
            outcome.representative_id = Some(external.clone());
        }
    }
    db.save_decision(&decision).unwrap();
    let snapshot = build_snapshot(&db).unwrap();
    assert!(snapshot.queue.is_empty());
    assert_eq!(snapshot.counts["baseline_reuse"], 1);
    assert_eq!(
        snapshot.baseline_findings[0]["representative_changed"],
        true
    );
}
struct Reader;
impl TextExtractor for Reader {
    fn extract(&self, _: &Path, pages: &[u32]) -> Result<Vec<PageText>> {
        Ok(pages
            .iter()
            .map(|p| PageText {
                page: *p,
                text: "Useful reference text.".into(),
                images: None,
                annotations: None,
            })
            .collect())
    }
}
fn library() -> (tempfile::TempDir, tempfile::TempDir, Store) {
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    for name in [
        "Pub/Book/book.pdf",
        "Dungeon Masters Guild/Book/guild-book.pdf",
    ] {
        let p = root.path().join(name);
        fs::create_dir_all(p.parent().unwrap()).unwrap();
        common::pdf(&p, name, "D:20260101", false);
    }
    fs::write(root.path().join("bundle.zip"), b"archive").unwrap();
    fs::write(
        root.path()
            .join("Dungeon Masters Guild/Book/guild-book.json"),
        b"{}",
    )
    .unwrap();
    let inv = scan_root(root.path()).unwrap();
    let mut db = Store::open(&work.path().join("s.db")).unwrap();
    db.upsert_inventory(&inv).unwrap();
    build_groups(&inv.sources, &[], &mut db).unwrap();
    for s in inv.sources.iter().filter(|s| s.kind == SourceKind::Pdf) {
        db.save_evidence(
            &inspect_pdf(&root.path().join(&s.relative_path), s, None, &Reader).unwrap(),
        )
        .unwrap();
    }
    (root, work, db)
}
#[test]
fn json_is_not_completion_and_baseline_candidates_do_not_enter_the_new_work_queue() {
    let (_root, work, db) = library();
    let snapshot = build_snapshot(&db).unwrap();
    assert_eq!(snapshot.queue.len(), 1);
    assert_eq!(snapshot.queue[0].publisher, "Pub");
    assert!(snapshot.queue[0].fingerprint.sha256.is_some());
    assert_eq!(snapshot.counts["archives"], 1);
    assert_eq!(snapshot.counts["baseline_pending"], 1);
    assert!(snapshot.sources.iter().all(|s| !s.baseline_established));
    let outputs = write_exports(&snapshot, &work.path().join("exports")).unwrap();
    assert!(outputs["selection.json"].exists());
    assert!(outputs["queue.tsv"].exists());
    let pointer: serde_json::Value =
        serde_json::from_slice(&fs::read(work.path().join("exports/current.json")).unwrap())
            .unwrap();
    assert!(
        pointer["generation"]
            .as_str()
            .unwrap()
            .starts_with("generations/")
    );
}

#[cfg(unix)]
#[test]
fn generation_symlink_cannot_redirect_export_writes_into_the_library() {
    let (root, work, db) = library();
    let snapshot = build_snapshot(&db).unwrap();
    let out = work.path().join("exports");
    fs::create_dir(&out).unwrap();
    std::os::unix::fs::symlink(root.path(), out.join("generations")).unwrap();
    let before = fs::read_dir(root.path()).unwrap().count();
    assert!(write_exports(&snapshot, &out).is_err());
    assert_eq!(fs::read_dir(root.path()).unwrap().count(), before);
}
#[test]
fn a_changed_source_is_removed_from_the_queue_and_old_export_survives_invalid_publication() {
    let (root, work, db) = library();
    let snapshot = build_snapshot(&db).unwrap();
    let out = work.path().join("exports");
    write_exports(&snapshot, &out).unwrap();
    let previous = fs::read(out.join("current.json")).unwrap();
    let mut bad = snapshot.clone();
    bad.queue.push(bad.queue[0].clone());
    assert!(write_exports(&bad, &out).is_err());
    assert_eq!(fs::read(out.join("current.json")).unwrap(), previous);
    fs::write(root.path().join("Pub/Book/book.pdf"), b"changed").unwrap();
    let next = build_snapshot(&db).unwrap();
    assert!(next.queue.is_empty());
    assert_eq!(next.counts["stale_groups"], 1);
    assert!(write_exports(&snapshot, root.path()).is_err());
}
#[test]
fn explicit_baseline_is_preserved_and_archives_are_not_missing_books() {
    let (_root, _work, mut db) = library();
    let mut inv: InventoryResult =
        serde_json::from_value(db.meta("inventory").unwrap().unwrap()).unwrap();
    inv.sources
        .iter_mut()
        .find(|s| s.publisher == "Dungeon Masters Guild")
        .unwrap()
        .baseline_established = true;
    db.upsert_inventory(&inv).unwrap();
    build_groups(&inv.sources, &[], &mut db).unwrap();
    let snapshot = build_snapshot(&db).unwrap();
    assert_eq!(snapshot.counts["baseline_reuse"], 1);
    assert_eq!(snapshot.counts["baseline_pending"], 0);
    assert_eq!(snapshot.queue.len(), 1);
    assert_eq!(snapshot.sources.len(), 3);
}
