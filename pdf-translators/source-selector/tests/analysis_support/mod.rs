#![allow(dead_code)]
use serde_json::{Value, json};
use std::path::Path;
pub fn write(path: &Path, v: &Value) {
    std::fs::write(path, serde_json::to_vec_pretty(v).unwrap()).unwrap();
}
pub fn database(path: &Path) {
    let c = rusqlite::Connection::open(path).unwrap();
    c.execute_batch("CREATE TABLE meta(key TEXT PRIMARY KEY,body TEXT); CREATE TABLE sources(id TEXT PRIMARY KEY,body TEXT,active INTEGER); CREATE TABLE records(kind TEXT,id TEXT,body TEXT,PRIMARY KEY(kind,id)); INSERT INTO meta VALUES('schema_version','1');").unwrap();
}
pub fn source(id: &str, path: &str) -> Value {
    json!({"source_id":id,"relative_path":path,"kind":"pdf","publisher":"Publisher","product_folder":"Product","fingerprint":{"size":20,"mtime_ns":1,"ctime_ns":1,"device":1,"inode":1,"sha256":null},"read_error":null})
}
pub fn insert_source(db: &Path, s: Value) {
    let c = rusqlite::Connection::open(db).unwrap();
    c.execute(
        "INSERT INTO sources VALUES(?1,?2,1)",
        rusqlite::params![s["source_id"].as_str().unwrap(), s.to_string()],
    )
    .unwrap();
}
pub fn record(db: &Path, kind: &str, id: &str, v: Value) {
    let c = rusqlite::Connection::open(db).unwrap();
    c.execute(
        "INSERT INTO records VALUES(?1,?2,?3)",
        rusqlite::params![kind, id, v.to_string()],
    )
    .unwrap();
}
pub fn setup(root: &Path) -> Value {
    for name in ["old.db", "current.db", "history.db"] {
        database(&root.join(name));
    }
    write(&root.join("status.json"), &json!({"run_id":"new"}));
    write(&root.join("rules.json"), &json!([]));
    std::fs::write(
        root.join("matches.csv"),
        "D file,G file,Status,Evidence,Other matching G files\n",
    )
    .unwrap();
    json!({"schema_version":1,"csv":root.join("matches.csv"),"d_root":"D:/Download","g_root":"G:/Library","old_inventory":root.join("old.db"),"current_inventory":root.join("current.db"),"history":root.join("history.db"),"history_status":root.join("status.json"),"historical_runs":["old","new"],"owner_rulings":root.join("rules.json"),"reference_complete":false,"sample_seed":"test","sample_per_stratum":5,"holdout_percent":20})
}
pub fn audit_fixture() -> (
    tempfile::TempDir,
    rpg_source_select::analysis::models::AuditResult,
) {
    let t = tempfile::tempdir().unwrap();
    let c = setup(t.path());
    for (id, path) in [
        ("a", "Publisher/Book<v3>.pdf"),
        ("b", "Publisher/Book&new.pdf"),
    ] {
        insert_source(&t.path().join("old.db"), source(id, path));
    }
    record(
        &t.path().join("old.db"),
        "groups",
        "g",
        json!({"group_id":"g","source_ids":["a","b"],"membership_digest":"m","reasons":[]}),
    );
    let f = rpg_source_select::analysis::inputs::freeze(
        &serde_json::from_value(c).unwrap(),
        &t.path().join("run"),
    )
    .unwrap();
    let h = rpg_source_select::analysis::models::HistoricalView {
        groups: Default::default(),
        unprocessed_groups: vec!["g".into()],
        warnings: vec![],
    };
    let a = rpg_source_select::analysis::audit::compare(&f, &h, &[]).unwrap();
    (t, a)
}
