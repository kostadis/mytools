<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
at `specs/005-notes-naming-and-export/plan.md`.
<!-- SPECKIT END -->

## CLI subcommands

`notetaker` exposes seven subcommands:

- `capture`, `extract`, `understand` — the chained pipeline stages.
- `run` — chains `capture → extract → understand` and prints the next-step
  `notetaker notes` command for the user to copy.
- **`notes`** — combines the slide content from `understand` with a
  transcript file (obtained via the post-capture browser snippet documented
  in `HOWTO.md "Obtaining a transcript"`) and renders polished Markdown via
  a single LLM call. The notes file is written under a human-readable name
  (`<YYYY-MM-DD>--<meeting>--<summary>.md`) per spec 005. See the specs at
  `specs/003-post-capture-notes/spec.md` and
  `specs/005-notes-naming-and-export/spec.md`.
- **`export`** — copy every cached notes file out into a user-specified
  directory under its human-readable name. Non-destructive; cache copies
  remain. See `specs/005-notes-naming-and-export/spec.md`.
- **`purge`** — delete the entire cache after explicit confirmation
  (`--yes` skips the prompt for non-interactive use). Sibling directories
  (logs, exported notes) are not touched.

The live transcript scrape inside `capture` is best-effort. When it misses
(empty transcript), the run still exits successfully and points the user at
the post-capture browser-snippet recovery procedure documented in
`HOWTO.md "Obtaining a transcript"`. Slide artifacts are unaffected.
