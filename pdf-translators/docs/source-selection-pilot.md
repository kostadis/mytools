# Source-selection pilot status

The Rust implementation was exercised against a bounded real-source sample: the six PDF files in *Empire Builder Kit — Street & Road Names*. The scan formed one candidate group. It did not use filename versions or timestamps to decide which copy was current.

The mounted files returned `Permission denied` on content reads. A separate read-only `pdfinfo` probe of a Dragonbane PDF also failed outside the sandbox, so this is a mount/file access limitation rather than a PDF parser result.

Observed results:

- Six PDFs inventoried, one candidate group.
- Six source reads refused, zero sources inspected, zero model calls.
- Zero selected sources, zero duplicate/supersession decisions, zero queue entries.
- Unreadable files remain explicit in the manifest; an empty queue is not presented as successful deduplication.

Private logs, SQLite state, and exported manifests are under `/tmp/rpg-source-selection-pilot` and `/tmp/source-selection-handoff` on the implementation host. No originals or existing DM's Guild outputs were changed.

The pilot has **not established real-library deduplication quality**. After read access is available, run the bounded pilot again with Muse's ambiguous groups, a cross-folder twin, distinct bundle works, and a text-bearing play aid. Include the RotDCE version pair as a comparison case without assuming its chronology. Limit the first content-reading pass to ten groups and bring unresolved choices to the user. Keep issue #144 open until the reviewed-list/pilot work is satisfied.
