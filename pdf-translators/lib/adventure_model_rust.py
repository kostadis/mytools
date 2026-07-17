"""
Python bindings for adventure_model Rust core.

This module provides a Pythonic interface to the Rust implementation
of the adventure data model, including validation, ID assignment,
and TOC building.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union

try:
    from adventure_model_rust import (
        BuildContext as RustBuildContext,
        HomebrewAdventure as RustHomebrewAdventure,
        OfficialAdventureData as RustOfficialAdventureData,
        ParseResult,
        ValidationMode as RustValidationMode,
        ValidationResult as RustValidationResult,
    )
    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False
    RustValidationMode = None
    RustValidationResult = None
    RustBuildContext = None
    RustHomebrewAdventure = None
    RustOfficialAdventureData = None


class ValidationMode:
    """Validation mode: WARN (collect issues) or STRICT (raise immediately)."""
    
    WARN = "WARN"
    STRICT = "STRICT"
    
    @staticmethod
    def warn() -> str:
        return ValidationMode.WARN
    
    @staticmethod
    def strict() -> str:
        return ValidationMode.STRICT


class ValidationResult:
    """Result of validation with errors and warnings."""
    
    def __init__(self, errors: List[str], warnings: List[str]):
        self.errors = errors
        self.warnings = warnings
    
    def has_errors(self) -> bool:
        return len(self.errors) > 0
    
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0
    
    def ok(self) -> bool:
        return len(self.errors) == 0
    
    def summary(self) -> str:
        parts = []
        if self.errors:
            parts.append(f"{len(self.errors)} error(s)")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warning(s)")
        return ", ".join(parts) if parts else "OK"


class BuildContext:
    """Context for validation with mode and ID tracking."""
    
    def __init__(self, mode: str = "warn"):
        self.mode = mode.upper()
        self._rust_ctx = None
        if RUST_AVAILABLE:
            mode_obj = RustValidationMode.warn() if self.mode == "WARN" else RustValidationMode.strict()
            self._rust_ctx = RustBuildContext(mode_obj)
    
    def error(self, msg: str) -> None:
        """Record an error."""
        if self._rust_ctx:
            self._rust_ctx.error(msg)
    
    def warn(self, msg: str) -> None:
        """Record a warning."""
        if self._rust_ctx:
            self._rust_ctx.warn(msg)
    
    def check_id(self, entry_id: str, path: str) -> None:
        """Check for duplicate IDs."""
        if self._rust_ctx:
            self._rust_ctx.check_id(entry_id, path)


class HomebrewAdventure:
    """A 5etools homebrew adventure document."""
    
    def __init__(self, meta: Dict[str, Any], adventure: List[Dict[str, Any]], 
                 adventure_data: List[Dict[str, Any]], is_book: Optional[bool] = None):
        self._data = {
            "_meta": meta,
            "adventure": adventure,
            "adventureData": adventure_data,
        }
        if is_book is not None:
            self._data["isBook"] = is_book
    
    @classmethod
    def from_json(cls, json_str: str) -> "HomebrewAdventure":
        """Parse JSON string into a HomebrewAdventure."""
        data = json.loads(json_str)
        return cls(
            meta=data.get("_meta", {}),
            adventure=data.get("adventure", []),
            adventure_data=data.get("adventureData", []),
            is_book=data.get("isBook"),
        )
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self._data, indent=2)
    
    def validate(self, ctx: Optional[BuildContext] = None) -> ValidationResult:
        """Validate the adventure document."""
        if RUST_AVAILABLE and ctx and ctx._rust_ctx:
            rust_result = self._rust_validate(ctx._rust_ctx)
            return ValidationResult(
                errors=rust_result.errors,
                warnings=rust_result.warnings,
            )
        # Fallback: basic validation
        errors = []
        warnings = []
        if not self._data.get("adventure"):
            errors.append("Missing adventure array")
        if not self._data.get("adventureData"):
            errors.append("Missing adventureData array")
        return ValidationResult(errors, warnings)
    
    def _rust_validate(self, ctx: RustBuildContext) -> RustValidationResult:
        """Validate using Rust backend."""
        rust_adv = RustHomebrewAdventure.from_json(self.to_json())
        return rust_adv.validate(ctx)
    
    def assign_ids(self) -> None:
        """Assign sequential IDs to section/entries/inset nodes."""
        if RUST_AVAILABLE:
            rust_adv = RustHomebrewAdventure.from_json(self.to_json())
            rust_adv.assign_ids()
            self._data = json.loads(rust_adv.to_json())
    
    def build_toc(self) -> None:
        """Rebuild contents[] from data[] sections."""
        if RUST_AVAILABLE:
            rust_adv = RustHomebrewAdventure.from_json(self.to_json())
            rust_adv.build_toc()
            self._data = json.loads(rust_adv.to_json())


class OfficialAdventureData:
    """Official adventure data format: {"data": [...]}."""
    
    def __init__(self, id: str, source: str, data: List[Dict[str, Any]]):
        self._data = {
            "id": id,
            "source": source,
            "data": data,
        }
    
    @classmethod
    def from_json(cls, json_str: str) -> "OfficialAdventureData":
        """Parse JSON string into an OfficialAdventureData."""
        data = json.loads(json_str)
        return cls(
            id=data.get("id", ""),
            source=data.get("source", ""),
            data=data.get("data", []),
        )
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self._data, indent=2)
    
    def validate(self, ctx: Optional[BuildContext] = None) -> ValidationResult:
        """Validate the adventure document."""
        if RUST_AVAILABLE and ctx and ctx._rust_ctx:
            rust_data = RustOfficialAdventureData.from_json(self.to_json())
            rust_result = rust_data.validate(ctx._rust_ctx)
            return ValidationResult(
                errors=rust_result.errors,
                warnings=rust_result.warnings,
            )
        return ValidationResult([], [])


def parse_document(raw: Dict[str, Any], ctx: Optional[BuildContext] = None) -> Union[HomebrewAdventure, OfficialAdventureData]:
    """Parse a raw JSON dict into the appropriate document type."""
    if not isinstance(raw, dict):
        if ctx:
            ctx.error("Top level must be a JSON object")
        return OfficialAdventureData(id="", source="", data=[])
    
    if "adventure" in raw and "adventureData" in raw:
        return HomebrewAdventure.from_json(json.dumps(raw))
    elif "book" in raw and "adventureData" in raw:
        return HomebrewAdventure.from_json(json.dumps(raw))
    elif "data" in raw:
        return OfficialAdventureData.from_json(json.dumps(raw))
    else:
        if ctx:
            ctx.error("Unrecognised top-level structure")
        return OfficialAdventureData(id="", source="", data=[])


# Re-export Rust types for direct use
if RUST_AVAILABLE:
    __all__ = [
        "ValidationMode",
        "ValidationResult",
        "BuildContext",
        "HomebrewAdventure",
        "OfficialAdventureData",
        "parse_document",
        "RustValidationMode",
        "RustValidationResult",
        "RustBuildContext",
        "RustHomebrewAdventure",
        "RustOfficialAdventureData",
    ]
else:
    __all__ = [
        "ValidationMode",
        "ValidationResult",
        "BuildContext",
        "HomebrewAdventure",
        "OfficialAdventureData",
        "parse_document",
    ]
