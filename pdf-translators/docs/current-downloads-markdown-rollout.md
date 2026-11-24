# Current-download CIFS Markdown rollout

The owner re-downloaded the DriveThru library and mounted it at `/mnt/winshare`, confirming these are the current delivered files. The new scan uses `--current-library`: each PDF is an independent current input, so publisher-supplied variants and missing/conflicting embedded dates do not exclude conversion. Source PDFs remain unchanged. Generated PDF-stem Markdown and `current-documents.json` are written beside them with relative source links and hashes.

## Scope and implementation

- 6,391 PDFs, totaling 143.42 GiB.
- 1,442 archives recorded but not expanded or converted; other non-PDF files remain untouched.
- Separate private scan state: `source-selection-data/winshare-current-state`.
- Separate output/checkpoints/logs: `source-selection-data/winshare-current-markdown`.
- Code commit: `f020a04`; immutable `selector-f020a04` SHA-256 `a161ca4d8f1e33e13b2d76518b5762fb201121b80546532c52d4793b441ea466`.
- User service: `rpg-markdown-winshare.service`, using `--workers 4` at the owner’s request, independent of the chat terminal; abnormal exits restart after 30 seconds. Normal completion and deliberate stops do not restart.
- Seeded prior content-addressed cache: 820 staged PDF files, 3,407 range checkpoints, 817 completion records and 6,591 raw metadata entries. Old source-root identities, selection records and ownership receipts were not adopted. Existing bytes are still verified before reuse.

The new policy preserves explicit holds/confirmed baselines and manual/foreign output protections. Output-name collisions are deferred. Default historical selection retains its existing date/duplicate policy. Shared SHA/extractor jobs now notify every consuming group when extraction finishes, ensuring identical PDF bytes at separate paths can each receive Markdown.

## Verification

The final complete Rust suite passed 164 tests, with 2 optional tests ignored. Format, diff checks, clippy with warnings denied and release build passed. One fresh Sol review produced three Important findings; all received failing regression tests and were fixed in one pass: colliding sibling targets, explicitly confirmed baselines and concurrent scan policy/progress races.

The optional mounted-filesystem probe passed on CIFS without warnings, exercising publication, replacement and resume inside a temporary directory.

A real-document CIFS pilot converted copies of four library PDFs: Pallowen; Secrets of the Sacred Stone; Kobold Guide to Worldbuilding; Jester David's Guide to Fantasy Worldbuilding. All four published successfully and resumed successfully. The pilot exercised both fresh extraction and cached-range reuse. Original and pilot PDF SHA-256 hashes, generated source links and directory records were verified. Its temporary CIFS directory was removed; private evidence and generated Markdown copies remain under `source-selection-data/winshare-current-pilot/verification.json` and `published/`.

The final inventory scan reported 7,833 PDF/archive inputs, 6,391 singleton PDF groups, no hints and no coverage errors. No MuSe/rpglib data was imported into this run. The old Drive converter was confirmed inactive before starting the dedicated CIFS service.

## Operations

From `pdf-translators/`:

```bash
systemctl --user status rpg-markdown-winshare.service
watch -n 5 cat source-selection-data/winshare-current-markdown/continuous-status.json
tail -f source-selection-data/winshare-current-markdown/continuous.log
```

Private `deployment.json`, `cache-seed.json` and rollout observation files identify the exact executable and durable progress. Worker logs are under `logs/`. Status counters distinguish queued extraction, active jobs, confirmed publications, OCR/native-empty exceptions, failures and output conflicts. The current search view is `corpus/current/books`; source-adjacent Markdown can also be searched recursively. A running background rollout is not a claim that every PDF has finished.

Deferred minor from review: importing historical MuSe hints spanning multiple current-library groups can trigger `needs_regroup`. This no-hint rollout does not use those options. The gdrive-cli transport design remains shelved.

The initial run used two extraction workers. At the owner’s request, continuous conversion gained a positive `--workers` setting (default two), with a gated integration test proving four independent extractors run concurrently. The deployed CIFS service uses four workers with the same combined capacity reservations and 20 GiB floor. The test uses disk-backed output because the small `/tmp` tmpfs correctly refuses four simultaneous extraction windows while preserving that floor.

The four-worker deployment uses code `a46aae7`, immutable `selector-a46aae7`, SHA-256 `668b55362e302ccdd95fbbe85046c7ea6d355de1d8428ac8d69c203f54ca4fec`. The initial two-worker run reached 386 confirmed publications before restart. Four worker processes and one metadata process were verified in the replacement service. Private `four-worker-transition.json` records before/after status and two existing Markdown samples whose contents and modification times were preserved. Counters rebuild during restart revalidation; previous outputs and extraction checkpoints remain saved.
