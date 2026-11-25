use pdf_extract::{MediaBox, OutputDev, OutputError, Transform};
/// Retain PDF drawing order (including columns), using glyph advances to
/// distinguish kerning/font changes from real inter-word gaps.
#[derive(Default)]
pub struct Text {
    pub text: String,
    last: Option<(f64, f64, f64)>,
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
        let x = trm.m31;
        let y = trm.m32;
        let scale = (trm.m11 * trm.m11 + trm.m12 * trm.m12).sqrt();
        let font = (size * scale).abs();
        if !x.is_finite() || !y.is_finite() || !font.is_finite() || !width.is_finite() {
            return Err(OutputError::FormatError(std::fmt::Error));
        }
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
