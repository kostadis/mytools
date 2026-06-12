use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use serde_json::Value;

use crate::entry::Entry;
use crate::homebrew::{HomebrewAdventure, OfficialAdventureData, ParseResult};
use crate::validation::{BuildContext, ValidationResult, ValidationMode};

/// Python bindings for adventure_model Rust core
#[pymodule]
fn adventure_model(_py: Python, m: &PyModule) -> PyResult<()> {
    // ValidationMode enum
    #[pyclass]
    #[derive(Clone)]
    struct PyValidationMode(ValidationMode);

    #[pymethods]
    impl PyValidationMode {
        #[getter]
        fn name(&self) -> String {
            match self.0 {
                ValidationMode::Warn => "WARN".to_string(),
                ValidationMode::Strict => "STRICT".to_string(),
            }
        }

        #[staticmethod]
        fn warn() -> PyValidationMode {
            PyValidationMode(ValidationMode::Warn)
        }

        #[staticmethod]
        fn strict() -> PyValidationMode {
            PyValidationMode(ValidationMode::Strict)
        }
    }

    m.add_class::<PyValidationMode>()?;

    // ValidationResult
    #[pyclass]
    struct PyValidationResult {
        errors: Vec<String>,
        warnings: Vec<String>,
    }

    #[pymethods]
    impl PyValidationResult {
        #[getter]
        fn get_errors(&self) -> Vec<String> {
            self.errors.clone()
        }

        #[getter]
        fn get_warnings(&self) -> Vec<String> {
            self.warnings.clone()
        }

        fn has_errors(&self) -> bool {
            !self.errors.is_empty()
        }

        fn has_warnings(&self) -> bool {
            !self.warnings.is_empty()
        }
    }

    impl From<ValidationResult> for PyValidationResult {
        fn from(val: ValidationResult) -> Self {
            PyValidationResult {
                errors: val.errors,
                warnings: val.warnings,
            }
        }
    }

    m.add_class::<PyValidationResult>()?;

    // BuildContext
    #[pyclass]
    struct PyBuildContext {
        mode: ValidationMode,
    }

    #[pymethods]
    impl PyBuildContext {
        #[new]
        fn new(mode: Option<&str>) -> PyResult<Self> {
            let mode_str = mode.unwrap_or("warn");
            let mode = match mode_str.to_uppercase().as_str() {
                "WARN" => ValidationMode::Warn,
                "STRICT" => ValidationMode::Strict,
                _ => return Err(PyValueError::new_err("Invalid mode, must be 'warn' or 'strict'")),
            };
            Ok(PyBuildContext { mode })
        }

        #[getter]
        fn mode(&self) -> PyValidationMode {
            PyValidationMode(self.mode.clone())
        }
    }

    m.add_class::<PyBuildContext>()?;

    // HomebrewAdventure
    #[pyclass]
    struct PyHomebrewAdventure {
        inner: HomebrewAdventure,
    }

    #[pymethods]
    impl PyHomebrewAdventure {
        #[staticmethod]
        fn from_json(json_str: &str) -> PyResult<Self> {
            let adventure: HomebrewAdventure = serde_json::from_str(json_str)
                .map_err(|e| PyValueError::new_err(format!("Failed to parse JSON: {}", e)))?;
            Ok(PyHomebrewAdventure { inner: adventure })
        }

        fn to_json(&self) -> String {
            serde_json::to_string_pretty(&self.inner).unwrap_or_default()
        }

        fn validate(&self) -> PyValidationResult {
            let ctx = self.inner.validate();
            PyValidationResult {
                errors: ctx.result.errors,
                warnings: ctx.result.warnings,
            }
        }

        fn assign_ids(&mut self) {
            self.inner.assign_ids();
        }

        fn build_toc(&mut self) {
            self.inner.build_toc();
        }
    }

    m.add_class::<PyHomebrewAdventure>()?;

    // OfficialAdventureData
    #[pyclass]
    struct PyOfficialAdventureData {
        inner: OfficialAdventureData,
    }

    #[pymethods]
    impl PyOfficialAdventureData {
        #[staticmethod]
        fn from_json(json_str: &str) -> PyResult<Self> {
            let data: OfficialAdventureData = serde_json::from_str(json_str)
                .map_err(|e| PyValueError::new_err(format!("Failed to parse JSON: {}", e)))?;
            Ok(PyOfficialAdventureData { inner: data })
        }

        fn to_json(&self) -> String {
            serde_json::to_string_pretty(&self.inner).unwrap_or_default()
        }
    }

    m.add_class::<PyOfficialAdventureData>()?;

    // parse_document
    #[pyfunction]
    fn parse_document(json_str: &str) -> PyResult<PyObject> {
        let value: Value = serde_json::from_str(json_str)
            .map_err(|e| PyValueError::new_err(format!("Failed to parse JSON: {}", e)))?;
        
        let mut ctx = BuildContext::new();
        match crate::parse_document(value, &mut ctx) {
            ParseResult::Homebrew(adv) => {
                let py_adv = PyHomebrewAdventure { inner: adv };
                Python::with_gil(|py| Ok(py_adv.into_py(py)))
            }
            ParseResult::Official(data) => {
                let py_data = PyOfficialAdventureData { inner: data };
                Python::with_gil(|py| Ok(py_data.into_py(py)))
            }
        }
    }

    m.add_function(wrap_pyfunction!(parse_document, m)?)?;

    Ok(())
}
