use std::collections::HashMap;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum ValidationMode {
    Warn,   // Collect issues as warnings/errors, never raise
    Strict, // Raise ValidationError immediately on the first error
}

#[derive(Debug)]
pub struct ValidationError {
    pub message: String,
}

impl std::fmt::Display for ValidationError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.message)
    }
}

#[derive(Debug, Default, Clone)]
pub struct ValidationResult {
    pub errors: Vec<String>,
    pub warnings: Vec<String>,
}

impl ValidationResult {
    pub fn new() -> Self {
        Self {
            errors: Vec::new(),
            warnings: Vec::new(),
        }
    }

    pub fn error(&mut self, msg: String) {
        self.errors.push(msg);
    }

    pub fn warn(&mut self, msg: String) {
        self.warnings.push(msg);
    }

    pub fn ok(&self) -> bool {
        self.errors.is_empty()
    }

    pub fn summary(&self) -> String {
        let mut parts = Vec::new();
        if !self.errors.is_empty() {
            parts.push(format!("{} error(s)", self.errors.len()));
        }
        if !self.warnings.is_empty() {
            parts.push(format!("{} warning(s)", self.warnings.len()));
        }
        if parts.is_empty() {
            "OK".to_string()
        } else {
            parts.join(", ")
        }
    }
}

#[derive(Clone, Debug)]
pub struct BuildContext {
    pub mode: ValidationMode,
    pub result: ValidationResult,
    pub ids_seen: HashMap<String, String>,
}

impl BuildContext {
    pub fn new() -> Self {
        Self {
            mode: ValidationMode::Warn,
            result: ValidationResult::new(),
            ids_seen: HashMap::new(),
        }
    }

    pub fn strict() -> Self {
        Self {
            mode: ValidationMode::Strict,
            result: ValidationResult::new(),
            ids_seen: HashMap::new(),
        }
    }

    pub fn error(&mut self, msg: String) {
        self.result.error(msg.clone());
        if self.mode == ValidationMode::Strict {
            panic!("{}", ValidationError { message: msg });
        }
    }

    pub fn warn(&mut self, msg: String) {
        self.result.warn(msg);
    }

    pub fn check_id(&mut self, entry_id: &str, path: &str) {
        if !entry_id.is_empty() {
            if let Some(first_path) = self.ids_seen.get(entry_id) {
                self.warn(format!(
                    "{}: duplicate id '{}' (first at {})",
                    path, entry_id, first_path
                ));
            } else {
                self.ids_seen.insert(entry_id.to_string(), path.to_string());
            }
        }
    }
}
