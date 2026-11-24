# Continuous selection and searchable Markdown conversion

Status: approved and implemented. The continuous coordinator is deployed against the full library using preserved metadata/extraction checkpoints. See [pilot and rollout verification](../../continuous-markdown-pilot.md).

## Purpose and agreed behavior

Start producing useful Markdown as soon as a complete candidate group has a valid selection. The user wants the searchable library to grow while the rest of the metadata is being checked, rather than waiting for a whole-library Ready list.

Keep the approved source-adjacent behavior: selected PDF-stem Markdown, a source link/hash inside it, `current-documents.json` per directory, all nonempty full extraction included with diagnostics, preservation of manual/edited output, and historical search deferred. Existing internal-date selection, adopted user/Sol authority, exact-alias handling, protected baselines and whole-component gates remain binding. This is still Rust with native extraction; no new external queue service or model calls are needed.

## Current barrier

The full source inventory/group scan has already completed. `selection::select` probes groups one at a time, caches each PDF's raw metadata and verified hash, holds `selection.lock` throughout the pass, and exports a single Ready snapshot only at its end. `markdown-rollout` waits for that lock and then invokes another complete selection before conversion. `conversion::run` also loads its job list once at startup.

Three changes are required together: durable per-group decisions before global completion; a scheduler that consumes newly eligible work; and publication authority that distinguishes unchecked groups from rejected/retired selections. Simply running the current converter beside the current selector does not remove those barriers safely.

References: [source-adjacent design](2026-11-23-source-adjacent-markdown-design.md), [existing native-text design](2026-11-23-searchable-markdown-design.md), [operator workflow](../../searchable-markdown.md).

## Approaches considered

- **Continuous pipeline — chosen:** completed groups make durable jobs eligible immediately; metadata and conversion run concurrently. More coordination is required, but one slow or unexamined group does not prevent unrelated eligible Markdown.
- **Alternating bounded batches:** check a small batch of complete groups, convert their winners, then repeat. Simpler control flow but the two stages keep waiting for each other. The user chose continuous operation instead.

## Run identity and private state

Use the completed inventory and candidate-group graph as the run's known universe. A run identity binds the canonical source root/identity, inventory/group membership and policy version. New files or a regrouped inventory require a new run; reuse compatible metadata and extraction caches. Do not silently grow a live component while judging its earlier members.

Create a private durable streaming ledger using the existing SQLite facilities. One coordinator owns its writes, conversion job state and source-directory publication. Metadata raw/hash caches remain in `metadata.db`, with one metadata worker as writer and WAL-compatible readers. Existing `markdown.db`, page caches, completion attestations, receipts and recovery operations can be reused or migrated rather than discarded. The exact table layout is left to the builder, but it must preserve these independently observable states:

- Group: pending metadata, collecting metadata, resolved selection, deferred, protected baseline, stale/input changed, or terminal metadata error.
- Selected work: queued, staging/extracting, extracted, published, needs OCR/visual review, extraction failed, source changed, or output conflict.
- Run: known groups/sources, groups accounted for, metadata complete, conversions outstanding, publications outstanding and exceptions.

Commit a group's complete resolution and its work eligibility atomically. A crash must not produce a selected work without its source hashes, membership and authority provenance. The queue is derived from durable ledger state, not an in-memory notification. Notifications wake the scheduler; missed/duplicate notifications cannot lose or duplicate work.

## Metadata production and group resolution

Designer default: **one metadata worker process and two conversion workers**. Keep memory/I/O bounded and the existing 20-page extraction ranges. A slow metadata read must not block the coordinator's worker polling or publication.

The metadata worker handles bounded per-PDF requests and never writes source directories or selection authority. Reuse the existing source fingerprint/hash/raw-metadata cache contracts. Results identify the run, source, requested fingerprint and request identity. Cached raw metadata is evidence; it is not itself a current selection decision.

The coordinator collects results for the complete connected group and applies the shared existing selection policy. Refactor the current group-resolution logic for both batch and continuous callers rather than maintaining two policies. A missing/failed competitor is not silently omitted, an alias does not shrink the component boundary, and a partial group cannot become automatically Ready. Adopted independent-work choices beside a hold retain their existing semantics.

At startup, look for cache-complete groups first and resolve them without fresh PDF-content reads when their verified fingerprints still match. Release the first eligible group immediately; do not finish a cache census of the whole library before scheduling conversion. Uncached metadata requests can run while the coordinator continues discovering other cache-complete groups. This is how the already completed part of the current pass becomes useful promptly.

Designer default: a per-PDF metadata deadline of **300 seconds**, with an explicit terminal error/deferred group on exhaustion rather than monopolizing the producer. Preserve successful cache entries, and use the existing explicit-rerun/bounded-failure retry model. A timeout is not evidence that the PDF or its alternatives are obsolete. The builder may implement the deadline using isolated child processes consistent with the existing worker pattern.

## Selection revisions and stale work

Give each group resolution a semantic revision derived from the group/membership, relevant source fingerprints and verified hashes, policy version, date evidence, baseline/ownership evidence and applicable review/evidence/hint inputs. Hash-bound review lineage must participate even after a file rename. Exclude wall-clock timestamps from this semantic identity.

The coordinator rereads applicable current review authority before resolving, dispatching and publishing a work; use main-store revision notifications plus relevant input digests rather than treating scan time as review freshness. A metadata result produced for superseded inputs can populate a compatible byte cache but cannot grant selection authority. Re-evaluate affected groups from cached evidence where possible. If new hints alter component boundaries, invalidate affected work and require the new grouping/run rather than accepting a smaller old component.

Changed fingerprints invalidate the cached observation and require byte verification. If the hash is unchanged, refresh the observation without changing semantic selection identity. If known PDF bytes actually change, they can add or remove exact-byte edges across components: do not grant new authority against the old frozen component. Mark the run `needs_regroup`, stop new authority dispatch/publication, checkpoint and let compatible in-flight cache work finish. Positively invalidated current entries are withdrawn; other already verified publications are retained. A refreshed inventory/group graph starts the next run, reusing compatible metadata/extraction and unchanged group resolutions. This conservative default avoids implementing dynamic graph repair inside the continuous scheduler. Missing/unreadable competitors remain unresolved; do not choose another source merely because a queued source changed. Newly discovered filenames are handled by the next inventory/run. Existing adopted-review protections continue to govern changed memberships and hashes.

Conversion jobs bind the selected source hash, engine contract and the work's selection revision. Before source publication, the coordinator confirms that this revision still selects those bytes and rechecks the group inputs needed to preserve that authority. A late job may finish compatible content-cache work but cannot restore a revoked choice. A user hold or conclusive new selection removes the old work from current authority without deleting its PDF or Markdown.

Supported review/evidence/hint writers and the coordinator share a short main-store authority gate. Stage expensive data and perform long reads outside it. Under the gate, reread relevant authority, verify the expected group revision/last stable source observations, and install the directory record or current-view pointer. A review committed before that gate cannot be bypassed by a stale publication; a review committed after installation is ordered after that publication and triggers prompt withdrawal on the coordinator's next reconciliation. All supported writers must participate, including library-level decision-save/import paths; direct external SQL edits are outside this supported synchronization contract. Drive file changes continue to use the existing observation/no-clobber model, not a claimed cross-client transaction.

## Continuous scheduling and capacity

Keep workers occupied whenever a durable eligible job exists. Do not wait for metadata completion, an arbitrary number of Ready groups, or another entire batch. The existing job leases, process/range timeouts, source staging/hash validation, full-completion attestations and crash recovery remain required. Complete cached extraction is assembled/revalidated rather than extracted again.

Because the total eligible queue is unknown initially, reserve space per job before staging its source. Account for both active workers and already cached source hashes, and retain the existing **20 GiB free-space reserve on the local work volume**. Cover source staging, bounded range checkpoints, metadata-cache growth and artifact/assembly output, not only source PDFs; grow reservations before additional data allocations using bounded/known output sizes. A second job may not double-spend the first job's reservation. Bounded diagnostics/checkpoints needed to record a pause may use the operational reserve; no new bulk data allocation may consume it. Check destination space separately before writing sibling Markdown; destination exhaustion leaves completed extraction cached and publication pending.

If capacity is insufficient, keep work pending with a volume-specific diagnostic and continue smaller work that fits. Once active/runnable work is drained and the remaining work cannot fit, save `capacity_pending` and exit with a retryable status instead of waiting indefinitely or reporting completion. Resume after space is available. Capacity denial does not consume an extraction-failure attempt. The exact durable reservation representation is left to the builder.

The metadata queue is bounded by the known inventory; conversion backlog entries contain identities, not full PDF/text payloads. Keep active process counts bounded. No additional reader models or OCR stage is introduced.

## Scoped source-adjacent publication

Publish each successfully extracted nonempty work promptly, without waiting for metadata elsewhere. Only the coordinator modifies source directories; keep pinned no-follow handles, ownership checks, no-clobber installation and the tested mounted-Drive recovery journal. Full page coverage and empty/sparse diagnostics remain unchanged.

Partial progress needs explicit authority. Directory reconciliation may update or retire only the groups whose complete current resolutions are known, including positively established moves/merges. An unchecked group is pending, not absent or obsolete. Preserve unrelated/unowned entries and previous unresolved managed entries with their prior authority; do not upgrade them to the new run just because another work in the directory finished. A directory containing several works can expose one newly published document while others remain pending.

Retirement proof is explicit:

- A current adopted hold/revocation, positively verified source disappearance/change, or a complete policy resolution assigning no current winner withdraws the corresponding old current claim. A complete date tie/ambiguity is a policy deferral, not proof that older bytes are obsolete; it still grants no current winner.
- Metadata access/parse failures and unchecked groups are unresolved outcomes, not authority to retire a prior claim. Retain the old entry under its prior revision and mark its current-run currency unverified. It does not become a confirmed new-run publication.
- Use recorded group membership/lineage plus exact source IDs/verified hashes for moves/merges/splits. A fully resolved current component can supersede a directly mapped legacy source entry; unmatched predecessor entries across a split/merge wait until all relevant successor components have authoritative resolutions, except for explicit revocation or proven disappearance. Do not infer lineage from a similar title or folder.
- Legacy v1 records with only source/work IDs and checksums establish file ownership, not an invented prior component boundary. Map what exact source identity and the current complete graph prove. If old private lineage is missing and that proof is unavailable, preserve the entry as unverified until a clean inventory/manifest-discovery reconciliation establishes its fate. No file deletion is required.

Version the manifest/ledger format to express run identity, per-entry group/work identity and selection revision, and local group coverage. A publisher must reject unsupported newer formats conservatively. Do not use a partial schema-v1 global snapshot as though its missing work IDs were authoritatively retired. Legacy full-snapshot operation keeps its existing semantics; compatibility adapters must explicitly distinguish full coverage from continuous scoped updates.

The document's current selection provenance binds its **own group's semantic selection revision**. It may retain the original run identity that established that rendering as historical provenance; the current run's confirmation is tracked in the private ledger/catalog rather than rewriting the document to embed every new run ID. Unchanged-document stability extends across inventory runs: resolving another known group, or adding an unrelated file in a later inventory, must not change earlier Markdown bytes/mtime when their semantic selection/rendering inputs are unchanged. Normalize generated-owned artifacts and incidental observations out of semantic input digests. Updated fingerprints with verified identical bytes are observations, not new content. Local records likewise change only when their own group membership, authority, rendering or coverage changes, not merely to copy a new global run ID. Record publication time separately from stable extraction time, preserving unknown legacy extraction timestamps honestly. Global progress counters live in the private run status.

Do not require a fresh full source-tree manifest-discovery walk before the first publication. Start with the known inventory, private ownership/recovery records and the resolved work's own directory. Continue discovery of other/emptied managed directories in bounded background steps. Until that discovery and relevant group coverage finish, do not claim whole-library reconciliation or clear uncertain older entries. Positively known changes can still be reconciled promptly.

## Current search view

Source-adjacent publication is the prompt deliverable. Refresh the local immutable current corpus periodically, using the existing publication batch/time controls and read-only shared artifacts. A global catalog revision can advance as more work finishes, but must not invalidate unchanged per-work selection revisions or cause full-library source rehashing/re-rendering.

Only confirmed current publications belong in a new current view. Unchecked prior-run entries are explicitly unresolved, not declared obsolete. Last-good retention is allowed only while it contains no positively revoked entries. A confirmed hold/revocation overrides retention immediately: if it removes the sole searchable book while other groups remain pending, advance to an **empty current generation with pending coverage**. A clean final empty set can also publish an empty generation. If current-view installation fails, report it as unavailable/unsafe rather than claiming a known revoked generation is a valid fallback; remove the managed default pointer when possible. Preserve the older generation as recovery history outside current search. No historical search database is introduced.

During conversion, avoid full-library validation on every group/worker event. Retain the recently added stable-observation cache rules: same authority/render inputs, identical verified before/after fingerprints, and no promotion of late edits or operational errors into successful cache entries. Changed pairs receive actual byte verification before their directory commit.

## Locks, progress and completion

Use one owning rollout/coordinator per output namespace. Long metadata work may not hold `selection.lock` or another lock required for unrelated conversion/publication. Keep policy/ledger commits short; a worker waiting for file I/O must not hold an authority lock. The coordinator owns conversion scheduling and ledger publication; metadata workers own only their byte caches. Preserve the per-source lease contract when older jobs still run.

Expose a durable status with separate counts for metadata checked/total, groups resolved/deferred/pending, eligible work queued, conversions active, documents published, OCR outcomes, failures and output/capacity conflicts. Log group eligibility, job starts/completions and publication, retain 100-item summaries and 30-second heartbeats. Do not label an entire active pipeline simply `metadata` while conversion is also happening.

A run finishes only when all known groups are accounted for and eligible conversion/publication queues are drained or have explicit terminal exceptions. An empty conversion queue while metadata remains active means wait for more work, not success. `capacity_pending` and `needs_regroup` are durable, resumable incomplete exits, not completed-with-exceptions. Metadata errors can be terminal for that pass while still unresolved for selection/retirement. Use completed-with-exceptions for a drained run's other terminal outcomes and retain checkpoints for explicit retry.

## Transition from the active rollout

Keep the current process running during design review. After implementation is approved and verified, replace the old controller/producer in a controlled transition:

1. Record the deployed process/binary identities and state paths. Stop the old controller from launching its eventual batch conversion before switching producers.
2. Quiesce the old metadata process, retain its SQLite/WAL caches, and verify its OS locks have released. Interrupted current-PDF work can be retried; committed hashes/raw metadata are reused.
3. If old extraction workers exist, preserve their leases and allow compatible private-cache work to finish. The new coordinator must not double-dispatch them or accept their old selection authority. Adopt cache results only through current group/source/engine checks.
4. Start the continuous coordinator using the same completed inventory and cache namespace. Bootstrap cache-complete groups and verify that conversion/publication actually starts while uncached metadata remains pending.

Do not delete caches, restart the broad inventory scan unnecessarily, or leave both old and new controllers able to publish into the same namespace. Preserve any already published, checksum-owned outputs. A new deployed binary has a stable path/version for this run.

## Acceptance checks

- Gate a slow uncached metadata task and prove that another cache-complete group produces sibling Markdown before that gate is released. Metadata must still be incomplete at the first successful publication; no global cache/discovery pass may be a hidden startup barrier.
- Prove that a half-read multi-candidate group never gets a date winner, while an independent resolved group converts.
- Verify existing selection-policy tests unchanged: metadata dates, aliases, broad groups, holds, independent adopted works and baseline protection.
- Resolve more groups from the frozen universe, then start a later inventory containing an unrelated new file; prove earlier Markdown/manifest bytes and mtimes remain unchanged unless their own semantic inputs or local coverage change.
- Exercise several groups in one directory, incomplete coverage, conclusive holds/moves, and eventual clean retirement without deleting source/Markdown files.
- Change/revoke review authority or a known competing source while a job runs; late metadata/conversion results may cache bytes but cannot publish revoked authority.
- Revoke the only current book while unrelated groups remain pending; prove current search becomes empty/pending instead of retaining the revoked book. Exercise a supported review writer racing the final publication gate.
- Change known bytes to add/remove an alias edge; prove the old component cannot grant a new winner and the run checkpoints as needs-regroup. Verify same-hash timestamp/permission changes only refresh observations.
- Interrupt metadata, group commit, extraction and directory commit; resume without losing queue entries or repeating successful extraction. Cover duplicate events, stale requests and leased older workers.
- Test concurrent capacity reservations, no-fit/fit jobs, empty conversion queues before producer completion, and terminal exceptions without starvation.
- Verify current-view hardlinks remain read-only, source redirects/manual edits are preserved, and stable-observation caches do not attest to late changes.
- Pilot with the existing four-document corpus plus an intentionally delayed group; then switch the actual rollout and report real first-publication evidence alongside ongoing metadata counts. Preserve all original PDF hashes.

## Designer defaults and boundaries

Proposed defaults are one metadata worker, two extraction workers, a 300-second per-PDF metadata deadline, existing 20-page chunks, reservations covering all local data growth with 20 GiB reserve, resumable capacity/regroup exits, and a short authority gate shared with supported review writers. Preserve unchanged per-group rendering across runs, explicitly withdraw known revocations even to an empty pending view, and retain uncertain lineage conservatively. Exact Rust module/table/manifest field names, event transport and background-discovery budget are left to the builder. No external queue service is required.

The chosen approach changes scheduling and authority granularity, not which content qualifies or how Markdown text is extracted. Historical indexing, archives, OCR, new search products and 5etools remain deferred.

## Builder check

A fresh Sol builder check raised six planning questions: retirement/lineage proof, revocation versus last-good retention, changed-byte regrouping, the review commit boundary, stability across inventory runs and capacity exit behavior. The designer resolved them explicitly above using conservative current-only authority and recoverable states. These are proposed implementation calls for user review; no production process was stopped or switched to continuous mode while writing this document.
