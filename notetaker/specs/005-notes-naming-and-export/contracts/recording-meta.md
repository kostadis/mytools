# Contract — `meta.json` (RecordingMetaSchema v2)

**File path**: `<cache-root>/<url-hash>/meta.json`
**Schema module**: `src/notetaker/contracts/recording_meta.py`
**Schema version**: `"2"` (current). Lenient read of legacy `"1"` (implicit) preserved.

This file is per-cache-entry metadata. It is NOT an inter-stage data contract (Article I.3) — it is read by multiple stages but does not move data from one stage to the next. The versioning discipline is applied here for forward-compatibility, not because Article I.3 requires it.

## v2 schema

```json
{
  "schema_version": "2",
  "recording_url": "https://...",
  "created_at": "2026-05-10T14:32:01.123456+00:00",
  "meeting_title": "Q2 Planning Sync",
  "recording_date": "2026-04-15",
  "summary": "Roadmap, headcount, OKR rollovers"
}
```

| Field | Type | Required | Default on lenient read | Validation |
|---|---|---|---|---|
| `schema_version` | `string` | required on write; absent on legacy v1 read | `"1"` if absent | Must be `"1"` or `"2"` on read; `"2"` on write. |
| `recording_url` | `string` | yes | n/a | Non-empty. |
| `created_at` | `string` (ISO-8601, UTC) | yes | n/a | Parseable as datetime. |
| `meeting_title` | `string \| null` | no | `null` | When non-null: length ≥ 1, length ≤ 500 (raw, pre-sanitization). |
| `recording_date` | `string \| null` | no | `null` | When non-null: matches `^\d{4}-\d{2}-\d{2}$`. |
| `summary` | `string \| null` | no | `null` | When non-null: length ≤ `NotesConfig.summary_max_chars` (default 50). |

## Lenient v1 → v2 upgrade

When `RecordingMetaSchema.from_path(p)` reads a legacy file:

1. Parse the JSON; if it lacks `schema_version`, treat as v1.
2. Set `schema_version="1"` in the loaded model (preserves "what we read") and add `meeting_title=None`, `recording_date=None`, `summary=None` defaults.
3. The next call to `model.write(p)` serialises with `schema_version="2"` and any fields that have since been populated. The on-disk upgrade is implicit on first write.

A pure read (no write afterwards) leaves the file untouched on disk. There is no separate migration entry point.

## Producers and consumers

- **Producer (capture stage)**: `Cache.initialise()` writes the v2 file with `recording_url` + `created_at` + (if available) `meeting_title` + `recording_date`. `summary` is `null` at this point.
- **Producer (notes stage)**: After a successful render + summary, the notes orchestrator updates the `summary` field and rewrites the file.
- **Consumer (notes stage)**: Reads `meeting_title`, `recording_date`, `summary` to derive the filename via `notes.naming.derive_notes_filename(meta)`.
- **Consumer (export command)**: Reads the same three fields per entry. If a field is `None`, applies the documented fallbacks.
- **Consumer (purge command)**: Only needs to know the file exists (used as the marker that distinguishes legitimate cache entries from partial-write directories during the cache walk).

## Failure modes

- *File missing* — the cache entry is treated as not initialised. Capture creates it; export and purge skip the entry directory.
- *File present but JSON-malformed* — schema load raises; the calling command logs and skips the entry. The file is not auto-repaired.
- *File present but field type wrong* — schema load raises; same handling as malformed JSON.
- *`schema_version` is a value other than `"1"` or `"2"`* — schema load raises with a clear message. The user is expected to be on a release where their cache and their code agree; this is the existing contract for upgrade safety.
