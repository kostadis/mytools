use serde::Serialize;
use std::io::{self, Write};
#[derive(Debug, Clone, Serialize)]
pub struct Outline {
    pub level: usize,
    pub title: String,
    pub page: Option<u32>,
}
pub const BACKEND: &str = "rust-pdf-reader/1";
pub fn emit(value: serde_json::Value) -> io::Result<()> {
    let stdout = io::stdout();
    let mut out = stdout.lock();
    serde_json::to_writer(&mut out, &value)?;
    out.write_all(b"\n")?;
    out.flush()
}
