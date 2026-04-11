# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

Personal tools repository with three components:

- **`kostadis-engine/`** — Standalone browser-based architectural document analysis tool (no backend, no build system)
- **`ConvertToMarkdown.gs`** — Sheet-bound Google Apps Script that batch-converts Google Docs to Markdown files in Drive
- **`dotfiles/claude/`** — Claude Code configuration: settings, custom skills, and plugin marketplace

## kostadis-engine

Single-file tool (`index.html`). All HTML, CSS, and JS are inlined — no framework, no npm, no build step.

**To run locally:**
```bash
cd kostadis-engine
python3 -m http.server 8080
# open http://localhost:8080
```
Or open `index.html` directly in a browser.

**Architecture:**
- Direct SSE streaming to `api.anthropic.com/v1/messages` (model: `claude-sonnet-4-20250514`)
- Five lenses: L0 (preprocessor), L1 Tribunal, L2 Anti-Gravity, L3 Lagrange, L4 Value Bridge
- `PROMPTS.md` is the source of truth for all system prompts — edit there first, then sync into `LENS_PROMPTS` in `index.html`
- Markdown rendering is hand-rolled via `renderMarkdown()` — do not add a library

**Hard constraints:**
- No frameworks (vanilla JS only)
- No external JS dependencies (Google Fonts via `@import` is fine)
- Do not split CSS/JS into separate files
- Do not add `localStorage` usage
- Do not change the model

See `kostadis-engine/.claude/CLAUDE.md` for full development instructions including how to add lenses and modify the design system.

## ConvertToMarkdown.gs

Google Apps Script — deploy via Google Sheets (Extensions → Apps Script). No local execution.

**Sheet layout:** Row 1 config (output folder in B1 named range `OUTPUT_FOLDER`), Row 3 headers, Row 4+ data rows with Google Doc URLs in column A.

**Key behaviors:**
- Folder URLs in column A are expanded into individual Doc rows (deduplication via `existingUrls` set)
- Docs are skipped if source `lastModified ≤ lastConverted`
- Output files are saved as `.md` to the Drive folder specified in B1; existing files are trashed before overwrite

## dotfiles/claude

Claude Code configuration files stored here for version control. The `settings.json` sets `"model": "sonnet"`. Custom skills in `dotfiles/claude/skills/` mirror the skills available in the session (tribunal, anti-gravity, lagrange, value-bridge, k-preprocess, k-parallel, k-sequential).
