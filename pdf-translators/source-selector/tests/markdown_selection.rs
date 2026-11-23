mod common;
use rpg_source_select::{
    markdown::{dates, selection},
    store::Store,
};
use serde_json::{Value, json};
use std::{collections::BTreeMap, fs, path::Path, process::Command};
use tempfile::tempdir;
fn metadata(value: Value) -> BTreeMap<String, Value> {
    serde_json::from_value(value).unwrap()
}
fn cli(work: &Path, args: &[&str]) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_rpg-source-select"))
        .arg("--work-dir")
        .arg(work)
        .args(args)
        .output()
        .unwrap()
}

#[test]
fn embedded_dates_normalize_offsets_fallback_and_reject_conflicts() {
    let a = dates::resolve(&metadata(
        json!({"ModDate":"D:20200325164626Z","CreationDate":"D:20200325164421Z"}),
    ));
    let b = dates::resolve(&metadata(json!({"CreationDate":"D:20200325184626+02'00'"})));
    assert!(a.flags.is_empty());
    assert_eq!(a.effective.unwrap().start_ms, b.effective.unwrap().start_ms);
    assert!(
        dates::resolve(&metadata(
            json!({"ModDate":"bad","CreationDate":"D:20200325164421Z"})
        ))
        .effective
        .is_none()
    );
    assert!(
        !dates::resolve(&metadata(
            json!({"ModDate":"D:20190101000000Z","CreationDate":"D:20200101000000Z"})
        ))
        .flags
        .is_empty()
    );
    assert!(dates::resolve(&BTreeMap::new()).effective.is_none());
}
#[test]
fn xmp_can_resolve_compatible_precision_but_not_a_conflicting_date() {
    let xmp = |date: &str| {
        format!(
            "<rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'><rdf:Description xmlns:xmp='http://ns.adobe.com/xap/1.0/' xmp:ModifyDate='{date}'/></rdf:RDF>"
        )
    };
    let good = dates::resolve(&metadata(
        json!({"ModDate":"D:20200325","xmp":xmp("2020-03-25T16:46:26Z")}),
    ));
    assert!(good.flags.is_empty(), "{:?}", good.flags);
    assert!(good.effective.unwrap().field.contains("xmp"));
    let bad = dates::resolve(&metadata(
        json!({"ModDate":"D:20200325164626Z","xmp":xmp("2020-03-26T16:46:26Z")}),
    ));
    assert!(bad.effective.is_none());
    assert!(
        dates::resolve(&metadata(json!({"ModDate":"D:20200325164626"})))
            .effective
            .is_none()
    );
    let partial = dates::resolve(&metadata(json!({"ModDate":"D:202003Z"})));
    let stamp = partial.effective.unwrap();
    assert!(stamp.end_ms - stamp.start_ms > 28 * 86400 * 1000);
}
#[test]
fn newest_internal_dates_create_an_additive_queue_without_reading_pages() {
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    let out = tempdir().unwrap();
    let folder = root.path().join("Publisher/AmberReference");
    fs::create_dir_all(&folder).unwrap();
    common::pdf(
        &folder.join("AmberReference_Colour.pdf"),
        "Useful reference material.",
        "D:20210101000000Z",
        false,
    );
    common::pdf(
        &folder.join("AmberReference_BW.pdf"),
        "Useful reference material.",
        "D:20220101000000Z",
        false,
    );
    fs::copy(
        folder.join("AmberReference_BW.pdf"),
        folder.join("AmberReference_BW.old-001.pdf"),
    )
    .unwrap();
    assert!(
        cli(
            work.path(),
            &["scan", "--root", root.path().to_str().unwrap()]
        )
        .status
        .success()
    );
    let db = Store::open_readonly(&work.path().join("selection.db")).unwrap();
    let before = fs::read(work.path().join("selection.db")).unwrap();
    let s = selection::select(&db, out.path(), None).unwrap();
    assert_eq!(s.ready.len(), 1);
    assert!(
        s.ready[0]
            .relative_path
            .to_string_lossy()
            .ends_with("AmberReference_BW.pdf")
    );
    assert_eq!(s.records[0].candidates.len(), 3);
    assert_eq!(s.ready[0].page_count, 1);
    assert_eq!(fs::read(work.path().join("selection.db")).unwrap(), before);
    assert_eq!(db.count_records("evidence").unwrap(), 0);
    assert_eq!(
        selection::load_current(out.path()).unwrap().snapshot_id,
        s.snapshot_id
    );
}
#[test]
fn tied_or_undated_competitors_and_ruleset_conflicts_stay_deferred() {
    for mode in ["tie", "missing", "ruleset"] {
        let root = tempdir().unwrap();
        let work = tempdir().unwrap();
        let out = tempdir().unwrap();
        let folder = root.path().join("Pub/Book");
        fs::create_dir_all(&folder).unwrap();
        let (a, b) = if mode == "ruleset" {
            ("Guide D&D 3.0.pdf", "Guide D&D 3.5.pdf")
        } else {
            ("Chronicle-v1.pdf", "Chronicle-v2.pdf")
        };
        common::pdf(
            &folder.join(a),
            "First useful reference material.",
            "D:20200101000000Z",
            false,
        );
        common::pdf(
            &folder.join(b),
            "Second useful reference material.",
            if mode == "missing" {
                ""
            } else if mode == "ruleset" {
                "D:20210101000000Z"
            } else {
                "D:20200101000000Z"
            },
            false,
        );
        assert!(
            cli(
                work.path(),
                &["scan", "--root", root.path().to_str().unwrap()]
            )
            .status
            .success()
        );
        let db = Store::open_readonly(&work.path().join("selection.db")).unwrap();
        let s = selection::select(&db, out.path(), None).unwrap();
        assert!(s.ready.is_empty(), "{mode}");
        assert!(s.records.iter().any(|r| r.status == "deferred_choice"));
    }
}
#[test]
fn adopted_holds_choices_and_baseline_are_preserved() {
    use rpg_source_select::{models::*, review::evidence_digest};
    for mode in ["hold", "choice", "partial", "baseline", "grown"] {
        let root = tempdir().unwrap();
        let work = tempdir().unwrap();
        let out = tempdir().unwrap();
        let folder = root.path().join("Pub/Book");
        fs::create_dir_all(&folder).unwrap();
        common::pdf(
            &folder.join("Book-v1.pdf"),
            "First reference material.",
            "D:20200101000000Z",
            false,
        );
        common::pdf(
            &folder.join("Book-v2.pdf"),
            "Second reference material.",
            "D:20210101000000Z",
            false,
        );
        assert!(
            cli(
                work.path(),
                &["scan", "--root", root.path().to_str().unwrap()]
            )
            .status
            .success()
        );
        let mut db = Store::open(&work.path().join("selection.db")).unwrap();
        let g = db.records::<Group>("groups").unwrap().remove(0);
        let sources = db.sources().unwrap();
        let old = sources
            .iter()
            .find(|s| s.relative_path.ends_with("Book-v1.pdf"))
            .unwrap();
        if mode == "baseline" {
            let mut inv: InventoryResult =
                serde_json::from_value(db.meta("inventory").unwrap().unwrap()).unwrap();
            inv.sources
                .iter_mut()
                .find(|s| s.source_id == old.source_id)
                .unwrap()
                .baseline_established = true;
            db.upsert_inventory(&inv).unwrap();
        } else {
            let d = Decision {
                packet_ids: vec![],
                source_hashes: Default::default(),
                group_id: g.group_id.clone(),
                membership_digest: if mode == "grown" {
                    "stale".into()
                } else {
                    g.membership_digest.clone()
                },
                evidence_digest: evidence_digest(&g, &[]),
                actor: "user".into(),
                actor_role: ActorRole::User,
                outcomes: g
                    .source_ids
                    .iter()
                    .map(|id| Outcome {
                        source_id: id.clone(),
                        status: if ["choice", "partial"].contains(&mode) && *id == old.source_id {
                            if mode == "partial" {
                                Status::DistinctWork
                            } else {
                                Status::Selected
                            }
                        } else {
                            Status::NeedsReview
                        },
                        work_id: Some("reviewed-work".into()),
                        representative_id: None,
                        successor_id: None,
                    })
                    .collect(),
                rationale: "review ruling".into(),
                evidence_refs: vec![],
            };
            let mut d = d;
            if mode == "choice" {
                for o in &mut d.outcomes {
                    if o.source_id != old.source_id {
                        o.status = Status::EquivalentPresentation;
                    }
                }
            }
            db.put_record("decisions", &g.group_id, &d).unwrap();
        }
        let s = selection::select(&db, out.path(), None).unwrap();
        if ["choice", "partial"].contains(&mode) {
            assert_eq!(s.ready.len(), 1);
            assert_eq!(s.ready[0].source_id, old.source_id);
            assert_eq!(s.ready[0].selection_basis, "adopted_review");
        } else {
            assert!(s.ready.is_empty(), "{mode}");
        }
    }
}
#[test]
fn fractional_precision_and_weak_zoned_witnesses_stay_conservative() {
    let xmp = |date: &str| {
        format!("<xmp:ModifyDate xmlns:xmp='http://ns.adobe.com/xap/1.0/'>{date}</xmp:ModifyDate>")
    };
    let a = dates::resolve(&metadata(json!({"xmp":xmp("2020-01-01T00:00:00.1Z")})))
        .effective
        .unwrap();
    let b = dates::resolve(&metadata(json!({"xmp":xmp("2020-01-01T00:00:00.15Z")})))
        .effective
        .unwrap();
    assert_eq!(a.end_ms - a.start_ms, 100);
    assert_eq!(b.end_ms - b.start_ms, 10);
    assert!(a.end_ms > b.start_ms);
    assert!(
        dates::resolve(&metadata(
            json!({"ModDate":"D:202001Z","xmp":xmp("20200102")})
        ))
        .effective
        .is_none()
    );
}
#[test]
fn zoned_month_cannot_resolve_more_precise_offset_free_day() {
    let d = dates::resolve(&metadata(
        json!({"ModDate":"D:202001Z","xmp":"<xmp:ModifyDate xmlns:xmp='http://ns.adobe.com/xap/1.0/'>20200102</xmp:ModifyDate>"}),
    ));
    assert!(d.effective.is_none());
}
#[test]
fn language_subfolders_are_protected_qualifiers() {
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    let out = tempdir().unwrap();
    for (language, v, date) in [
        ("English", 1, "D:20200101000000Z"),
        ("French", 2, "D:20210101000000Z"),
    ] {
        let folder = root.path().join("Pub/Book").join(language);
        fs::create_dir_all(&folder).unwrap();
        common::pdf(
            &folder.join(format!("Scarlet Almanac-v{v}.pdf")),
            language,
            date,
            false,
        );
    }
    assert!(
        cli(
            work.path(),
            &["scan", "--root", root.path().to_str().unwrap()]
        )
        .status
        .success()
    );
    assert!(
        selection::select(
            &Store::open_readonly(&work.path().join("selection.db")).unwrap(),
            out.path(),
            None
        )
        .unwrap()
        .ready
        .is_empty()
    );
}
#[test]
fn generic_family_and_explicit_reader_conflicts_defer_the_whole_component() {
    use rpg_source_select::models::*;
    for mode in ["generic", "claims"] {
        let root = tempdir().unwrap();
        let work = tempdir().unwrap();
        let out = tempdir().unwrap();
        let folder = root.path().join("Pub/Book");
        fs::create_dir_all(&folder).unwrap();
        let stem = if mode == "generic" {
            "Map"
        } else {
            "Chronicle"
        };
        for (v, date) in [(1, "D:20200101000000Z"), (2, "D:20210101000000Z")] {
            common::pdf(
                &folder.join(format!("{stem}-v{v}.pdf")),
                &format!("Different reference {v}"),
                date,
                false,
            );
        }
        assert!(
            cli(
                work.path(),
                &["scan", "--root", root.path().to_str().unwrap()]
            )
            .status
            .success()
        );
        let mut db = Store::open(&work.path().join("selection.db")).unwrap();
        if mode == "claims" {
            for (i, s) in db.sources().unwrap().iter().enumerate() {
                let e = Evidence {
                    source_id: s.source_id.clone(),
                    sha256: rpg_source_select::grouping::hash_source(
                        &root.path().join(&s.relative_path),
                    )
                    .unwrap(),
                    version: 1,
                    pdf_metadata: Default::default(),
                    pages: vec![],
                    page_count: 1,
                    bookmarks: Value::Null,
                    errors: vec![],
                    text_quality: "unknown".into(),
                    claims: vec![Claim {
                        claim_id: i.to_string(),
                        kind: "ruleset".into(),
                        value: if i == 0 { "5e" } else { "pathfinder" }.into(),
                        source_id: s.source_id.clone(),
                        page: 1,
                        quote: "rule".into(),
                        actor: "reader".into(),
                        role: ActorRole::Reader,
                    }],
                };
                db.save_evidence(&e).unwrap();
            }
        }
        assert!(
            selection::select(&db, out.path(), None)
                .unwrap()
                .ready
                .is_empty(),
            "{mode}"
        );
    }
}
#[cfg(unix)]
#[test]
fn managed_state_symlink_cannot_write_into_library() {
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    let out = tempdir().unwrap();
    common::pdf(
        &root.path().join("Book.pdf"),
        "Source",
        "D:20200101000000Z",
        false,
    );
    assert!(
        cli(
            work.path(),
            &["scan", "--root", root.path().to_str().unwrap()]
        )
        .status
        .success()
    );
    std::os::unix::fs::symlink(
        root.path().join("forbidden.db"),
        out.path().join("metadata.db"),
    )
    .unwrap();
    assert!(
        selection::select(
            &Store::open_readonly(&work.path().join("selection.db")).unwrap(),
            out.path(),
            None
        )
        .is_err()
    );
    assert!(!root.path().join("forbidden.db").exists());
}
#[test]
fn empty_xmp_modification_is_malformed_instead_of_creation_fallback() {
    let d = dates::resolve(&metadata(
        json!({"CreationDate":"D:20210101000000Z","xmp":"<xmp:ModifyDate xmlns:xmp='http://ns.adobe.com/xap/1.0/'/>"}),
    ));
    assert!(d.effective.is_none());
    assert!(!d.flags.is_empty());
}
#[test]
fn renamed_byte_alias_keeps_hash_bound_human_hold() {
    use rpg_source_select::models::*;
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    let out = tempdir().unwrap();
    let pdf = root.path().join("Original.pdf");
    common::pdf(&pdf, "Held source text", "D:20210101000000Z", false);
    assert!(
        cli(
            work.path(),
            &["scan", "--root", root.path().to_str().unwrap()]
        )
        .status
        .success()
    );
    let mut db = Store::open(&work.path().join("selection.db")).unwrap();
    let g = db.records::<Group>("groups").unwrap().remove(0);
    let source = db.sources().unwrap().remove(0);
    let d = Decision {
        packet_ids: vec![],
        source_hashes: BTreeMap::from([(
            source.source_id.clone(),
            rpg_source_select::grouping::hash_source(&pdf).unwrap(),
        )]),
        group_id: g.group_id.clone(),
        membership_digest: g.membership_digest,
        evidence_digest: String::new(),
        actor: "user".into(),
        actor_role: ActorRole::User,
        outcomes: vec![Outcome {
            source_id: source.source_id,
            status: Status::NeedsReview,
            work_id: None,
            representative_id: None,
            successor_id: None,
        }],
        rationale: "hold".into(),
        evidence_refs: vec![],
    };
    db.put_record("decisions", &g.group_id, &d).unwrap();
    drop(db);
    fs::rename(pdf, root.path().join("Renamed.pdf")).unwrap();
    assert!(
        cli(
            work.path(),
            &["scan", "--root", root.path().to_str().unwrap()]
        )
        .status
        .success()
    );
    assert!(
        selection::select(
            &Store::open_readonly(&work.path().join("selection.db")).unwrap(),
            out.path(),
            None
        )
        .unwrap()
        .ready
        .is_empty()
    );
}
#[test]
fn byte_alias_bridge_does_not_shrink_a_cross_product_component() {
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    let out = tempdir().unwrap();
    let a = root.path().join("Pub/Amber");
    let b = root.path().join("ZZOther/Independent");
    fs::create_dir_all(&a).unwrap();
    fs::create_dir_all(&b).unwrap();
    common::pdf(
        &a.join("Amber-v1.pdf"),
        "Older amber book",
        "D:20200101000000Z",
        false,
    );
    common::pdf(
        &a.join("Amber-v2.pdf"),
        "Newer amber book",
        "D:20210101000000Z",
        false,
    );
    fs::copy(a.join("Amber-v1.pdf"), b.join("Independent.pdf")).unwrap();
    assert!(
        cli(
            work.path(),
            &["scan", "--root", root.path().to_str().unwrap()]
        )
        .status
        .success()
    );
    let s = selection::select(
        &Store::open_readonly(&work.path().join("selection.db")).unwrap(),
        out.path(),
        None,
    )
    .unwrap();
    assert!(s.ready.is_empty());
    assert_eq!(s.records.len(), 1);
}
