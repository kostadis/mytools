# Contract — CLI surface (new `export` and `purge` subcommands)

**Module**: `src/notetaker/cli.py` (registration), `src/notetaker/cache_ops.py` (implementation)

## Existing surface (unchanged by this feature)

```text
notetaker capture     <url>   [--debug] [--force]
notetaker extract     <url>   [--debug] [--force]
notetaker understand  <url>   [--debug] [--force]
notetaker run         <url>   [--debug] [--force]
notetaker notes       <url> [transcript-path] [--output PATH] [--force] [--re-render] [--dry-run] [--debug]
```

## New subcommands

### `notetaker export <directory>`

Copies every rendered notes file from the configured cache root into `<directory>` under each file's human-readable name.

**Arguments**:

| Position / Flag | Type | Required | Description |
|---|---|---|---|
| `<directory>` | path | yes | Target directory. Created (with parents) if it does not exist. May be relative; resolved against `cwd`. |
| `--overwrite` | flag | no (default off) | Replace files in the target directory whose name already matches an exporting source. Without this flag, collisions are skipped and reported. |
| `--debug` | flag | no | Verbose logging (existing convention). |

**Exit codes**:

| Code | Meaning |
|---|---|
| 0 | Run completed. Skipped entries (no notes, collision) do NOT cause non-zero exit; they appear in the summary. |
| 1 | Hard error: target path unwritable, source file unreadable, or the cache root contains a malformed `meta.json` that prevents the walker from completing. The summary reports what was copied before the error. |
| 2 | Argument parse error (typer default). |

**Stdout**:

```text
exported to: /abs/path/to/<directory>
copied=<N>  skipped_no_notes=<N>  skipped_collision=<N>  legacy_resolved=<N>
```

When `copied=0` and either skip count is non-zero, the line is followed by a per-entry breakdown (one line per skipped entry) so the user can act on the report.

**Stderr**:

Standard structured-logging output from `_setup` plus the per-entry `export.entry_copied` / `export.entry_skipped_*` records described in the plan's V.1 row.

**Idempotency**: SC-005 — running this command twice in a row against the same cache and target directory copies zero files on the second run (collision-skip behaviour ensures this).

---

### `notetaker purge`

Deletes every per-recording entry under the configured cache root.

**Arguments**:

| Flag | Type | Required | Description |
|---|---|---|---|
| `--yes` | flag | no (default off) | Skip the interactive confirmation prompt. Required for non-interactive use. |
| `--debug` | flag | no | Verbose logging. |

**Behaviour**:

1. Summarises what is about to be deleted: cache root path, entry count, total bytes.
2. If stdin is a TTY and `--yes` is not set, prompts `Proceed? [y/N]:`. Any response other than `y` (case-insensitive) cancels.
3. If stdin is not a TTY and `--yes` is not set, exits 1 with `[notetaker purge] Refusing to purge non-interactively without --yes`.
4. Walks `Cache.iter_entries()` and removes each entry directory (`shutil.rmtree`). Accumulates byte count by walking each entry first.
5. Removes any stray non-entry files at the cache root (logged at debug level), but NOT the cache root directory itself, NOT sibling directories like `~/.local/share/notetaker/logs/`, NOT exported notes elsewhere on the user's filesystem.

**Exit codes**:

| Code | Meaning |
|---|---|
| 0 | Run completed (including the empty-cache no-op and the user-cancelled cases). |
| 1 | Hard error: non-TTY without `--yes`, or rmtree raised on an entry. |
| 2 | Argument parse error (typer default). |

**Stdout**:

On a confirmed delete:

```text
purged: <abs cache root>
entries_removed=<N>  bytes_reclaimed=<N>
```

On user cancel:

```text
purge cancelled
```

On empty cache or missing cache root:

```text
purged: <abs cache root>
entries_removed=0  bytes_reclaimed=0
```

**Safety invariants** (FR-022):

- The configured cache root is the *only* directory the command touches. The `~/.local/share/notetaker/` parent is never traversed; the `logs/` sibling is never read.
- The cache root directory itself is preserved (not removed). Subsequent notetaker runs do not have to recreate it.
- A failed `rmtree` on one entry does not prevent attempts on the others; failed entries are reported in the summary's `entries_removed` count (decremented) and surface as `purge.entry_remove_failed` log records.

---

## Help text

The new subcommands are registered with help strings consistent with the existing five:

```text
export       Copy every cached notes file into <directory> under its
             human-readable name.
purge        Delete the entire cache. Requires confirmation; pass --yes
             for non-interactive use.
```

The top-level `notetaker --help` output is updated to list seven subcommands.
