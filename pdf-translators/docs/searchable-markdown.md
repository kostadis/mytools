# Searchable Markdown from selected PDFs

The Rust source selector can freeze an additive internal-date selection queue, then extract entire winning PDFs into searchable page-based Markdown. This works across systems. It does not run OCR, models, 5etools conversion, or search-index promotion.

From `pdf-translators/`, build with Rust 1.95+ and install Poppler's `pdftotext`:

```bash
cargo build --manifest-path source-selector/Cargo.toml --release --locked
SELECT=source-selector/target/release/rpg-source-select
STATE=/path/to/completed-scan-state
OUTPUT=/path/to/private-markdown-output
"$SELECT" --work-dir "$STATE" markdown-select --output "$OUTPUT"
"$SELECT" markdown-convert --output "$OUTPUT"
rg -i 'search phrase' "$OUTPUT/corpus/current/books" --glob '*.md'
```

Both state and output must be outside the PDF library. Output is a dedicated managed directory: its contents must not be symlinks, except the managed `corpus/current` view. Keep private source caches and generated book text out of Git.

## Publish beside the PDFs

Add `--publish-next-to-source` to use the integrated source-adjacent workflow:

```bash
"$SELECT" markdown-convert --output "$OUTPUT" --publish-next-to-source
```

For each selected PDF, this writes a sibling with the same filename stem and `.md` extension, plus `current-documents.json` in that directory. The Markdown includes a clickable relative PDF link, source hash, work/source and selection identity, converter/quality provenance and physical page headings. Full extraction time is retained when known; preexisting checkpoints without a recorded time expose it as unknown rather than inventing an extraction date.

The directory record can contain multiple works and distinguishes pending, published, empty/OCR, extraction failures, changed sources and output conflicts. Only confirmed current publications enter this mode's local `corpus/current/books` view; that local copy uses a source link appropriate to its own location. A plain recursive search over all sibling Markdown also finds retained older files, so use the current view or a manifest-aware index for current-only results. No historical database or new search index is created.

The publisher preserves unrecognized Markdown, user-edited generated files, foreign/invalid directory records and PDF bytes. Such cases become output conflicts while independent directories continue. Existing directory records and source outputs are checksum-checked; matching names alone do not establish ownership. A hidden `.current-documents.lock` coordinates each directory. Durable ownership receipts and publication intents remain under `$OUTPUT/adjacent/`, outside the source library. Keep one output/coordinator namespace per managed library.

After interruption, rerun the same command. An intent written before the Markdown rename allows the directory record to finish without new extraction. Receipts survive current-entry removal and support reselection or revised PDFs at the same filename. If private ownership state is lost, current recognized records can rebuild proof of ownership; unlisted old Markdown without surviving proof is preserved as a conflict.

Manifest discovery also checks directories whose last PDF disappeared. Complete coverage allows obsolete managed entries to be removed from current records without deleting files. Incomplete scan/discovery coverage retains uncertain entries with their old selection identity, records partial reconciliation, and excludes them from newly confirmed current results. Inspect `publication.adjacent` and `publication.pending` in `last-run.json`, especially `errors` and per-work `states`. The previous good local view is retained explicitly as pending when no new current documents can publish.

Without the flag, the existing local-only behavior remains unchanged: the command writes no source-directory outputs. Workers and extraction caches always stay private; only the coordinator publishes sibling files. The workflow assumes Drive is mounted and writable and uses same-directory atomic rename and flush operations for each record, without claiming a cross-directory or cross-machine transaction.

## Selection

`markdown-select` reads the existing scan database without changing legacy decisions, samples, or exports. It probes PDF metadata independently of the five-page inspection budget. For large PDFs this can still involve substantial PDF I/O. Metadata is cached by content hash. The selection snapshot keeps all alternatives and raw date evidence; its separate queue does not claim older files are obsolete.

Within a compatible whole candidate component, byte-identical aliases collapse first. Different content competes using embedded Info/XMP modification dates, falling back to creation dates only when modification dates are absent. Conflicts, malformed values, timezone ambiguity, overlapping precision intervals, and ties defer the choice. Generic/coarse families and explicit ruleset/language/role conflicts defer. Adopted user/Sol choices and holds take precedence; changed reviewed groups require review. Baseline-linked Dungeon Masters Guild material stays in reconciliation. A single uncontested usable PDF can be ready without comparing dates; an undated old-only copy stays deferred.

The immutable snapshot lives at `selection/generations/<id>/markdown-selection.json`, alongside `markdown-queue.tsv` and `markdown-review.jsonl`. `selection/current.json` selects the current snapshot. Optional `--provenance /path/to/pilot-cases.json` attaches verified original identities to locally staged pilot sources; it does not create review authority.

Run selection against a completed scan. Do not start write stages against a database being populated by the broad scan; the pilot uses an independent completed scan.

## Conversion, logs and recovery

The coordinator uses two isolated workers and 20-page extraction ranges by default. Useful options:

```text
--workers 2 --chunk-pages 20 --timeout-secs 120
--job-timeout-secs 1800 --limit 4 --pdftotext /usr/bin/pdftotext
--retry-failed
```

The coordinator alone writes `markdown.db`. Worker logs are append-only under `logs/<job-id>.log`; coordinator stderr reports completed books and a heartbeat every 30 seconds. Each verified range is atomically checkpointed under `cache/pages/<source-hash>/<engine-id>/`. Selected PDFs are streamed to `cache/sources/` and checked against the frozen queue hash before use. No unselected source is copied for conversion.

Repeat the same command after a crash: valid range checkpoints are reused, and corrupt ones are extracted again. A completion attestation binds the full ordered range checksums before a book can publish. Newly extracted ranges are checked against the staged PDF hash before checkpointing. Completed books are revalidated from checkpoints without additional extraction. Missing or damaged artifact/sidecar files are repaired from verified ranges, and abandoned temporary corpus pointers are recovered. `--limit` prioritizes unfinished runnable work ahead of completed-book validation. `--retry-failed` authorizes another failed-job attempt, with a three-failure ceiling per source/extractor contract. A live orphaned worker retains its OS lease; the coordinator reports it and can be rerun after it exits. Changing the executable bytes/version or extraction contract produces a new cache identity. Cached inputs allow offline reruns; an observed mismatch with an accessible original requires a rescan and cannot be masked by that cache. Zero-text documents become `needs_ocr_or_visual_review`; no empty successful Markdown is published.

`last-run.json` reports results. A successful command exit means the coordinator finished reporting; inspect `failed`, `needs_ocr_or_visual_review`, and `publication.pending` to distinguish book failures from completion. The publication report includes the visible `published_snapshot` as well as the latest `selection_id`, and pending work states/errors/missing ranges. Catalogs also retain explicit failed versus unfinished states.

## Reading the corpus

Search only **`corpus/current/books`**, which contains ordinary `.md` files and matching JSON sidecars. Each book has source identity/date front matter and a heading per physical PDF page. Literal page text is HTML-escaped inside `<pre>` blocks to preserve whitespace and avoid interpreting source text as markup. Sidecars retain the unescaped UTF-8 extraction and full provenance.

Immutable artifacts and corpus generations are retained outside the default search view. Publication atomically switches the Linux symlink `corpus/current`; successful independent books can publish while others remain pending. Publication rereads the latest selection, so a late worker can supply cached bytes but cannot restore an older policy. When a new selection has no compatible completed books yet, the previous view stays available and `corpus/pending.json` explicitly identifies the pending selection. Do not treat that previous view as satisfying the new queue.

Native text can have font substitutions, disrupted reading order, unrecognized tables, and missing image text. Empty/sparse pages and extractor warnings are recorded, but these heuristics cannot establish semantic completeness or reliably detect a scanned page with a caption. Review the PDF when exact layout or wording matters. OCR and improved layout handling are later work.
