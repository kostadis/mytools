# Contract: CLI Surface (Before/After)

The notetaker CLI exposes a closed set of subcommands. This document
records the diff this feature applies to that set.

## Before this feature (six subcommands)

```text
notetaker capture     <url> [--debug] [--force]
notetaker extract     <url> [--debug] [--force]
notetaker understand  <url> [--debug] [--force]
notetaker synthesise  <url> [--debug] [--force]    # legacy
notetaker notes       <url> [transcript] [--output PATH] [--force] [--re-render] [--dry-run] [--debug]
notetaker run         <url> [--debug] [--force]
```

`notetaker run`'s observed behaviour: chains
`capture → extract → understand → synthesise`. Final printed line:

```text
Pipeline complete. Summary: <cache>/<hash>/synthesis/summary.md
```

## After this feature (five subcommands)

```text
notetaker capture     <url> [--debug] [--force]
notetaker extract     <url> [--debug] [--force]
notetaker understand  <url> [--debug] [--force]
notetaker notes       <url> [transcript] [--output PATH] [--force] [--re-render] [--dry-run] [--debug]
notetaker run         <url> [--debug] [--force]
```

`notetaker synthesise` is deleted. Invoking it produces the standard
typer/click "no such command" error and a non-zero exit code (FR-001).

`notetaker run` chains `capture → extract → understand` and exits. Final
printed lines:

```text
Pipeline complete (capture + extract + understand). Cache: <cache>/<hash>/
Next: notetaker notes "<url>" <transcript-file>
       (or omit <transcript-file> to use the cached transcript.json from a successful live capture)
```

The exact wording is a UX detail — what's contractually required is:
1. The first line names the cache directory the user just populated.
2. The second line is a copy-pasteable `notetaker notes` invocation that
   uses the same `<url>` the user passed and includes a placeholder for
   the transcript file path.
3. Exit code is 0 on success of the three chained stages.

## Behavioural contract checklist

| Property | Before | After | Spec ref |
|---------|--------|-------|----------|
| `notetaker --help` lists `synthesise` | yes | no | FR-001, SC-001 |
| `notetaker synthesise <url>` exits zero | yes | no (CLI parser error) | FR-001 |
| `notetaker run <url>` invokes the legacy stage | yes | no | FR-002 |
| `notetaker run --help` describes a four-stage chain | yes | no (three-stage) | FR-003 |
| `notetaker run`'s final printed line names the next command | no | yes | FR-002 |
| `notetaker notes` continues to work unchanged | yes | yes (unchanged) | (out of scope; spec 003) |
| Default model when `notes.model` unset is `claude-sonnet-4-6` | yes | yes (now baked into NotesConfig) | FR-006, SC-007 |
