# Source-adjacent Markdown pilot

The Rust publisher now supports the approved integrated workflow: Markdown beside each selected PDF and a `current-documents.json` record in its directory. All nonempty complete native extraction can publish across game systems. Quality notes remain diagnostic, and historical search stays deferred.

## Run the workflow

From `pdf-translators/`, use a completed source-selection scan and an output directory outside the PDF library:

```bash
cargo build --manifest-path source-selector/Cargo.toml --release --locked
SELECT=source-selector/target/release/rpg-source-select
"$SELECT" --work-dir /path/to/completed-scan-state markdown-select --output /path/to/private-output
"$SELECT" markdown-convert --output /path/to/private-output --publish-next-to-source
```

Without the destination flag, existing local-only operation remains unchanged. Full operator instructions, manifest semantics, conflicts and recovery are in [searchable-markdown.md](searchable-markdown.md).

## Four-document result

The final locked release published these files beside the existing staged pilot PDFs under `source-selection-data/content-pilot-02/sources/`:

| Work | Sibling Markdown | Physical pages |
| --- | --- | ---: |
| Bad Decisions | `Bad_Decisions_Color_print.md` | 40 |
| Improved Travel: Expanded Discoveries | `Expanded_Discoveries_-_No_Background.md` | 10 |
| Improved Travel: Planning Sheet | `Improved_Travel_Prep_Sheet.md` | 5 |
| Chivalry & Sorcery 5th Edition Character Sheet | `CnS5-Character-Sheet-Final_BW_-_26th_March_2020.md` | 6 |

Each of the four source directories has a matching current-document record with the selected PDF, source/output checksums, work/source and selection IDs, selection basis, publication state and quality findings. The Markdown links relatively to its sibling PDF, and the local current corpus copy has a correctly located absolute source link. All 61 page headings were verified. Empty/sparse-page and font/layout caveats from [the native-text pilot](markdown-pilot-01.md) remain unchanged.

The existing five verified extraction ranges were reused: both final release runs reported **four published books, five reused ranges, zero extracted ranges, zero failures and no pending publication**. All eight sibling Markdown/manifest files retained their exact bytes and modification times across the reruns. All 18 staged PDF hashes still match the original pilot manifest. No full-library conversion or historical indexing was started.

Private verification evidence remains under `source-selection-data/markdown-pilot-01/`: `adjacent-final-run-01.json`, `adjacent-final-run-02.json`, their logs, `adjacent-before-final.json` and `adjacent-verification.json`. The frozen selection is `e6ab36f911353996280412ed23fe585ab70c22b8880fd303209df189772020b6`.

## Automated and mounted-filesystem checks

The final Rust suite passed **119 tests**; the installed-Poppler integration test and a mounted-Drive fixture were invoked separately and passed. Formatting, strict Clippy and the locked release build passed. New coverage includes byte-safe links, manual edits, foreign/invalid records, collisions, bounded batches, sparse/empty books, ownership recovery, same-name revisions, source changes, empty-directory discovery and incomplete coverage.

A fresh Sol review found redirected-root/concurrent-write hazards, missing final pair verification, a stale nonempty current view after authoritative retirement, generated Dungeon Masters Guild Markdown being misclassified as legacy output on rescan, and known moves being retained under unrelated coverage errors. One correction pass addressed all findings. Regressions demonstrated RED→GREEN for the observed CLI faults and staging boundaries; final checks now revalidate every proposed source/output pair after staging the directory record. Explicit legacy baselines and unrelated artifacts remain protected, including after a generated PDF is revised at the same filename.

The mounted test created an isolated temporary PDF directory within the real Drive mount, exercised publication, an unchanged rerun and replacement after a revision, then removed it. It did not modify existing library PDFs or publish their Markdown. File flush and Linux no-overwrite rename passed; directory flush and exchange rename returned `EINVAL`.

The publisher therefore uses pinned no-follow directory handles and journaled no-overwrite installation. An owned prior file is moved aside and verified before the new file is installed, with displaced unexpected edits preserved. Private operations record staged and backup filenames/checksums before these moves. Recovery restores a prior record after an interruption. A filename can be briefly absent during replacement: readers must retry rather than infer an empty selection. Unsupported directory flush produces an explicit adjacent-output warning; private journal/file flush requirements remain intact. This is the documented refinement of the initial atomic-replacement availability proposal.

## Remaining boundaries

- Full-library throughput and rollout remain unmeasured; the verified content pilot is four staged documents.
- Publication targets Linux. Local recovery does not establish cross-client Drive synchronization or cross-machine atomicity/durability.
- Legacy completion checkpoints without a recorded extraction time expose an unknown timestamp. No extraction date is invented to fill that gap.
- OCR/layout reconstruction, archives, new search databases, historical indexing and 5etools output remain later work. The local current view and directory records are available for current-only search.

No Critical/Important review finding within this milestone was deferred, and no minor findings were reported.
