# Date Format Convention (Campaign Chronicles)

## The stamp
In-text dates appear as:

    DD-MM-Tarsakh 1495

- **DD** = day of month (1-31)
- **MM** = month (the MIDDLE number is the month, NOT Tarsakh)
- **Tarsakh** = the Forgotten Realms calendar month name (3rd month). It is a constant label here; the trailing **1495** is the year (DR).

So `07-03-Tarsakh 1495` = Day 7, Tarsakh (month 3), 1495 DR.

## Spelling
- Correct: **Tarsakh** (FR month, T-A-R-S-A-K-H).
- WRONG (user-corrected dyslexia): Taraskh. If found anywhere, fix in one global pass.

## Variants to normalize
- `DD-MM Tarsakh 1495` (space instead of hyphen after MM) — normalize to hyphen form `DD-MM-Tarsakh 1495`.
- Agents may write `sort_date` as `1495-01-DD` (treating Tarsakh as month 01). This is WRONG. Always recompute `sort_date` from the verbatim `date_label` at merge: `DD-MM-Tarsakh 1495` → `1495-MM-DD`.

## Example anchors (non-destructive injection)
Narrative day boundary (own line, BEFORE the turning line):
    <!-- INFERRED DATE: 10-03-Tarsakh 1495 -->

Entity-scan chapter header (trailing line after `## Chapter N:`):
    ## Chapter 44: Victory Lap
    <!-- DATE: 26-03-Tarsakh 1495 → 29-03-Tarsakh 1495 -->

## Month-length caveat
When accumulating inferred dates (no explicit stamps), the in-world month lengths are unspecified. Use a 30-day-month placeholder and STATE it as a caveat — do not present it as canon. Derived month from an ordinal: `m = o//30 + 1; d = o % 30` (with d==0 → previous month, day 30).
