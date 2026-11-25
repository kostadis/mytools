# Local source patches

Source releases: `lopdf` 0.47.0 (https://github.com/J-F-Liu/lopdf) and
`pdf-extract` 0.12.1 (https://github.com/jrmuizel/pdf-extract), from their published
crates. Source headers, READMEs and manifest authors are retained. Both declare
MIT. lopdf's LICENSE is copied verbatim. pdf-extract's crate omits a separate
LICENSE; its declared MIT grant is included here with manifest-author attribution.
No upstream test PDFs or private library documents are vendored.

Changes from the published source:

- pdf-extract/Cargo.toml: use lopdf 0.47 (no default/Rayon features).
- pdf-extract/src/lib.rs: skip Image XObjects while traversing Forms; use
  Content::decode_strict and propagate decoding errors; use the fallible
  get_page_content_with_limit API (64 MiB) for lopdf 0.47 compatibility.
  Form traversal inherits graphics state/CTM, applies Form matrices and caps
  recursion; font cache keys use dictionary identity rather than local resource
  names. Missing CID mappings can use unambiguous embedded TrueType cmaps
  (ttf-parser 0.25.1); unmapped glyphs are marked for explicit application error.
- lopdf/src/reader.rs, load_encrypted_document: consume raw_objects with
  pop_first as they are parsed/decrypted, and apply the provided filter to
  decrypted objects. This reduces overlapping raw/decrypted allocations and
  makes text-only filtering work on empty-password encrypted files.

The application owns positioned text output, outline traversal, protocol and
error policy outside the vendor tree. Dependencies are local/pinned so a build
never edits the global Cargo registry. Regression coverage is in tests/worker.rs.
