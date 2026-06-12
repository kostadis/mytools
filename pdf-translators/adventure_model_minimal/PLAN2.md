# PLAN2.md

## Phase 1: Rust Core Implementation

1. **Struct Design**  
   - Split entry types into files with ≤3 structs each:  
     - `section.rs`: `SectionEntry`, `EntriesEntry`, `InsetEntry`  
     - `quote.rs`: `QuoteEntry`, `VariantInnerEntry`  
     - `list.rs`: `ListEntry`, `ItemEntry`, `ItemSubEntry`  
     - `table.rs`: `TableEntry`, `TableGroupEntry`  
     - `image.rs`: `ImageEntry`, `GalleryEntry`  
     - `structure.rs`: `HrEntry`, `InlineEntry`, `FlowchartEntry`  
     - `statblock.rs`: `StatblockEntry`, `SpellcastingEntry`  
     - `generic.rs`: `GenericEntry`  

2. **Validation Infrastructure**  
   - Implement `BuildContext` and `ValidationResult` for error tracking  
   - Add tag validation logic for all text fields  

3. **JSON Handling**  
   - Use `serde` for serialization/deserialization  
   - Create `parse_entry()` and `to_dict()` methods for each struct  

4. **CLI Implementation**  
   - Read input JSON → parse → validate → output processed JSON  
   - Support `--validate` and `--format` flags  

## Phase 2: Python Integration

1. **PyO3 Bindings**  
   - Create Rust crate with `#[pyclass]` for core structs  
   - Expose `parse_document()` and `HomebrewAdventure.build()`  

2. **Python Wrapper**  
   - Implement Python module mirroring `adventure_model.py` API  
   - Handle data conversion between Python and Rust  

3. **Testing**  
   - Run existing Python tests against Rust core  
   - Verify TOC alignment and ID assignment consistency