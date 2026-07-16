---
name: NLQ product_type case mismatch
description: NLQ prompt must use exact lowercase DB vocabulary for product_type, not capitalized English words
type: feedback
originSessionId: cd022ce6-7f43-402a-aadd-a1bc95bf0786
---
The NLQ SYSTEM_PROMPT must use the exact same product_type values stored in the DB (lowercase snake_case: `adventure`, `sourcebook`, `gm_aid`, etc.). Using capitalized English words like `"Adventure"` causes zero results because the SQL WHERE clause is case-sensitive.

**Why:** DB stores product types as lowercase snake_case. The NLQ prompt originally said "use exact values: Adventure, Sourcebook..." which Haiku faithfully echoed back, silently killing all structured product_type filters.

**How to apply:** Whenever adding or modifying a structured filter in the NLQ prompt, verify the vocabulary matches the exact DB-stored values. Also defensively `.lower().replace(" ", "_")` any LLM-returned product_type before using it in a SQL query.
