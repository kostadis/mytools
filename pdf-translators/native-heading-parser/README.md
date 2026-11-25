# Heading parser experiment

This optional Rust/PyO3 parser was generated through fast-anything 0.8.6 and
implemented manually. It preserves the converter's heading values and Python
`splitlines` behavior, including lone surrogates. It reads Python Unicode
storage directly rather than copying the document to a Rust UTF-8 string.
It uses Python's native string operations to construct the output strings.

The converter uses this parser automatically when built. It retains Python
when the optional binary is absent or cannot load. Runtime parsing errors
propagate normally. Set `FAST_ANYTHING_DISABLE=1` before starting a converter
process to force Python. This is an optional local build, not a required
installed dependency. See [the experiment report](../docs/heading-parser-experiment.md).

## Build and check (Linux)

From `pdf-translators/`, with Cargo and the converter's Python environment:

```sh
python3 native-heading-parser/build.py
PDF_HEADING_NATIVE_DIR=native-heading-parser/target/python python3 -m pytest tests/test_native_heading_parser.py tests/test_heading_parser_benchmark.py tests/test_pdf_to_5etools_v2.py -q
python3 benchmarks/heading_parser_memory.py --markdown /path/to/book.md --native-dir native-heading-parser/target/python --runs 5 > /tmp/heading-parser-memory.json
```

The extension requires Python 3.10 or newer and uses PyO3's stable ABI. The
commands above target Linux; other platforms need their native extension
filename. The benchmark calls the offline Markdown path without inference or
writing converted files. Its separate RSS/tracemalloc samples use fresh
processes and verify output hashes. Timing inside each sample excludes imports;
RSS includes the interpreter, imports, extension, and conversion allocations.

## Original fast-anything workflow

The initial experiment ran `fast-anything scan` on an offline converter invocation using a cached
Markdown file and `--provider claude-code --dry-run`, recorded the
`converters/pdf_to_5etools_v2.py:parse_markdown_headings` candidate with `port`,
read the generated contract, copied this crate's `src/lib.rs` into its generated
crate, then ran `verify`, `enable`, `bench`, and `report`. Its temporary activation
block was removed after benchmarking:

```sh
fast-anything -C . disable converters/pdf_to_5etools_v2.py:parse_markdown_headings
```

The durable loader now replaces that temporary activation block.
`FAST_ANYTHING_DISABLE=1` selects Python for both mechanisms. The memory
benchmark explicitly disables automatic acceleration in every worker, then selects native mode itself, so activation cannot
contaminate the Python baseline. Private recordings and compiled libraries in
`.fast/` are ignored; keep them out of commits.
