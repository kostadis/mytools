# Plan: Implement Container Entries with entries[] Field

This plan outlines a phased approach to implementing the container entries that have an `entries[]` field in the Rust adventure_model implementation. These are the most common entry types in the 5etools format.

## Phase 1: Core Container Entry Structure (1 day)

### 1.1 Base Container Entry
- Create `ContainerEntry` trait to define common behavior for all entries with entries[]
- Implement shared functionality for entries[] validation and serialization
- Define common constructor pattern

### 1.2 Entry Base Extension
- Extend `EntryBase` to include `entries` field and common validation
- Implement `_validate_entries()` method for validating the entries array
- Implement `_entries_to_list()` helper for serialization

### 1.3 Entry Enum Update
- Update `Entry` enum to include all container entry types
- Implement `to_json_value()` for container entry types

### 1.4 Compile Step
- Run `cargo build` to verify compilation
- Run `cargo test` to verify all tests pass
- Verify PyO3 binding compiles successfully

## Phase 2: Implement Basic Container Entries (2 days)

### 2.1 Implement SectionEntry
- Implement with proper validation in __post_init__ equivalent
- Implement to_dict() with entries[] serialization
- Test with various entry types in entries[]

### 2.2 Implement EntriesEntry
- Implement with proper validation
- Implement to_dict() with entries[] serialization
- Test with various entry types in entries[]

### 2.3 Implement InsetEntry
- Implement with proper validation
- Implement to_dict() with entries[] serialization
- Test with various entry types in entries[]

### 2.4 Implement InsetReadaloudEntry
- Implement with proper validation
- Implement to_dict() with entries[] serialization
- Test with various entry types in entries[]

### 2.5 Compile Step
- Run `cargo build` to verify compilation
- Run `cargo test` to verify all tests pass
- Verify PyO3 binding compiles successfully
- Test Python import of new types

## Phase 3: Implement Advanced Container Entries (2 days)

### 3.1 Implement InlineEntry
- Implement with proper validation
- Implement to_dict() with entries[] serialization
- Test with various entry types in entries[]

### 3.2 Implement InlineBlockEntry
- Implement with proper validation
- Implement to_dict() with entries[] serialization
- Test with various entry types in entries[]

### 3.3 Implement FlowBlockEntry
- Implement with proper validation
- Implement to_dict() with entries[] serialization
- Test with various entry types in entries[]

### 3.4 Implement VariantInnerEntry
- Implement with proper validation
- Implement to_dict() with entries[] serialization
- Test with various entry types in entries[]

### 3.5 Compile Step
- Run `cargo build` to verify compilation
- Run `cargo test` to verify all tests pass
- Verify PyO3 binding compiles successfully
- Test Python import of new types

## Phase 4: Implement Specialized Container Entries (1 day)

### 4.1 Implement QuoteEntry
- Implement with by and from_ fields
- Implement proper validation of all fields
- Implement to_dict() with entries[], by, and from_ serialization
- Test with various entry types in entries[]

### 4.2 Compile Step
- Run `cargo build` to verify compilation
- Run `cargo test` to verify all tests pass
- Verify PyO3 binding compiles successfully
- Test Python import of new types

## Phase 5: Integration and Testing (2 days)

### 5.1 Complete Entry Enum
- Add all container entries to Entry enum
- Implement to_json_value() for all container entries

### 5.2 PyO3 Binding
- Expose all container entry types to Python
- Test Python compatibility

### 5.3 Comprehensive Testing
- Test all container entries with various entry types in entries[]
- Test validation of entries[] (strings, other entries)
- Test edge cases (empty entries[], null entries)
- Test with test_adventure_model.py expectations

### 5.4 Compile Step
- Run `cargo build` to verify compilation
- Run `cargo test` to verify all tests pass
- Verify PyO3 binding compiles successfully
- Test full Python integration with all container entries

## Success Criteria

- All container entries implement the same pattern: entries[] field with validation
- All entries follow the same serialization pattern
- JSON output matches Python implementation exactly
- All validation rules are preserved
- PyO3 binding exposes all types correctly
- All tests pass with identical behavior to Python
- Code compiles successfully after each phase
- Python integration works after each phase

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Inconsistent implementation across entry types | Use ContainerEntry trait to enforce common pattern |
| JSON format differences | Compare output with Python implementation at each step |
| PyO3 binding issues | Test Python compatibility early and often |
| Validation logic differences | Implement validation methods with exact Python behavior |
| Time constraints | Focus on core functionality first, add edge cases later |
| Compilation failures | Compile after each phase to catch issues early |

## Timeline

Total estimated time: 8 days

This phased approach allows us to:
1. Build confidence with a common pattern first
2. Implement entries incrementally with consistent behavior
3. Test each component thoroughly before moving to the next
4. Maintain code quality throughout
5. Provide regular progress updates
6. Catch compilation and integration issues early with compile steps after each phase

We'll start with Phase 1: Core Container Entry Structure, implementing the ContainerEntry trait and extending EntryBase.