# Contract: Command Line

**Requirements**: FR-010c, FR-013 | **Research**: R6

```text
Usage: markdown-editor [--chooser=MODE] [--] [FILE]

Options:
  --chooser=MODE   Which file chooser Open and Save As use:
                     auto    system dialog on a local display, the built-in
                             chooser over SSH or when unsure (default)
                     system  always try the system dialog first
                     window  always use the built-in chooser
  -h, --help       Print this help and exit
  --               Treat everything after it as a file name
```

| Input | Result | Exit |
|-------|--------|------|
| *(no args)* | Starts with an empty document, `auto` | — |
| `notes.md` | Opens `notes.md`, `auto` | — |
| `--chooser=window notes.md` | Opens `notes.md`, in-window chooser | — |
| `--chooser window notes.md` | Same as above | — |
| `notes.md --chooser=system` | Opens `notes.md`, system dialog | — |
| `-- --chooser=window` | Opens a file literally named `--chooser=window` | — |
| `--help` / `-h` | Prints usage to stdout | 0 |
| `--chooser=bogus` | `error: unknown chooser 'bogus' (expected auto, system or window)` and usage, to stderr | 2 |
| `--chooser` (no value) | `error: --chooser needs a value` and usage, to stderr | 2 |
| `--frobnicate` | `error: unknown option '--frobnicate'` and usage, to stderr | 2 |
| `a.md b.md` | `error: expected at most one file` and usage, to stderr | 2 |

Arguments are read as `OsString`, so non-UTF-8 file names still open
(FR-013). Option names and values must be UTF-8.
