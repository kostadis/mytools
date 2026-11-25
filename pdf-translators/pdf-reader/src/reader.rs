use crate::{outline, protocol::Outline, text::Text};
use lopdf::{Document, LoadOptions, Object, ObjectId};
use std::path::Path;
pub fn filter(id: ObjectId, object: &mut Object) -> Option<(ObjectId, Object)> {
    if let Ok(stream) = object.as_stream_mut() {
        if stream.dict.get(b"Subtype").and_then(Object::as_name).ok() == Some(b"Image".as_slice()) {
            stream.content = Vec::new();
            stream.dict.set("Length", 0);
        }
    }
    Some((id, object.clone()))
}
pub struct Reader {
    doc: Document,
    pub count: u32,
    pub outline: Vec<Outline>,
}
impl Reader {
    pub fn open(path: &Path) -> Result<Self, (&'static str, String)> {
        if !path.is_file() {
            return Err((
                "unreadable_input",
                format!("cannot read {}", path.display()),
            ));
        }
        let doc = Document::load_with_options(
            path,
            LoadOptions {
                filter: Some(filter),
                max_decompressed_size: Some(64 * 1024 * 1024),
                ..Default::default()
            },
        )
        .map_err(|e| ("invalid_pdf", e.to_string()))?;
        if doc.is_encrypted() {
            return Err(("password_required", "PDF requires a password".into()));
        }
        let count = doc.get_pages().len() as u32;
        if count == 0 {
            return Err(("invalid_pdf", "PDF has no readable pages".into()));
        }
        let outline = outline::read(&doc).map_err(|e| ("invalid_outline", e))?;
        Ok(Self {
            doc,
            count,
            outline,
        })
    }
    pub fn text(&self, page: u32) -> Result<String, String> {
        let mut output = Text::default();
        pdf_extract::output_doc_page(&self.doc, &mut output, page).map_err(|e| e.to_string())?;
        Ok(output.text)
    }
}
