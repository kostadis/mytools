use crate::{
    Result, SelectionError, grouping::hash_source, inventory::fingerprint, models::*, store::Store,
};
use lopdf::{Document, Object};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    io::{Read, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::{Duration, Instant},
};

pub trait TextExtractor {
    fn extract(&self, path: &Path, pages: &[u32]) -> Result<Vec<PageText>>;
}
pub struct PopplerExtractor {
    binary: PathBuf,
    timeout: Duration,
}
impl PopplerExtractor {
    pub fn new(binary: PathBuf, timeout: Duration) -> Self {
        Self { binary, timeout }
    }
    fn range(&self, path: &Path, first: u32, last: u32) -> Result<Vec<PageText>> {
        let mut child = Command::new(&self.binary)
            .args([
                "-enc",
                "UTF-8",
                "-eol",
                "unix",
                "-f",
                &first.to_string(),
                "-l",
                &last.to_string(),
            ])
            .arg(path.canonicalize()?)
            .arg("-")
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| {
                SelectionError::Invalid(format!("cannot start {}: {e}", self.binary.display()))
            })?;
        let stdout = child.stdout.take().expect("piped stdout");
        let stderr = child.stderr.take().expect("piped stderr");
        let output = std::thread::spawn(move || {
            let mut v = vec![];
            stdout
                .take(64 * 1024 * 1024 + 1)
                .read_to_end(&mut v)
                .map(|_| v)
        });
        let errors = std::thread::spawn(move || {
            let mut v = vec![];
            stderr.take(1024 * 1024 + 1).read_to_end(&mut v).map(|_| v)
        });
        let start = Instant::now();
        let status = loop {
            if let Some(status) = child.try_wait()? {
                break Some(status);
            }
            if start.elapsed() >= self.timeout {
                let _ = child.kill();
                let _ = child.wait();
                break None;
            }
            std::thread::sleep(Duration::from_millis(10));
        };
        let bytes = output
            .join()
            .map_err(|_| SelectionError::Invalid("text reader failed".into()))??;
        let errors = errors
            .join()
            .map_err(|_| SelectionError::Invalid("stderr reader failed".into()))??;
        if status.is_none() {
            return Err(SelectionError::Invalid(format!(
                "pdftotext timed out after {:?}",
                self.timeout
            )));
        }
        if !status.unwrap().success() {
            return Err(SelectionError::Invalid(format!(
                "pdftotext failed: {}",
                String::from_utf8_lossy(&errors)
            )));
        }
        if bytes.len() > 64 * 1024 * 1024 {
            return Err(SelectionError::Invalid(
                "text extraction exceeded 64 MiB; request fewer pages".into(),
            ));
        }
        let text = String::from_utf8(bytes)
            .map_err(|e| SelectionError::Invalid(format!("non-UTF-8 extraction: {e}")))?;
        let parts: Vec<_> = text.split('\u{c}').collect();
        let count = (last - first + 1) as usize;
        if parts.len() < count {
            return Err(SelectionError::Invalid(
                "extractor returned fewer pages than requested".into(),
            ));
        }
        Ok((0..count)
            .map(|i| PageText {
                page: first + i as u32,
                text: parts[i].to_string(),
                images: None,
                annotations: None,
            })
            .collect())
    }
}
impl TextExtractor for PopplerExtractor {
    fn extract(&self, path: &Path, pages: &[u32]) -> Result<Vec<PageText>> {
        let sorted: BTreeSet<_> = pages.iter().copied().collect();
        if sorted.contains(&0) {
            return Err(SelectionError::Invalid("page numbers start at 1".into()));
        }
        let pages: Vec<_> = sorted.into_iter().collect();
        let mut out = vec![];
        let mut i = 0;
        while i < pages.len() {
            let first = pages[i];
            let mut last = first;
            i += 1;
            while i < pages.len() && pages[i] == last + 1 {
                last = pages[i];
                i += 1;
            }
            out.extend(self.range(path, first, last)?);
        }
        Ok(out)
    }
}

fn resolve<'a>(doc: &'a Document, obj: &'a Object, depth: usize) -> Option<&'a Object> {
    if depth > 16 {
        return None;
    }
    match obj {
        Object::Reference(id) => resolve(doc, doc.get_object(*id).ok()?, depth + 1),
        _ => Some(obj),
    }
}
fn metadata(doc: &Document) -> BTreeMap<String, Value> {
    let mut out = BTreeMap::new();
    if let Some(Object::Dictionary(info)) = doc
        .trailer
        .get(b"Info")
        .ok()
        .and_then(|o| resolve(doc, o, 0))
    {
        for (key, obj) in info.iter() {
            if let Some(o) = resolve(doc, obj, 0) {
                let v = match o {
                    Object::String(bytes, _) => json!(
                        lopdf::decode_text_string(o)
                            .unwrap_or_else(|_| String::from_utf8_lossy(bytes).into_owned())
                    ),
                    _ => json!(format!("{o:?}")),
                };
                out.insert(String::from_utf8_lossy(key).into_owned(), v);
            }
        }
    }
    if let Ok(catalog) = doc.catalog() {
        if let Some(Object::Stream(s)) = catalog
            .get(b"Metadata")
            .ok()
            .and_then(|o| resolve(doc, o, 0))
        {
            match s.get_plain_content_with_limit(1024 * 1024) {
                Ok(bytes) => {
                    out.insert("xmp".into(), json!(String::from_utf8_lossy(&bytes)));
                }
                Err(e) => {
                    out.insert("xmp_error".into(), json!(e.to_string()));
                }
            }
        }
    }
    out
}

pub fn inspect_pdf(
    path: &Path,
    source: &Source,
    pages: Option<&[u32]>,
    extractor: &dyn TextExtractor,
) -> Result<Evidence> {
    if fingerprint(path)? != source.fingerprint {
        return Err(SelectionError::Invalid("source changed since scan".into()));
    }
    let sha = hash_source(path)?;
    let doc = Document::load(path)
        .map_err(|e| SelectionError::Invalid(format!("PDF parse {}: {e}", path.display())))?;
    if doc.is_encrypted() {
        return Err(SelectionError::Invalid(
            "encrypted PDF requires manual inspection".into(),
        ));
    }
    let page_ids = doc.get_pages();
    let count = page_ids.len() as u32;
    let selected: Vec<u32> = pages
        .map(|v| v.to_vec())
        .unwrap_or_else(|| (1..=count).collect());
    if selected.is_empty() || selected.iter().any(|p| !page_ids.contains_key(p)) {
        return Err(SelectionError::Invalid(
            "requested page is outside the document".into(),
        ));
    }
    let mut text = extractor.extract(path, &selected)?;
    let expected: BTreeSet<_> = selected.iter().copied().collect();
    let got: BTreeSet<_> = text.iter().map(|p| p.page).collect();
    if expected != got || text.len() != got.len() {
        return Err(SelectionError::Invalid(
            "extractor page coverage mismatch".into(),
        ));
    }
    for p in &mut text {
        let id = page_ids[&p.page];
        p.images = doc.get_page_images(id).ok().map(|images| images.len());
        p.annotations = doc
            .get_dictionary(id)
            .ok()
            .and_then(|d| match d.get(b"Annots") {
                Ok(o) => resolve(&doc, o, 0)
                    .and_then(|o| o.as_array().ok())
                    .map(|a| a.len()),
                Err(lopdf::Error::DictKey(_)) => Some(0),
                _ => None,
            });
    }
    text.sort_by_key(|p| p.page);
    let mut errors = vec![];
    let bookmarks = match doc.get_toc() {
        Ok(toc) => {
            errors.extend(toc.errors);
            json!(
                toc.toc
                    .into_iter()
                    .map(|t| json!({"level":t.level,"title":t.title,"page":t.page}))
                    .collect::<Vec<_>>()
            )
        }
        Err(e) => {
            errors.push(format!("bookmarks unavailable: {e}"));
            json!([])
        }
    };
    if fingerprint(path)? != source.fingerprint {
        return Err(SelectionError::Invalid(
            "source changed during inspection".into(),
        ));
    }
    let quality = if text.iter().any(|p| p.text.chars().any(char::is_alphabetic)) {
        "text"
    } else {
        "unknown"
    };
    Ok(Evidence {
        source_id: source.source_id.clone(),
        sha256: sha,
        version: 1,
        pdf_metadata: metadata(&doc),
        pages: text,
        page_count: count,
        bookmarks,
        errors,
        text_quality: quality.into(),
        claims: vec![],
    })
}

pub fn normalize_whitespace(text: &str) -> String {
    text.split_whitespace().collect::<Vec<_>>().join(" ")
}
pub fn validate_claim(claim: &Claim, evidence: &Evidence) -> bool {
    let quote = normalize_whitespace(&claim.quote);
    !quote.is_empty()
        && claim.source_id == evidence.source_id
        && evidence
            .pages
            .iter()
            .any(|p| p.page == claim.page && normalize_whitespace(&p.text).contains(&quote))
}

impl Store {
    pub fn save_evidence(&mut self, evidence: &Evidence) -> Result<()> {
        let mut compressor = flate2::write::GzEncoder::new(vec![], flate2::Compression::default());
        compressor.write_all(&serde_json::to_vec(evidence)?)?;
        self.put_record(
            "evidence",
            &evidence.source_id,
            &json!({"codec":"gzip","bytes":compressor.finish()?}),
        )
    }
    pub fn evidence(&self) -> Result<Vec<Evidence>> {
        self.records::<Value>("evidence")?
            .into_iter()
            .map(|v| {
                let bytes: Vec<u8> = serde_json::from_value(v["bytes"].clone())?;
                let mut out = vec![];
                flate2::read::GzDecoder::new(bytes.as_slice())
                    .take(64 * 1024 * 1024 + 1)
                    .read_to_end(&mut out)?;
                if out.len() > 64 * 1024 * 1024 {
                    return Err(SelectionError::Invalid(
                        "cached evidence exceeds limit".into(),
                    ));
                }
                Ok(serde_json::from_slice(&out)?)
            })
            .collect()
    }
}
