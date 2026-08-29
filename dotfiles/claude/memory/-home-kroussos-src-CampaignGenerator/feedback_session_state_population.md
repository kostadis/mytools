---
name: Session state population pattern
description: How shared state (session directory, derived paths) enters the app — two-route bug and the fix
type: feedback
---

State enters the app via two routes:
1. `ui_config.yaml` pre-populates widget keys at startup via `apply_ui_config_defaults`
2. The user types into a field on Session Config, VTT Summary, or another page

**Bug 1 — empty saves clobber mapped defaults:** `save_ui_config_from_session()` persists ALL session_state keys, including empty strings. On next load, `cfg.get(key, val)` returns the saved `""` instead of the mapped config default (e.g., `session_doc_session_dir`). Fix: use `cfg.get(key) or val` so empty saved values fall through to the mapped default.

**Bug 2 — callbacks don't fire on load:** Streamlit `on_change` callbacks only fire on user interaction, not when values are loaded from YAML. So derived paths (`sd_extract_dir`, `sd_session`, etc.) may be missing even when the parent key (`sd_session_dir`) is present. Fix: at the top of each page function, re-derive paths if the session dir is set but a derived field is empty:

```python
if not st.session_state.get("sd_session_dir"):
    for _src in ("sw_session_dir", "vtt_session_dir"):
        if st.session_state.get(_src):
            st.session_state["sd_session_dir"] = st.session_state[_src]
            break
if st.session_state.get("sd_session_dir") and not st.session_state.get("sd_extract_dir"):
    _sd_populate_from_dir()
```

**How to apply:** Watch for both bugs when adding new pages or new shared fields. Any widget key that gets saved to YAML must not block a mapped config default when empty. Any derived-path chain must re-derive at page load, not rely solely on callbacks.
