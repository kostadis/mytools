# Feature Specification: Human-readable notes filenames, export, and cache delete

**Feature Branch**: `005-notes-naming-and-export`
**Created**: 2026-05-10
**Status**: Draft
**Input**: User description: "the current mechanism to find notes relies on a binary key like d0c7585ad7629cdf- which means finding notes later is going to involve a lot of grepping. I would like to have the notes.md file have a proper name. Ideally the name of the zoom meeting itself with a date and a one line descriptive summary not longer than 50 characters. And I would like to be able to copy all of the notes file from the cache with those names into a user specified directory. And finally i would like to be able to delete the cache"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Notes files have human-readable names (Priority: P1)

When the user finishes a `notetaker notes` run, the resulting notes file is saved under a name that lets the user identify the meeting at a glance — the Zoom meeting title, the recording date, and a short descriptive summary — instead of being addressable only by an opaque 16-character cache hash.

**Why this priority**: This is the core unlock. Without a human-readable name, both the export workflow (P2) and any general "find my notes" workflow remain dependent on grep over an opaque hash tree. Solving naming first delivers immediate value (the user can browse the cache by name) and is a prerequisite for P2.

**Independent Test**: Run `notetaker notes <url>` end-to-end against a recording whose meeting title is "Q2 Planning Sync". Verify that the resulting notes file inside the cache has a filename containing the meeting title, the recording date, and a summary ≤ 50 characters — and is locatable by browsing the filesystem without grep.

**Acceptance Scenarios**:

1. **Given** a fully-cached recording whose Zoom meeting title is "Q2 Planning Sync" and recording date is 2026-04-15, **When** the user runs `notetaker notes <url>`, **Then** a notes file is written into the cache with a name that contains "Q2 Planning Sync", "2026-04-15", and a generated summary ≤ 50 characters, and the printed `notes:` line points at that human-readable path.
2. **Given** a recording whose meeting title contains characters disallowed in filenames (`/`, `:`, `*`), **When** notes are written, **Then** the filename strips or replaces those characters and remains ≤ 200 characters total.
3. **Given** the meeting title cannot be retrieved (scrape failed, network blocked the page metadata), **When** notes are written, **Then** the system falls back to a deterministic, recognizable name (e.g. an `untitled-<hash-prefix>` form) that still includes the date and the summary, and logs a warning.
4. **Given** the rendered notes content is empty or the summary cannot be generated, **When** notes are written, **Then** the system uses a fixed placeholder summary (e.g. `no-summary`) and the file is still produced with the meeting name and date components.

---

### User Story 2 - Export all cached notes into a user-specified directory (Priority: P2)

The user invokes a single command that copies every rendered notes file from the cache into a directory of their choosing, preserving the human-readable filenames. This lets the user pull all of their meeting notes into a personal archive, a Dropbox folder, an Obsidian vault, etc., without manually walking the cache tree.

**Why this priority**: P2 turns the cache from an opaque transient store into a usable source of long-term records. It depends on P1 (without good filenames the export is useless), and it is the workflow that justifies P3 — once notes are exported, the cache becomes safe to delete.

**Independent Test**: Populate the cache with notes for three different recordings, then run the export command pointing at an empty target directory. Verify all three notes files appear in the target with their human-readable names, the cache copies are still present, and the command reports `copied=3 skipped=0`.

**Acceptance Scenarios**:

1. **Given** the cache contains three cache entries with rendered notes files, **When** the user runs the export command targeting an empty directory, **Then** all three notes files are copied into the target with their human-readable names, the cache originals remain, and the command reports the count copied.
2. **Given** the target directory does not exist yet, **When** the user runs the export command, **Then** the system creates the directory and copies the files.
3. **Given** the cache contains an entry that has no rendered notes file (only frames or working_doc, e.g., a partial pipeline run), **When** the user runs the export command, **Then** that entry is skipped and the command reports it under "skipped (no notes)".
4. **Given** a file with the same destination filename already exists in the target directory, **When** the user runs the export command without an overwrite flag, **Then** the existing file is preserved, the cache copy is not written over it, and the command reports the collision in its summary; re-running with an explicit overwrite flag replaces the existing file.
5. **Given** the cache contains entries created before this feature shipped (named `notes.md` rather than human-readable), **When** the user runs the export command, **Then** those entries are exported under a generated human-readable name (recomputed at export time from whatever metadata is available) so legacy notes are not lost.

---

### User Story 3 - Delete the cache (Priority: P3)

The user invokes a single command that removes the entire notetaker cache, reclaiming disk space. The command requires explicit confirmation because it is destructive.

**Why this priority**: Disk hygiene. Once the user has exported the notes they care about (P2), the cache becomes throwaway. P3 makes that final step a one-liner instead of a `rm -rf` against a path the user has to remember.

**Independent Test**: Populate the cache with two recordings' worth of artifacts, then run the delete-cache command and confirm. Verify the cache root is empty (or the directory itself is gone), and the command reports the number of entries removed and the bytes reclaimed.

**Acceptance Scenarios**:

1. **Given** a cache containing one or more recording entries, **When** the user runs the delete-cache command and confirms the prompt, **Then** every entry under the cache root is removed and the command reports the count and reclaimed bytes.
2. **Given** the user runs the delete-cache command but declines the confirmation prompt, **When** the prompt is cancelled, **Then** no files are removed and the command exits cleanly with a "cancelled" message.
3. **Given** the user passes a non-interactive `--yes` flag, **When** the command runs, **Then** the cache is deleted without prompting.
4. **Given** the cache root is already empty or does not exist, **When** the user runs the delete-cache command, **Then** the command exits cleanly and reports zero entries removed (no error).

---

### Edge Cases

- Two recordings on the same date have identical meeting titles and similar summaries that collapse to the same sanitized filename. The system must disambiguate (e.g., short hash suffix) so notes are never silently overwritten in the cache or in export.
- Meeting title contains characters that are legal on Linux but illegal on macOS or Windows (e.g., colon). Sanitization must produce names safe across the platforms `notetaker` supports.
- Meeting title is non-ASCII (e.g., Japanese, accented Latin). Sanitization must preserve readability where possible rather than stripping to nothing.
- A cache entry has `working_doc.md` but no `notes.md` (an interrupted run). Export skips it; delete-cache removes it.
- The user passes a target directory that lives on a different filesystem (network share, slow disk). The command continues without erroring.
- The user runs `notetaker notes <url>` against a recording that already has a notes file from before this feature (literally `notes.md`). The system MUST either rename it in place or write the new human-readable file alongside without losing data.
- The user runs the delete-cache command while another `notetaker` process is mid-run on the same cache root. Behaviour is best-effort: the in-flight run may fail, but the cache root is not corrupted into a half-deleted state that breaks future runs.
- The user has redirected `--output` on prior `notetaker notes` runs, so notes also exist outside the cache. The export and delete commands operate only on the configured cache root; out-of-cache notes are out of scope.
- Filename component lengths: meeting title, date, and summary together must fit within filesystem name limits (target ≤ 200 characters, with hard ceiling 255 to stay safe across filesystems). If a meeting title is very long, it is truncated before the date and summary are appended.

## Requirements *(mandatory)*

### Functional Requirements

#### Naming (User Story 1)

- **FR-001**: System MUST write each rendered notes file using a human-readable filename composed of the meeting name, the recording date, and a generated descriptive summary, with a `.md` extension.
- **FR-002**: System MUST cap the descriptive summary at 50 characters and the entire filename (excluding the `.md` extension) at ≤ 200 characters; longer components MUST be truncated, not rejected.
- **FR-003**: System MUST sanitize the meeting name and the summary for filesystem use (strip or replace path separators, ASCII control characters, and characters that are reserved on the filesystems `notetaker` supports).
- **FR-004**: System MUST source the meeting name from the Zoom recording page title and persist it into the cache so subsequent runs reuse the same name. If the title cannot be retrieved, the system MUST fall back to a deterministic, recognizable name that still allows the user to find the file (e.g., `untitled-<short-hash>`) and MUST emit a warning log record.
- **FR-005**: System MUST source the recording date in `YYYY-MM-DD` form, preferring the recording's own date when available and falling back to the cache entry's creation date.
- **FR-006**: System MUST generate the descriptive summary from the rendered notes content (not from the raw transcript or slide content). The summary generation MUST be observable (logged) and MUST NOT block notes production: if summary generation fails, the system uses a fixed placeholder and proceeds.
- **FR-007**: System MUST guarantee uniqueness of the human-readable filename within a single cache entry's `notes/` directory by appending a short disambiguator (e.g., a hash suffix) when a name would otherwise collide with an existing file.
- **FR-008**: System MUST keep the existing `working_doc.md` artifact under its current name and location alongside the renamed notes file, so the `--re-render` workflow continues to function unchanged.
- **FR-009**: System MUST preserve cache lookup-by-URL: a user (or downstream tool) who passes a recording URL or 16-character cache id MUST still be able to locate that recording's notes file regardless of its human-readable name.

#### Export (User Story 2)

- **FR-010**: System MUST provide a CLI subcommand that copies every rendered notes file from the configured cache root into a user-specified target directory.
- **FR-011**: Export MUST copy (not move) — the cache originals remain after export.
- **FR-012**: Export MUST create the target directory if it does not exist, including any missing parents.
- **FR-013**: Export MUST skip cache entries that have no rendered notes file and report the skipped count separately from the copied count.
- **FR-014**: Export MUST NOT overwrite an existing file in the target directory by default. When a destination filename already exists, the source file MUST be skipped and the collision reported. An explicit overwrite flag MUST be available for users who want to replace existing files.
- **FR-015**: Export MUST report a clear summary: number of files copied, number skipped (no notes), number skipped (collision), and the resolved target directory.
- **FR-016**: Export MUST exit with a non-zero status only on hard errors (target path unwritable, source file unreadable). A run with collisions or skipped entries is not, by itself, a failure.
- **FR-017**: Export MUST handle legacy cache entries (notes files created before this feature, named `notes.md`) by recomputing a human-readable destination name at export time using the same naming rules as FR-001 through FR-007.

#### Delete cache (User Story 3)

- **FR-018**: System MUST provide a CLI subcommand that deletes the entire configured cache root, including all recording entries (`notes/`, `capture/`, `extraction/`, `understanding/`, `meta.json`).
- **FR-019**: The delete-cache subcommand MUST require explicit interactive confirmation before proceeding, AND MUST support a non-interactive `--yes` flag for scripted use.
- **FR-020**: The delete-cache subcommand MUST be a no-op (clean exit, zero entries removed reported) if the cache root is missing or already empty.
- **FR-021**: The delete-cache subcommand MUST report a summary on completion: number of recording entries removed and bytes reclaimed.
- **FR-022**: The delete-cache subcommand MUST NOT touch directories outside the configured cache root (in particular, it MUST NOT remove logs, exported notes, or the `~/.local/share/notetaker/` parent directory itself).

### Key Entities *(include if feature involves data)*

- **Notes filename**: A composite identifier for a rendered notes file, derived from `<meeting-name>` + `<recording-date>` + `<summary>` (≤ 50 chars). Sanitized for filesystem use and capped at ≤ 200 characters total. Lives inside a cache entry's `notes/` subdirectory and is also the destination filename when the file is exported.
- **Meeting metadata**: Per-cache-entry data needed to compute the notes filename: meeting name (Zoom recording page title), recording date, and the generated summary. Persisted alongside the cache entry so the same file gets the same name across re-runs.
- **Export target directory**: A user-specified directory (any path the user has write access to) into which cached notes are copied. May or may not exist before the export call.
- **Cache root**: The configured directory under which all per-recording cache entries live. Operated on as a unit by the export and delete-cache subcommands.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user looking for a specific meeting's notes can locate the correct file by browsing or shell-completing filenames in under 30 seconds, without using `grep`. (Today: requires grepping or remembering a 16-character hash.)
- **SC-002**: 100% of newly produced notes filenames are filesystem-safe across Linux and macOS (no path separators, no reserved characters, ≤ 255 bytes), and 100% have a `.md` extension.
- **SC-003**: 100% of newly produced summaries are ≤ 50 characters.
- **SC-004**: After exporting a cache containing N rendered notes files into an empty target directory, exactly N files appear in the target with their human-readable names, and the cache continues to contain those N files (zero data loss).
- **SC-005**: Re-running export against an unchanged cache and an unchanged target directory produces zero copies and zero collisions resolved (the operation is idempotent in steady state).
- **SC-006**: After a confirmed delete-cache run, the cache root contains zero entries and ≥ 99% of the prior cache's disk usage is reclaimed.
- **SC-007**: Cancelling the delete-cache prompt leaves the cache 100% intact (zero files modified or removed).
- **SC-008**: The export command completes in under 5 seconds per 100 cached notes files on a local SSD (the work is filesystem copies, not LLM calls).

## Assumptions

- The Zoom recording page exposes a meeting title that can be retrieved during the existing capture stage. If retrieval fails, a deterministic fallback is acceptable (per FR-004) and does not block the feature.
- The descriptive summary is produced as part of the existing post-capture notes flow (e.g., as a small addition to the rendering call or an immediate follow-up call). Cost is negligible relative to the main notes render and stays within the existing `[notes] cost_warn_threshold_usd` envelope; no new budget knob is introduced.
- The cache is treated by the user as ephemeral — long-term records live in the export target directory. The expected workflow is: run pipeline → review notes → export to target → delete cache when disk pressure warrants.
- The delete-cache subcommand wipes the entire cache root including `notes/` subdirectories; users are expected to export first if they want to keep notes. (This is a deliberate simplification — a finer-grained "keep notes, delete artifacts" mode is out of scope for this feature and could be added later.)
- The export and delete-cache subcommands operate against the configured cache root only. Notes files written elsewhere via `notetaker notes --output <path>` are out of scope for both commands.
- Legacy cache entries (notes files produced before this feature, literally named `notes.md`) are handled lazily: they are renamed or augmented on next access, and the export command computes a human-readable destination name for them at export time. No standalone migration script is required.
- The existing `[notes] retention_days` retention knob continues to apply to the renamed notes files; renaming does not change retention semantics.
- "Recording date" defaults to the cache entry's creation date if a true recording date cannot be cheaply extracted; this is good enough for filename disambiguation in practice.
