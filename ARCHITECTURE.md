# mytools — Architecture

_Generated 2026-07-05 from a full codebase-memory graph index (11,242 nodes / 27,940 edges; 219 Python, 29 Rust, 15 Vue, 13 TypeScript files). A machine-readable copy is persisted in the codebase-memory ADR store (`manage_adr(mode='get')`)._

## What this repo is

A **multi-project personal tools monorepo** — not a single application. Each top-level directory is an independent project with its own dependencies, entry points, and (often) its own `CLAUDE.md`/`ARCHITECTURE.md`. There is no shared build, no top-level virtualenv, and almost no cross-project imports. The call graph confirms this: clusters align strongly with top-level folders, and cross-folder edges are dominated by tests→src within each project.

The one shared-library exception is `claudelib/claudelib.py` — a generic Anthropic API wrapper with retry logic (rate limits, server errors, timeouts), packaged via `pyproject.toml` for reuse across projects.

## Project inventory (by theme)

### RPG tooling (the largest theme)

- **`pdf-translators/`** — the biggest and most active project (~40% of graph nodes). Converts RPG PDFs to 5etools homebrew JSON.
  - *Pipeline core:* `pdf_to_5etools_v2.py` (pure entry layer, only outbound calls) → `app.py` (core; `Job.append` is the #2 hotspot in the repo with fan-in 202) → `claude_api.py` / `llm_backend.py` (LLM backends) → `extract_monsters.py`, `extract_markdown.py`.
  - *Batch layer:* `batch_convert.py` (`parse_args` fan-in 51) + `batch_state.py` (`StateDB`, SQLite state; `close` fan-in 76) + `batch_marker.py` / `batch_mistral_ocr.py` (OCR routes: Marker for scans, Mistral OCR).
  - *Editors:* multiple small Flask editor apps — `toc_editor.py`, `adventure_editor.py`, `toc_fixer.py`, `markdown_editor.py`, `monster_editor.py`, `probe_editor.py` — each serving `/api/load`, `/api/save`, `/api/undolog/*` style routes.
  - *Frontend:* `frontend/` Vite/Vue 3 SPA (Pinia store `stores/editor.ts`) that HTTP-calls the Flask editor backends (confirmed graph edge: `editor.ts save()` → `toc_editor.py /api/save`).
  - *Rust:* `adventure_model_minimal/` — Rust crate with PyO3 bindings (`pybindings.rs`) for the adventure data model + validation (`ValidationResult::new` fan-in 40); Python shim `adventure_model_rust.py`.
- **`rpg-lib/`** — full-stack RPG PDF library. `pdf_indexer.py` + `pdf_enricher.py` (Claude API) → SQLite; FastAPI backend `library_api/` (routes: `/search`, `/search/facets`, `/books`, `/resolve`, `/book/{id}`, favorites, `/filters`, `/stats`; `resolve` fan-in 34, `search` fan-in 32) + Vue 3 SPA `frontend/`. Also `library_mcp.py` (MCP server) and Obsidian/wiki generators. Start/stop only via `./service.sh`.
- **`flexai-combat/`** (port 5106) and **`flexai-social/`** (port 5105) — twin Flask GM tools implementing FlexAI rules; each is a single `app.py` + rules-engine module + tests. Structurally isolated from everything else.
- **`rpg-bot-ui/`** — static D&D class/spell-builder HTML pages + Flask `app.py` server + `class_extractor/` and `spell_extractor/` (config-driven HTML/text parsers feeding `data/*.json`).
- **`vtt-to-tts/`** — single script `transcript_to_mp3.py` (Zoom VTT → per-speaker edge-tts MP3, chunk cache).
- **`zoomscrape/`** — two Node scripts (`scrape.js`/`download.js`) for Zoom recordings.

### Cloud-drive tooling (three generations, coexisting)

- **`gdrive/`** — Python scripts, two parallel stacks: Google Drive (`auth.py`, `dupes.py`, `move.py`, `scan.py`, `trash.py`) and OneDrive via Microsoft Graph (`onedrive_*.py` prefix convention). All leaf scripts (fan-in 0) — independent CLIs, not a library.
- **`gdrive-cli/`** — Rust rewrite (`src/auth/{google,onedrive}.rs`, `src/onedrive/{scan,dupes,move_file,trash}.rs`). Forms its own high-cohesion call cluster (0.76).
- **`drive-tagger/`** — Python Drive tagger; its `gdrive.get` is the single highest fan-in symbol in the repo (348) — the choke point for all Drive API access in that project.

### Note/transcript pipeline

- **`notetaker/`** — spec-driven (`.specify/`, `specs/001–005`) Zoom recording → slides/transcript → notes pipeline. `src/notetaker/` with `cli.py` (`run` fan-in 32), `stages/`, `contracts/` (schema classes like `RecordingMetaSchema.write`, fan-in 45), `cache.py`/`cache_ops.py`. Well-tested: contract + integration + unit tiers (the repo's 516 TESTS edges come heavily from here).

### Architectural analysis

- **`kostadis-engine/`** — single-file `index.html` browser tool, no backend/build; streams directly to api.anthropic.com. Hard constraints: vanilla JS only, no external deps, no localStorage, prompts live in `PROMPTS.md` then sync to `LENS_PROMPTS`.
- **`dotfiles/claude/`** — version-controlled Claude Code config: 17 skills (vtt-spell-pass with its dmetaphone matcher — fan-in 40 — dossier-merge, codebase-memory, etc.), agents, plugin marketplaces. The skill scripts are real Python entry points, each with a `main`.

### Other

- **`nutanix/`** — README-only audit scaffold (no code indexed).
- **`ConvertToMarkdown.gs`** — Apps Script, deployed via Sheets, not run locally.

## Structural facts worth knowing (from the graph)

- **Layering inside pdf-translators is clean.** `pdf_to_5etools_v2` and all `test_*` modules are pure entry layers (only outbound calls); `app`, `batch_convert`, `claude_api`, `extract_monsters`, `llm_backend` are core (high fan-in, zero fan-out). Dependency direction: CLI/tests → core → LLM backends.
- **Hotspots** (highest fan-in, riskiest to change): `drive_tagger.gdrive.get` (348), `pdf-translators app.Job.append` (202), `batch_state.StateDB.close` (76), `batch_convert.parse_args` (51), notetaker `RecordingMetaSchema.write` (45), vtt-spell-pass `dmetaphone.match` (40), `adventure_model_minimal ValidationResult::new` (40).
- **Only one real cross-stack HTTP edge:** pdf-translators Vue frontend (`stores/editor.ts`) → Flask editor `/api/*` routes. The other HTTP_CALLS edges in the graph are false positives from test fixtures (file paths misread as URLs) — don't chase them.
- **gdrive scripts are dead-ends by design:** every drive/`onedrive_*` script has module-level fan-in 0 and fan-out 0 — standalone CLIs, not a library. Do not refactor them into one.
- **Web services in the repo:** rpg-lib FastAPI (`service.sh`), pdf-translators Flask editors (`start_editor.sh`/`service.sh`), flexai-combat :5106, flexai-social :5105, rpg-bot-ui `app.py`. Long-running services always start via their `service.sh`.

## Conventions (enforced)

- Per-project dependencies; no monorepo build. Defer to each subdirectory's `CLAUDE.md`.
- `service.sh` for anything long-running — never spawn python directly for rpg-lib / pdf-translators / flexai-*.
- OneDrive code in `gdrive/` follows the `onedrive_*` filename prefix.
- kostadis-engine: no frameworks, no external JS, single file, no localStorage, `PROMPTS.md` is the prompt source of truth.
- Untracked scratch artifacts are expected; don't commit them unprompted.
