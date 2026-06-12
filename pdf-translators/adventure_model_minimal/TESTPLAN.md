TESTPLAN.md
Rust CLI Implementation Test Plan for adventure_model.py Compatibility
This test plan verifies that the Rust CLI implementation exactly matches the Python adventure_model.py behavior. The Python implementation is the source of truth, with tests in test_adventure_model.py and validation rules in adventure_model.py.
1. Test JSON Serialization/Deserialization of All Entry Types
Objective: Verify that all 18+ entry types serialize and deserialize identically to the Python implementation.
Steps:
1. Create test cases for each of the 18+ entry types defined in adventure_model.py:
- SectionEntry, EntriesEntry, InsetEntry, InsetReadaloudEntry
- QuoteEntry, VariantInnerEntry
- ListEntry, ItemEntry, ItemSubEntry
- TableEntry, TableGroupEntry
- ImageEntry, GalleryEntry
- HrEntry, InlineEntry, InlineBlockEntry
- FlowchartEntry, FlowBlockEntry
- StatblockEntry, SpellcastingEntry, GenericEntry
2. For each entry type, perform these tests:
- Create a Python instance with sample data (name, id, page, entries, etc.)
- Serialize to JSON using Python's to_dict() method
- Deserialize the same JSON using the Rust CLI
- Serialize the Rust result back to JSON
- Compare the original Python JSON with the Rust-generated JSON byte-for-byte
3. Test nested structures:
- Create a SectionEntry containing a ListEntry with ItemEntry children
- Create a TableEntry with colLabels and rows containing strings
- Create an ImageEntry with ImageHref containing type and path
- Create a QuoteEntry with by and from_ fields
- Create a FlowchartEntry containing multiple FlowBlockEntry objects
Expected Outcomes:
- All entry types must serialize to identical JSON structure as Python
- Field names must match exactly (e.g., colLabels, from_ becomes from, maxWidth)
- Optional fields must be omitted when null (Python omits id, page, name if None)
- Nested structures must maintain identical hierarchy and field ordering
- All JSON must be identical byte-for-byte between Python and Rust implementations
2. Validate Field Naming, Ordering, Null Handling, and Extra Fields
Objective: Ensure Rust implementation matches Python's exact handling of field naming conventions, ordering, null values, and extra fields.
Steps:
1. Test field naming:
- Verify from_ in Python becomes from in JSON (not from_)
- Verify colLabels is used (not col_labels or col-labels)
- Verify maxWidth is used (not max_width or max-width)
- Verify entries, items, rows, headers are used as in Python
2. Test field ordering:
- Serialize a SectionEntry with all fields: type, name, id, page, entries
- Verify JSON field order matches Python exactly: type, name, id, page, entries
3. Test null handling:
- Create entries with name=None, id=None, page=None
- Verify these fields are completely omitted from JSON output
- Verify entries field is omitted when empty list
4. Test extra fields:
- Create an ImageEntry with additional fields like mapRegions
- Serialize with Python and verify extra fields are preserved
- Deserialize with Rust and serialize back
- Verify extra fields are preserved in output
Expected Outcomes:
- All field names must match Python exactly (camelCase, no underscores)
- Field ordering must be identical to Python's to_dict() output
- Null/None values must be omitted from JSON (not represented as null)
- Extra fields must be preserved during round-trip serialization
- Field names and structure must match 5etools specification exactly
3. Test Validation Rules
Objective: Verify Rust implementation enforces the same validation rules as Python's BuildContext.
Steps:
1. Test unknown tag validation:
- Create JSON with {@badtag} in any field (name, entry, caption, etc.)
- Verify Rust implementation reports error on unknown tags
- Compare error message format with Python's "unknown tag '{@badtag}'"
2. Test unbalanced braces:
- Create JSON with unclosed { or } in string fields
- Verify Rust implementation reports warning for unbalanced braces
- Verify message matches Python's "unbalanced opening brace" / "unbalanced closing brace"
3. Test duplicate ID validation:
- Create JSON with two entries having the same id value
- Verify Rust implementation reports warning on duplicate ID
- Verify message format matches Python's "duplicate id 'X'"
4. Test missing href validation:
- Create ImageEntry with href field missing or null
- Verify Rust implementation reports error for missing href
- Verify message matches Python's "image has no href"
5. Test type validation:
- Create TableEntry with colLabels missing but rows present
- Verify Rust implementation reports warning for missing colLabels
- Verify message matches Python's "table has rows but no colLabels"
6. Test array validation:
- Create ListEntry with items as string instead of array
- Verify Rust implementation reports error for non-array items
- Verify message matches Python's "items must be an array"
7. Test strict mode validation:
- Implement strict mode equivalent to Python's ValidationMode.STRICT
- Verify errors cause immediate failure (not just warning collection)
- Verify warnings are collected in non-strict mode
Expected Outcomes:
- All validation rules must match Python exactly (errors vs warnings)
- Error/warning messages must be identical in format and content
- Validation must occur during deserialization (not only during serialization)
- Strict mode must halt processing on first error
- Validation must be comprehensive across all entry types and fields
4. Verify ID Assignment and TOC Building Behavior
Objective: Ensure Rust implementation matches Python's ID assignment and TOC building logic.
Steps:
1. Test ID assignment:
- Create a SectionEntry containing EntriesEntry and InsetEntry
- Run the ID assignment algorithm (equivalent to _assign_ids_recursive)
- Verify IDs are assigned sequentially as "000", "001", "002", etc.
- Verify only section, entries, and inset types receive IDs
- Verify list, item, table, etc. do not receive IDs
2. Test TOC building:
- Create a HomebrewAdventure with SectionEntry containing multiple EntriesEntry children
- Run the TOC building algorithm (equivalent to build_toc())
- Verify contents[] array has one entry per top-level section
- Verify each TOC entry's name matches the section's name
- Verify each TOC entry's headers[] contains entries for child EntriesEntry/SectionEntry with name
- Verify headers have depth: 0 (not 1 or other values)
- Verify headers are ordered the same as in the data
3. Test alignment validation:
- Create a document where contents[] length ≠ data[] length
- Verify Rust implementation reports warning about misalignment
- Create a document where contents[i].name ≠ data[i].name
- Verify Rust implementation reports warning about name mismatch
Expected Outcomes:
- ID assignment must be identical to Python's sequential numbering
- Only section, entries, and inset types should receive IDs
- TOC must be built exactly as per Python's build_toc() algorithm
- TOC headers must have depth: 0 for all entries (no depth 1+)
- Alignment warnings must match Python's wording and conditions
- No IDs should be assigned to non-container types (list, item, table, etc.)
5. Test Round-Trip Parsing of Official and Homebrew Adventure Files
Objective: Verify Rust implementation can parse and reproduce Python-generated files.
Steps:
1. Test with official adventure files:
- Load official 5etools adventure files (e.g., adventure-lmop.json)
- Parse with Python and verify no errors (as in TestOfficialFiles)
- Parse the same file with Rust CLI
- Serialize Rust output back to JSON
- Compare original file with Rust output byte-for-byte
2. Test with homebrew files:
- Load homebrew files generated by Python (e.g., adventure-toworlds.json)
- Parse with Python and verify no errors
- Parse with Rust CLI
- Serialize Rust output back to JSON
- Compare original file with Rust output byte-for-byte
3. Test edge cases:
- Files with non-section top-level entries (should warn in homebrew, error in official)
- Files with missing _meta or adventure/adventureData fields
- Files with empty data arrays
- Files with unknown entry types (should be preserved as GenericEntry)
4. Test document type detection:
- Verify Rust correctly identifies official format (only "data" field)
- Verify Rust correctly identifies homebrew format ("adventure" and "adventureData" fields)
- Verify Rust correctly identifies book format ("book" and "bookData" fields)
Expected Outcomes:
- All official and homebrew files must parse with identical results to Python
- Byte-for-byte identical output when re-serializing
- Error/warning messages must match Python exactly
- Unknown entry types must be preserved as GenericEntry
- Document type detection must match Python's logic exactly
- No data loss during round-trip parsing
6. Compare Output Hashes with Python-Generated Files
Objective: Ensure Rust implementation produces identical output to Python for all test cases.
Steps:
1. Generate test files with Python:
- Create 10 test files covering all entry types, nesting levels, and edge cases
- Serialize each using Python's to_json() method
- Compute SHA-256 hash of each output file
2. Generate identical test files with Rust:
- Create equivalent test data in Rust
- Serialize using Rust CLI's output method
- Compute SHA-256 hash of each output file
3. Compare hashes:
- Compare Python-generated hash with Rust-generated hash for each test file
- Verify all hashes match exactly
4. Test with real files:
- Use the same official and homebrew files referenced in test_adventure_model.py
- Generate outputs with both Python and Rust
- Compute and compare hashes
5. Test different formatting:
- Test with different indentation levels
- Test with different line endings
- Verify hashes match even with different formatting (if specification allows)
Expected Outcomes:
- All output files must have identical SHA-256 hashes between Python and Rust
- Output must be byte-for-byte identical
- No whitespace differences, ordering differences, or encoding differences
- All test files must pass hash comparison
- If formatting differences are allowed, specify exact format requirements (e.g., tabs for indentation, UTF-8 encoding, LF line endings)
This comprehensive test plan ensures the Rust CLI implementation exactly matches the Python adventure_model.py behavior across all critical dimensions: data model, validation rules, serialization, deserialization, ID assignment, TOC building, and round-trip compatibility with real-world files.

