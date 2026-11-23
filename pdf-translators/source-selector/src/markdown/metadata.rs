use super::*;
use crate::{
    digest_json,
    grouping::hash_source,
    inventory::{checked_path, fingerprint},
    store::Store,
};
use std::collections::BTreeMap;

#[derive(Clone, Debug, Serialize, Deserialize)]
struct Cached {
    page_count: u32,
    raw: BTreeMap<String, Value>,
}
pub fn probe(root: &Path, source: &Source, legacy: &Store, cache: &mut Store) -> Candidate {
    let mut result = Candidate {
        source: source.clone(),
        sha256: None,
        page_count: None,
        dates: dates::DateEvidence::default(),
        error: None,
    };
    let attempt = (|| -> Result<()> {
        let path = checked_path(root, &source.relative_path)?;
        if fingerprint(&path)? != source.fingerprint {
            return Err(SelectionError::Invalid(
                "source changed since inventory; rescan".into(),
            ));
        }
        let key = digest_json(&(1, &source.fingerprint));
        let sha = match legacy
            .get_cached(&source.source_id, "hash", &key)?
            .and_then(|v| v.as_str().map(str::to_string))
        {
            Some(s) => s,
            None => hash_source(&path)?,
        };
        result.sha256 = Some(sha.clone());
        let metadata: Cached = if let Some(v) = cache.get_cached(&sha, "pdf_metadata", "v1")? {
            serde_json::from_value(v)?
        } else {
            let doc = lopdf::Document::load(&path)
                .map_err(|e| SelectionError::Invalid(format!("metadata parse failed: {e}")))?;
            if doc.is_encrypted() {
                return Err(SelectionError::Invalid(
                    "encrypted PDF requires review".into(),
                ));
            }
            let value = Cached {
                page_count: doc.get_pages().len() as u32,
                raw: crate::evidence::metadata(&doc),
            };
            if value.page_count == 0 {
                return Err(SelectionError::Invalid("PDF has no pages".into()));
            }
            if fingerprint(&path)? != source.fingerprint {
                return Err(SelectionError::Invalid(
                    "source changed during metadata probe".into(),
                ));
            }
            cache.put_cached(&sha, "pdf_metadata", "v1", &serde_json::to_value(&value)?)?;
            value
        };
        result.page_count = Some(metadata.page_count);
        result.dates = dates::resolve(&metadata.raw);
        Ok(())
    })();
    if let Err(e) = attempt {
        result.error = Some(e.to_string());
    }
    result
}
