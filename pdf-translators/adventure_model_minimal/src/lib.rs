pub mod entry;
pub mod homebrew;
pub mod validation;
pub mod tags;

// Re-export main types for Python bindings
pub use entry::Entry;
pub use homebrew::{HomebrewAdventure, OfficialAdventureData, parse_document, ParseResult};
pub use validation::{BuildContext, ValidationResult, ValidationMode};

// Python bindings via PyO3
#[cfg(feature = "python")]
pub mod pybindings;
