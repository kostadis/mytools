# Four-document searchable Markdown pilot

The metadata-selected pilot produced four searchable Markdown documents covering **61 physical PDF pages**, with text on 60 pages. All four queue entries completed; none failed or required whole-document OCR. A second run reused all five range checkpoints and extracted zero new ranges. No model calls were used for conversion.

| Work | Selected PDF | Pages | Findings |
| --- | --- | ---: | --- |
| Bad Decisions | `Bad_Decisions_Color_print.pdf` | 40 | Page 11 has sparse text |
| Improved Travel: Expanded Discoveries | `Expanded_Discoveries_-_No_Background.pdf` | 10 | Page 1 has no native text |
| Improved Travel: Planning Sheet | `Improved_Travel_Prep_Sheet.pdf` | 5 | Native text on all pages |
| Chivalry & Sorcery 5th Edition Character Sheet | `CnS5-Character-Sheet-Final_BW_-_26th_March_2020.pdf` | 6 | Native text on all pages; some font substitutions visible |

The selected internal modification dates, in UTC, were respectively 2021-08-21 00:57:14, 2020-07-07 14:58:30, 2019-04-22 14:40:48 and 2020-03-25 16:46:26. Byte aliases collapsed before comparison; filenames did not choose the winners. Original library identities from `content-pilot-02/pilot-cases.json` are attached to the generated sidecars.

## Reproduce and search

From `pdf-translators/`:

```bash
cargo build --manifest-path source-selector/Cargo.toml --release --locked
SELECT=source-selector/target/release/rpg-source-select
PILOT=source-selection-data/markdown-pilot-01
"$SELECT" --work-dir source-selection-data/content-pilot-02/state markdown-select \
  --output "$PILOT" --provenance source-selection-data/content-pilot-02/pilot-cases.json
"$SELECT" markdown-convert --output "$PILOT"
rg -i 'Random Encounter Rolls|Parent’s Vocation' "$PILOT/corpus/current/books" --glob '*.md'
```

`corpus/current/books` is the default search view. Each Markdown document has a heading for every physical page, source/date front matter, and escaped literal native text. Matching JSON sidecars retain the unescaped extraction, alternatives and original-source provenance. The output is private, ignored data; only code and reports belong in Git.

## Verification

- Checked the exact four selected hashes against the expected winners and locally staged PDF bytes.
- Checked page sequences and Markdown headings: 40 + 10 + 5 + 6 = 61, with no omitted or repeated physical page numbers.
- Verified a known searchable phrase in each output document.
- Rehashed all 18 staged candidate files against the original pilot manifest; all matched.
- Confirmed resume reports four published books, five reused ranges, zero extracted ranges, zero failures and no pending publication.
- Rust checks covered internal dates, authority/baseline preservation, coarse/qualified groups, source hash binding, full-page conversion, range corruption repair, failure isolation, policy-only assembly, and stale-worker publication. Operator instructions are in [searchable-markdown.md](searchable-markdown.md).

Detailed local evidence: `source-selection-data/markdown-pilot-01/{pilot-run-01.json,pilot-run-02.json,verification.json}`; coordinator and per-job logs are retained alongside them.

## Interpretation

The pilot establishes a usable searchable-text path and restart behavior for these four native-text documents. It does not establish perfect reading order, table structure, image coverage, or exact font decoding. Expanded Discoveries' first page has no native text; Bad Decisions' page 11 is sparse. The character sheet shows font mappings such as `Sociaˈ` in place of an expected final letter, which the sparse-page heuristic does not detect. Exact layout and wording still require checking the source PDF.

This pilot stays separate from the ongoing full-library scan and existing Dungeon Masters Guild outputs. No broader conversion, search-index promotion, OCR, or 5etools transformation was started.
