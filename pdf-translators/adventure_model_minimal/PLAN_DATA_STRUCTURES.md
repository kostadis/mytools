# Plan: Implement Rust Data Structures for adventure_model

This plan outlines a phased approach to implementing the Rust data structures equivalent to the Python adventure_model.py implementation. The goal is to create a complete, compatible implementation while maintaining code quality and manageability.

## Phase 1: Core Foundation (1-2 days)

### 1.1 Basic Types
- Implement `ValidationMode` enum (Warn/Strict)
- Implement `ValidationResult` struct with errors and warnings vectors
- Implement `BuildContext` struct with mode, result, and ids_seen HashMap
- Implement `ImageHref` struct with type, path, and url fields

### 1.2 Base Entry Structure
- Implement `EntryBase` struct with type, name, id, page, _ctx, and _path fields
- Implement basic constructor and helper methods for EntryBase
- Implement simple `to_dict()` method for EntryBase

### 1.3 Simple Entry Types
- Implement `HrEntry` (no additional fields beyond EntryBase)
- Implement `GenericEntry` (with _raw HashMap)

### 1.4 Container Entry Structure
- Define `Entry` enum to represent the union type (String, SectionEntry, etc.)
- Implement basic `to_json_value()` method for Entry enum

## Phase 2: Container Entries (2-3 days)

### 2.1 Entries with entries[] field
- Implement `SectionEntry`
- Implement `EntriesEntry`
- Implement `InsetEntry`
- Implement `InsetReadaloudEntry`
- Implement `InlineEntry`
- Implement `InlineBlockEntry`
- Implement `FlowBlockEntry`

### 2.2 Specialized Container Entries
- Implement `QuoteEntry` (with by and from_ fields)
- Implement `VariantInnerEntry`

### 2.3 List and Item Entries
- Implement `ListEntry` (with items and style fields)
- Implement `ItemEntry` (with entry and optional entries)
- Implement `ItemSubEntry`

## Phase 3: Table and Image Entries (2-3 days)

### 3.1 Table Entries
- Implement `TableEntry` (with caption, colLabels, colStyles, rows)
- Implement `TableGroupEntry`

### 3.2 Image Entries
- Implement `ImageEntry` (with href, title, maxWidth, _extra)
- Implement `GalleryEntry`

## Phase 4: Advanced Entries (2 days)

### 4.1 Flowchart Entries
- Implement `FlowchartEntry`

### 4.2 Specialized Entries
- Implement `StatblockEntry` (with tag and source)
- Implement `SpellcastingEntry` (with headerEntries and _raw)

## Phase 5: Document-Level Structures (1-2 days)

### 5.1 TOC and Index Structures
- Implement `TocHeader`
- Implement `TocEntry`
- Implement `AdventureIndex`

### 5.2 Meta Structures
- Implement `MetaSource`
- Implement `Meta`

### 5.3 Data Structures
- Implement `AdventureData`
- Implement `HomebrewAdventure`
- Implement `OfficialAdventureData`

## Phase 6: Integration and Validation (2-3 days)

### 6.1 Validation Functions
- Implement `validate_tags()` with exact TAG_RE regex pattern matching
- Implement `_validate_entry_list()`
- Implement `_entries_to_list()`

### 6.2 Document Building Functions
- Implement `HomebrewAdventure.build()`
- Implement `assign_ids()`
- Implement `build_toc()`
- Implement `parse_entry()`
- Implement `parse_document()`

### 6.3 Type Dispatch System
- Implement type dispatch system equivalent to Python's _TYPE_MAP
- Implement handling of unknown entry types with GenericEntry

## Phase 7: PyO3 Binding (2-3 days)

### 7.1 Basic Binding Setup
- Set up PyO3 extension module
- Expose ValidationMode enum to Python
- Expose ValidationResult struct to Python
- Expose BuildContext struct to Python

### 7.2 Data Structure Exposure
- Expose all EntryBase subclasses to Python
- Expose all document-level structures to Python
- Implement proper memory management for Python-Rust interop

### 7.3 Function Exposure
- Expose validate_tags() to Python
- Expose parse_entry() to Python
- Expose parse_document() to Python
- Expose HomebrewAdventure.build() to Python

## Success Criteria

- All Python data classes have equivalent Rust implementations
- JSON output matches exactly with Python implementation
- All validation behavior is preserved
- PyO3 binding provides identical API surface
- Code is well-documented and maintainable

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Complexity of data structures | Implement incrementally, test each phase |
| JSON format compatibility | Compare output with Python implementation at each step |
| PyO3 memory management issues | Use PyO3 documentation and examples, test with Python tests |
| Performance issues | Profile after implementation, optimize only if needed |
| Time constraints | Focus on core functionality first, add edge cases later |

## Timeline

Total estimated time: 15-20 days

This phased approach allows us to:
1. Build confidence with simple structures first
2. Test each component incrementally
3. Identify and fix issues early
4. Maintain code quality throughout
5. Provide regular progress updates

We'll start with Phase 1: Core Foundation, implementing ValidationMode, ValidationResult, BuildContext, ImageHref, and EntryBase.