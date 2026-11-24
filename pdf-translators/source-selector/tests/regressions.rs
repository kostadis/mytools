//! Real CLI reproductions of the independent Sol review findings.
mod common;
use rpg_source_select::{grouping::build_groups, inventory::scan_root, models::*, store::Store};
use serde_json::{Value, json};
use std::{
    fs,
    path::Path,
    process::{Command, Output},
};
use tempfile::{TempDir, tempdir};
fn cli(work: &Path, args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .arg("--work-dir")
        .arg(work)
        .args(args)
        .output()
        .unwrap()
}
fn ok(work: &Path, args: &[&str]) -> Value {
    let o = cli(work, args);
    assert!(o.status.success(), "{}", String::from_utf8_lossy(&o.stderr));
    serde_json::from_slice(&o.stdout).unwrap()
}
fn library(names: &[&str]) -> (TempDir, TempDir) {
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    for name in names {
        let p = root.path().join(name);
        fs::create_dir_all(p.parent().unwrap()).unwrap();
        common::pdf(
            &p,
            &format!("Useful reference material for {name}"),
            "D:20260101",
            false,
        );
    }
    (root, work)
}
fn scan(root: &Path, work: &Path) {
    ok(work, &["scan", "--root", root.to_str().unwrap()]);
}
fn snapshot(work: &Path) -> Value {
    let o = ok(work, &["export"]);
    serde_json::from_slice(&fs::read(o["files"]["selection.json"].as_str().unwrap()).unwrap())
        .unwrap()
}
fn response(work: &Path, role: &str) -> Value {
    let out = work.join(format!("{role}.jsonl"));
    ok(
        work,
        &[
            "review",
            "export",
            "--role",
            role,
            "--out",
            out.to_str().unwrap(),
        ],
    );
    let s = fs::read_to_string(out).unwrap();
    let v: Value = serde_json::from_str(s.lines().next().unwrap()).unwrap();
    v["response_template"].clone()
}
fn import(work: &Path, r: &Value) -> Output {
    let path = work.join("response.json");
    fs::write(&path, serde_json::to_vec(r).unwrap()).unwrap();
    cli(
        work,
        &["review", "import", "--file", path.to_str().unwrap()],
    )
}

#[test]
fn cross_collection_revisions_and_rpglib_relationships_do_not_escape_comparison() {
    let (root, work) = library(&[
        "Dungeon Masters Guild/Old Mirror/Guide-v1.pdf",
        "Ash Publishing/New Mirror/Guide-v2.pdf",
    ]);
    let v = ok(
        work.path(),
        &["scan", "--root", root.path().to_str().unwrap()],
    );
    assert_eq!(v["groups"], 1);
    ok(work.path(), &["inspect"]);
    assert_eq!(snapshot(work.path())["counts"]["queue"], 0);
    let inv = scan_root(root.path()).unwrap();
    let mut db = Store::open(&work.path().join("other.db")).unwrap();
    db.upsert_inventory(&inv).unwrap();
    let hints: Vec<_> = inv
        .sources
        .iter()
        .map(|s| Hint {
            origin: "rpglib".into(),
            source_ids: vec![s.source_id.clone()],
            payload: json!({"product_id":"shared-product"}),
            unmatched_references: vec![],
        })
        .collect();
    assert_eq!(
        build_groups(&inv.sources, &hints, &mut db).unwrap().len(),
        1
    );
}

#[test]
fn baseline_protection_follows_equivalent_work_not_the_chosen_path() {
    let (root, work) = library(&[
        "Dungeon Masters Guild/Old Mirror/Guide-v1.pdf",
        "Ash Publishing/New Mirror/Guide-v2.pdf",
    ]);
    let guild = root
        .path()
        .join("Dungeon Masters Guild/Old Mirror/Guide-v1.pdf");
    fs::write(guild.with_extension("json"), b"{}").unwrap();
    fs::copy(
        &guild,
        root.path().join("Ash Publishing/New Mirror/Guide-v2.pdf"),
    )
    .unwrap();
    scan(root.path(), work.path());
    ok(work.path(), &["inspect"]);
    let v = snapshot(work.path());
    assert_eq!(v["counts"]["queue"], 0);
    assert_eq!(v["counts"]["baseline_pending"], 1);
}

#[test]
fn stale_packets_cannot_be_rebound_and_current_human_rulings_win() {
    let (root, work) = library(&["book-v1.pdf", "book-v3.pdf"]);
    for name in ["book-v1.pdf", "book-v3.pdf"] {
        common::pages(&root.path().join(name), 2);
    }
    scan(root.path(), work.path());
    ok(work.path(), &["inspect", "--pages", "1"]);
    let old = response(work.path(), "sol");
    ok(work.path(), &["inspect", "--pages", "2"]);
    let fresh = response(work.path(), "sol");
    let mut stale = fresh.clone();
    stale["packet_ids"] = old["packet_ids"].clone();
    stale["decision"]["rationale"] = json!("Rebound stale packet");
    assert!(!import(work.path(), &stale).status.success());
    let mut user = response(work.path(), "user");
    user["decision"]["rationale"] = json!("GM confirms distinct works");
    for o in user["decision"]["outcomes"].as_array_mut().unwrap() {
        o["status"] = json!("distinct_work");
    }
    assert!(import(work.path(), &user).status.success());
    let mut sol = fresh;
    sol["decision"]["rationale"] = json!("Replace the user");
    assert!(!import(work.path(), &sol).status.success());
    assert_eq!(snapshot(work.path())["counts"]["queue"], 2);
}

#[test]
fn adding_reader_claims_does_not_invalidate_a_human_ruling_on_unchanged_files() {
    let (root, work) = library(&["book-v1.pdf", "book-v3.pdf"]);
    scan(root.path(), work.path());
    ok(work.path(), &["inspect"]);
    let mut user = response(work.path(), "user");
    user["decision"]["rationale"] = json!("GM confirms distinct works");
    for o in user["decision"]["outcomes"].as_array_mut().unwrap() {
        o["status"] = json!("distinct_work");
    }
    assert!(import(work.path(), &user).status.success());
    let before = snapshot(work.path());
    let group = before["groups"][0]["group_id"].as_str().unwrap();
    let file = work.path().join("reader-extra.jsonl");
    ok(
        work.path(),
        &[
            "review",
            "export",
            "--group",
            group,
            "--role",
            "reader",
            "--out",
            file.to_str().unwrap(),
        ],
    );
    let row: Value =
        serde_json::from_str(fs::read_to_string(file).unwrap().lines().next().unwrap()).unwrap();
    let excerpt = &row["packet"]["excerpts"][0];
    let claim = json!({"packet_id":row["packet"]["packet_id"],"claims":[{"claim_id":"extra-fact","kind":"title","value":"Useful reference material","source_id":excerpt["source_id"],"page":excerpt["page"],"quote":"Useful reference material","actor":"reader","role":"reader"}]});
    assert!(import(work.path(), &claim).status.success());
    let after = snapshot(work.path());
    assert_eq!(after["counts"]["queue"], 2);
    assert_eq!(after["decisions"][0]["actor_role"], "user");
}

#[test]
fn fabricated_unreadable_and_leftover_selected_references_are_rejected() {
    let (root, work) = library(&["book-v1.pdf", "book-v3.pdf"]);
    scan(root.path(), work.path());
    ok(work.path(), &["inspect"]);
    let mut r = response(work.path(), "user");
    r["decision"]["rationale"] = json!("Retain works");
    for o in r["decision"]["outcomes"].as_array_mut().unwrap() {
        o["status"] = json!("distinct_work");
    }
    r["decision"]["outcomes"][0]["representative_id"] = json!("bogus");
    assert!(!import(work.path(), &r).status.success());
    r["decision"]["outcomes"][0]["representative_id"] = Value::Null;
    r["decision"]["outcomes"][1]["status"] = json!("unreadable");
    assert!(!import(work.path(), &r).status.success());
    assert!(cli(work.path(), &["export"]).status.success());
}

#[test]
fn an_empty_replacement_root_preserves_inventory_and_published_pointer() {
    let (root, work) = library(&["book.pdf"]);
    scan(root.path(), work.path());
    ok(work.path(), &["inspect"]);
    snapshot(work.path());
    let pointer = fs::read(work.path().join("exports/current.json")).unwrap();
    fs::rename(root.path(), work.path().join("original")).unwrap();
    fs::create_dir(root.path()).unwrap();
    assert!(!cli(work.path(), &["export"]).status.success());
    assert!(
        !cli(
            work.path(),
            &["scan", "--root", root.path().to_str().unwrap()]
        )
        .status
        .success()
    );
    assert_eq!(
        fs::read(work.path().join("exports/current.json")).unwrap(),
        pointer
    );
}

#[test]
fn oversized_metadata_still_produces_bounded_judgment_packets_with_comparisons() {
    let (root, work) = library(&["book-v1.pdf", "book-v3.pdf"]);
    let path = root.path().join("book-v1.pdf");
    let mut doc = lopdf::Document::load(&path).unwrap();
    let meta = doc.add_object(lopdf::Stream::new(
        lopdf::dictionary! {"Type"=>"Metadata","Subtype"=>"XML"},
        vec![b'X'; 33000],
    ));
    doc.catalog_mut().unwrap().set("Metadata", meta);
    doc.save(&path).unwrap();
    scan(root.path(), work.path());
    ok(work.path(), &["inspect"]);
    let out = work.path().join("packets.jsonl");
    ok(
        work.path(),
        &[
            "review",
            "export",
            "--role",
            "sol",
            "--out",
            out.to_str().unwrap(),
        ],
    );
    let text = fs::read_to_string(out).unwrap();
    let mut filesystem_sources = 0;
    let mut changed_pages = 0;
    for line in text.lines() {
        let v: Value = serde_json::from_str(line).unwrap();
        assert!(v["packet"]["comparison_context"].is_array());
        filesystem_sources += v["packet"]["source_context"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|s| s["filesystem"].is_object())
            .count();
        changed_pages += v["packet"]["comparison_context"]
            .as_array()
            .unwrap()
            .iter()
            .map(|c| c["changed_page_count"].as_u64().unwrap_or(0))
            .sum::<u64>();
        assert!(serde_json::to_string(&v["packet"]).unwrap().chars().count() <= 32000);
    }
    assert_eq!(filesystem_sources, 2);
    assert!(changed_pages > 0);
}

#[test]
fn repeated_bounded_inspection_prioritizes_unattempted_work() {
    let (root, work) = library(&["good.pdf"]);
    fs::write(root.path().join("bad.pdf"), b"broken").unwrap();
    scan(root.path(), work.path());
    let mut n = 0;
    for _ in 0..2 {
        let out = cli(work.path(), &["inspect", "--limit", "1"]);
        let v: Value = serde_json::from_slice(&out.stdout).unwrap();
        n += v["inspected_sources"].as_u64().unwrap();
    }
    assert_eq!(n, 1);
}

#[test]
fn a_cover_label_does_not_qualify_a_multi_page_image_scan() {
    let (root, work) = library(&[]);
    let p = root.path().join("scan.pdf");
    common::pdf(&p, "A", "", true);
    common::pages(&p, 3);
    scan(root.path(), work.path());
    ok(work.path(), &["inspect"]);
    let v = snapshot(work.path());
    assert_eq!(v["counts"]["queue"], 0);
    assert_eq!(v["counts"]["needs_review"], 1);
}
