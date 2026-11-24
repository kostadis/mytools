use super::worker::Engine;
use super::*;
pub fn uri(path: &Path) -> String {
    let mut out = String::new();
    for b in crate::inventory::path_bytes(path) {
        if b.is_ascii_alphanumeric() || b"-._~/".contains(&b) {
            out.push(b as char);
        } else {
            out.push_str(&format!("%{b:02X}"));
        }
    }
    out
}
pub fn annotate(
    md: &str,
    ready: &Ready,
    s: &Snapshot,
    engine: &Engine,
    quality: &Value,
    extracted_at: Option<String>,
) -> Result<String> {
    let (head, body) = md
        .split_once("\n---\n")
        .ok_or_else(|| SelectionError::Invalid("missing Markdown front matter".into()))?;
    Ok(format!(
        "{head}\ngenerator: \"rpg-source-select\"\nwork_id: {}\nselection_policy: {}\nconverter: {}\nextracted_at: {}\nquality: {}\n---\n\n[Source PDF]({})\n{body}",
        serde_json::to_string(&ready.work_id)?,
        serde_json::to_string(&s.policy)?,
        serde_json::to_string(engine)?,
        serde_json::to_string(&extracted_at)?,
        serde_json::to_string(quality)?,
        uri(&s.source_root.join(&ready.relative_path))
    ))
}
pub fn sibling(md: &str, ready: &Ready, s: &Snapshot) -> String {
    let old = format!(
        "[Source PDF]({})",
        uri(&s.source_root.join(&ready.relative_path))
    );
    let new = format!(
        "[Source PDF]({})",
        uri(Path::new(ready.relative_path.file_name().unwrap()))
    );
    md.replacen(&old, &new, 1)
}
