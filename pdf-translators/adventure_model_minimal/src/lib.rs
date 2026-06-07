use pyo3::prelude::*;

pub mod model;
pub mod parser;

pub use model::{Entry, SectionEntry, Meta, ParseError, HomebrewAdventure, TocEntry, TocHeader};
pub use parser::{parse_entry, parse_document};

#[pymodule]
fn adventure_model_minimal(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(parse_entry, m)?)?;
    m.add_function(wrap_pyfunction!(parse_document, m)?)?;
    Ok(())
}