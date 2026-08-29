---
name: UI review — Phase 2 & Phase 3 plan
description: Remaining Streamlit UI fixes from the clarity/consistency/best-practices review (consolidation + UX polish)
type: project
---

## Phase 2 — Consolidate shared logic

**Issue 4 — Duplicated session-dir populate logic**
`_populate_from_session_dir()` was created in Phase 1 by merging three functions. Remaining work: the auto-detection logic (VTT file, GM recap, session summary, roleplay summary) now lives in one place but the filename lists should be reviewed for completeness. `session_clean.md` was in `_sd_populate_from_dir` but not the others — verify unified function covers all variants.
**Why:** Three near-identical functions drifted apart over time, causing inconsistent file detection across pages.
**How to apply:** Verify `_populate_from_session_dir` handles all filename variants. No further structural work needed after Phase 1.

**Issue 8 — Inconsistent chunk_size handling**
Four pages conditionally add `--chunk-size` only when non-default (e.g. `if chunk_size != 60000`), three always add it unconditionally. Pick one pattern and apply everywhere.
- Conditional: `page_distill`, `page_party`, `page_planning` (×2)
- Unconditional: `page_campaign_state`, `page_query`, `page_vtt_summary`
**Why:** Inconsistency is confusing when maintaining the code.
**How to apply:** Always appending is simpler — the CLI default handles it either way. Standardize on unconditional.

**Issue 12 — `multi_path_field` pattern**
Fixed in Phase 1 (pre-seed session_state, drop `value=`). No remaining work.

**Issue 14 — Repeated command-building pattern**
Every page builds a `cmd` list with the same conditional-append boilerplate. Optional: extract a small helper, e.g.:
```python
def cmd_opt(cmd, flag, value):
    if value:
        cmd += [flag, str(value)]
```
Or a `CmdBuilder` class with `add_opt("--flag", value)` and `add_flag("--no-log", bool)`.
**Why:** ~12 pages duplicate the same `if value: cmd += [...]` pattern.
**How to apply:** Low priority — only do this if touching most pages for another reason.

---

## Phase 3 — UX polish

**Issue 6 — `config_buttons()` on every page**
Load/Save config buttons appear at the top of all 16 pages. Auto-save already happens on Run (`run_panel` calls `save_ui_config_from_session()`). These are power-user controls.
**Why:** Clutter — takes prime screen real estate on every page.
**How to apply:** Remove `config_buttons()` from individual pages. Keep Save inside `run_panel`. Add a single Load/Save pair to the Settings page or sidebar.

**Issue 7 — Duplicate editable fields across pages**
These fields appear editable on both Session Config and downstream pages (they share `key=` so they stay in sync, but it's confusing):
- `vtt_date`, `vtt_session_name` — Session Config + VTT page
- `sd_characters` — Session Config + Extract page + Editor page
- `vtt_context` / `sd_context` — Session Config + VTT page + Editor page
**Why:** Users see the same field on multiple pages and don't know which is authoritative.
**How to apply:** On downstream pages, show shared values as read-only `st.info("Characters: ...  — change on Session Config")`. Only render the editable widget on Session Config.

**Issue 9 — Model selector has no visible label**
The sidebar model selectbox uses `label_visibility="collapsed"`. No visible label or section header.
**Why:** Fine for debug UI, unclear for primary interface.
**How to apply:** Add `st.caption("MODEL")` above it, or set `label_visibility="visible"`.

**Issue 13 — Run button not disabled when required fields empty**
`run_panel` always shows an enabled Run button. Some pages compute `ready` (e.g. `page_session_doc_extract`) but don't pass it through. The subprocess fails with an unhelpful error.
**Why:** Bad UX — user clicks Run, gets a cryptic subprocess error.
**How to apply:** Add a `ready: bool = True` parameter to `run_panel`. Disable the button when `ready=False`. Pages that already compute `ready` can pass it in.

**Issue 15 — "Experimental" label too discouraging**
NAV_GROUPS label is "EXPERIMENTAL" for Session Narrative and Enhance Recap. The Workflow Guide says "They work but are not as reliable."
**Why:** Deters users from trying working tools.
**How to apply:** Rename to "ALTERNATIVE WORKFLOWS" or "ADVANCED". Soften the guide text.
