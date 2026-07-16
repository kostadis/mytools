---
name: Web UI usage pattern
description: CampaignGenerator's web UI has one user; pages are used one at a time, not in parallel. Session Config is revisited often within a session.
type: project
originSessionId: 5cd1f67f-a609-4753-8709-037e343f794b
---
The CampaignGenerator web UI is single-user (Kostadis only) and used one page at a time — never multiple tabs, never two pages open in parallel.

**Why:** Confirmed by the user during bug triage of `SessionConfig.vue`'s mount-timing race (2026-05-03). Frames severity for any class of bug that depends on concurrent state across pages or fast navigation between them.

**How to apply:**

- Race conditions and "if you click X then Y in 200ms" bugs are mostly theoretical — don't burn cycles fixing them unless the workflow forces the trigger pattern.
- "11 pages have empty forms on second visit" is a low-priority cosmetic issue when the pages are read-only or have no save path; the user just retypes or reloads.
- BUT — **Session Config gets revisited frequently within a single browser session**, so any bug on that page that triggers on revisit is real and worth fixing. Same heuristic applies if you find another page that's used the same way.
- When triaging a UI bug, ask "does this manifest in normal one-page-at-a-time usage on a single browser tab?" before estimating effort. If the answer is no, downgrade severity.
- Data-loss bugs are still worth fixing even when rare, because the user has no undo for `ui_config.yaml`.
