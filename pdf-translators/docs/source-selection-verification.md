# Source-selector verification

After the independent Sol review and one regression-test-driven fix pass, the standalone Rust build, formatting, and Clippy with warnings denied pass. The Rust suite has 45 passing tests plus one explicitly run Poppler round-trip test (46 total). Existing Python batch regression coverage: 42 passed.

## Existing full-suite baseline

The initial full Python run had 412 passed, 6 skipped, and these nine failures because the existing `adventure_model_minimal` CLI executable is absent. The new selector does not modify that crate.

- `adventure_model_minimal/test_integration.py::TestRustCLI::test_cli_simple_validate`
- `adventure_model_minimal/test_integration.py::TestRustCLI::test_cli_assigns_ids`
- `adventure_model_minimal/test_integration.py::TestRustCLI::test_cli_builds_toc`
- `adventure_model_minimal/test_integration.py::TestRustCLI::test_cli_complex_structure`
- `adventure_model_minimal/test_integration.py::TestRustCLI::test_cli_invalid_json`
- `adventure_model_minimal/test_integration.py::TestValidation::test_unknown_tag_error`
- `adventure_model_minimal/test_integration.py::TestValidation::test_duplicate_id_warning`
- `adventure_model_minimal/test_integration.py::TestEdgeCases::test_empty_adventure`
- `adventure_model_minimal/test_integration.py::TestEdgeCases::test_missing_meta`

The real-library content pilot is blocked by PDF read permissions; see [pilot findings](source-selection-pilot.md). No source-selection quality claim is made from an unreadable corpus.

## Independent review fixes

All eight reproduced findings now have passing CLI regressions in `source-selector/tests/regressions.rs`: cross-collection candidates; work-level baseline protection; issued-packet/current-evidence binding and human precedence; status-specific reference validation; replaced/empty root protection; bounded metadata and native comparison context; bounded retry fairness; and conservative sparse-scan classification. Additional tests cover a user-selected external equivalent of a confirmed baseline and preservation of human rulings when reader facts are added about unchanged bytes.

The eight original CLI reproductions were run before fixes and all eight failed. A targeted mutation also demonstrated that removing source-bound human precedence loses an existing human ruling; restoring it makes that regression pass. The final whole Rust suite is green. No second reviewer pass was used.

## Implementation rulings

- The native worktree service did not return. Git created the isolated `codex/rpg-source-selection` branch under `/tmp/rpg-source-selection`; this needs manual worktree lifecycle handling.
- The nine pre-existing missing-legacy-binary failures were kept out of this independent selector's scope; the full historical Python suite remains red for that existing reason.
- Review policy functions take current source context explicitly, because opaque group IDs cannot establish `.old` paths, readability, or baseline preference. This adds one context parameter to the proposed interfaces.
- The real content pilot stays open because mounted PDFs are unreadable, even outside the sandbox. No real-library revision chronology or deduplication quality has been inferred.

No review findings were deferred as cosmetic minors. The reviewer declined to judge real-library quality/publication chronology because the PDFs could not be read, and the unchanged legacy-binary failures; both limitations remain recorded above.
