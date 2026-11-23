use rpg_source_select::{inventory::scan_root, models::SourceKind, store::Store};
use std::fs;
use tempfile::tempdir;

#[test]
fn inventory_retains_old_pdfs_archives_and_artifacts_without_writing_sources() {
    let root = tempdir().unwrap();
    let folder = root.path().join("Publisher/Book");
    fs::create_dir_all(folder.join("book-responses")).unwrap();
    fs::write(folder.join("book.PDF"), b"original").unwrap();
    fs::write(folder.join("book.old-001.pdf"), b"previous").unwrap();
    fs::write(folder.join("bundle.zip"), b"archive").unwrap();
    fs::write(folder.join("book.json"), b"{}").unwrap();
    fs::write(folder.join("book-responses/noise.pdf"), b"noise").unwrap();
    let before = fs::metadata(folder.join("book.PDF"))
        .unwrap()
        .modified()
        .unwrap();
    let inventory = scan_root(root.path()).unwrap();
    assert_eq!(inventory.sources.len(), 3);
    assert_eq!(
        inventory
            .sources
            .iter()
            .filter(|s| s.kind == SourceKind::Pdf)
            .count(),
        2
    );
    assert!(
        inventory
            .sources
            .iter()
            .any(|s| s.relative_path.ends_with("book.old-001.pdf"))
    );
    assert_eq!(fs::read(folder.join("book.PDF")).unwrap(), b"original");
    assert_eq!(
        fs::metadata(folder.join("book.PDF"))
            .unwrap()
            .modified()
            .unwrap(),
        before
    );
    assert!(!inventory.sources.iter().any(|s| s.baseline_established));
}

#[test]
fn state_reuses_only_matching_cache_keys_and_refuses_a_different_root() {
    let root = tempdir().unwrap();
    fs::write(root.path().join("a.pdf"), b"one").unwrap();
    let work = tempdir().unwrap();
    let inventory = scan_root(root.path()).unwrap();
    let id = inventory.sources[0].source_id.clone();
    let mut db = Store::open(&work.path().join("selection.db")).unwrap();
    db.upsert_inventory(&inventory).unwrap();
    db.put_cached(&id, "hash", "old", &serde_json::json!({"digest":"abc"}))
        .unwrap();
    assert!(db.get_cached(&id, "hash", "new").unwrap().is_none());
    assert_eq!(db.sources().unwrap().len(), 1);
    assert_eq!(
        db.get_cached(&id, "hash", "old").unwrap().unwrap()["digest"],
        "abc"
    );
    let other = tempdir().unwrap();
    assert!(
        db.upsert_inventory(&scan_root(other.path()).unwrap())
            .is_err()
    );
}

#[test]
fn missing_root_is_an_error_and_removed_sources_disappear_from_current_inventory() {
    let root = tempdir().unwrap();
    assert!(scan_root(&root.path().join("missing")).is_err());
    fs::write(root.path().join("a.pdf"), b"one").unwrap();
    let work = tempdir().unwrap();
    let mut db = Store::open(&work.path().join("selection.db")).unwrap();
    db.upsert_inventory(&scan_root(root.path()).unwrap())
        .unwrap();
    fs::remove_file(root.path().join("a.pdf")).unwrap();
    db.upsert_inventory(&scan_root(root.path()).unwrap())
        .unwrap();
    assert!(db.sources().unwrap().is_empty());
}

#[cfg(unix)]
#[test]
fn symlinks_are_reported_without_following_them() {
    let root = tempdir().unwrap();
    let outside = tempdir().unwrap();
    fs::write(outside.path().join("secret.pdf"), b"outside").unwrap();
    std::os::unix::fs::symlink(outside.path(), root.path().join("escape")).unwrap();
    let inventory = scan_root(root.path()).unwrap();
    assert!(inventory.sources.is_empty());
    assert_eq!(inventory.errors.len(), 1);
    assert!(inventory.errors[0].contains("symlink"));
}

#[cfg(unix)]
#[test]
fn equal_size_replacement_invalidates_observed_identity() {
    let root = tempdir().unwrap();
    let path = root.path().join("a.pdf");
    fs::write(&path, b"one").unwrap();
    let before = scan_root(root.path())
        .unwrap()
        .sources
        .remove(0)
        .fingerprint;
    let old_time = fs::metadata(&path).unwrap().modified().unwrap();
    fs::write(root.path().join("new"), b"two").unwrap();
    fs::rename(root.path().join("new"), &path).unwrap();
    fs::File::options()
        .write(true)
        .open(&path)
        .unwrap()
        .set_modified(old_time)
        .unwrap();
    let after = scan_root(root.path())
        .unwrap()
        .sources
        .remove(0)
        .fingerprint;
    assert_ne!(before, after);
}
