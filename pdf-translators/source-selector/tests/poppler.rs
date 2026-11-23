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

#[cfg(unix)]
#[test]
fn extractor_timeout_and_nonzero_exit_are_explicit_errors() {
    use std::os::unix::fs::PermissionsExt;
    let root = tempdir().unwrap();
    let path = root.path().join("book.pdf");
    common::pdf(&path, "text", "", false);
    let script = root.path().join("extractor");
    std::fs::write(&script, "#!/bin/sh\nexec sleep 3\n").unwrap();
    std::fs::set_permissions(&script, std::fs::Permissions::from_mode(0o700)).unwrap();
    let start = std::time::Instant::now();
    let e = PopplerExtractor::new(script.clone(), Duration::from_millis(50))
        .extract(&path, &[1])
        .unwrap_err();
    assert!(e.to_string().contains("timed out"));
    assert!(start.elapsed() < Duration::from_secs(1));
    std::fs::write(&script, "#!/bin/sh\necho broken-extractor >&2\nexit 3\n").unwrap();
    let e = PopplerExtractor::new(script, Duration::from_secs(1))
        .extract(&path, &[1])
        .unwrap_err();
    assert!(e.to_string().contains("broken-extractor"));
}

#[cfg(unix)]
#[test]
fn version_timeout_does_not_wait_for_inherited_child_pipes() {
    use std::os::unix::fs::PermissionsExt;
    let root = tempdir().unwrap();
    let script = root.path().join("extractor");
    std::fs::write(&script, "#!/bin/sh\nsleep 3\n").unwrap();
    std::fs::set_permissions(&script, std::fs::Permissions::from_mode(0o700)).unwrap();
    let extractor = PopplerExtractor::new(script, Duration::from_millis(100));
    let start = std::time::Instant::now();
    let provenance = extractor.provenance();
    assert!(
        provenance["version_error"]
            .as_str()
            .unwrap()
            .contains("timed out")
    );
    assert!(start.elapsed() < Duration::from_secs(1));
}
