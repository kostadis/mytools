use std::fs;
use std::io;
use std::path::{Path, PathBuf};

#[derive(Default)]
pub struct Document {
    text: String,
    saved_text: String,
    path: Option<PathBuf>,
}

impl Document {
    pub fn text(&self) -> &str {
        &self.text
    }

    pub fn text_mut(&mut self) -> &mut String {
        &mut self.text
    }

    pub fn path(&self) -> Option<&Path> {
        self.path.as_deref()
    }

    pub fn is_dirty(&self) -> bool {
        self.text != self.saved_text
    }

    pub fn title(&self) -> String {
        let name = self
            .path
            .as_deref()
            .and_then(Path::file_name)
            .map(|name| name.to_string_lossy().into_owned())
            .unwrap_or_else(|| "Untitled.md".to_owned());
        format!(
            "{}{} — Markdown Editor",
            name,
            if self.is_dirty() { " *" } else { "" }
        )
    }

    pub fn new_file(&mut self) {
        *self = Self::default();
    }

    pub fn open(&mut self, path: PathBuf) -> io::Result<()> {
        let text = fs::read_to_string(&path)?;
        self.saved_text = text.clone();
        self.text = text;
        self.path = Some(path);
        Ok(())
    }

    pub fn save(&mut self) -> io::Result<()> {
        let path = self.path.clone().ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidInput,
                "Choose a file name with Save As first",
            )
        })?;
        fs::write(path, &self.text)?;
        self.saved_text.clone_from(&self.text);
        Ok(())
    }

    pub fn save_as(&mut self, path: PathBuf) -> io::Result<()> {
        fs::write(&path, &self.text)?;
        self.path = Some(path);
        self.saved_text.clone_from(&self.text);
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn open_save_and_dirty_tracking() {
        let path = std::env::temp_dir().join(format!(
            "markdown-editor-{}-{}.md",
            std::process::id(),
            "document-test"
        ));
        fs::write(&path, "# Original\n").unwrap();
        let mut doc = Document::default();
        doc.open(path.clone()).unwrap();
        assert!(!doc.is_dirty());
        doc.text_mut().push_str("More text\n");
        assert!(doc.is_dirty());
        doc.save().unwrap();
        assert!(!doc.is_dirty());
        assert_eq!(
            fs::read_to_string(&path).unwrap(),
            "# Original\nMore text\n"
        );
        fs::remove_file(path).unwrap();
    }

    #[test]
    fn failed_open_keeps_current_document() {
        let mut doc = Document::default();
        doc.text_mut().push_str("keep me");
        assert!(
            doc.open(PathBuf::from("/this/file/does/not/exist.md"))
                .is_err()
        );
        assert_eq!(doc.text(), "keep me");
        assert!(doc.is_dirty());
    }
}
