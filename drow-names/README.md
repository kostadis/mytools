# drow-names

Drow name generator built from the name-element table in *Dragon* Magazine #267 (January 2000).
It makes first names (prefix + suffix, female/male) and house names, and shows what each part means.

**This repo is public, so it holds no table content.** The table lives in
`~/src/homebrew-private/book/dragon-267-drow-names/` (`$DROW_NAMES_DATA_DIR` overrides the base):
`source.txt` is the verbatim paste and `tables.json` is the parsed form. `import` refuses to write inside this repo.

## Setup (once)

```bash
cargo run -- import        # source.txt -> tables.json; checks 100/100/30/30 rows
```

## Use

```bash
cargo run -- -n 5                    # full names: first + house
cargo run -- first --sex female -n 3
cargo run -- house
cargo run -- --cross --sex female    # house option: females may take male elements
cargo run -- list suffixes
cargo run -- --json --seed 7
```

## Rules

- Males draw only male or single-form elements. Females draw female or single-form elements, plus male ones with `--cross`.
- Rows printed with a single form are treated as usable by either sex; `import` lists them.
- Typos in the source are kept verbatim.
