use rpg_source_select::{
    grouping::build_groups,
    hints::{read_muse, read_rpglib},
    inventory::scan_root,
    store::Store,
};
use std::fs;
use tempfile::tempdir;

#[test]
fn absolute_snapshot_paths_outside_the_inventory_root_do_not_match_by_suffix() {
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    fs::create_dir_all(root.path().join("Pub/Book")).unwrap();
    fs::write(root.path().join("Pub/Book/a.pdf"), b"one").unwrap();
    let inv = scan_root(root.path()).unwrap();
    let snapshot = work.path().join("rpg.json");
    fs::write(
        &snapshot,
        r#"[{"filepath":"/elsewhere/Pub/Book/a.pdf","id":99}]"#,
    )
    .unwrap();
    let hints = read_rpglib(&snapshot, &inv.sources).unwrap();
    assert!(hints[0].source_ids.is_empty());
    assert_eq!(hints[0].unmatched_references.len(), 1);
}

#[test]
fn exact_copies_cross_folders_but_similar_sizes_do_not_prove_identity() {
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    for (name, body) in [
        ("A/One/a.pdf", "same"),
        ("B/Two/b.pdf", "same"),
        ("C/Three/c.pdf", "else"),
    ] {
        let p = root.path().join(name);
        fs::create_dir_all(p.parent().unwrap()).unwrap();
        fs::write(p, body).unwrap();
    }
    let inv = scan_root(root.path()).unwrap();
    let mut db = Store::open(&work.path().join("state.db")).unwrap();
    db.upsert_inventory(&inv).unwrap();
    let groups = build_groups(&inv.sources, &[], &mut db).unwrap();
    assert_eq!(groups.len(), 2);
    assert_eq!(groups.iter().filter(|g| g.source_ids.len() == 2).count(), 1);
    assert!(
        groups
            .iter()
            .any(|g| g.reasons.iter().any(|r| r == "exact_bytes"))
    );
}

#[test]
fn version_names_are_candidates_not_winners_and_membership_changes_reopen_group() {
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    let dir = root.path().join("AAW/Rise of the Drow");
    fs::create_dir_all(&dir).unwrap();
    fs::write(dir.join("5E-RotDCE-v2.pdf"), b"old").unwrap();
    fs::write(dir.join("5E-RotDCE-v3.pdf"), b"different").unwrap();
    let mut db = Store::open(&work.path().join("state.db")).unwrap();
    let inv = scan_root(root.path()).unwrap();
    db.upsert_inventory(&inv).unwrap();
    let first = build_groups(&inv.sources, &[], &mut db).unwrap();
    assert_eq!(first.len(), 1);
    assert_eq!(first[0].source_ids.len(), 2);
    fs::write(dir.join("5E-RotDCE-v1.pdf"), b"another").unwrap();
    let inv = scan_root(root.path()).unwrap();
    db.upsert_inventory(&inv).unwrap();
    let next = build_groups(&inv.sources, &[], &mut db).unwrap();
    assert_eq!(next[0].group_id, first[0].group_id);
    assert_ne!(next[0].membership_digest, first[0].membership_digest);
}

#[test]
fn imported_confidence_is_only_a_hint_and_missing_references_are_reported() {
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    let dir = root.path().join("Pub/Bundle");
    fs::create_dir_all(&dir).unwrap();
    fs::write(dir.join("123-Volume_1.pdf"), b"first").unwrap();
    fs::write(dir.join("123-Volume_2.pdf"), b"second").unwrap();
    let inv = scan_root(root.path()).unwrap();
    let mut db = Store::open(&work.path().join("state.db")).unwrap();
    db.upsert_inventory(&inv).unwrap();
    assert_eq!(build_groups(&inv.sources, &[], &mut db).unwrap().len(), 2);
    let csv = work.path().join("muse.csv");
    fs::write(&csv,"publisher,product_folder,canonical_file,duplicate_files,confidence\nPub,Bundle,123-Volume_1.pdf,missing.pdf,high\n").unwrap();
    let hints = read_muse(&csv, &inv.sources, None).unwrap();
    assert_eq!(hints[0].unmatched_references.len(), 1);
    assert_eq!(hints[0].payload["confidence"], "high");
    assert_eq!(
        build_groups(&inv.sources, &hints, &mut db).unwrap().len(),
        2
    );
    let snap = work.path().join("rpg.json");
    fs::write(&snap,"{\"books\":[{\"id\":42,\"filepath\":\"Pub/Bundle/123-Volume_1.pdf\",\"is_old_version\":true}]}").unwrap();
    let h = read_rpglib(&snap, &inv.sources).unwrap();
    assert_eq!(h[0].source_ids.len(), 1);
    assert_eq!(h[0].payload["id"], 42);
}

#[test]
fn punctuation_twins_compare_and_language_and_system_labels_stay_distinct() {
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    for name in [
        "Pub/Book – Core/book.pdf",
        "Pub/Book - Core/book.pdf",
        "Pub/Bundle/Book-5e.pdf",
        "Pub/Bundle/Book-PF2.pdf",
        "Pub/Bundle/Book-ITA.pdf",
    ] {
        let p = root.path().join(name);
        fs::create_dir_all(p.parent().unwrap()).unwrap();
        fs::write(&p, name.as_bytes()).unwrap();
    }
    let inv = scan_root(root.path()).unwrap();
    let mut db = Store::open(&work.path().join("state.db")).unwrap();
    db.upsert_inventory(&inv).unwrap();
    let groups = build_groups(&inv.sources, &[], &mut db).unwrap();
    assert_eq!(groups.len(), 4);
}
