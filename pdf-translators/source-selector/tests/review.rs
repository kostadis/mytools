mod common;
use rpg_source_select::{
    Result,
    evidence::{TextExtractor, inspect_pdf},
    grouping::build_groups,
    inventory::scan_root,
    models::*,
    review::*,
    store::Store,
};
use std::path::Path;
use tempfile::tempdir;
struct Reader;

#[test]
fn user_can_defer_an_uninspected_group_without_claiming_it_is_convertible() {
    let (_r, _w, mut db, sources, group, _evidence) = setup(&["book-v1.pdf", "book-v3.pdf"]);
    let mut d = propose_decision(&group, &[], &sources, None);
    d.actor_role = ActorRole::User;
    d.actor = "gm".into();
    d.rationale = "Defer until readable evidence is available".into();
    db.save_decision(&d).unwrap();
    let saved = db.current_decisions().unwrap();
    assert_eq!(saved.len(), 1);
    assert!(
        saved[0]
            .outcomes
            .iter()
            .all(|o| o.status == Status::NeedsReview)
    );
}

#[test]
fn split_packets_preserve_unicode_text_and_say_when_more_parts_are_required() {
    let (_r, _w, _db, sources, group, mut evidence) = setup(&["book.pdf"]);
    evidence[0].pages[0].text = "Ω revision evidence. ".repeat(1000);
    let packets = prepare_packets(&group, &evidence, &sources, ActorRole::Reader, 4096).unwrap();
    assert!(packets.len() > 1);
    let combined: String = packets
        .iter()
        .flat_map(|p| p.excerpts.iter().map(|x| x.text.as_str()))
        .collect();
    assert_eq!(combined, evidence[0].pages[0].text);
    for p in &packets {
        assert_eq!(p.total_parts, packets.len());
        assert!(serde_json::to_string(p).unwrap().chars().count() <= 4096);
    }
}

#[test]
fn source_changes_reject_saved_decisions_even_when_group_record_is_unchanged() {
    let (root, _w, mut db, sources, group, evidence) = setup(&["book.pdf"]);
    for e in &evidence {
        db.save_evidence(e).unwrap();
    }
    let proposal = propose_decision(&group, &evidence, &sources, None);
    std::fs::write(root.path().join(&sources[0].relative_path), b"changed").unwrap();
    assert!(db.save_decision(&proposal).is_err());
}

#[test]
fn sol_cannot_cite_another_groups_claim_to_exclude_a_source() {
    let (_r, _w, _db, sources, group, mut evidence) = setup(&["book-v1.pdf", "book-v3.pdf"]);
    let mut unrelated = evidence[0].clone();
    unrelated.source_id = "unrelated".into();
    unrelated.claims.push(Claim {
        claim_id: "outside".into(),
        kind: "revision".into(),
        value: "2026".into(),
        source_id: "unrelated".into(),
        page: 1,
        quote: "Revision 2026".into(),
        actor: "reader".into(),
        role: ActorRole::Reader,
    });
    evidence.push(unrelated);
    let mut d = propose_decision(&group, &evidence, &sources, None);
    d.actor_role = ActorRole::Sol;
    d.actor = "sol".into();
    d.evidence_refs = vec!["outside".into()];
    d.rationale = "Unsupported comparison".into();
    d.outcomes[0].status = Status::Selected;
    d.outcomes[1].status = Status::Superseded;
    d.outcomes[1].successor_id = Some(d.outcomes[0].source_id.clone());
    assert!(accept_decision(d, &group, &evidence, &sources).is_err());
}
impl TextExtractor for Reader {
    fn extract(&self, _: &Path, pages: &[u32]) -> Result<Vec<PageText>> {
        Ok(pages
            .iter()
            .map(|p| PageText {
                page: *p,
                text: "Revision 2026 replaces revision 2020.".into(),
                images: None,
                annotations: None,
            })
            .collect())
    }
}
fn setup(
    names: &[&str],
) -> (
    tempfile::TempDir,
    tempfile::TempDir,
    Store,
    Vec<Source>,
    Group,
    Vec<Evidence>,
) {
    let root = tempdir().unwrap();
    let work = tempdir().unwrap();
    std::fs::create_dir_all(root.path().join("P/Book")).unwrap();
    for (i, name) in names.iter().enumerate() {
        common::pdf(
            &root.path().join("P/Book").join(name),
            &format!("{i}"),
            "D:20260101",
            false,
        );
    }
    let inv = scan_root(root.path()).unwrap();
    let mut db = Store::open(&work.path().join("s.db")).unwrap();
    db.upsert_inventory(&inv).unwrap();
    let groups = build_groups(&inv.sources, &[], &mut db).unwrap();
    assert_eq!(groups.len(), 1);
    let evidence = inv
        .sources
        .iter()
        .map(|s| inspect_pdf(&root.path().join(&s.relative_path), s, None, &Reader).unwrap())
        .collect();
    (root, work, db, inv.sources, groups[0].clone(), evidence)
}
#[test]
fn differing_versions_are_reviewed_and_single_old_copy_is_not_auto_selected() {
    let (_r, _w, _db, sources, group, evidence) = setup(&["book-v1.pdf", "book-v3.pdf"]);
    let proposal = propose_decision(&group, &evidence, &sources, None);
    assert!(
        proposal
            .outcomes
            .iter()
            .all(|o| o.status == Status::NeedsReview)
    );
    let (_r, _w, _db, sources, group, evidence) = setup(&["book.old-001.pdf"]);
    assert_eq!(
        propose_decision(&group, &evidence, &sources, None).outcomes[0].status,
        Status::NeedsReview
    );
}
#[test]
fn reader_cannot_make_decisions_and_stale_or_dangling_rulings_are_rejected() {
    let (_r, _w, _db, sources, group, evidence) = setup(&["book-v1.pdf", "book-v3.pdf"]);
    let mut proposal = propose_decision(&group, &evidence, &sources, None);
    proposal.actor_role = ActorRole::Reader;
    assert!(accept_decision(proposal.clone(), &group, &evidence, &sources).is_err());
    proposal.actor_role = ActorRole::User;
    proposal.outcomes[0].status = Status::Superseded;
    proposal.outcomes[0].successor_id = Some("missing".into());
    assert!(accept_decision(proposal.clone(), &group, &evidence, &sources).is_err());
    proposal.outcomes.remove(0);
    assert!(accept_decision(proposal, &group, &evidence, &sources).is_err());
}
#[test]
fn user_can_keep_distinct_works_and_ruling_survives_only_unchanged_membership() {
    let (_r, _w, mut db, sources, group, evidence) = setup(&["book-v1.pdf", "book-v3.pdf"]);
    for e in &evidence {
        db.save_evidence(e).unwrap();
    }
    let mut ruling = propose_decision(&group, &evidence, &sources, None);
    ruling.actor_role = ActorRole::User;
    ruling.actor = "gm".into();
    ruling.rationale = "Different works after inspection".into();
    for outcome in &mut ruling.outcomes {
        outcome.status = Status::DistinctWork;
    }
    let ruling = accept_decision(ruling, &group, &evidence, &sources).unwrap();
    db.save_decision(&ruling).unwrap();
    assert_ne!(ruling.outcomes[0].work_id, ruling.outcomes[1].work_id);
    assert_eq!(db.current_decisions().unwrap().len(), 1);
    let mut changed = group.clone();
    changed.membership_digest = "changed".into();
    assert!(accept_decision(ruling, &changed, &evidence, &sources).is_err());
    db.replace_records(
        "groups",
        &[(
            changed.group_id.clone(),
            serde_json::to_value(changed).unwrap(),
        )],
    )
    .unwrap();
    assert!(db.current_decisions().unwrap().is_empty());
}
#[test]
fn exact_duplicates_prefer_explicit_baseline_and_reader_claims_require_real_quotes() {
    let (root, _w, mut db, mut sources, _group, _evidence) = setup(&["book-v1.pdf", "book-v3.pdf"]);
    std::fs::copy(
        root.path().join(&sources[0].relative_path),
        root.path().join(&sources[1].relative_path),
    )
    .unwrap();
    sources = scan_root(root.path()).unwrap().sources;
    sources[1].baseline_established = true;
    db.upsert_inventory(&InventoryResult {
        root: root.path().to_path_buf(),
        started: "".into(),
        finished: "".into(),
        sources: sources.clone(),
        errors: vec![],
    })
    .unwrap();
    let group = build_groups(&sources, &[], &mut db).unwrap().remove(0);
    let evidence: Vec<_> = sources
        .iter()
        .map(|s| inspect_pdf(&root.path().join(&s.relative_path), s, None, &Reader).unwrap())
        .collect();
    let proposal = propose_decision(&group, &evidence, &sources, None);
    let duplicate = proposal
        .outcomes
        .iter()
        .find(|o| o.status == Status::ExactDuplicate)
        .unwrap();
    assert_eq!(
        duplicate.representative_id.as_deref(),
        Some(sources[1].source_id.as_str())
    );
    let packets = prepare_packets(&group, &evidence, &sources, ActorRole::Reader, 2000).unwrap();
    assert!(!packets.is_empty());
    let claim = Claim {
        claim_id: "c1".into(),
        kind: "revision".into(),
        value: "2026".into(),
        source_id: sources[0].source_id.clone(),
        page: 1,
        quote: "Revision 2026".into(),
        actor: "small".into(),
        role: ActorRole::Reader,
    };
    assert_eq!(
        apply_reader_claims(&packets[0], std::slice::from_ref(&claim), &evidence)
            .unwrap()
            .len(),
        1
    );
    let mut fake = claim;
    fake.quote = "Never written".into();
    assert!(apply_reader_claims(&packets[0], &[fake], &evidence).is_err());
}
