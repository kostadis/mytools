# Kostadis Engine — Claude Code Project Instructions

## What This Project Is

A standalone architectural document analysis tool. The user pastes a technical document, selects one or more analytical lenses, and receives a structured verdict. No backend, no framework, no build system.

## Architecture

Single file: `index.html`
- All HTML, CSS, and JS in one file
- Direct streaming calls to `api.anthropic.com/v1/messages`
- No Node.js, no npm, no bundler
- Open in any browser — it just works

Supporting files:
- `PROMPTS.md` — source of truth for all four system prompts (edit here first, then sync to index.html)
- `README.md` — usage overview

## The Four Lenses

| ID | Name | Purpose |
|---|---|---|
| l1 | Tribunal (v10) | Architectural reasoning audit — does the author think in systems or scripts? |
| l2 | Anti-Gravity (v10.1) | Management Gravity analysis — MOID, state locality, orphan reconciliation |
| l3 | Lagrange | Constraint transformation — what hidden assumption makes this hard? |
| l4 | Value Bridge (v1) | Business translation — board narrative, pain pillars, SE trap questions |

The four lenses run in sequence. Each lens produces a structured markdown section. Output is streamed and rendered inline.

## Developer Preferences

- **No frameworks.** Vanilla JS only. No React, Vue, Svelte, etc.
- **No build step.** The file must be openable by double-clicking.
- **No external dependencies** except Google Fonts (already loaded via @import).
- **Inline everything.** CSS in `<style>`, JS in `<script>`. Do not split into separate files.
- **Streaming responses.** Always use SSE streaming from the Anthropic API, never batch.
- **Markdown rendering is hand-rolled.** Do not add a markdown library. Extend the existing `renderMarkdown()` function.

## API Details

- Model: `claude-sonnet-4-20250514`
- Endpoint: `https://api.anthropic.com/v1/messages`
- Required header: `anthropic-dangerous-direct-browser-access: true`
- Max tokens: 4000 per lens (can increase if needed)
- API key: entered by user in the UI, never hardcoded

## Design System

Dark terminal aesthetic. CSS variables defined in `:root`:
- `--bg` / `--surface` / `--surface2` — background layers
- `--accent` — gold (#e8c547), used for active state and headers
- `--red` / `--green` / `--blue` — verdict colors
- `--mono` — IBM Plex Mono (all UI labels, code, output)
- `--sans` — IBM Plex Sans (body text)

PASS verdicts render green. FAIL verdicts render red. These are injected by `renderMarkdown()`.

## Common Tasks

**Add a new lens:**
1. Add the system prompt to `PROMPTS.md`
2. Add the prompt string to the `LENS_PROMPTS` object in `index.html`
3. Add a toggle in the sidebar `.lens-list`
4. Add the key to `lensChecks` state object

**Modify a lens prompt:**
1. Edit in `PROMPTS.md` first (source of truth)
2. Sync the change into the corresponding `LENS_PROMPTS[lX]` string in `index.html`

**Change output format:**
- Extend `renderMarkdown()` in the `<script>` block
- Add new CSS rules to the `.md-output` section

**Run locally:**
```bash
cd ~/kostadis-engine
python3 -m http.server 8080
# then open http://localhost:8080
```
Or just open `index.html` directly in a browser.

## What NOT to Do

- Do not add a package.json or npm dependencies
- Do not split CSS/JS into separate files
- Do not add a backend or proxy server
- Do not replace the hand-rolled markdown renderer with a library
- Do not add localStorage usage (not supported in some environments)
- Do not change the model from `claude-sonnet-4-20250514`
