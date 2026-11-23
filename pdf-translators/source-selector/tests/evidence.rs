mod common;
use rpg_source_select::{
    Result,
    compare::compare_evidence,
    evidence::{TextExtractor, inspect_pdf, validate_claim},
    inventory::scan_root,
    models::*,
};
use std::path::Path;
use tempfile::tempdir;
struct Reader(&'static str);
impl TextExtractor for Reader {
    fn extract(&self, _: &Path, pages: &[u32]) -> Result<Vec<PageText>> {
        Ok(pages
            .iter()
            .map(|p| PageText {
                page: *p,
                text: self.0.into(),
                images: None,
                annotations: None,
            })
            .collect())
    }
}

#[test]
fn raw_indirect_dates_pages_and_quoted_evidence_survive_inspection() {
    let root = tempdir().unwrap();
    let path = root.path().join("book-v3.pdf");
    common::pdf(&path, "Revision 2020", "D:20200101garbled", false);
    let source = scan_root(root.path()).unwrap().sources.remove(0);
    let evidence = inspect_pdf(
        &path,
        &source,
        None,
        &Reader("Revision 2020. Keep THIS punctuation!"),
    )
    .unwrap();
    assert_eq!(evidence.pdf_metadata["ModDate"], "D:20200101garbled");
    assert_eq!(evidence.pages[0].page, 1);
    assert_eq!(evidence.page_count, 1);
    let mut claim = Claim {
        claim_id: "c1".into(),
        kind: "revision".into(),
        value: "2020".into(),
        source_id: source.source_id.clone(),
        page: 1,
        quote: "Revision  2020.".into(),
        actor: "small".into(),
        role: ActorRole::Reader,
    };
    assert!(validate_claim(&claim, &evidence));
    claim.quote = "revision 2020.".into();
    assert!(!validate_claim(&claim, &evidence));
    claim.quote = "Invented date".into();
    assert!(!validate_claim(&claim, &evidence));
    assert!(inspect_pdf(&path, &source, Some(&[2]), &Reader("text")).is_err());
}

#[test]
fn equal_text_with_different_images_does_not_establish_equivalence() {
    let root = tempdir().unwrap();
    common::pdf(&root.path().join("a.pdf"), "same", "D:20240101", false);
    common::pdf(&root.path().join("b.pdf"), "same", "D:20200101", true);
    let sources = scan_root(root.path()).unwrap().sources;
    let a = inspect_pdf(
        &root.path().join(&sources[0].relative_path),
        &sources[0],
        None,
        &Reader("same contents"),
    )
    .unwrap();
    let b = inspect_pdf(
        &root.path().join(&sources[1].relative_path),
        &sources[1],
        None,
        &Reader("same contents"),
    )
    .unwrap();
    let comparison = compare_evidence(&a, &b);
    assert!(comparison.normalized_text_equal);
    assert!(comparison.visual_differences);
    assert!(!comparison.exact_bytes);
    assert_ne!(a.pdf_metadata["ModDate"], b.pdf_metadata["ModDate"]);
}

#[test]
fn empty_text_is_unknown_and_bad_pdfs_are_not_successful_empty_evidence() {
    let root = tempdir().unwrap();
    let path = root.path().join("scan.pdf");
    common::pdf(&path, "", "", true);
    let source = scan_root(root.path()).unwrap().sources.remove(0);
    let a = inspect_pdf(&path, &source, None, &Reader("")).unwrap();
    assert_eq!(a.text_quality, "unknown");
    assert!(!compare_evidence(&a, &a).normalized_text_equal);
    std::fs::write(&path, b"not a pdf").unwrap();
    assert!(inspect_pdf(&path, &source, None, &Reader("")).is_err());
}
