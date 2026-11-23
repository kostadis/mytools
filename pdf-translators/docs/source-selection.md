# Select PDFs for Markdown conversion

`rpg-source-select` creates an evidence-backed conversion list. It does not convert books, write into the library, alter rpg-lib flags, or change existing 5etools results. It works across game systems and includes text-bearing handouts, reference sheets, and map booklets.

Build from `pdf-translators/`:

```bash
cargo build --manifest-path source-selector/Cargo.toml --release --locked
source-selector/target/release/rpg-source-select --help
```

Rust 1.95 or newer is required. PDF inspection also needs Poppler's `pdftotext` on PATH (`poppler-utils` on Debian/Ubuntu). Inventory, status, and reading saved packets do not require a model or Python. All new application code is Rust; the old Python converter remains separate.

## Inventory and inspection

Choose a private working directory outside the PDF tree. Start with a representative sample before processing the whole library. `scan` inventories PDFs and archives, hashes possible equal-size copies, and groups candidates. Large network libraries can incur substantial file reads even though no models run.

```bash
SELECT=source-selector/target/release/rpg-source-select
WORK=/tmp/rpg-source-selection-data
"$SELECT" --work-dir "$WORK" scan --root '/path/to/pdf-sample'
"$SELECT" --work-dir "$WORK" inspect --limit 10
"$SELECT" --work-dir "$WORK" status
```

`inspect` defaults to at most ten groups needing work. It fully reads competing versions and samples singleton books. Repeat to process more groups; unchanged evidence is reused. `--group GROUP_ID --pages 1-5,12` requests additional pages. `--pdftotext PATH --timeout-secs 120` selects the executable and per-range timeout. Failed PDFs are reported without preventing other inspections. An inspection run with failures exits 1, even when other books succeeded.

Unchanged failures are deferred on ordinary subsequent runs so they cannot consume every bounded batch. Use `--retry-failed`, or target a particular `--group`, after fixing access or extraction problems. Sparse text and image-heavy cover labels stay pending rather than qualifying an entire scan for automatic selection. Use a persistent work directory for a full-library run; `/tmp` above is only a sample workspace.

Archives remain uninspected containers. An empty text layer is an unresolved scan/OCR case, not proof that a PDF is a disposable map. A missing mount or a source change cannot replace an earlier published list with a falsely successful one.

## Existing scans and library metadata

Optional scan arguments:

```text
--muse-csv /path/to/DriveThruRPG-Duplicate-Report.csv
--twins-json /path/to/twin-folders.json
--rpglib-json /path/to/library-api-snapshot.json
--baseline-manifest /path/to/confirmed-baseline.json
```

Muse CSV columns are imported as supplied, including canonical/duplicate filenames, Drive IDs, dates, reasons, and confidence. Missing local matches are reported. A twin-folder file is an array such as `[{"publisher":"Example","folders":["Book – Core","Book - Core"]}]` and requires `--muse-csv`. These hints propose comparisons; they do not exclude files.

The rpg-lib snapshot accepts a books array directly or under `books`/`items`, with each row carrying `filepath` and optional `id`, title, publisher, game-system, Drive metadata, and duplicate/version flags. Absolute paths must match the scanned root, while relative paths must match an inventoried file. Obtain the snapshot through rpg-lib's existing API, not by editing or directly reading its database. Optional `drive_file_id` and `drive_modified_time` remain attributed metadata; local processing does not require Drive access.

The baseline manifest explicitly confirms source identity:

```json
{"schema_version":1,"sources":[{"relative_path":"Dungeon Masters Guild/Example/example.pdf","sha256":"verified SHA-256 of the established source"}]}
```

Hashes are checked on import. Existing JSON alone does not establish baseline identity or Markdown completion. Artifact-bearing DM's Guild candidates stay out of the new-work queue pending confirmation; confirmed baseline sources are preserved as reuse records. No sidecars are regenerated. `.extract_skip` contents are retained as old workflow hints, not automatic Markdown exclusions.

Candidate discovery compares normalized filenames library-wide and uses imported product/title relationships across publishers and folders. These broad relationships can increase review work; they never prove equivalence. Baseline protection follows the work's related sources, including an equivalent external path chosen by a user. Proposed baseline representative/successor changes are reported separately, not silently queued.

## Reader, Sol, and user review

```bash
"$SELECT" --work-dir "$WORK" review export --role reader --limit 10 --out "$WORK/reader.jsonl"
"$SELECT" --work-dir "$WORK" review import --file "$WORK/reader-results.jsonl"
"$SELECT" --work-dir "$WORK" review export --role sol --limit 10 --out "$WORK/sol.jsonl"
"$SELECT" --work-dir "$WORK" review import --file "$WORK/sol-results.jsonl"
```

Every exported line contains a packet and a response template. Give factual reading to a simpler model. Give reasoning/judgment to Sol. The binary itself does not invoke models, so it cannot silently bill a provider or substitute a model. The operator is responsible for choosing the actual reader/judge; actor labels are an audit record, not authentication.

Reader responses use the issued `packet_id` and a `claims` array. Each claim needs `claim_id`, `kind`, `value`, `source_id`, 1-based `page`, `quote`, `actor`, and `role: "reader"`. Quotations must match that packet and the extracted page; only whitespace differences are tolerated. A reader cannot select or exclude a book. Unsupported claims and conflicting reused claim IDs are refused.

After importing claims, export fresh Sol packets. A judgment response acknowledges all `packet_ids` for that group and includes the template's complete `decision`. Keep its group, membership, and evidence digests. Set a rationale and outcomes for every source. Sol exclusions need checked claim IDs in `evidence_refs`. A filename version, mtime, or text similarity alone never automatically chooses the newer book.

For a human ruling, export `--role user` and edit its response template. The user can select a source, keep distinct works, identify a visual asset, or leave outcomes as `needs_review`. A user ruling with a reason is recorded as human authority; it does not assert that chronology was proved by the model. Selected sources receive work IDs if their `work_id` is null. Excluded equivalents need a selected `representative_id`; superseded revisions need a selected `successor_id`. Self references, chains, cycles, missing members, and arbitrary source IDs are refused.

Packets declare inspected pages, total pages, offsets, and part counts. A long page is split without dropping text. All parts are required for a judgment. If the context itself exceeds the packet budget, the command asks for a smaller group rather than truncating it. Book text is untrusted reference data, never an instruction to tools or models.

Source context and native comparison summaries are distributed across bounded parts. Packets include filesystem dates, changed-page counts/ranges, text overlap, and image/annotation differences. Repeated metadata and claim summaries are bounded with explicit truncation indicators and full-evidence references. Retrieve the original cached metadata, pages, and claims when needed:

```bash
"$SELECT" --work-dir "$WORK" evidence --source SOURCE_ID
```

That command returns stored evidence with its source hash; it does not claim that the current mount is unchanged. Judgment imports must match the issued packet set and current evidence. Packet IDs are persisted with the ruling. A current human ruling takes precedence over later model responses and remains authoritative when a reader adds facts about the same unchanged file bytes. Only another user ruling, or an actually changed source/group, can reopen that authority.

Keep real packets private: they contain book excerpts and local paths. Commit only synthetic fixtures. Changed bytes, group membership, or inspected evidence reopen affected decisions. A lone `.old` copy is a possible fallback for review, not automatically selected or treated as established obsolete content.

## Export and handoff

```bash
"$SELECT" --work-dir "$WORK" export
```

The command prints paths and reconciled counts. `$WORK/exports/current.json` points to a complete immutable generation containing:

- `selection.json`: authoritative versioned manifest, sources, decisions, history, provenance, SHA-256 fingerprints, and queue.
- `queue.tsv`: one selected, current source per work for the later Markdown converter.
- `review.jsonl`: unresolved decisions.
- `baseline-findings.json`: confirmed baseline reuse and pending baseline identity cases.
- `report.md`: inventory coverage, archive limits, pending cases, errors, and counts.

Unresolved, unreadable, stale, excluded, and superseded files do not enter the queue. Clear byte duplicates use one representative and retain links to the copies. Distinct works retain separate work IDs. Non-UTF-8 paths are preserved as raw bytes in JSON and omitted from TSV with an explicit report count. Older export generations remain available after an unsuccessful publication.

`status` reads stored state without updating it; it does not claim that the mounted PDFs are unchanged. `export` rechecks current source fingerprints and inspected content hashes before publishing. Run `scan` and `inspect` again when sources change. This stage ends at the list; Markdown conversion and CampaignGenerator ingestion are later milestones.

The selector also checks the observed root directory identity. A replaced/missing mount, an unreadable root, or a previously populated library becoming completely empty cannot overwrite prior inventory/export state. Verify the mount first. An intentional reset to a different or empty library needs a fresh work directory.

Exit codes: 0 successful command (possibly with pending review), 1 operational failure, 2 usage/schema error. Always read the counts: a successful command does not mean every book is selected or every revision is resolved.

## Verification

```bash
cargo fmt --manifest-path source-selector/Cargo.toml --check
cargo clippy --manifest-path source-selector/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path source-selector/Cargo.toml --locked
cargo test --manifest-path source-selector/Cargo.toml --locked --test poppler -- --ignored
```

All fixtures are synthetic. The final command exercises installed Poppler against an actual generated PDF.
