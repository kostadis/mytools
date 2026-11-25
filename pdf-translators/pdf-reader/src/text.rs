use pdf_extract::{MediaBox, OutputDev, OutputError, Transform};
use std::collections::HashMap;
type Cell = (i64, i64);
type PositionedGlyph = (f64, f64, String);

/// Retain PDF drawing order (including columns), using glyph advances to
/// distinguish kerning/font changes from real inter-word gaps.
#[derive(Default)]
pub struct Text {
    pub text: String,
    last: Option<(f64, f64, f64)>,
    seen: HashMap<Cell, Vec<PositionedGlyph>>,
}
impl OutputDev for Text {
    fn begin_page(
        &mut self,
        _: u32,
        _: &MediaBox,
        _: Option<(f64, f64, f64, f64)>,
    ) -> Result<(), OutputError> {
        Ok(())
    }
    fn end_page(&mut self) -> Result<(), OutputError> {
        Ok(())
    }
    fn output_character(
        &mut self,
        trm: &Transform,
        width: f64,
        _: f64,
        size: f64,
        ch: &str,
    ) -> Result<(), OutputError> {
        if ch.contains('\u{fffd}') {
            return Err(OutputError::IoError(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "unmapped font glyph requires review",
            )));
        }
        let x = trm.m31;
        let y = trm.m32;
        let scale = (trm.m11 * trm.m11 + trm.m12 * trm.m12).sqrt();
        let font = (size * scale).abs();
        if !x.is_finite() || !y.is_finite() || !font.is_finite() || !width.is_finite() {
            return Err(OutputError::FormatError(std::fmt::Error));
        }
        // Shadow/bold overprints often draw the same glyph several times with
        // tiny offsets. Deduplicate by geometry, never by repeated letters in
        // the text. Cap tolerance below the advance of a real narrow glyph.
        let epsilon = (font * 0.1)
            .clamp(0.05, 3.0)
            .min((width.abs() * font * 0.3).max(0.05));
        let cell = ((x / 4.0).floor() as i64, (y / 4.0).floor() as i64);
        for dx in -1..=1 {
            for dy in -1..=1 {
                if self
                    .seen
                    .get(&(cell.0.saturating_add(dx), cell.1.saturating_add(dy)))
                    .is_some_and(|items| {
                        items.iter().any(|(px, py, text)| {
                            text == ch && (x - px).abs() <= epsilon && (y - py).abs() <= epsilon
                        })
                    })
                {
                    return Ok(());
                }
            }
        }
        self.seen
            .entry(cell)
            .or_default()
            .push((x, y, ch.to_owned()));
        if let Some((end, last_y, last_size)) = self.last {
            if (y - last_y).abs() > font.min(last_size) * 0.45 {
                if !self.text.ends_with('\n') {
                    self.text.push('\n');
                }
            } else if x - end > font.min(last_size) * 0.25
                && !self.text.ends_with(char::is_whitespace)
            {
                self.text.push(' ');
            }
        }
        self.text.push_str(ch);
        self.last = Some((x + width * font, y, font));
        Ok(())
    }
    fn begin_word(&mut self) -> Result<(), OutputError> {
        Ok(())
    }
    fn end_word(&mut self) -> Result<(), OutputError> {
        Ok(())
    }
    fn end_line(&mut self) -> Result<(), OutputError> {
        Ok(())
    }
}
