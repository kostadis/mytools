---
name: No automatic search triggers
description: User wants search to fire only on explicit button press or Enter, never automatically
type: feedback
originSessionId: fca993f6-88a6-422e-bb8f-460be6969a3c
---
Never add live/debounced search or automatic filter-triggered search to this library UI. Search fires **only** on explicit button click or Enter key press.

**Why:** User prefers this interaction model (old-school Google style), and with the size of the dataset, automatic re-searching on every keystroke or filter change is annoying.

**How to apply:** Any UX recommendation suggesting debounced input, live filtering, or removing the Search button should be declined for the text search inputs. Filter dropdowns (`@change`) already trigger search immediately and that's acceptable — the restriction is specifically on free-text inputs.
