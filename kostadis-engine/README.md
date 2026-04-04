# Kostadis Engine v10

Architectural document analysis system. Four lenses applied in sequence.

## Lenses

| ID | Name | Purpose |
|---|---|---|
| v10 | Tribunal | Architectural reasoning audit — Scribe vs. Architecturalist |
| AG | Anti-Gravity | Management Gravity analysis — MOID, state locality, orphan reconciliation |
| LG | Lagrange | Constraint transformation — what must be true? coordinate shift |
| VB | Value Bridge | Business translation — board narrative, pain pillars, trap questions |

## Usage

1. Open `index.html` in a browser
2. Enter your Anthropic API key
3. Select which lenses to apply
4. Paste a technical document
5. Run analysis
6. Copy the markdown report

## Files

- `index.html` — standalone tool, no backend required
- `PROMPTS.md` — all four system prompts verbatim (source of truth for Cursor)

## Development

Open the repo in Cursor. All prompts are in `PROMPTS.md`. The tool makes direct streaming calls to `api.anthropic.com/v1/messages` using `claude-sonnet-4-20250514`.
