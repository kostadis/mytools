# Bulk searchable Markdown beside selected PDFs

Status: proposed design for user approval. This document authorizes no implementation or library-wide conversion by itself.

## Purpose and agreed requirements

Make the RPG library useful for content creation by converting eligible PDFs to searchable Markdown across all game systems. The four-document native-text pilot established the extraction and resume path; this extension publishes the resulting documents where the user wants to keep them.

The user decided:

- Markdown lives beside the selected PDF, with an explicit pointer to that PDF inside the document.
- Any successfully extracted nonempty document is useful enough to publish. Sparse text, blank pages, font substitutions and layout issues are recorded and do not block inclusion.
- Each directory has a record identifying its current PDF/Markdown pairs, conversion status and why each PDF was selected. A directory may contain multiple distinct works.
- Historical conversion and a separate historical search database are deferred.
- Assume Google Drive is available. Use an integrated conversion/publication workflow; no separate offline publishing operation is needed.

The existing internal-date selection policy, review authority, baseline protection, whole-component gates and five-page selection-inspection limit continue unchanged. Full conversion reads every page of a selected PDF. Archives, OCR, layout reconstruction, model-based quality gates and 5etools encoding remain later work.

## Existing system and what changes

The Rust `rpg-source-select` binary already creates an additive frozen Ready queue and converts it with two isolated workers, 20-page native-text ranges, verified source staging, checksummed range checkpoints and full-completion attestations. The coordinator owns SQLite writes and publication. It publishes complete local artifacts and a current corpus view; the pilot covered four documents and 61 physical pages.

Today `export::validate_work_dir` deliberately keeps managed output outside the source tree, and `markdown::publication` publishes only under that private output root. Source-adjacent publication therefore needs a specific new coordinator-owned destination. Keep working state, source caches, range caches, full JSON page sidecars and immutable artifacts outside the PDF library. Do not weaken the general work-directory guard or let worker jobs write into source directories.

References: [existing design](2026-11-23-searchable-markdown-design.md), [operator instructions](../../searchable-markdown.md), [pilot evidence](../../markdown-pilot-01.md). Root and project `CLAUDE.md` guidance still applies; established Dungeon Masters Guild output remains protected.

## Approaches considered

1. **Integrated publication:** as each full conversion completes, the coordinator writes Markdown beside its selected PDF and updates the directory record. This is the recommended approach accepted in the conversation after the user specified that Drive should be assumed available. It adds source-directory writes to the existing pipeline and needs recoverable per-directory publication.
2. **Separate publication command:** finish local conversion first, then run another operation to copy documents and update records. It separates conversion from destination availability but adds an operational step the user does not need under the agreed assumption.

Use approach 1. Checkpointing and ordinary error recovery remain useful for interrupted processes and write failures; they do not introduce an offline mode or another user approval step.

## Source-adjacent document contract

For `Bad_Decisions_Color_print.pdf`, publish `Bad_Decisions_Color_print.md` in the same directory. Derive the name from the actual selected PDF's exact filename stem. Do not write beside every byte alias or skipped older candidate.

Each Markdown document contains:

- A visible clickable relative link to its PDF, constructed from the sibling filename with URI-safe escaping.
- Byte-safe source filename provenance, source SHA-256, work/source IDs, extraction time, selection snapshot/policy/basis and the selected internal date in front matter.
- Converter identity and quality findings, with full provenance and raw page data retained in the private JSON artifact.
- One heading for every physical PDF page, the existing literal escaped native text, and an explicit no-native-text marker for empty pages.

Preserve Unix filename bytes using the existing path serialization convention. A display string is not an identity. The local corpus copy must use a link appropriate to its location; copying a sibling-only link unchanged into another directory would point at the wrong PDF. The builder may choose target-specific rendering or a second correctly escaped source link.

If distinct selected PDFs derive the same Markdown destination, report a destination conflict and keep them pending. Do not silently choose a different selected source or overwrite a conflicting file.

## Directory record

The user-facing filename is `current-documents.json`, placed in the directory that directly contains the selected PDF. Entries use sibling filenames, not arbitrary paths elsewhere in the tree. Multiple works can have separate current entries.

Illustrative shape; placeholders below represent full actual hashes and IDs:

```json
{
  "schema_version": 1,
  "generator": "rpg-source-select",
  "selection_id": "selection-snapshot-id",
  "reconciliation_status": "complete",
  "updated_at": "2026-11-23T20:00:00Z",
  "documents": [
    {
      "generator": "rpg-source-select",
      "work_id": "work-id",
      "source_id": "source-id",
      "selection_id": "selection-snapshot-id",
      "pdf": "Bad_Decisions_Color_print.pdf",
      "pdf_sha256": "full-source-sha256",
      "markdown": "Bad_Decisions_Color_print.md",
      "markdown_sha256": "full-published-markdown-sha256",
      "status": "published",
      "selection_basis": "most_recent_internal_date"
    }
  ]
}
```

The minimum identity/status fields above implement the agreed directory record. The per-entry generator and selection ID, plus reconciliation status, are designer-proposed bookkeeping to distinguish owned entries and incomplete updates. Add an optional attributed effective internal date, compact quality findings and a diagnostic error for non-published entries. Those are implementation proposals, not new selection authority. Use the actual stored selection basis rather than substituting the illustrative value.

The record identifies selected PDFs before they finish conversion. Status differentiates `pending`, `published`, `needs_ocr_or_visual_review`, `failed`, `source_changed` and `output_conflict`. `markdown_sha256` is absent until matching bytes have actually been published. A target filename alone does not establish completion. Quality flags do not change `published` into a hold.

Records describe current entries, not a conversion history. Known managed directories whose selected works are authoritatively shown to disappear, move or become deferred are reconciled as part of applying the complete latest selection. Remove those managed current entries without deleting their PDFs or Markdown files. An empty managed record is valid and prevents an old selection from continuing to claim currency. Incomplete coverage is handled separately below and is not proof of disappearance.

## Publication and ownership

Only the coordinator publishes. Under the existing selection/coordinator locking discipline, reconcile directory records against the complete newest snapshot, not only the `--limit` batch prefix. Reuse extracted pages whose source and compatible converter contract still match, and retain unchanged published bytes when all their embedded assembly metadata also matches. Mark newly selected or invalidated work pending. A late old worker may provide cached text but cannot publish a source no longer selected.

When a newer snapshot reconfirms the same PDF, the published document and its manifest entry must cite that latest snapshot, basis and effective date. Reassemble from cached pages when those embedded fields change, without repeating extraction. Preserve the actual extraction timestamp across assembly-only updates; publication time is separate. Repeating publication for the same snapshot/rendering must not introduce new timestamps merely to rewrite identical files. This continues the existing policy-only reassembly contract.

For each completed, nonempty book:

1. Validate full coverage and completion attestation using the existing extraction contract.
2. Resolve the selected source and destination within the expected real source directory, rejecting traversal and redirected symlink writes. Verify that the accessible PDF still matches the frozen selected hash.
3. Check destination ownership and render the source-adjacent Markdown with its source link and metadata.
4. Persist a recoverable publication intent locally, binding destination identity, source/work/snapshot, intended Markdown checksum and prior directory-record state.
5. Write a uniquely named temporary Markdown in the destination directory, flush it and atomically rename it into place.
6. Recheck latest selection/source validity as needed before committing the directory record. Atomically replace the record only after the published Markdown bytes exist and match its checksum. The record is the per-directory publication commit point.
7. Complete the local publication journal and refresh the local current view from confirmed current publications.

A Markdown file and a directory record cannot be renamed atomically as one transaction. Before the record commits, current readers must treat new Markdown as uncommitted, and validate the old record's checksum if its target was replaced. On rerun, the intent and expected checksums let the coordinator finish or repair interrupted publication without re-extracting PDF pages. An interrupted reconciliation remains visible as pending; do not claim whole-library atomicity across independent directories. A run is fully reconciled only after all known affected directory records have been processed.

Ownership rules are conservative defaults proposed by the designer:

- Never modify PDF bytes.
- Preserve existing Markdown unless a prior owned manifest entry, durable checksum receipt or recoverable publication intent proves ownership of the exact file and its current checksum. If a user edited a managed file, report a conflict and preserve it.
- Keep durable private ownership receipts keyed by source-root identity and byte-safe destination, recording the exact previously published checksum and owning work/source. These receipts survive removal or replacement of current manifest entries. They permit normal A-to-B-to-A reselection and replacement at the same filename when the existing Markdown still matches an owned checksum. During pending publication retain that prior proof privately; do not treat the new PDF hash as proof of ownership of old Markdown.
- After private-state loss, current recognized owned manifest entries can reestablish their exact checksum receipts. If an unlisted older Markdown has no surviving receipt or recoverable intent, preserve it as an output conflict. Its front matter alone is insufficient proof that it was not edited. This conservative recovery limitation is intentional; it does not add historical search to this milestone.
- Preserve an existing unrecognized, invalid or newer-schema `current-documents.json`; report a directory conflict and skip publishing that directory while other directories continue. Do not adopt it merely because its name matches.
- Merge the recognized manifest's entries explicitly owned by `rpg-source-select`; preserve entries with another or absent entry generator as uninterpreted data and exclude them from this tool's current view. Interpret only supported owned schema; reject unsafe paths even in owned records.
- A source/output mismatch or ownership conflict never triggers automatic source substitution, deletion or a prompt for each PDF. Report it for later resolution.

The exact local journal schema, checksum helper reuse and lock granularity are left to the builder. Recovery and ownership behavior above are required outcomes. Flush/rename support must be verified on the actual mounted filesystem; do not claim Drive-client synchronization is an atomic transaction across machines.

## Current search and deferred history

The current collection is defined by successfully published current manifest entries whose identities/checksums match the latest selected works. The existing local `corpus/current/books` view remains a convenient ordinary-file search view and should mirror those confirmed publications in this mode. Private immutable artifacts remain available as conversion evidence.

Directory records are portable inputs for a future indexer. This milestone does not create or configure a separate search database. Rebuilding current state from recognized directory records must not rely solely on a private cache surviving. Identify affected directories from the latest inventory, prior managed publication records, and an independent read-only discovery of `current-documents.json` throughout the configured source root. Discovery must include directories with no remaining PDFs, while rejecting symlink traversal and recording inaccessible paths. That allows an old owned record to be reconciled even after its last PDF moved and local state was lost. The builder may combine this discovery with an inventory walk, but PDF-only inventory is insufficient.

Treat inventory coverage errors and manifest-discovery coverage errors as uncertainty, not disappearance. Publish verified eligible works and reconcile positively known changes in accessible directories. Do not delete a prior entry just because its work is missing under incomplete coverage. Retain such an entry with its prior per-entry selection ID and report it as unverified for the latest snapshot, listing unresolved entries under a partial reconciliation diagnostic. The record's top-level selection ID identifies the attempted reconciliation; it does not upgrade older entries to current authority. A directory or run is `complete` only when the relevant inventory/discovery coverage is clean and every known affected owned entry has been reconciled.

Only entries positively matched to the latest selection and verified source/output checksums enter a new current corpus generation. Retained uncertain older entries stay out of that generation and remain reported as unresolved, not obsolete. If no new confirmed current content can publish, preserve the last good local view and explicitly report its published snapshot, the attempted latest snapshot, partial coverage and pending reconciliation. This uses the existing last-good-view behavior without interpreting missing access as an empty library.

When selection changes, leave previous Markdown physically beside its PDF, but omit it from current entries and the current search view. No older-alternative conversion, historical indexing, migration, or deletion is required. A raw recursive search over every `.md` file does not apply current selection; current-only search uses the managed corpus view or manifest-aware consumers.

## Bulk operation

Continue using a completed scan and the additive metadata-selected queue across all game systems. Keep the existing safe selection gates; deferred groups do not block Ready work. Do not run write stages against the broad scan's live database.

Designer-proposed CLI compatibility choice: retain the existing private-output default and add an explicit destination option such as `markdown-convert --publish-next-to-source`. The user's normal bulk invocation supplies that option and performs conversion plus adjacent publication in one command. This avoids changing existing callers' library-write behavior. It is not a separate publishing command or interactive permission gate. Exact naming is left to the builder.

Keep the default two workers, 20-page chunks, bounded retries and local checkpoints. Only ready selected PDFs are converted; exact aliases reuse bytes. `--limit` bounds runnable conversion work, while reconciliation applies the full snapshot. Nonempty full extraction publishes despite quality issues; all-empty extraction records the OCR/visual outcome without an empty successful Markdown; failed ranges remain resumable and no partial book is published.

Retain worker logs, job results, explicit failure states and the 30-second heartbeat. Add source-adjacent publication and reconciliation counts/errors to the run report. During long metadata/selection and directory-reconciliation work, preserve progress in local state and provide summaries at least every 100 files/directories plus a heartbeat during long individual operations. Failures in one book or directory do not suppress successful independent directories.

## Validation and rollout

Implement in Rust by extending the existing subsystem. Exercise an isolated directory tree first, using the four proven documents or controlled PDF fixtures. Verify actual source-adjacent files and manifests, then repeat to prove no unnecessary extraction or rewriting of unchanged published bytes. Also verify:

- Several distinct works in one directory; selected-only alias handling; nested directories and byte-safe/special-character filenames and links.
- Nonempty sparse/blank-page books publish; all-empty and failed books have accurate records and no claimed successful Markdown.
- Existing/manual/edited Markdown, unrecognized records, destination collisions, protected baseline material and unrelated directory entries remain intact.
- A bounded batch retains previously published compatible work; an updated or deferred selection invalidates obsolete current entries without deleting files.
- A-to-B-to-A and same-filename revisions retain ownership proof; loss of private state recovers proof from recognized current records and preserves unlisted files whose ownership cannot be established.
- Independent manifest discovery finds a stale record after the directory's last PDF moved; incomplete scan/discovery coverage does not falsely clear missing works or claim complete reconciliation.
- A new snapshot for the same PDF refreshes selection provenance from cached text, preserves extraction time and performs no redundant rewrite when the snapshot/rendering is unchanged.
- Stale workers, a changed source and source moves cannot restore an old current entry.
- Interruptions before/after the Markdown rename and before/after record replacement recover using checksums/intents. Corrupt outputs are repaired only when ownership permits; user edits remain conflicts.
- Directory failures stay isolated, and the local current view contains only confirmed current source-adjacent publications. Existing local-only operation and legacy selection exports still pass their checks.

After implementation verification, a separate explicitly requested bulk run can apply this to the real eligible library. This design does not start that run or alter existing library files. Full-library throughput is measured during rollout; OCR/layout improvement and historical search remain deferred.

## Designer calls for review

- Use exact PDF-stem `.md` naming and a versioned `current-documents.json` with multiple work entries.
- Preserve unrecognized or user-edited output and report conflicts; leave obsolete generated Markdown in place but outside current entries.
- Keep private caches/artifacts outside the library and preserve existing CLI behavior with an explicit adjacent-publication destination option.
- Use per-directory atomic record commits plus a local recovery intent, with no claim of cross-directory or cross-machine atomicity.
- Retain the local current corpus as a mirror of confirmed current files; defer a new search database and historical indexing.
- Retain private checksum ownership receipts after current-entry removal; preserve unlisted Markdown as a conflict if those receipts are lost.
- Discover manifests even in directories with no PDFs, and treat incomplete coverage as partial reconciliation rather than proof that a work disappeared.
- Refresh embedded selection provenance on a new snapshot using cached extraction, keeping extraction time distinct from publication time.

These choices are proposals within the agreed workflow. The builder may settle implementation details that do not change these behaviors.

## Builder check

A fresh Sol builder check identified four questions about durable ownership, discovery of emptied directories, incomplete scan coverage and refreshed provenance. The designer resolved them in the explicit contracts above. None requires a new user preference to plan the agreed workflow; the conservative defaults and their recovery limitation are listed for review. This remains a proposed design, awaiting user approval before an implementation plan.
