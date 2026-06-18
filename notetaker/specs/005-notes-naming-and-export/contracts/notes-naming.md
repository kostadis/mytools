# Contract — Notes filename derivation

**Module**: `src/notetaker/notes/naming.py`
**Public surface**:
- `derive_notes_filename(meta: RecordingMetaSchema, *, max_chars: int, summary_max_chars: int, collision_suffix: str | None = None) -> str`
- `sanitize_component(raw: str | None, *, max_chars: int, fallback: str) -> str`

## Output shape

```text
<YYYY-MM-DD>--<sanitized-meeting-title>--<sanitized-summary>.md
```

Example: `2026-04-15--Q2 Planning Sync--Roadmap, headcount, OKR rollovers.md`

With a within-cache-entry collision disambiguator (Decision 5(A)):

```text
2026-04-15--Q2 Planning Sync--Roadmap, headcount, OKR rollovers--a1b2c3d4.md
```

The disambiguator is the first 8 hex chars of the recording's URL hash (deterministic, stable across re-runs of the same recording). `--<disambiguator>` is inserted *before* the `.md` extension.

## Sanitization pipeline (per component)

Apply in order:

1. If `raw` is `None`, return `fallback`.
2. Strip leading and trailing whitespace.
3. Replace each character in the disallowed set with a single space:
   - `/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`
   - NUL byte (`\x00`)
   - All ASCII control characters (`\x00`–`\x1F`, `\x7F`)
4. Collapse runs of whitespace into a single space.
5. Strip leading dots (avoids hidden files on Unix).
6. Truncate to `max_chars`. Truncation cuts at the last word boundary ≤ `max_chars` if one exists in the last 25% of the truncated window; otherwise it cuts at exactly `max_chars` and re-strips trailing whitespace.
7. If the result is empty, return `fallback`.

The same pipeline is used for both the meeting-title and the summary components, with different `max_chars` values:
- Meeting title: bounded by the overall filename length (filenames are capped at `filename_max_chars=200`; the title gets whatever fits after subtracting the date, separators, summary, and `.md`).
- Summary: bounded by `summary_max_chars=50` (FR-002 / SC-003).

Non-ASCII characters (Japanese, accented Latin, etc.) are preserved by the pipeline. Only the explicit disallowed set is replaced.

## Composition rules

1. `date = meta.recording_date or meta.created_at[:10]`. If both are missing or unparseable, use `"undated"` as the date component (extreme edge case; logged as a warning).
2. `title = sanitize_component(meta.meeting_title, max_chars=<title_budget>, fallback="untitled")`.
3. `summary = sanitize_component(meta.summary, max_chars=summary_max_chars, fallback="no-summary")`.
4. Compose: `f"{date}--{title}--{summary}.md"` (and `--{collision_suffix}` before `.md` if provided).
5. If the composed length exceeds `max_chars`, recompute `title_budget = max_chars - len(date) - len(summary) - len("--") * 2 - len(".md") - (8+2 if collision_suffix else 0)` and re-sanitize the title with the smaller budget. Re-compose.
6. Hard guarantee: the final string never exceeds `max_chars + len(".md")`. Tested in `test_notes_naming.py::test_filename_under_cap_for_pathological_titles`.

## Determinism

Given the same `meta` and the same config values, `derive_notes_filename` returns the same string. This is what makes re-runs idempotent (SC-005) and what makes the within-entry collision suffix safe to apply silently.

## When the orchestrator applies the collision suffix

The notes orchestrator (in `src/notetaker/notes/__init__.py`) calls `derive_notes_filename` without a `collision_suffix` first. If the resulting path already exists with content that does NOT match what is about to be written, it re-derives with `collision_suffix=meta.url_hash[:8]` and uses that name. This case is rare in practice (it requires a re-render against a recording whose summary has materially changed), but the determinism of the suffix means the same recording always lands at the same disambiguated name.

## Legacy-cache rename detection

The orchestrator separately detects the legacy `notes.md` filename: if `<cache>/<hash>/notes/notes.md` exists and the human-readable file does not, the legacy file is renamed to the human-readable path before any new content is written. The rename is recorded as `notes.legacy_renamed` with `from` and `to` fields.

## Cross-platform safety

The disallowed character set is the union of macOS HFS+/APFS-troublesome characters and Linux ext4 reserved characters, plus the cross-platform-shell trouble set. Concretely:

- Linux ext4 reserves only `/` and NUL — the pipeline replaces both.
- macOS APFS technically allows `:` but Finder displays it as `/`, leading to user confusion — replaced.
- Cross-platform shells trip on `*`, `?`, `"`, `<`, `>`, `|` — replaced.
- ASCII control characters and NUL — replaced (defence in depth against malformed model output).

Windows reserved names (CON, PRN, AUX, NUL, COM1–9, LPT1–9) are NOT specifically detected. Per the spec's macOS/Linux scope, Windows is out of support; if a future feature adds Windows support, a Windows-reserved-name check belongs in this same pipeline.

## Edge-case examples

| Raw `meeting_title` | Sanitized result |
|---|---|
| `"Q2 Planning Sync"` | `Q2 Planning Sync` |
| `"Q1/Q2 Roadmap"` | `Q1 Q2 Roadmap` |
| `"  weekly:: standup  "` | `weekly  standup` (collapses to `weekly standup` after step 4) |
| `"Quarterly Business Review — Engineering"` | `Quarterly Business Review — Engineering` (em-dash preserved) |
| `"営業ミーティング"` | `営業ミーティング` (CJK preserved) |
| `"...:::"` | `untitled` (everything stripped, fallback applies) |
| `None` | `untitled` |
| `"a" * 500` | first `<title_budget>` chars |
