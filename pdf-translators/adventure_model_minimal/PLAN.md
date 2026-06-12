# Plan: Replace adventure_model.py with Rust Implementation

This document outlines the comprehensive plan to replace the Python `adventure_model.py` implementation with a Rust implementation in `adventure_model_minimal`, using a Python wrapper via PyO3.

## Overview

The goal is to create a high-performance Rust implementation of the 5etools adventure data model that maintains exact compatibility with the existing Python API, exposing it through a Python wrapper to ensure seamless integration with the existing codebase.

## Phase 1: Rust Implementation (Core Functionality)

### 1.1 Struct Design
- Create equivalent Rust structs for all Python dataclasses:
  - `EntryBase` (base class with type, name, id, page fields)
  - All 18+ subclasses: `SectionEntry`, `EntriesEntry`, `InsetEntry`, `InsetReadaloudEntry`, `QuoteEntry`, `ListEntry`, `ItemEntry`, `ItemSubEntry`, `TableEntry`, `TableGroupEntry`, `ImageEntry`, `GalleryEntry`, `HrEntry`, `InlineEntry`, `InlineBlockEntry`, `FlowchartEntry`, `FlowBlockEntry`, `StatblockEntry`, `SpellcastingEntry`, `GenericEntry`
  - `ImageContext` (nested structure for ImageHref)
  - `BuildContext` (with mode, result, ids_seen fields)
  - `ValidationMode` (enum)
  - `ValidationResult` (with errors and warnings)
  - `MetaSource`, `Meta`, `TocHeader`, `TocEntry`, `AdventureIndex`, `AdventureData`, `HomebrewAdventure`, `OfficialAdventureData`

### 1.2 Serialization/Deserialization
- Use `serde` for JSON serialization/deserialization with precise field mapping
- Implement custom serialization for complex types (e.g., `ImageHref`, `TocHeader`)
- Ensure exact JSON output format matches Python implementation (including field ordering, null handling, and extra field preservation)
- Implement type dispatch system equivalent to Python's `_TYPE_MAP` dictionary
- Handle unknown entry types with GenericEntry
- Preserve extra fields in ImageEntry and GenericEntry
- Implement `parse_entry()` and `parse_document()` with identical behavior to Python
- Support both homebrew format (`_meta`, `adventure`, `adventureData`) and official format (`data`)

### 1.3 Validation Logic
- Replicate `validate_tags()` function with identical regex pattern matching from `validate_adventure.py`
- Implement `validate_entries()` with same error detection logic
- Replicate `validate_tags()` and `_validate_entry_list()` functions
- Support both `ValidationMode.WARN` (collect issues) and `ValidationMode.STRICT` (raise immediately) modes
- Implement BuildContext with error/warning collection and id tracking
- Replicate ID uniqueness checking with ids_seen dictionary

### 1.4 Document Building
- Implement `HomebrewAdventure.build()` with identical parameter handling (name, source, sections, ctx, is_book, authors, convertedBy)
- Replicate `assign_ids()` recursive ID assignment
- Replicate `build_toc()` for rebuilding table of contents from data
- Implement `from_dict()` methods for both HomebrewAdventure and OfficialAdventureData
- Ensure same behavior for all document types and edge cases

## Phase 2: Python Integration Layer

### 2.1 Create PyO3 Binding
- Use PyO3 to create Python bindings for Rust functionality
- Implement Python module with same API surface as `adventure_model.py`
- Expose all functions: parse_entry, parse_document, validate_tags, HomebrewAdventure.build()
- Expose all classes: EntryBase, SectionEntry, EntriesEntry, InsetEntry, InsetReadaloudEntry, QuoteEntry, ListEntry, ItemEntry, ItemSubEntry, TableEntry, TableGroupEntry, ImageEntry, GalleryEntry, HrEntry, InlineEntry, InlineBlockEntry, FlowchartEntry, FlowBlockEntry, StatblockEntry, SpellcastingEntry, GenericEntry, ImageHref, BuildContext, ValidationMode, ValidationResult, MetaSource, Meta, TocHeader, TocEntry, AdventureIndex, AdventureData, HomebrewAdventure, OfficialAdventureData
- Ensure seamless replacement - Python code should import `adventure_model` without changes

### 2.2 Memory Management
- Handle Python object lifecycle properly with PyO3
- Ensure proper conversion between Python objects and Rust types
- Implement error handling that translates Rust errors to Python exceptions
- Manage memory for nested structures and complex object graphs

## Phase 3: Integration Testing

### 3.1 Replace Imports
- Modify `claude_api.py`, `pdf_to_5etools_v2.py`, `fix_adventure_json.py`, `adventure_editor.py`, `validate_adventure.py`, `extract_monsters.py` to use the Rust implementation via the Python binding

### 3.2 Run Test Suite
- Execute all tests in `test_adventure_model.py` with Rust backend
- Verify all 90+ tests pass with identical behavior
- Test integration with `test_adventure_editor.py` and `test_validate_adventure.py`

### 3.3 End-to-End Testing
- Test full workflow with `pdf_to_5etools_v2.py` using sample PDFs
- Verify output matches exactly with Python implementation
- Test edge cases: empty documents, malformed JSON, unknown tags, etc.

## Phase 4: Performance Optimization

### 4.1 Benchmark Analysis
- Measure performance difference between Python and Rust implementations
- Identify bottlenecks in serialization/deserialization and validation
- Optimize memory allocation patterns

### 4.2 Optimization Strategies
- Implement string interning for repeated tag names
- Optimize regex pattern matching
- Reduce memory allocations during parsing
- Implement caching for frequently accessed data

## Phase 5: Documentation and Migration

### 5.1 Update Documentation
- Update `CLAUDE.md` to reflect Rust implementation
- Document any changes in behavior or error messages
- Update API documentation for the Rust implementation

### 5.2 Migration Guide
- Create guide for developers to understand the new implementation
- Document any changes in error messages or output format
- Provide troubleshooting guide for common issues

### 5.3 Deprecation Plan
- Mark Python implementation as deprecated
- Plan for eventual removal of Python code
- Maintain backward compatibility during transition

## Phase 6: Validation and Verification

### 6.1 Verify Output Integrity
- Compare JSON output from Rust and Python implementations for 100+ official adventure files
- Ensure identical file hashes for all outputs
- Verify 5etools can load all generated files identically

### 6.2 Security Review
- Check for memory safety issues in Rust implementation
- Verify no buffer overflows or use-after-free conditions
- Validate input sanitization

### 6.3 Final Testing
- Run complete test suite with all components
- Verify all CLI tools work with Rust backend
- Test web UIs (adventure_editor.py, toc_editor.py, monster_editor.py)

## Implementation Constraints

- The Rust implementation must have a Python wrapper via PyO3
- All features from the Python implementation must be preserved
- Error message format must be maintained exactly as in Python
- No specific performance targets are required

## Success Criteria

- All existing tests pass with identical behavior
- No changes required to any Python code that imports `adventure_model`
- Output JSON matches exactly with Python implementation
- Performance is improved (though not a primary goal)
- Memory usage is reduced
- No regressions in functionality

## Risks

- Incompatibility in JSON output format
- Differences in error messages
- Memory management issues with PyO3
- Performance degradation due to binding overhead
- Integration issues with existing code

## Mitigations

- Comprehensive test suite coverage
- Exact replication of error messages
- Thorough memory safety analysis
- Incremental integration and testing
- Backup of original Python implementation

## Timeline

- Phase 1: Rust Implementation - 5-7 days (increased due to complexity)
- Phase 2: Python Integration Layer - 3-4 days
- Phase 3: Integration Testing - 3-4 days
- Phase 4: Performance Optimization - 1-2 days
- Phase 5: Documentation and Migration - 1 day
- Phase 6: Validation and Verification - 2 days

Total estimated time: 15-21 days

---

*This plan was created on Sun Jun 07 2026 for the pdf-translators project.*