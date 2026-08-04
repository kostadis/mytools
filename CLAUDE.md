# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

Personal tools repository. Each top-level directory is an independent project with its own dependencies and (where relevant) its own `CLAUDE.md` with deeper guidance. Most projects are oriented around two themes: **tabletop RPG tooling** (PDF library, adventure conversion, GM combat/social aids, transcript narration) and **architectural analysis** (the Kostadis Engine lenses, mirrored as Claude skills).

When working in a subdirectory, defer to that subdirectory's `CLAUDE.md` if one exists — it is the source of truth for that project.

## Top-level layout

### Architectural analysis

- **`kostadis-engine/`** — Standalone browser-based architectural document analysis tool. Single-file `index.html`, no backend, no build. Streams to `api.anthropic.com/v1/messages` directly. Five lenses: L0 preprocessor, L1 Tribunal, L2 Anti-Gravity, L3 Lagrange, L4 Value Bridge. `PROMPTS.md` is the source of truth for system prompts. See `kostadis-engine/.claude/CLAUDE.md`.
- **`dotfiles/claude/`** — Version-controlled Claude Code configuration: `settings.json`, custom skills, plugin marketplace. Skills mirror the engine's lenses (tribunal, anti-gravity, lagrange, value-bridge, k-preprocess, k-parallel, k-sequential) plus campaign helpers (mempalace-campaign, voice-file, style-examples, dossier-merge).

### RPG tooling

- **`rpg-lib/`** — Full-stack RPG PDF library. Python indexer + Claude API enricher → SQLite; FastAPI + Vue 3 SPA on top. Always start/stop the backend via `./service.sh` (never spawn python directly). See `rpg-lib/CLAUDE.md`.
- **`pdf-translators/`** — Converts RPG sourcebook/adventure PDFs to [5etools](https://5e.tools) homebrew JSON. Unified `pdf_to_5etools_v2.py` routes digital PDFs to PyMuPDF and scans/1e modules to Marker; Flask UI on top. See `pdf-translators/CLAUDE.md`.
- **`flexai-combat/`** — Flask GM tool (port 5106) implementing FlexAI for Combat Encounters from the *FlexAI Guidebook* (Infinium Game Studios, 2020), driven by the official Digital Resource Companion workbook. See `flexai-combat/README.md`.
- **`flexai-social/`** — Flask GM tool (port 5105) implementing FlexAI for Social Encounters from the same Guidebook. Pairs with `flexai-combat`. See `flexai-social/README.md`.
- **`vtt-to-tts/`** — Single script (`transcript_to_mp3.py`) that converts a Zoom closed-caption transcript into an MP3 with per-speaker `edge-tts` voices. No API key required. Caches chunks next to the output for incremental regeneration.
- **`md-to-vtt/`** — Single script (`md_transcript_to_vtt.py`, stdlib only) that converts a speaker-labelled Zoom `.md` transcript (`**dave:** …`) into WebVTT, so CampaignGenerator's `enhance_summary`/`scene_extract` can read it — they glob `*.vtt` only, and the whisper-derived VTTs carry no speaker labels. Timestamps are synthetic; the payload is `speaker: text`. See `md-to-vtt/README.md` for the pipeline gotchas (NOTE-block leakage, doubled Zoom transcripts, `--max-tokens 30000`).

### Cloud-drive and document tooling

- **`gdrive/`** — Personal tools against Google Drive and OneDrive APIs (despite the name). Two parallel stacks: Drive (`auth.py`, `dupes.py`, `move.py`, …) and OneDrive (`onedrive_*.py`) via Microsoft Graph. New OneDrive code follows the `onedrive_*` prefix convention. See `gdrive/CLAUDE.md`.
- **`ConvertToMarkdown.gs`** — Sheet-bound Google Apps Script that batch-converts Google Docs to Markdown in Drive. Deploy via Sheets (Extensions → Apps Script); no local execution. Sheet layout: B1 = `OUTPUT_FOLDER` named range, row 3 headers, row 4+ data rows with Doc URLs in column A. Folder URLs in column A are expanded; Docs are skipped if `lastModified ≤ lastConverted`.

### Vendor / external API analysis

- **`nutanix/`** — Local-only audit of Nutanix v4 OpenAPI specs. Not an SDK. Pipeline: fetch specs → validate → generate clients → diff against official SDK → write `REPORT/`. Every claim in the report must trace to a verifiable artifact. See `nutanix/README.md`.

### Shared

- **`lib/claudelib.py`** — Generic Anthropic Claude API wrapper with retry logic (rate limits, server errors, timeouts). Extracted from CampaignGenerator's `campaignlib.py` for reuse across projects in this repo.

## kostadis-engine — hard constraints

Repeated here because they are easy to violate:

- No frameworks (vanilla JS only)
- No external JS dependencies (Google Fonts via `@import` is fine)
- Do not split CSS/JS into separate files
- Do not add `localStorage` usage
- Do not change the model
- Edit prompts in `PROMPTS.md` first, then sync into `LENS_PROMPTS` in `index.html`

## Conventions across the repo

- Each project owns its own `requirements.txt` / dependencies. There is no top-level virtualenv or monorepo build.
- Long-running services (`rpg-lib`, `pdf-translators`, `flexai-*`) ship a `service.sh`; use it rather than spawning Python directly.
- Untracked working artifacts (rollback TSVs, `__pycache__/`, scratch dirs) are expected — do not commit them without being asked.
