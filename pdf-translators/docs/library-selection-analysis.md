# Library selection analysis

The Rust `analysis` commands build a private, read-only benchmark and proposed conversion list. They never change selection state, library PDFs, existing Markdown, or directory manifests. They launch no extraction, OCR, rendering, or model calls. Current download presence is evidence of availability; it is not proof that absent owned editions are obsolete.

Run from `pdf-translators/source-selector`, or pass `--manifest-path` when building from elsewhere:

```bash
cargo build --release
./target/release/rpg-source-select analysis run --config /absolute/private/config.json --output /absolute/private/run-v1
./target/release/rpg-source-select analysis review-export --run /absolute/private/run-v1 --output /absolute/private/review-v1
```

A configuration has `schema_version: 1` and these fields:

```json
{
  "schema_version": 1,
  "csv": "/absolute/path/DriveThru file matches.csv",
  "d_root": "D:/Users/kosta/DriveThruRpg",
  "g_root": "G:/My Drive/DriveThru",
  "old_inventory": "/absolute/path/selection.db",
  "current_inventory": "/absolute/path/current/selection.db",
  "history": "/absolute/path/continuous.db",
  "history_status": "/absolute/path/continuous-status.json",
  "historical_runs": ["oldest-run-id", "latest-run-id"],
  "owner_rulings": "/absolute/private/owner-rulings.json",
  "evidence_imports": [],
  "reference_complete": false,
  "sample_seed": "library-analysis-v1",
  "sample_per_stratum": 5,
  "holdout_percent": 20
}
```

Use `source-selection-data/heuristic-validation/` for private configuration, inputs, reports, review bundles, and derived runs. Never put private library data or capability URLs in Git. Input snapshots include SQLite WAL contents through the SQLite backup API; no PDF bytes are read. The run refuses Unicode/case path collisions, out-of-root Windows paths, changed input snapshots, unknown historical run ordering, and library/output overlap. CSV alternate matches do not inherit the primary copy's evidence method.

Rerunning the identical command resumes completed stages without rewriting the report. If the reference CSV, inventories, rulings, configuration, or evidence changes, use a new run directory. An interrupted snapshot without its final receipt is not a valid run: keep it for diagnosis and choose a new directory. Completed snapshot stages survive interrupted subsequent audit/report work; only known incomplete owned temporary files may be recovered. `progress.json` gives stage, completed/total/remaining and errors; `progress.jsonl` logs every 100 processed records, stage boundaries, and every 30 seconds during analysis. Initial input backup reports to stderr before the progress writer starts.

The report directory includes file and relationship ledgers, reference outcomes, publisher and available metadata breakdowns, bounded stratified sample membership and holdouts, proposed conversion eligibility, protection bindings, and evidence limitations. Historical deferrals and unprocessed groups are coverage, not mistakes. A candidate group is not a verified unique work. Unresolved readable candidates remain eligible; unreadable retained sources need recovery. The proposed list is not automatically applied to the converter.

## Owner rulings and Nulb

Start with an array of rules, or `[]` if none:

```json
[{
  "id": "keep-nulb-v3",
  "wording": "Keep and convert the owner's withdrawn Nulb v3.0 edition, even though a replacement exists.",
  "provenance": "Explicit owner instruction in the library analysis discussion",
  "source_id": null,
  "fingerprint": null,
  "action": "keep_and_convert"
}]
```

An unbound rule is recorded as unfinished identification and does not choose by filename. Once existing document evidence or an explicitly bounded inspection confirms the edition, bind `source_id` and the exact inventory `fingerprint` from the source row. Record the identification evidence separately. A changed fingerprint invalidates the binding, not the owner's desire to retain the edition. A bound owner rule is honored directly and cannot be omitted by a conflicting Clef pick.

Use the existing `inspect` command for any separately planned first-pass reading; its limit is five pages per PDF including prior cached pages. No automatic sample expansion or full-library rendering is implied. Preserve page citations and warnings. Routine factual reading may use simpler models; judgment uses Sol. New evidence does not silently update a frozen run.

Optional evidence files are arrays of records with `source_id`, exact `fingerprint`, `method`, `scope`, `provenance`, and `actor`. Supported methods are `exact_bytes`, `all_rendered_pages`, `sampled_bytes`, `sampled_pages`, and `partial_reference`; other labels are retained as unconfirmed. These records are shown as evidence, never as approvals or automatic exclusions. Model records additionally need `model` and `kind` (`fact` or `judgment`); judgments require `role: "sol"`; factual records need a nonempty `quote` and positive `page` verified against saved source page evidence. Import no complete-document equivalence conclusion from a bounded sample. Record rendering settings and full page coverage for imported all-page comparisons; incomplete-file matching remains partial evidence.

## Clef review and read-back

Use the installed review-pages skill to build the frozen export, without scores unless an actual bound score file exists:

```bash
python3 /home/kostadis/.codex/skills/review-pages/scripts/build_pages.py \
  --items /absolute/private/review-v1/review_items.json \
  --map /absolute/private/review-v1/review_map.json \
  --out /absolute/private/bundle-v1 --page-size 100
```

An export with no cases needs no review bundle. For a nonempty queue, use the skill's private Tailscale server and durable service workflow. Save each page before navigation. Named choices are individual; generic approval cannot choose an edition. The renderer allows at most 12 choices: groups above nine candidates show keep-all/separate/defer while preserving every candidate and its evidence. A narrower selection in such a group needs a focused follow-up review; it is never made by dropping options silently. Unmarked, Discuss and deferred relationships stay retained. Notes remain verbatim; notes needing interpretation keep a choice pending. Exact “keep both”/“keep all” notes can resolve retention within the displayed scope.

Normalize actual saved exports before import:

```bash
python3 /home/kostadis/.codex/skills/review-pages/scripts/read_results.py \
  --bundle /absolute/private/bundle-v1 --out /absolute/private/results-v1.json
./target/release/rpg-source-select analysis review-import \
  --run /absolute/private/run-v1 \
  --manifest /absolute/private/review-v1/review-manifest.json \
  --results /absolute/private/results-v1.json \
  --output /absolute/private/reviewed-v1
```

The explicit `--manifest` selects the exact frozen question/action scope; the command does not guess a review directory. Pass only normalized results from the shared read-back tool. The importer rejects different review IDs, altered scopes, unoffered picks, missing marked-page provenance, and a changed audit. It creates a derived analysis run, preserving the original run, normalized rulings, provenance, and notes. It cannot authorize changes to production.

For changed inputs, export a new bundle and preserve prior saves. Match unaffected cases by their exact case ID and scope, and record an explicit cross-version mapping before carrying any ruling forward; do not rewrite saved IDs to force acceptance. A changed candidate set, fingerprint, question or evidence reopens affected cases. The present CLI deliberately rejects wholesale import against a changed audit.

## Reference completion

CSV snapshots remain provisional until the owner confirms the recheck is finished. Then create a new configuration/run with `reference_complete: true` and a nonempty `completion_attestation` recording that confirmation. New CSV statuses require inspection of their stated method; unknown labels remain unconfirmed. A finalized reference does not imply every historical relationship is resolved or that a sampled match is complete equivalence.
