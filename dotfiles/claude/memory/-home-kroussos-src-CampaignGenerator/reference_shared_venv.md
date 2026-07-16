---
name: reference-shared-venv
description: "The single shared Python venv used for CampaignGenerator and sibling projects, and which envs are kept separate"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 865b482f-e334-4fa4-933e-44f97f50ee0d
---

All generic Python work shares one venv: **`~/.venvs/main`** (Python 3.12.3). Activate with `source ~/.venvs/main/bin/activate`.

- `mempalace`, `turbovecdb`, and `notetaker` are installed **editable** in it (→ their `~/src` repos), so source edits take effect live.
- CampaignGenerator has no venv of its own and its `startup` script doesn't pin one — run it with `~/.venvs/main` active. Its deps (anthropic, fastapi, uvicorn, pyyaml, pyperclip, pyvis, aiofiles, mcp) are all installed there.
- `~/worldanvil_pipeline/venv` is a **symlink → `~/.venvs/main`** (that project's scripts use a relative `venv/`).

Kept deliberately **separate** (heavy/pinned deps that would conflict): `~/src/5etools-kostadis/pdf-translators/marker-env` (marker-pdf/surya/transformers OCR stack) and `~/src/mytools/vtt-to-tts/.venv`.

History: consolidated 2026-06-03 from four redundant per-repo venvs (mempalace ×3, notetaker ×1, ~1.5 GB reclaimed), then relocated from `~/worldanvil_pipeline/venv` to the neutral `~/.venvs/main`. To rebuild: recreate venv, `pip install` the frozen non-editable deps, then `pip install -e` mempalace/turbovecdb/notetaker — venvs are not relocatable by copy (absolute paths are baked in).
