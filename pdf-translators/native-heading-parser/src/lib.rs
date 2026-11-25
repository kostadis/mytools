//! Memory-oriented parser experiment. Borrow Python Unicode storage; never
//! encode/copy the full document into a Rust UTF-8 String.
use pyo3::prelude::*;
use pyo3::types::{PyList, PyString, PyTuple};

fn whitespace(c: u32) -> bool {
    matches!(c, 0x09..=0x0d | 0x1c..=0x20 | 0x85 | 0xa0 | 0x1680 |
        0x2000..=0x200a | 0x2028..=0x2029 | 0x202f | 0x205f | 0x3000)
}

// Callers restrict indices to the length of this immutable Python string.
fn read_char(s: &Bound<'_, PyString>, i: isize) -> u32 {
    unsafe { pyo3::ffi::PyUnicode_ReadChar(s.as_ptr(), i) }
}

fn clean_heading<'py>(
    py: Python<'py>,
    line: &Bound<'py, PyString>,
    start: isize,
    end: isize,
) -> PyResult<Bound<'py, PyAny>> {
    // Python slicing preserves lone surrogates, unlike Rust UTF-8 conversion.
    let title = unsafe {
        Bound::from_owned_ptr_or_err(
            py,
            pyo3::ffi::PyUnicode_Substring(line.as_ptr(), start, end),
        )?
    };
    title
        .call_method1("replace", ("*", ""))?
        .call_method0("strip")
}

#[pyfunction]
#[pyo3(signature = (md_text, *, heading_type=None))]
fn parse_markdown_headings<'py>(
    py: Python<'py>,
    md_text: &Bound<'py, PyAny>,
    heading_type: Option<Bound<'py, PyAny>>,
) -> PyResult<Py<PyAny>> {
    // Use the exact Python splitlines contract (including Unicode separators).
    let lines = md_text.call_method0("splitlines")?.cast_into::<PyList>()?;
    let headings = PyList::empty(py);
    let heading_type = match heading_type {
        Some(cls) => cls,
        None => match py.import("__main__")?.getattr("MdHeading") {
            Ok(cls) => cls,
            Err(_) => py
                .import("converters.pdf_to_5etools_v2")?
                .getattr("MdHeading")?,
        },
    };
    for (line_no, item) in lines.iter().enumerate() {
        let line = item.cast::<PyString>()?;
        let n = unsafe { pyo3::ffi::PyUnicode_GetLength(line.as_ptr()) };
        let mut hashes = 0;
        while hashes < n && read_char(line, hashes) == u32::from('#') {
            hashes += 1;
        }
        if hashes == 0 || hashes == n || !whitespace(read_char(line, hashes)) {
            continue;
        }
        let mut start = hashes;
        while start < n && whitespace(read_char(line, start)) {
            start += 1;
        }
        if start == n {
            // Regex \s+(.+?) backtracks one whitespace for the nonempty group.
            if n - hashes < 2 {
                continue;
            }
            start = n - 1;
        }
        let title = clean_heading(py, line, start, n)?;
        headings.append(heading_type.call1((hashes, title, line_no))?)?;
    }
    Ok(PyTuple::new(py, [headings.as_any(), lines.as_any()])?
        .unbind()
        .into_any())
}

#[pymodule]
fn fa_converters_pdf_to_5etools_v2_py_parse_markdown_headings(
    m: &Bound<'_, PyModule>,
) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(parse_markdown_headings, m)?)?;
    Ok(())
}
