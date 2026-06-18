# Phase 0 Research: Human-readable notes filenames, export, and cache delete

The spec did not contain any `[NEEDS CLARIFICATION]` markers (deliberate; see the spec's checklist note). What follows is decision recording with rationale for the judgment calls that the functional requirements imply but the spec leaves to implementation. There are no open items.

## Decision 1 — Where the meeting name comes from

**Decision**: Scrape the meeting name from the Zoom recording page during the existing capture stage and persist it into `meta.json`. Use Playwright's `page.title()` first, then a CSS-selector fallback for the recording-topic element if the document title returns the generic Zoom string. Persist the result under `meta.json.meeting_title` (string or null). Subsequent runs (notes, export) read the persisted value and never re-scrape.

**Rationale**:
- FR-004 names the Zoom recording page title as the source. The capture stage already has a Playwright `page` open and authenticated; adding one `await page.title()` call is the cheapest possible plumbing.
- Persisting at capture time (not at notes time) means the notes step can run offline against a populated cache. It also means `--re-render` does not need a browser to recompute the filename.
- Article I.2 ("platform-specific logic lives only in capture adapters") is honoured: the title scrape lives in `stages/capture/adapters/zoom.py` next to the existing `SLIDE_SELECTOR` and `TRANSCRIPT_PANEL_SELECTOR` constants. Downstream code reads `meta.json.meeting_title`, a platform-neutral string.
- The CSS-selector fallback is needed because `page.title()` on Zoom recording pages frequently returns "Zoom" or "Zoom Meetings" (the document title) rather than the recording's topic. The recording topic appears in a `<h1>` or topic-class element on the page; a single-selector fallback is sufficient. The exact selector is a config knob (`capture.recording_title_selector`, default `.recording-topic, .topic-name, h1`) so it can be adjusted without code changes if Zoom's DOM rotates.

**Alternatives considered**:
- *Read the meeting name from the URL.* Rejected — Zoom recording URLs (`/rec/share/<opaque-id>`) do not encode the topic. Some replay URLs include a slug, but most do not, and the slug is sanitised already in ways that lose readability.
- *Ask the user to type the meeting name when capture starts.* Rejected — the spec's user-facing premise is that the system already knows enough to produce a good filename; adding an interactive prompt would defeat that. Also breaks the `notetaker run` chained workflow.
- *Use the first slide's title as the meeting name.* Rejected — the first slide is often a title slide whose text is presentation-specific ("Welcome", "Agenda") rather than a meeting topic. Also deferred until after the understanding stage runs, which would force notes-time scraping anyway.
- *Persist the meeting name in a sibling file (`title.txt`) instead of `meta.json`.* Rejected — `meta.json` is the existing per-cache-entry metadata file; adding fields there is the natural locus and keeps a single read for any consumer.

---

## Decision 2 — How the descriptive summary is generated

**Decision**: After the existing main Sonnet render call produces the notes Markdown, make a separate small Haiku call that takes the rendered notes as input and returns a JSON object `{"summary": "<text ≤50 chars>"}`. Roll the cost into the notes-stage cost reporting; log a `notes.summary_render` record with token counts and cost. On any failure (API error, JSON parse error, length over the cap that the local truncation can't fix safely), fall back to the placeholder string `"no-summary"`, log `notes.summary_fallback` with a `reason` field, and proceed — the notes file is still written.

**Rationale**:
- The user's global `CLAUDE.md` rule says: *Before planning any LLM call, state what decision you are removing from the human.* For the summary call: the LLM is making no scope/ordering/attribution decision. It is rendering a label on already human-reviewable content (the rendered notes themselves). A 10%-wrong label only changes a filename — no automated downstream step inherits the error; the user can rename the file. **This is the safe pattern.**
- A separate Haiku call rather than augmenting the Sonnet prompt: (a) the Sonnet output is optimised for readable notes, not parseable metadata; embedding a sentinel like `# Title: …` would be brittle to extract. (b) Failure isolation: if the summary call fails, the notes file is unaffected. (c) Cost: Haiku at ~600 input tokens + ~30 output tokens is ≈ $0.0006 per call — three orders of magnitude under the existing $0.50 `cost_warn_threshold_usd`.
- JSON-shaped response (not free text): lets the parser reject malformed responses cleanly and apply a defensive client-side length cap.
- Defensive truncation client-side: if Haiku ignores the prompt's "≤50 chars" instruction and returns a longer string, truncate at the last word boundary ≤ `summary_max_chars` (config). This guarantees SC-003 regardless of model behaviour.

**Alternatives considered**:
- *Inline the summary into the Sonnet render call.* Rejected for the reliability and failure-isolation reasons above.
- *Take the first H1 from the rendered notes as the summary.* Rejected — H1s are often the meeting title itself (duplicating that filename component) or the first topical section ("Agenda", "Roll call"), neither of which describes the meeting. Also fragile across prompt revisions.
- *Skip the summary entirely; use only meeting title + date.* Rejected — User Story 1 explicitly asks for the one-line descriptive summary, and the spec's motivating example (weekly "Q2 Planning Sync" recurrences) breaks without it.
- *Generate the summary deterministically from slide content (e.g., concatenate the first three slide titles).* Rejected — slide titles are presentation-specific labels, not meeting summaries. A Haiku call against the rendered notes is far closer to "what was this meeting about" by construction.

---

## Decision 3 — Filename template

**Decision**: `<YYYY-MM-DD>--<sanitized-meeting-title>--<sanitized-summary>.md`. Date first; double-dash separator between components.

**Rationale**:
- Date-first sorts chronologically in any file manager and any shell `ls`. This is the dominant ordering need: users review notes in time order.
- Double-dash `--` is unambiguous: meeting titles and summaries can legitimately contain single-dash hyphens (e.g., "Q2-2026 Planning Sync") and single spaces; the double-dash separator does not collide with either.
- The two-separator form is parseable back into components (split on `--`, strip the `.md` from the last) if any future tooling needs to introspect, but the spec does not require structured-name parsing.

**Alternatives considered**:
- *Use space-as-separator.* Rejected — shell tab-completion is fine, but parseability and visual scanability are worse, and downstream tools (rsync, find) handle dash-separated names more gracefully.
- *Use underscore-as-separator.* Rejected — visually noisier and less idiomatic for meeting-note filenames in the user's likely targets (Obsidian, plain folders).
- *Put the meeting title first.* Rejected — recurring meetings ("Q2 Planning Sync") would all sort together regardless of date, the opposite of what the user wants when scanning recent notes.
- *ISO-8601 date with time (`YYYY-MM-DDTHHMM`).* Rejected — adds noise without value; the user's stated unit of disambiguation is the day, not the minute. Time can be retrieved from filesystem mtime if ever needed.

---

## Decision 4 — Filename sanitization rules

**Decision**: For each component (meeting title and summary), apply the following pipeline in order:

1. Strip leading and trailing whitespace.
2. Replace every character in the disallowed set with a single space: `/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`, NUL byte (`\x00`), and ASCII control characters (`\x00`–`\x1F`, `\x7F`).
3. Collapse runs of whitespace into a single space.
4. Strip leading dots (avoids hidden files).
5. Truncate to the component's max length (`filename_max_chars` for the title, `summary_max_chars=50` for the summary), then strip trailing whitespace again.
6. If the component is empty after the pipeline, replace with the fallback (`"untitled"` for the title, `"no-summary"` for the summary).

After per-component sanitization, the date prefix and the `.md` suffix are appended. If the total filename exceeds 200 characters (excluding `.md`), the meeting-title component is truncated further until the whole name fits.

**Rationale**:
- The disallowed set is the union of characters reserved on Linux ext4, macOS APFS/HFS+, and the "ordinary trouble" characters on cross-platform shells. Windows reserved names (CON, PRN, AUX, NUL, COM1–9, LPT1–9) are documented out of scope per the spec's macOS/Linux target — but the disallowed-character set above already prevents the most dangerous reserved patterns.
- Replacing rather than stripping disallowed characters preserves word boundaries: `"Q1/Q2 Roadmap"` becomes `"Q1 Q2 Roadmap"`, not `"Q1Q2 Roadmap"`. Whitespace collapse then keeps the result tidy.
- Stripping leading dots is necessary on Unix to avoid creating a hidden file. Trailing dots are not stripped (rare in practice; harmless on Linux/macOS).
- Empty-after-sanitization is possible (e.g., a meeting title that was nothing but emoji and slashes). The fallback strings give the user a recognisable name to rename later if they care.

**Alternatives considered**:
- *Use a more permissive sanitizer (e.g., only replace `/`).* Rejected — the spec's SC-002 requires filenames safe across both platforms, and macOS has historically had subtle issues with `:` in particular (Finder treats it as `/`).
- *Use a stricter sanitizer that allows only `[A-Za-z0-9-_ ]`.* Rejected — strips non-ASCII content (Japanese meeting titles, accented Latin) which the spec's edge-case list explicitly calls out as something to preserve.
- *Use Python's `slugify` from `python-slugify` or similar.* Rejected — adds a dependency and produces lowercased, hyphen-only names that are over-aggressive for the user's stated need ("the name of the zoom meeting itself"). Title casing and spaces should be preserved when safe.

---

## Decision 5 — Filename collision handling

**Decision**: Collisions can occur in two contexts and are handled differently in each.

(A) *Within a single cache entry's `notes/` subdirectory* (FR-007 — same recording, different summary on re-render): if `<derived-name>.md` already exists with different content from what we are about to write, append `--<8-char-disambiguator>` to the meeting-title component, where the disambiguator is the first 8 characters of the URL hash. This makes the per-recording name deterministic across re-runs (same URL → same disambiguator). If the existing file's content matches what we're about to write, no rename is needed.

(B) *Across cache entries during export* (FR-014 — two different recordings derive the same filename): the destination filename in the user-specified target directory already has a collision. The export skips the file by default, reports the collision in the summary, and the user re-runs with `--overwrite` to replace. The spec is explicit that overwrite-by-default is the wrong behaviour because the user may have edited the exported copy.

**Rationale**:
- The two contexts have different correctness needs. Within a cache entry, the system is the only writer, so disambiguating with a deterministic suffix is safe and silent. Across cache entries, the user is a writer (they may edit exported notes), so the system MUST NOT overwrite without explicit consent.
- Using the first 8 characters of the URL hash as the (A) disambiguator gives 32 bits of entropy — collision probability across a single user's lifetime cache is effectively zero. Deterministic across runs (always the same hash for the same URL) means re-runs are idempotent, satisfying SC-005.

**Alternatives considered**:
- *Append a numeric counter `--2`, `--3`.* Rejected — non-deterministic across re-runs (depends on filesystem listing order on first collision) and confusing when the user looks at the filename.
- *Append a timestamp suffix.* Rejected — same non-determinism issue and adds noise to the filename.
- *Refuse to write on collision and require user resolution.* Rejected — too brittle for the (A) case; the user shouldn't have to think about why a re-render failed.

---

## Decision 6 — How legacy `notes.md` files are handled

**Decision**: Lazy migration. When `notetaker notes` runs against a cache entry that contains a legacy `notes.md` (no human-readable file present), the system computes the human-readable name from current `meta.json` (running the title scrape if `meta.json` is also legacy and missing the field — see Decision 7), renames `notes.md` to the new path inside the same `notes/` subdirectory, and writes new content there. When the `export` command encounters a legacy `notes.md`, it computes the destination name on the fly and copies under that name (the cache copy is not renamed by export — only by `notes`). Both code paths emit `notes.legacy_renamed` (or `export.legacy_resolved`) log records so the migration is observable.

**Rationale**:
- The spec's edge-case list explicitly calls out the "cache contains entries created before this feature shipped" case and requires that legacy notes are not lost.
- Lazy migration (vs a one-shot script) means there is no migration command for the user to remember to run. Caches that are never touched again simply sit with their old name; caches that are touched migrate transparently.
- Renaming on `notes` runs (vs on every read) keeps the migration where the user is already paying for an LLM call; the rename is essentially free relative to the render cost.
- Not renaming during `export` (only resolving the destination name) avoids surprising the user — `export` is a copy command in the user's mental model; mutating the source as a side effect would violate principle of least surprise.

**Alternatives considered**:
- *Ship a one-shot `notetaker migrate` command.* Rejected — adds surface area for a problem that lazy migration solves cleanly.
- *Always also write a sibling `notes.md` symlink for backwards compatibility.* Rejected — symlinks are filesystem-specific (Windows), and the `notes.md` filename has no consumers outside the `notes` step itself, which is being updated in this same change.
- *Refuse to operate on legacy caches and force a migration.* Rejected — violates the principle that users should not be punished for having cached data from before a feature shipped.

---

## Decision 7 — The `meta.json` v2 schema and lenient v1 reads

**Decision**: Formalise `meta.json` as `RecordingMetaSchema` (Pydantic) with `schema_version="2"`. New fields: `meeting_title: str | None`, `recording_date: str | None` (ISO date `YYYY-MM-DD`), `summary: str | None`. Existing fields remain: `recording_url: str`, `created_at: str` (ISO datetime). Lenient read of legacy files (no `schema_version`, no new fields): treat missing fields as `None`, treat absent `schema_version` as `"1"`. On the next write — typically the next time the file is touched, e.g. when `notes` adds the summary — the file is rewritten under the v2 schema with all available fields populated. Explicit reads-then-writes go through the schema, so the upgrade is automatic.

**Rationale**:
- Article I.3 establishes versioning discipline for inter-stage contracts; while `meta.json` is per-entry rather than inter-stage, applying the same discipline gives us the lenient-default semantics for free and a clear path for future field additions.
- Pydantic is already in the tree (used for transcript, slide_timeline, slide_content). The marginal cost is one small contract file.
- `recording_date` is sourced from `meta.json.created_at` (the cache-entry creation date) by default, with a forward path to a true recording-date scrape later. The spec's Assumptions section already commits to this default.

**Alternatives considered**:
- *Read `meta.json` as a raw `dict` with `.get()` calls everywhere.* Rejected — scatters defaults, makes the upgrade silent, and offers nothing the schema doesn't give us. Future readers would have no single place to learn what the v2 layout is.
- *Bump to a new file (`meta_v2.json`) and ignore the old one.* Rejected — wastes existing legacy meta.json contents (the `recording_url` is still useful), and complicates the `Cache.iter_entries()` walker.

---

## Decision 8 — CLI subcommand names: `export` and `purge`

**Decision**: The two new subcommands are `notetaker export <directory>` and `notetaker purge`.

**Rationale**:
- `export` is the conventional name for "copy these artifacts out of the system into a user-controlled location". Aligns with how users describe the workflow ("I want to export my notes").
- `purge` echoes the existing `Cache.purge_stale()` codebase term; the user-facing semantics ("remove the cache") and the internal terminology stay consistent. Less aggressive-sounding than `delete-cache` while being unambiguous.
- Both names are short enough for muscle memory and unambiguous in `notetaker --help` output. Combined with the existing five subcommands (`capture`, `extract`, `understand`, `notes`, `run`), the seven-name surface remains comprehensible.

**Alternatives considered**:
- *`copy-notes`*: rejected — verbose and less idiomatic.
- *`archive`*: rejected — implies tar/zip semantics, which the user did not ask for.
- *`clean` / `reset` / `clear-cache`*: rejected — `clean` is too generic (clean what?), `reset` implies bringing back to a known state (more complex semantics than the user asked for), `clear-cache` is fine but `purge` matches existing internal vocabulary.

---

## Decision 9 — Confirmation UX for `purge`

**Decision**: `notetaker purge` defaults to interactive confirmation: prints a summary of what is about to be deleted (cache root path, entry count, total bytes) and prompts for `y` (proceed) or anything else (cancel). A `--yes` flag skips the prompt for non-interactive use (CI, scripts). On non-TTY stdin without `--yes`, the command exits 1 with an explanatory error rather than blocking forever or silently proceeding.

**Rationale**:
- Destructive operations should default to safe (FR-019). Showing the user *what* is about to be deleted before asking gives them grounded consent.
- The non-TTY path is critical: a CI script that pipes nothing into `notetaker purge` should error out loudly rather than hang or auto-confirm.

**Alternatives considered**:
- *Default to `--yes` and require `--no` to opt into the prompt.* Rejected — destructive defaults are an anti-pattern.
- *Type a confirmation phrase like the database name (rsync/heroku style).* Rejected — overkill for a personal CLI; the action is reversible if the user has exported (per the workflow assumption in the spec).

---

## Decision 10 — How export handles the cache walk

**Decision**: A new classmethod `Cache.iter_entries(cache_root) -> Iterator[tuple[str, RecordingMetaSchema]]` walks the cache root, yielding `(url_hash, meta)` for every directory that contains a valid `meta.json`. Directories without a `meta.json` are skipped silently (they are partial-write artifacts or out-of-band manual copies). The export and purge commands both use this walker. For each yielded entry, export resolves the human-readable filename (computing it from `meta` plus the in-cache notes file content if needed), checks for a notes file, and copies. Purge simply deletes the entry directory.

**Rationale**:
- A single walker keeps export and purge consistent (they see the same entries in the same order). Skipping directories without `meta.json` is the correct robustness behaviour: such directories are not legitimate cache entries.
- Exposing the walker as a `Cache` classmethod (rather than a free function) keeps cache-layout knowledge concentrated in `cache.py`.

**Alternatives considered**:
- *Have export and purge each implement their own filesystem walk.* Rejected — duplicates cache-layout knowledge.
- *Exposing a list (not iterator).* Rejected — for a power user with hundreds of entries, the iterator interface defers IO until each entry is actually processed and is more memory-friendly.
