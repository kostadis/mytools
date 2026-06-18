# Contract: Configuration Surface (Before/After)

The shipped `config.toml` and the `Config` dataclass it deserialises into
form a contract with users who edit the file. This document records the
diff this feature applies.

## Before this feature

`config.toml` (extract):

```toml
[notes]
# Model for the post-capture notes render call. Empty string = inherit synthesis.summary_model.
model = ""
max_output_tokens = 8192
retention_days = 365
working_doc_filename = "working_doc.md"
notes_filename = "notes.md"
cost_warn_threshold_usd = 0.50

[synthesis]
# Model for per-slide and overall summary generation
summary_model = "claude-sonnet-4-6"
```

`Config` dataclass (relevant fields):
- `Config.synthesis: SynthesisConfig` with `summary_model = "claude-sonnet-4-6"`
- `Config.notes: NotesConfig` with `model = ""`
- `Config.resolved_notes_model() -> str` returns `notes.model or synthesis.summary_model`

## After this feature

`config.toml` (extract):

```toml
[notes]
# Model for the post-capture notes render call. Defaults to "claude-sonnet-4-6".
# Override here to swap in a different Claude model for the single render call.
model = "claude-sonnet-4-6"
max_output_tokens = 8192
retention_days = 365
working_doc_filename = "working_doc.md"
notes_filename = "notes.md"
cost_warn_threshold_usd = 0.50
```

The `[synthesis]` section is gone.

`Config` dataclass:
- `Config.synthesis` field — DELETED
- `SynthesisConfig` dataclass — DELETED
- `Config.notes.model` default — `"claude-sonnet-4-6"` (baked-in)
- `Config.resolved_notes_model() -> str` returns `notes.model` (single source)
- TOML loader silently ignores any unknown `[synthesis]` section in user
  config files (existing behaviour of the TOML loader; no new code).

## Behavioural contract checklist

| Property | Before | After | Spec ref |
|---------|--------|-------|----------|
| Shipped `config.toml` contains `[synthesis]` | yes | no | FR-004 |
| Shipped `[notes]` comment mentions inherited fallback | yes | no | FR-004 |
| User config with stale `[synthesis]` loads successfully | yes | yes | FR-005 |
| Per-run deprecation warning when `[synthesis]` is present | no | no (don't add one) | FR-005 |
| `Config.resolved_notes_model()` exists | yes | yes | (preserved chokepoint) |
| Default model name returned for unconfigured user is `claude-sonnet-4-6` | yes | yes | FR-006, SC-007 |
| User-set `notes.model = "..."` overrides the default | yes | yes | (preserved) |
| Empty-string `notes.model = ""` falls back to a sibling section | yes | no — empty is honoured literally | (Decision 1 in research.md) |

## Notes on the empty-string edge case

Before: a literal `notes.model = ""` in the user's config silently fell
back to `synthesis.summary_model`. After: it is honoured literally and
will likely cause the SDK call to error.

This is acceptable because:
1. The shipped `config.toml` no longer ships `model = ""`. A user only
   hits this if they explicitly hand-set the empty string.
2. A user who explicitly sets `model = ""` is making a typo or
   experimenting; the resulting SDK error is loud, immediate, and
   self-evidently the user's setting (not a silent surprise).
3. There is no reasonable interpretation of "the user wanted an empty
   model name" that this code path could honour.
