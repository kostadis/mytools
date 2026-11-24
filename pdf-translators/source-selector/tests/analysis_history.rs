mod analysis_support;
use analysis_support::*;
use rpg_source_select::analysis::{history, inputs::freeze};
use serde_json::json;
fn fixture() -> (tempfile::TempDir, serde_json::Value) {
    let t = tempfile::tempdir().unwrap();
    let c = setup(t.path());
    for (id, ids) in [
        ("one", vec!["a", "b"]),
        ("two", vec!["c"]),
        ("three", vec!["d"]),
        ("pending", vec!["e"]),
    ] {
        record(
            &t.path().join("old.db"),
            "groups",
            id,
            json!({"group_id":id,"source_ids":ids,"membership_digest":"m","reasons":[]}),
        );
    }
    for (id, path) in [
        ("a", "a.pdf"),
        ("b", "b.pdf"),
        ("c", "c.pdf"),
        ("d", "d.pdf"),
        ("e", "e.pdf"),
    ] {
        insert_source(&t.path().join("old.db"), source(id, path));
    }
    (t, c)
}
fn observation(
    t: &std::path::Path,
    run: &str,
    group: &str,
    selected: &str,
    policy: &str,
    status: &str,
) {
    record(
        &t.join("history.db"),
        "continuous_groups",
        &format!("{run}-{group}"),
        json!({"snapshot":{"policy":policy,"source_root":"G:/Library","ready":if selected.is_empty(){json!([])}else{json!([{"source_id":selected,"relative_path":format!("{selected}.pdf"),"sha256":"hash"}])},"records":[{"group_id":group,"status":status,"reason":"reason","candidates":[]}]}}),
    );
}
#[test]
fn latest_saved_group_overlays_older_without_double_vote() {
    let (t, c) = fixture();
    observation(t.path(), "old", "one", "a", "internal-recency-v1", "ready");
    observation(t.path(), "new", "one", "b", "internal-recency-v1", "ready");
    observation(t.path(), "old", "two", "c", "internal-recency-v1", "ready");
    let f = freeze(&serde_json::from_value(c).unwrap(), &t.path().join("run")).unwrap();
    let h = history::load(&f).unwrap();
    assert_eq!(h.groups.len(), 2);
    assert_eq!(h.groups["one"].run_id, "new");
    assert_eq!(h.groups["one"].selected[0].source_id, "b");
    assert_eq!(h.groups["two"].run_id, "old");
    assert_eq!(h.unprocessed_groups, vec!["pending", "three"]);
}
#[test]
fn unprocessed_and_deferred_are_not_bad_choices() {
    let (t, c) = fixture();
    observation(
        t.path(),
        "new",
        "one",
        "",
        "internal-recency-v1",
        "baseline_deferred",
    );
    observation(t.path(), "new", "two", "c", "alien-policy", "ready");
    let f = freeze(&serde_json::from_value(c).unwrap(), &t.path().join("run")).unwrap();
    let h = history::load(&f).unwrap();
    assert!(h.groups["one"].selected.is_empty());
    assert!(!h.groups["two"].scorable);
    assert!(!h.warnings.is_empty());
    assert_eq!(h.unprocessed_groups.len(), 2);
}
#[test]
fn unknown_run_order_is_rejected() {
    let (t, c) = fixture();
    observation(
        t.path(),
        "unlisted",
        "one",
        "a",
        "internal-recency-v1",
        "ready",
    );
    let f = freeze(&serde_json::from_value(c).unwrap(), &t.path().join("run")).unwrap();
    assert!(history::load(&f).is_err());
}
#[test]
fn fresh_inventory_cache_reuses_hash_after_record_inode_change() {
    let (t, c) = fixture();
    let s = source("a", "a.pdf");
    let fp: rpg_source_select::models::Fingerprint =
        serde_json::from_value(s["fingerprint"].clone()).unwrap();
    let key = rpg_source_select::digest_json(&(1, &fp));
    let conn = rusqlite::Connection::open(t.path().join("old.db")).unwrap();
    conn.execute_batch("CREATE TABLE IF NOT EXISTS cache(id TEXT,stage TEXT,cache_key TEXT,body TEXT,PRIMARY KEY(id,stage,cache_key))").unwrap();
    conn.execute(
        "INSERT INTO cache VALUES('a','hash',?1,?2)",
        rusqlite::params![key, json!("a".repeat(64)).to_string()],
    )
    .unwrap();
    drop(conn);
    observation(t.path(), "new", "one", "a", "internal-recency-v1", "ready");
    let f = freeze(&serde_json::from_value(c).unwrap(), &t.path().join("run")).unwrap();
    let h = history::load(&f).unwrap();
    assert_eq!(h.verified_hashes["a"], "a".repeat(64));
}
fn rich_history(
    t: &std::path::Path,
    saved_inode: u64,
    saved_hash: &str,
    current_hash: Option<&str>,
) {
    let mut old = source("a", "a.pdf");
    old["fingerprint"]["inode"] = json!(saved_inode);
    record(
        &t.join("history.db"),
        "continuous_groups",
        "new-one",
        json!({"snapshot":{"policy":"internal-recency-v1","source_root":"G:/Library","ready":[{"source_id":"a","group_id":"one","relative_path":"a.pdf","sha256":saved_hash}],"records":[{"group_id":"one","status":"ready","candidates":[{"source":old,"sha256":saved_hash}]}]}}),
    );
    if let Some(h) = current_hash {
        let c = rusqlite::Connection::open(t.join("old.db")).unwrap();
        c.execute_batch("CREATE TABLE IF NOT EXISTS cache(id TEXT,stage TEXT,cache_key TEXT,body TEXT,PRIMARY KEY(id,stage,cache_key))").unwrap();
        let fp: rpg_source_select::models::Fingerprint =
            serde_json::from_value(source("a", "a.pdf")["fingerprint"].clone()).unwrap();
        c.execute(
            "INSERT INTO cache VALUES('a','hash',?1,?2)",
            rusqlite::params![
                rpg_source_select::digest_json(&(1, &fp)),
                json!(h).to_string()
            ],
        )
        .unwrap();
    }
}
#[test]
fn typed_equal_fingerprints_preserve_saved_hash_without_current_cache() {
    let (t, c) = fixture();
    rich_history(t.path(), 1, &"a".repeat(64), None);
    let f = freeze(&serde_json::from_value(c).unwrap(), &t.path().join("run")).unwrap();
    let h = history::load(&f).unwrap();
    assert!(h.groups["one"].scorable);
    assert_eq!(h.groups["one"].hashes["a"], "a".repeat(64));
}
#[test]
fn changed_bytes_cannot_replace_saved_selection_hash() {
    let (t, c) = fixture();
    rich_history(t.path(), 2, &"a".repeat(64), Some(&"b".repeat(64)));
    let f = freeze(&serde_json::from_value(c).unwrap(), &t.path().join("run")).unwrap();
    let h = history::load(&f).unwrap();
    assert!(!h.groups["one"].scorable);
    assert_eq!(
        h.groups["one"].selected[0].sha256.as_deref(),
        Some("a".repeat(64).as_str())
    );
    assert_eq!(h.verified_hashes["a"], "b".repeat(64));
    assert!(!h.groups["one"].hashes.contains_key("a"));
}
