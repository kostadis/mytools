mod common;
use rpg_source_select::{grouping::build_groups, inventory::scan_root, models::*, store::Store};
use serde_json::{Value, json};
use std::{fs, path::Path, process::Command};
use tempfile::{TempDir, tempdir};

fn cli(work: &Path, args: &[&str]) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .arg("--work-dir")
        .arg(work)
        .args(args)
        .output()
        .unwrap()
}
fn ok(work: &Path, args: &[&str]) -> Value {
    let out = cli(work, args);
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    serde_json::from_slice(&out.stdout).unwrap()
}
fn reader_fixture() -> (TempDir, TempDir, Vec<Value>) {
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    for version in 1..=2 {
        let p = root.path().join(format!("Book-v{version}.pdf"));
        common::pdf(
            &p,
            &format!("Explicit reference evidence for this document, edition {version}."),
            "D:20260101",
            false,
        );
        common::pages(&p, 3);
    }
    ok(
        work.path(),
        &["scan", "--root", root.path().to_str().unwrap()],
    );
    ok(work.path(), &["inspect"]);
    let out = work.path().join("reader.jsonl");
    ok(
        work.path(),
        &[
            "review",
            "export",
            "--role",
            "reader",
            "--out",
            out.to_str().unwrap(),
        ],
    );
    let rows = fs::read_to_string(out)
        .unwrap()
        .lines()
        .map(|l| serde_json::from_str(l).unwrap())
        .collect();
    (root, work, rows)
}
fn claim(rows: &[Value], page: u32, id: &str) -> Value {
    let e = rows
        .iter()
        .flat_map(|r| r["packet"]["excerpts"].as_array().unwrap())
        .find(|e| e["page"] == page)
        .unwrap();
    json!({"claim_id":id,"kind":"observed_text","value":"The page contains explicit reference evidence.","source_id":e["source_id"],"page":page,"quote":"Explicit reference evidence","actor":"test-reader","role":"reader"})
}
fn import(work: &Path, value: Value) -> std::process::Output {
    let file = work.join("results.json");
    fs::write(&file, serde_json::to_vec(&value).unwrap()).unwrap();
    cli(
        work,
        &["review", "import", "--file", file.to_str().unwrap()],
    )
}

#[test]
fn presentation_labels_join_exact_copy_subgroups_without_selecting_differing_content() {
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    for (n, name) in [
        "Travel.pdf",
        "Travel_-_No_Background.pdf",
        "Travel_Colour.pdf",
        "Travel_BW_print.pdf",
        "Travel_Digital.pdf",
        "Travel_Interactive.pdf",
        "Travel_Fillable.pdf",
    ]
    .iter()
    .enumerate()
    {
        let p = root.path().join(name);
        common::pdf(
            &p,
            &format!("Useful reference material with a distinct presentation identifier {n}."),
            "",
            false,
        );
        fs::copy(&p, root.path().join(name.replace(".pdf", ".old-001.pdf"))).unwrap();
    }
    ok(
        work.path(),
        &["scan", "--root", root.path().to_str().unwrap()],
    );
    let db = Store::open_readonly(&work.path().join("selection.db")).unwrap();
    let groups: Vec<Group> = db.records("groups").unwrap();
    assert_eq!(groups.len(), 1);
    assert!(
        groups[0]
            .reasons
            .iter()
            .any(|r| r == "presentation_candidate")
    );
    ok(work.path(), &["inspect"]);
    let export = ok(work.path(), &["export"]);
    assert_eq!(export["counts"]["queue"], 0);
    assert_eq!(export["counts"]["needs_review"], 14);
}

#[test]
fn presentation_keys_preserve_volumes_languages_systems_and_internal_words() {
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    for title in [
        "Guide_5e",
        "Guide_PF2",
        "Guide_FR",
        "Guide_Volume_1",
        "Guide_Volume_2",
        "The_Colour_of_Magic",
        "No_Background_in_Sight",
    ] {
        for suffix in ["", "_BW"] {
            fs::write(
                root.path().join(format!("{title}{suffix}.pdf")),
                format!("{title}{suffix}"),
            )
            .unwrap();
        }
    }
    let inv = scan_root(root.path()).unwrap();
    let mut db = Store::open(&work.path().join("s.db")).unwrap();
    db.upsert_inventory(&inv).unwrap();
    let groups = build_groups(&inv.sources, &[], &mut db).unwrap();
    assert_eq!(groups.len(), 7);
    assert!(groups.iter().all(|g| g.source_ids.len() == 2));
}

#[test]
fn reader_claims_bind_across_pages_without_packet_ids_and_save_the_audit() {
    let (_root, work, rows) = reader_fixture();
    assert!(rows[0]["response_template"].get("packet_id").is_none());
    let out = import(
        work.path(),
        json!({"claims":[claim(&rows,1,"fact-1"),claim(&rows,3,"fact-3")]}),
    );
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let counts: Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(counts["accepted_claims"], 2);
    assert_eq!(counts["auto_bound_claims"], 2);
    let db = Store::open_readonly(&work.path().join("selection.db")).unwrap();
    let bindings: Vec<Value> = db.records("claim_bindings").unwrap();
    assert_eq!(bindings.len(), 2);
    for binding in bindings {
        assert_eq!(binding["mode"], "automatic");
        assert_eq!(binding["source_sha256"].as_str().unwrap().len(), 64);
        assert!(
            rows.iter()
                .any(|r| r["packet"]["packet_id"] == binding["packet_id"])
        );
    }
    let fact = claim(&rows, 1, "lookup");
    let cached = ok(
        work.path(),
        &["evidence", "--source", fact["source_id"].as_str().unwrap()],
    );
    assert_eq!(cached["citation_bindings"].as_array().unwrap().len(), 2);
}

#[test]
fn unsupported_automatic_citation_rolls_back_other_claims_and_bindings() {
    let (_root, work, rows) = reader_fixture();
    let good = claim(&rows, 1, "valid");
    let mut bad = claim(&rows, 3, "invalid");
    bad["quote"] = json!("This evidence does not exist in the document.");
    assert!(
        !import(work.path(), json!({"claims":[good,bad]}))
            .status
            .success()
    );
    let db = Store::open_readonly(&work.path().join("selection.db")).unwrap();
    assert!(db.evidence().unwrap().iter().all(|e| e.claims.is_empty()));
    assert!(db.records::<Value>("claim_bindings").unwrap().is_empty());
}

#[test]
fn automatic_binding_rejects_stale_reader_packets_after_source_change() {
    let (root, work, rows) = reader_fixture();
    let fact = claim(&rows, 1, "stale");
    let p = root.path().join("Book-v1.pdf");
    common::pdf(
        &p,
        "Explicit reference evidence for this document, edition 1.",
        "D:20280101",
        false,
    );
    common::pages(&p, 3);
    // Change both sources so whichever stable source ordering supplied the fact
    // is forced to require fresh packet evidence.
    let p = root.path().join("Book-v2.pdf");
    common::pdf(
        &p,
        "Explicit reference evidence for this document, edition 2.",
        "D:20280101",
        false,
    );
    common::pages(&p, 3);
    ok(
        work.path(),
        &["scan", "--root", root.path().to_str().unwrap()],
    );
    ok(work.path(), &["inspect"]);
    let out = import(work.path(), json!({"claims":[fact]}));
    assert!(!out.status.success());
    assert!(String::from_utf8_lossy(&out.stderr).contains("current issued reader"));
}

#[test]
fn automatic_binding_rejects_unknown_sources_wrong_pages_and_wrong_roles() {
    let (_root, work, rows) = reader_fixture();
    for (field, value) in [
        ("source_id", json!("unknown")),
        ("page", json!(99)),
        ("role", json!("sol")),
        ("quote", json!("")),
    ] {
        let mut fact = claim(&rows, 1, "invalid");
        fact[field] = value;
        assert!(
            !import(work.path(), json!({"claims":[fact]}))
                .status
                .success()
        );
    }
}

#[test]
fn empty_automatic_reader_rows_are_harmless_in_a_mixed_batch() {
    let (_root, work, rows) = reader_fixture();
    let out = import(
        work.path(),
        json!([{"claims":[]},{"claims":[claim(&rows,1,"fact")]}]),
    );
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let v: Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(v["accepted_claims"], 1);
    assert_eq!(v["auto_bound_claims"], 1);
    let empty = import(work.path(), json!({"claims":[]}));
    assert!(empty.status.success());
    let v: Value = serde_json::from_slice(&empty.stdout).unwrap();
    assert_eq!(v["accepted_claims"], 0);
}

#[test]
fn presentation_candidates_preserve_dotted_ruleset_editions_and_date_suffixes() {
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    for name in [
        "Field Guide D&D 3.0 Colour.pdf",
        "Field Guide D&D 3.5 BW.pdf",
        "Field Guide D&D v3.0 Colour.pdf",
        "Field Guide D&D v3.5 BW.pdf",
        "Sheet_Final_26th_March_2020.pdf",
        "Sheet_Final_BW_-_26th_March_2020.pdf",
    ] {
        fs::write(root.path().join(name), name.as_bytes()).unwrap();
    }
    let inv = scan_root(root.path()).unwrap();
    let mut db = Store::open(&work.path().join("s.db")).unwrap();
    db.upsert_inventory(&inv).unwrap();
    let groups = build_groups(&inv.sources, &[], &mut db).unwrap();
    assert_eq!(groups.len(), 3);
    for group in groups {
        let paths: Vec<_> = inv
            .sources
            .iter()
            .filter(|s| group.source_ids.contains(&s.source_id))
            .map(|s| s.relative_path.to_string_lossy())
            .collect();
        assert!(
            !(paths.iter().any(|p| p.contains("3.0")) && paths.iter().any(|p| p.contains("3.5")))
        );
        assert_eq!(paths.len(), 2);
    }
}

#[test]
fn failed_packet_export_cannot_authorize_automatic_citations() {
    let (_root, work, rows) = reader_fixture();
    let mut db = Store::open(&work.path().join("selection.db")).unwrap();
    db.replace_records("packets", &[]).unwrap();
    let out = cli(
        work.path(),
        &[
            "review",
            "export",
            "--role",
            "reader",
            "--out",
            work.path().to_str().unwrap(),
        ],
    );
    assert!(!out.status.success());
    assert!(db.records::<Value>("packets").unwrap().is_empty());
    assert!(
        !import(work.path(), json!({"claims":[claim(&rows,1,"unissued")]}))
            .status
            .success()
    );
}

#[test]
fn replaying_an_explicit_claim_preserves_the_first_automatic_binding() {
    let (_root, work, rows) = reader_fixture();
    let fact = claim(&rows, 1, "fact");
    assert!(
        import(work.path(), json!({"claims":[fact.clone()]}))
            .status
            .success()
    );
    let db = Store::open_readonly(&work.path().join("selection.db")).unwrap();
    let before: Vec<Value> = db.records("claim_bindings").unwrap();
    assert_eq!(before.len(), 1);
    assert_eq!(before[0]["mode"], "automatic");
    assert!(
        import(
            work.path(),
            json!({"packet_id":before[0]["packet_id"],"claims":[fact.clone()]})
        )
        .status
        .success()
    );
    assert_eq!(db.records::<Value>("claim_bindings").unwrap(), before);
    assert!(
        import(work.path(), json!({"claims":[fact]}))
            .status
            .success()
    );
    assert_eq!(db.records::<Value>("claim_bindings").unwrap(), before);
}
