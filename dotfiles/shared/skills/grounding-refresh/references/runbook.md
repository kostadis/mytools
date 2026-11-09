# Summary-native grounding execution

## 1. Preconditions and capabilities

Run from the campaign root. Read campaign instructions and inspect working-tree changes. Locate `docs/summaries/`, `config/config.yaml`, and the adjacent grounding configuration. Resolve paths using the CLI's campaign-root rules.

Read applicable sections of the current toolkit manuals:

- `~/src/CampaignGenerator/docs/cli/summary_native_howto.md`: corpus, extraction, synthesis, audit, threads, comparisons, NPC pointers.
- `~/src/CampaignGenerator/docs/cli/grounding_bundle_migration.md`: first migration or migration recovery.
- `~/src/CampaignGenerator/docs/cli/grounding_bundle_promotion.md`: claims, sign-offs, publication and recovery.

Use the installed environment/entry points and command `--help`. Inspect toolkit version/status when behavior differs from its manuals; do not automatically pull or switch its checkout. Verify selected backend/model/effort support before model calls. The reviewed toolkit supports `codex-cli`; exact model IDs must resolve in the execution environment.

DGX extraction is optional. If selected, read the topmost LIVE snapshot in `~/src/dgx-fun/current-setup.md`, use its actual IP endpoints and probe `/v1/models`. Do not assume Spark hostnames resolve or reuse stale endpoints. Respect backend guards; the Claude source's `CG_BACKEND=claude-code` prefixes are harness-specific, not universal Codex requirements. Do not bypass guards to enable a different provider.

Record range, requested stop, models by operation and existing authorization. Examples use shell variables `S`/`U` for chosen chapter bounds, `C=config/config.yaml`, and illustrative placeholders; replace every placeholder before execution. Confirm commands against current help.

## 2. Validate/build and extraction

```bash
summary_native validate --summaries-dir docs/summaries --since "$S" --until "$U"
summary_native build --summaries-dir docs/summaries --since "$S" --until "$U"
```

Validation may inspect outside the range, and duplicate chapter numbers can block globally. Explain unrelated findings rather than expanding edits without reason. Where flat `docs/summaries` files are generated replicas, correct the authored summary under `summaries/` and regenerate via the campaign's supported process. Apply established rulings; obtain a GM ruling when a correction changes uncertain canon.

Rebuild with supported `--force` when dependencies stale the manifest. This flag does not waive review/publication gates.

Run `extract` with selected backend/model and supported endpoint/effort flags. DGX example:

```bash
summary_native extract --summaries-dir docs/summaries --since "$S" --until "$U" \
  --backend dgx --model MODEL_ID --endpoints ENDPOINT_1 ENDPOINT_2
```

Retain logs and use asynchronous sessions for long jobs. Inspect results, incomplete chunks and `state/notes/drops.md`; report kept/dropped counts and reasons. Missing citations or non-verbatim quotations are dropped evidence, not permission to invent replacements. Investigate chunks with most/all notes dropped as uncited. Prefer documented missing/incomplete-chunk resume or targeted retry. Never remove metadata to fake success. If the current manual requires quarantining a cache artifact, preserve it with provenance and report the retry. Model/prompt cache changes can cause the entire range to re-extract.

In the reviewed toolkit exit 3 means incomplete extraction/synthesis and exit 4 means model failure. Check current code/help if behavior differs. Old successful drafts can survive failed calls: require agreement among exit status, logs, fresh run records, completeness and output provenance.

## 3. Synthesis and tracking audit

Read `synth --help` and `audit --help`. Pass explicit range/configuration and selected model flags to each call:

1. `summary_native synth world_state ...`
2. `summary_native audit ...` with the selected consistency/adjudication model.
3. `summary_native synth campaign_state ...` consuming the current audit through its supported path; do not pass the retired `--audit` option.
4. `summary_native synth party ...`
5. `summary_native synth planning ...`

Use the user's generation model for prose and consistency model for audit. For `codex-cli`, pass `--codex-reasoning-effort` where supported. Do not fall through to toolkit model defaults. Independent eligible calls may overlap, but audit must finish before dependent campaign-state synthesis. This skill does not require subagents.

Check fresh successful runs and completeness, not just file existence or an old `Wrote draft` line. Stop on usage limits/provider failure, report completed stages and retain resumable artifacts. Use supported resume rather than indefinite retries or provider substitution. Report word-budget `OVER` warnings without automatically cutting prose.

World-state/planning synthesis can require eligible published, verified NPC dossiers. Read current pointer/carry rules if refused. Use `$summary-native-npc-delta` for touched NPCs when authorized. Do not manufacture unchanged attestations, reuse ineligible dossiers or silently enable `--fallback-npc-lines`; that fallback requires an explicit user choice with its reduced behavior explained.

## 4. Threads and content review

Only GM-ratified thread groups populate corresponding active-plot sections. Offer ratification before regeneration or publication with honestly unratified sections. Inspect current `thread-propose`/`thread_registry` help, record each ruling and regenerate affected documents. Do not auto-ratify model suggestions.

Use `summary_native compare <document> ... --live docs/<document>.md` with matching range/configuration. Review all four drafts, relevant reference captions, unratified threads and audit text against reviewed summaries, applicable `notes/session_prep/`, batch rulings, authority records and recent relevant changes. Preserve canon precedence, uncertainty and audience boundaries. “The party never told her” does not establish “she does not know.” An NPC's faction confusion is not the objective faction relationship.

Correct errors at their authored source, regenerate flat replicas, rebuild stale dependencies and rerun affected synthesis/checks. Do not hand-edit regenerable drafts. Do not publish a known error merely to preserve an older manifest's eligibility. If a correction exceeds the requested scope/stop, preserve the finding and explain what remains instead of representing it as approved.

## 5. First migration, when needed

```bash
summary_native promotion status --config "$C" --json
```

Initialize authority/review stores only if missing; never reset existing stores. Inspect the migration preview:

```bash
summary_native authority init --campaign-dir "$PWD" --json
summary_native review init --campaign-dir "$PWD" --json
migrate_grounding_bundle --campaign-dir "$PWD" --dry-run --json
```

Show the GM every member, alias, config change and baseline choice. Apply only the approved exact plan digest:

```bash
migrate_grounding_bundle --campaign-dir "$PWD" --plan-sha256 PLAN_DIGEST --json
migrate_grounding_bundle --campaign-dir "$PWD" --verify --json
```

If needed use the toolkit environment's documented `python -m server.migrate_grounding_bundle` equivalent. Explain legacy-outline mismatches and propose bounded corrections. Do not automatically move live files aside or rename headings to force an absent/accepted baseline. Unknown files, unsafe links and incomplete bundles are findings, not permission to delete them.

Aliases cover four documents, canon timeline and reference tree under `docs/grounding/current/`. An absent baseline can leave readers unavailable until first publication; disclose that consequence before choosing it.

## 6. Claims scope, coverage and findings

```bash
summary_native claims select --config "$C" --since "$S" --until "$U" --json
```

Retain proposed selection/mandatory source closure. Resolve every `unresolved_scope` entry through `claims selection resolve-scope` with explicit GM applicable/not-applicable ruling, rationale and reviewer. Context-only records stay in the closure. Deleting entries does not resolve them; scope rulings do not grant fact authority.

Explain coverage before asking for a decision:

- Structured checks cover contradiction, superseded state, suspicion presented as fact, resolved threads presented as active, incompatible state and audience leaks.
- Zero chunks is supported ledger-only coverage. It does **not** read/verify draft prose. Record this limitation; GM reading/sign-off remains necessary.
- Selected draft chunks require complete extraction or attributed imported candidates and review of each normalized meaning. This can create a substantial review queue. Confirm exact sources/chunks and model authorization first.

Obtain/reuse an explicitly supplied reviewer name. Save via the CLI, using its current paths/output wrappers:

```bash
summary_native claims selection save --config "$C" --input SELECTION_FILE --reviewer REVIEWER --json
summary_native claims review --config "$C" --selection SAVED_SELECTION --review REVIEW_ID --json
summary_native claims check --config "$C" --selection SAVED_SELECTION --review REVIEW_ID --json
summary_native claims show --config "$C" --report REPORT_ID --json
```

For selected chunks, perform supported `claims extract` with explicit backend/model/effort before reviewing/checking. `claims import` grants no authority. Review meanings and resolve findings through supported evidence-bound actions; rerun the check. Mechanical failures and GM-confirmed false claims cannot be waived. Use fresh reviews when changed inputs require new bindings; do not transfer stale approvals by copying decisions.

## 7. Exact sign-offs and publication

Read current v2 document items, hashes and decision revisions from the review/check. Do not hardcode old IDs such as `document-world_state` or assume revision zero. After explicit GM approval of each current document:

```bash
summary_native review document sign REVIEW_ID --item CURRENT_ITEM_ID \
  --document-sha256 CURRENT_DOCUMENT_SHA --expected-decision-revision CURRENT_REVISION \
  --reviewer REVIEWER --campaign-dir "$PWD" --config "$C" --json
```

Complete claims-coverage acknowledgment through its supported current action. Verify all four sign-offs and coverage against the final current report. Changed documents, sources, authority, audience, meanings, rules or reports can stale approvals; recompute/review affected items.

For authorized publication, inspect every gate in a fresh preview:

```bash
summary_native promote --config "$C" --since "$S" --until "$U" \
  --review REVIEW_ID --check-report REPORT_ID --dry-run --json
summary_native promote --config "$C" --since "$S" --until "$U" \
  --review REVIEW_ID --check-report REPORT_ID \
  --preview-sha256 FRESH_PREVIEW_DIGEST --request-id UNIQUE_REQUEST_ID --json
```

Require eligibility and unchanged intent/inputs. Preserve request/operation IDs and receipt. On `PROMOTION_COMMIT_UNKNOWN`, inspect status, receipt and `promotion recover --operation OPERATION_ID`; do not guess failure and retry with a new request ID. Same-ID retry is only for identical intent.

Verify active generation, managed members/aliases, receipt and migration verification. Do not copy individual drafts into place to bypass whole-bundle publication.

## 8. Corrections after publication

Prefer fixing authored sources and producing a newly reviewed generation. Check current support before assuming a native patch API exists; do not invent subcommands.

The reviewed toolkit allows human edits to editable live documents; published-generation bytes and historical receipts stay immutable. For an explicitly requested between-build correction, follow campaign origin rules, show exact before/after locations, preserve aliases and edit only the documented live location under `docs/grounding/current/`. Never replace compatibility symlinks or alter immutable published members/receipts. Record the ruling, origin fix, affected locations, date and regeneration status in a campaign-approved record outside the managed bundle, such as `docs/grounding_patches.md`. Use inline disclosure if established campaign practice requires it. Verify status reports the edit and explain the next regeneration/review must reconcile it.

For incremental requests, prepare this permitted correction’s concrete application/exception before the final content review, following [review through application](review-and-apply.md). Consume a saved exact-plan approval directly; do not add a second permission round for the same effect.

This does not justify publishing a known incorrect pending draft before fixing its source.

## 9. Delivery and optional Git work

Report range; draft paths or generation; kept/dropped counts and retries; incomplete stages/budget warnings; claims coverage/limitations; review/report/receipt IDs; named sign-offs; pending threads/corrections.

Commit, push, PR or merge only as requested, honoring existing authorization. Stage explicit campaign paths and inspect the staged diff. Include required config, managed aliases/members, authority/review evidence, source fixes and reproducibility records. Follow repo conventions for bulky prompt dumps; retain required run `record.json` provenance. Exclude unrelated changes, review-runtime files and media. Keep campaigns in separate commits. Publication itself does not perform Git operations.
