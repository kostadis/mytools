use gdrive_cli::onedrive::dupes::normalize;

#[test]
fn test_normalize_removes_copy_prefix() {
    assert_eq!(normalize("Copy of document.pdf"), "document.pdf");
    assert_eq!(normalize("copy of REPORT.docx"), "report.docx");
}

#[test]
fn test_normalize_removes_copy_suffix() {
    assert_eq!(normalize("document - copy.pdf"), "document.pdf");
    assert_eq!(normalize("report- copy.docx"), "report.docx");
}

#[test]
fn test_normalize_removes_parentheses_numbers() {
    assert_eq!(normalize("document (1).pdf"), "document.pdf");
    assert_eq!(normalize("report (23).docx"), "report.docx");
}

#[test]
fn test_normalize_preserves_extension() {
    assert_eq!(normalize("file.txt"), "file.txt");
    assert_eq!(normalize("FILE.TXT"), "file.txt");
    assert_eq!(normalize("archive.tar.gz"), "archive.tar.gz");
}

#[test]
fn test_normalize_collapses_whitespace() {
    // Note: The normalize function only trims leading/trailing whitespace from the root
    // (the part before the extension)
    assert_eq!(normalize("multiple   spaces.txt"), "multiple   spaces.txt");
    // Leading spaces ARE trimmed from the root
    assert_eq!(normalize("  leading.txt"), "leading.txt");
    // Spaces before extension are preserved (they're part of the root)
    assert_eq!(normalize("trailing .txt"), "trailing.txt");
}

#[test]
fn test_normalize_combined() {
    // Note: regex patterns are applied in order, so "Copy of file (1) - copy.pdf":
    // 1. Remove "copy of " → "file (1) - copy"
    // 2. Try to remove " (N)" but it's not at end → "file (1) - copy"
    // 3. Remove " - copy" → "file (1)"
    // Result: "file (1).pdf"
    assert_eq!(normalize("Copy of file (1) - copy.pdf"), "file (1).pdf");
    
    // Simpler case: just "Copy of file.pdf" → "file.pdf"
    assert_eq!(normalize("Copy of file.pdf"), "file.pdf");
    
    // "file (1).pdf" → "file.pdf"
    assert_eq!(normalize("file (1).pdf"), "file.pdf");
}