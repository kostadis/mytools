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

Repeat the same command after a crash: valid range checkpoints are reused, and corrupt ones are extracted again. Completed books are revalidated from checkpoints without additional extraction. `--retry-failed` authorizes another failed-job attempt, with a three-failure ceiling per source/extractor contract. A live orphaned worker retains its OS lease; the coordinator reports it and can be rerun after it exits. Changing the executable bytes/version or extraction contract produces a new cache identity. Cached inputs allow offline reruns. Zero-text documents become `needs_ocr_or_visual_review`; no empty successful Markdown is published.

`last-run.json` reports results. A successful command exit means the coordinator finished reporting; inspect `failed`, `needs_ocr_or_visual_review`, and `publication.pending` to distinguish book failures from completion.

## Reading the corpus

Search only **`corpus/current/books`**, which contains ordinary `.md` files and matching JSON sidecars. Each book has source identity/date front matter and a heading per physical PDF page. Literal page text is HTML-escaped inside `<pre>` blocks to preserve whitespace and avoid interpreting source text as markup. Sidecars retain the unescaped UTF-8 extraction and full provenance.

Immutable artifacts and corpus generations are retained outside the default search view. Publication atomically switches the Linux symlink `corpus/current`; successful independent books can publish while others remain pending. Publication rereads the latest selection, so a late worker can supply cached bytes but cannot restore an older policy. When a new selection has no compatible completed books yet, the previous view stays available and `corpus/pending.json` explicitly identifies the pending selection. Do not treat that previous view as satisfying the new queue.

Native text can have font substitutions, disrupted reading order, unrecognized tables, and missing image text. Empty/sparse pages and extractor warnings are recorded, but these heuristics cannot establish semantic completeness or reliably detect a scanned page with a caption. Review the PDF when exact layout or wording matters. OCR and improved layout handling are later work.
