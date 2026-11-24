# Extract library archives

Execute the authorized operational task natively in Rust using installed libarchive's bsdtar backend. Four workers; keep original archives and all existing outputs. Each archive publishes a separate `<archive filename>.extracted` directory only after successful extraction; hidden staging directories and durable private receipts support restart. Nested ZIP/RAR archives are queued after successful publication, with an eight-level bound recorded as an exception if reached. Do not start Markdown conversion in this task.

- [x] Add Rust CLI integration regressions for nested extraction/resume, preserved existing directories and malformed/traversal archives. Run RED against the current CLI.
- [x] Implement bounded extraction, source observations, atomic no-clobber directory publication, recovered extracted intents, per-archive logs, status/heartbeat and free-space floor. Delegate decoding/path security to bsdtar without its unsafe absolute-path mode. Test real ZIP/RAR support and the CIFS directory rename operation.
- [x] Run full selector suite, native archive tests, fmt/clippy/release and one fresh Sol review; correct important findings once with regressions.
- [x] Pilot a bounded batch on CIFS, then launch the complete archive inventory under a user service. Log every archive and every extracted entry, save completion after each archive, and verify sustained progress. Keep PDFs/Markdown unchanged and report newly exposed PDF counts.

Initial inventory: 1,442 archives (1,422 ZIP/20 RAR), 149,851,892,528 compressed bytes. Valid ZIP headers declare 142.57 GiB expanded, 2,020 PDF entries and 143 nested archives; seven ZIP header/index failures and no encrypted ZIP flags. CIFS has about 1.3 TiB available. Native libarchive-tools 3.8.5 was downloaded/unpacked privately, matching the installed libarchive 3.8.5 runtime; no system packages changed. User data/cache paths remain ignored.

Verification: full suite167 passed /9 optional ignored; the8 archive integration cases (including optional native/low-space cases) passed separately, as did2 child/source-redirect unit regressions. fmt, clippy with denied warnings and release passed. One fresh Sol review; Important findings fixed in one TDD pass: incomplete-stage reclamation, extractor kill/reap on I/O error, real-directory identity recovery, source ancestor revalidation, capacity exit75. Each regression was observed RED→GREEN.

Ruling: bounded real-root pilot remains separate, then its exact receipts/logs are migrated into full output without its limited jobs.json — preserves the four pilot outputs as owned and avoids redundant extraction. Cost if wrong: those folders conservatively become conflicts; no overwrite is permitted.

Deferred minors: unnecessary whole-manifest rewrites when no nested jobs are added; staging-name inventory exclusion applies below the root too. Recorded in archive-extraction.md.

Deployment: code53fbbe3, private immutable selector/bsdtar pair, user service rpg-archive-extraction.service with4 workers. Real CIFS pilot4/4 succeeded,96 files/6 PDFs, resume4/4 reused; records/logs migrated without bounded jobs.json. Full batch remained active past one minute with66 completed archives and223 PDF entries exposed, zero failures/conflicts. Status/receipt evidence remains in source-selection-data/winshare-archive-extraction. The long-running extraction itself is ongoing in the background.
