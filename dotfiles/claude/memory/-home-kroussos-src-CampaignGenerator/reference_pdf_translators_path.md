---
name: reference-pdf-translators-path
description: Canonical filesystem location of pdf-translators (the PDF → 5etools JSON converter that fivetools_ingest.py and convert_book.py call into)
metadata: 
  node_type: memory
  type: reference
  originSessionId: 2f87ff81-fffd-4fa9-992f-c366fe307be8
---

`pdf-translators` lives at `~/src/mytools/pdf-translators/` — that's the canonical checkout for `adventure_model.py`, `pdf_to_5etools_v2.py`, the editors (`adventure_editor`, `toc_editor`, `monster_editor`), etc.

Stale copies that you may find on disk and should ignore:
- `~/src/5etools-kostadis/pdf-translators/` — has a leftover `__pycache__/adventure_model.cpython-312.pyc` but no `.py` source; was the historic default
- `~/src/5etools-src/pdf-translators/` — older copy with API drift (e.g. exposes `ValidationMode` only, no `ErrorMode`)

The `--pdf-translators` defaults in `fivetools_ingest.py` and `convert_book.py` were updated to point at `~/src/mytools/pdf-translators/` (the bookData-shape patch branch). If you see them pointing somewhere else in the future, that's a regression.

Note: `_DEFAULT_FIVETOOLS_DATA_ROOT` in `fivetools_ingest.py` points at `~/src/5etools-kostadis/data/` and is correct — that's the 5etools data tree (bestiary-mm.json, spells-phb.json, …), a different concept from pdf-translators.
