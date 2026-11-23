use super::worker::{Engine, all_chunks};
use super::*;
use crate::digest_json;
use std::collections::BTreeSet;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Publication {
    pub selection_id: String,
    pub generation: Option<String>,
    pub books: usize,
    pub pending: bool,
}
/// Always reread the latest policy under its lock. A completed old job supplies
/// reusable bytes, never authority to restore its old selection.
pub fn publish(output: &Path, engine: &Engine) -> Result<Publication> {
    let _guard = lock(output, "selection.lock")?;
    let snapshot = selection::load_current(output)?;
    let mut catalog = vec![];
    let mut books = vec![];
    let mut seen = BTreeSet::new();
    for ready in &snapshot.ready {
        safe_id(&ready.work_id)?;
        if !seen.insert(&ready.work_id) {
            return Err(SelectionError::Invalid("duplicate current work IDs".into()));
        }
        if let Ok(chunks) = all_chunks(output, ready, engine) {
            let pages: Vec<_> = chunks.iter().flat_map(|c| c.pages.iter()).collect();
            let text_pages = pages.iter().filter(|p| !p.text.trim().is_empty()).count();
            if text_pages == 0 {
                catalog
                    .push(serde_json::json!({"work":ready,"status":"needs_ocr_or_visual_review"}));
                continue;
            }
            let empty: Vec<_> = pages
                .iter()
                .filter(|p| p.text.trim().is_empty())
                .map(|p| p.page)
                .collect();
            let sparse: Vec<_> = pages
                .iter()
                .filter(|p| {
                    !p.text.trim().is_empty()
                        && p.text.chars().filter(|c| c.is_alphanumeric()).count() < 40
                })
                .map(|p| p.page)
                .collect();
            let mut warnings: Vec<_> = chunks
                .iter()
                .flat_map(|c| c.warnings.iter().cloned())
                .collect();
            for p in &pages {
                if p.text.contains('\u{fffd}') {
                    warnings.push(format!(
                        "PDF page {} contains replacement characters",
                        p.page
                    ));
                }
            }
            let metadata = serde_json::json!({"schema_version":1,"format_version":2,"selection_id":snapshot.snapshot_id,"source":ready,"engine":engine,"total_pages":ready.page_count,"text_pages":text_pages,"empty_pages":empty,"sparse_pages":sparse,"warnings":warnings,"native_layout_limitation":"Native text may omit images, confuse column/table order, or miss text inside images. Caption-only scans may escape sparse-page detection.","pages":pages});
            let mut md = format!(
                "---\ntitle: {}\npublisher: {}\nsource_id: {}\nsource_path: {}\nsource_sha256: {}\npdf_pages: {}\nselection_id: {}\nselection_basis: {}\ninternal_date: {}\n---\n\n# {}\n\nNative PDF text. Images and reading order may need visual review.\n",
                serde_json::to_string(&ready.title)?,
                serde_json::to_string(&ready.publisher)?,
                serde_json::to_string(&ready.source_id)?,
                serde_json::to_string(&ready.relative_path)?,
                serde_json::to_string(&ready.sha256)?,
                ready.page_count,
                serde_json::to_string(&snapshot.snapshot_id)?,
                serde_json::to_string(&ready.selection_basis)?,
                serde_json::to_string(&ready.date)?,
                escape(&ready.title)
            );
            for p in &pages {
                md.push_str(&format!("\n## PDF page {}\n\n", p.page));
                // HTML pre preserves physical line breaks and whitespace without
                // allowing source text to become Markdown/HTML instructions.
                md.push_str("<pre>\n");
                md.push_str(&escape(&p.text));
                md.push_str("</pre>\n");
            }
            let artifact = digest_json(&(1, &metadata, &md));
            let dir = output.join("artifacts").join(&artifact);
            if !dir.join("book.md").exists() {
                atomic_write(&dir.join("book.md"), md.as_bytes())?;
                write_json(&dir.join("book.json"), &metadata)?;
            }
            catalog.push(serde_json::json!({"work":ready,"status":"searchable_with_flags","artifact":artifact,"markdown_sha256":digest_json(&md),"empty_pages":empty,"sparse_pages":sparse}));
            books.push((ready.work_id.clone(), dir));
        } else {
            catalog.push(serde_json::json!({"work":ready,"status":"pending"}));
        }
    }
    let mut result = Publication {
        selection_id: snapshot.snapshot_id.clone(),
        generation: None,
        books: books.len(),
        pending: books.len() < snapshot.ready.len(),
    };
    if books.is_empty() {
        write_json(&output.join("corpus/pending.json"), &result)?;
        return Ok(result);
    }
    let catalog = serde_json::json!({"schema_version":1,"selection_id":snapshot.snapshot_id,"engine":engine,"books":catalog,"policy_records":snapshot.records,"coverage_errors":snapshot.coverage_errors});
    let id = digest_json(&catalog);
    let dir = output.join("corpus/generations").join(&id);
    if !dir.exists() {
        let staging = output
            .join("corpus/generations")
            .join(format!(".build-{}", std::process::id()));
        if staging.exists() {
            fs::remove_dir_all(&staging)?;
        }
        fs::create_dir_all(staging.join("books"))?;
        for (work, artifact) in &books {
            fs::copy(
                artifact.join("book.md"),
                staging.join("books").join(format!("{work}.md")),
            )?;
            File::open(staging.join("books").join(format!("{work}.md")))?.sync_all()?;
            fs::copy(
                artifact.join("book.json"),
                staging.join("books").join(format!("{work}.json")),
            )?;
            File::open(staging.join("books").join(format!("{work}.json")))?.sync_all()?;
        }
        write_json(&staging.join("catalog.json"), &catalog)?;
        File::open(staging.join("books"))?.sync_all()?;
        File::open(&staging)?.sync_all()?;
        fs::rename(staging, &dir)?;
        File::open(dir.parent().unwrap())?.sync_all()?;
    }
    #[cfg(unix)]
    {
        let tmp = output
            .join("corpus")
            .join(format!(".current-{}", std::process::id()));
        let _ = fs::remove_file(&tmp);
        std::os::unix::fs::symlink(Path::new("generations").join(&id), &tmp)?;
        fs::rename(tmp, output.join("corpus/current"))?;
        File::open(output.join("corpus"))?.sync_all()?;
    }
    #[cfg(not(unix))]
    return Err(SelectionError::Invalid(
        "atomic corpus view currently requires Unix".into(),
    ));
    result.generation = Some(id);
    write_json(&output.join("corpus/pending.json"), &result)?;
    Ok(result)
}
fn escape(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}
