# Data Model: Meeting Recording Slide Extractor

**Date**: 2026-05-08 | **Branch**: `001-slide-extractor`

All entities are implemented as Pydantic v2 models in `src/notetaker/contracts/`.
Each schema carries a `schema_version` string field. Breaking changes (field removal,
type change, semantic rename) require a MAJOR version bump and a documented migration.
Additive changes (new optional fields) are MINOR bumps.

---

## Utterance

Represents one turn of speech in the meeting transcript.

| Field | Type | Required | Description |
|---|---|---|---|
| `start_seconds` | float | ✅ | Playback time when the utterance began |
| `end_seconds` | float | ✅ | Playback time when the utterance ended |
| `speaker` | string | ✅ | Speaker name as displayed in the Zoom transcript panel; empty string if unknown |
| `text` | string | ✅ | Spoken text of the utterance |

**Validation rules**:
- `end_seconds > start_seconds`
- `text` may not be empty (blank lines are excluded during scraping)

---

## TranscriptSchema *(stage output: Capture)*

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | string | ✅ | `"1.0"` |
| `recording_url` | string | ✅ | Canonical (normalised) Zoom viewer URL |
| `captured_at` | string (ISO 8601) | ✅ | Timestamp when the capture session completed |
| `utterances` | `Utterance[]` | ✅ | Ordered list of utterances; empty array if no transcript was available |
| `transcript_unavailable` | boolean | ✅ | `true` if the Zoom transcript panel was absent or empty |

---

## FramesManifest *(stage output: Capture — companion to TranscriptSchema)*

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | string | ✅ | `"1.0"` |
| `recording_url` | string | ✅ | Canonical Zoom viewer URL |
| `frames` | `FrameEntry[]` | ✅ | Ordered list of captured frames |

### FrameEntry

| Field | Type | Required | Description |
|---|---|---|---|
| `timestamp_ms` | integer | ✅ | Playback position in milliseconds when this frame was captured |
| `file_path` | string | ✅ | Relative path to the JPEG file within the cache directory |

---

## SlideOccurrence

Represents one contiguous on-screen appearance of a unique slide.

| Field | Type | Required | Description |
|---|---|---|---|
| `slide_id` | string | ✅ | Stable identifier (e.g., `"s001"`); multiple occurrences share a `slide_id` |
| `start_seconds` | float | ✅ | Playback time when this slide first appeared |
| `end_seconds` | float | ✅ | Playback time when this slide was replaced or recording ended |
| `frame_path` | string | ✅ | Path to the representative frame image for this occurrence |
| `frame_hash` | string | ✅ | 64-bit pHash hex string of the representative frame; used for de-duplication |
| `frame_sha256` | string | ✅ | SHA-256 of the frame image bytes; used as vision model cache key |

**Invariants**:
- All `SlideOccurrence` records sharing a `slide_id` have equal `frame_hash` values
  (within the Hamming threshold).
- `end_seconds > start_seconds`

---

## SlideTimelineSchema *(stage output: Slide Extraction)*

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | string | ✅ | `"1.0"` |
| `recording_url` | string | ✅ | Canonical Zoom viewer URL |
| `slides` | `SlideOccurrence[]` | ✅ | Time-ordered list of slide occurrences |

---

## SlideContent

Extracted information for one unique slide (keyed by `slide_id`).

| Field | Type | Required | Description |
|---|---|---|---|
| `slide_id` | string | ✅ | Matches `slide_id` in `SlideTimelineSchema` |
| `title` | string | ✅ | Slide title; empty string if none detected |
| `bullets` | string[] | ✅ | Bullet point texts in document order; empty array if none |
| `visual_description` | string | ✅ | Plain-language description of charts, diagrams, or images; empty string if text-only |
| `raw_ocr` | string | ✅ | All visible text in reading order |
| `extraction_method` | enum | ✅ | `"vision"` or `"ocr"` — indicates which path produced this content |
| `estimated_cost_usd` | float | ✅ | API cost for this extraction; `0.0` for OCR |

---

## SlideContentSchema *(stage output: Slide Understanding)*

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | string | ✅ | `"1.0"` |
| `recording_url` | string | ✅ | Canonical Zoom viewer URL |
| `total_cost_usd` | float | ✅ | Cumulative API cost for this run's understanding stage |
| `budget_ceiling_usd` | float | ✅ | Budget ceiling that was in effect (from config) |
| `slides` | `SlideContent[]` | ✅ | One entry per unique slide |

---

## AlignedSegment

The pairing of one slide occurrence with the transcript text spoken during it.

| Field | Type | Required | Description |
|---|---|---|---|
| `slide_id` | string or null | ✅ | `null` for the `"general_discussion"` segments (unanchored transcript) |
| `occurrence_index` | integer | ✅ | 0-based index of this occurrence within the slide's appearances |
| `slide_content` | `SlideContent` or null | ✅ | `null` for `"general_discussion"` segments |
| `transcript_text` | string | ✅ | Concatenated utterance text for the slide's time window |
| `duration_seconds` | float | ✅ | Length of this slide's on-screen time |
| `start_seconds` | float | ✅ | Playback position when this segment started |

---

## AlignedSegmentsSchema *(stage output: Synthesis — intermediate)*

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | string | ✅ | `"1.0"` |
| `recording_url` | string | ✅ | Canonical Zoom viewer URL |
| `segments` | `AlignedSegment[]` | ✅ | Time-ordered aligned segments; includes `"general_discussion"` segments |

---

## SummarySchema *(stage output: Synthesis — final)*

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | string | ✅ | `"1.0"` |
| `recording_url` | string | ✅ | Canonical Zoom viewer URL |
| `generated_at` | string (ISO 8601) | ✅ | When the summary was produced |
| `overall_summary` | string | ✅ | 2–5 sentence high-level meeting narrative |
| `per_slide_summaries` | `PerSlideSummary[]` | ✅ | One entry per slide (or general discussion) |
| `action_items` | string[] | ✅ | Extracted action items across the full meeting |
| `decisions` | string[] | ✅ | Key decisions recorded during the meeting |

### PerSlideSummary

| Field | Type | Required | Description |
|---|---|---|---|
| `slide_id` | string or null | ✅ | `null` for general discussion sections |
| `slide_title` | string | ✅ | Slide title or `"General Discussion"` |
| `summary` | string | ✅ | 2–4 sentence summary of discussion during this slide |
| `key_points` | string[] | ✅ | Bullet points of notable statements or facts |

---

## Entity Relationships

```
Recording URL
    │
    ├── CaptureSession ──────────────── FramesManifest
    │       └── TranscriptSchema           └── [FrameEntry, ...]
    │               └── [Utterance, ...]
    │
    ├── SlideTimelineSchema
    │       └── [SlideOccurrence, ...]  ─── groups by slide_id → UniqueSlide concept
    │
    ├── SlideContentSchema
    │       └── [SlideContent, ...]     ─── one per unique slide_id
    │
    ├── AlignedSegmentsSchema
    │       └── [AlignedSegment, ...]   ─── joins SlideOccurrence + Utterance by time
    │
    └── SummarySchema
            ├── overall_summary
            ├── [PerSlideSummary, ...]
            ├── action_items
            └── decisions
```

All entities are keyed by the canonical `recording_url`. Stage outputs reference
the `recording_url` explicitly to make cross-stage provenance unambiguous.
