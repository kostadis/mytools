mod common;
use rpg_source_select::{
    evidence::{PopplerExtractor, TextExtractor},
    inventory::scan_root,
};
use std::time::Duration;
use tempfile::tempdir;
#[test]
#[ignore = "requires installed Poppler; run explicitly"]
fn poppler_roundtrip_preserves_page_text_and_literal_shell_characters() {
    let root = tempdir().unwrap();
    let path = root.path().join("book;$(touch sentinel).pdf");
    common::pdf(&path, "The current revision is 2026.", "D:20260101", false);
    let extractor = PopplerExtractor::new("pdftotext".into(), Duration::from_secs(10));
    let pages = extractor.extract(&path, &[1]).unwrap();
    assert!(pages[0].text.contains("current revision is 2026"));
    assert_eq!(pages[0].page, 1);
    assert!(!root.path().join("sentinel").exists());
    assert_eq!(scan_root(root.path()).unwrap().sources.len(), 1);
}
#[test]
fn missing_extractor_reports_failure() {
    let extractor = PopplerExtractor::new("/nonexistent/pdftotext".into(), Duration::from_secs(1));
    assert!(
        extractor
            .extract(std::path::Path::new("/missing.pdf"), &[1])
            .is_err()
    );
}
