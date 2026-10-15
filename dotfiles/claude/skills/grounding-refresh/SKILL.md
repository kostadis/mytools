---
name: grounding-refresh
description: Rebuild and officially publish a campaign's four grounding documents (world_state, campaign_state, party, planning) from its structured session summaries with CampaignGenerator's summary_native pipeline — extract on the DGX Spark, synth through claude-code, GM review, the one-time grounding-bundle migration, the claims check, the GM's four document sign-offs, managed promotion, and post-promotion patches. Every precision decision (coverage, threads, sign-offs, canon wording, patches) stays with the GM. Use when the user asks to regenerate or refresh the grounding docs after new sessions, to "do the summary-native world_state flow", to make new drafts the official documents, or to patch a published grounding line between builds. Invoke as /grounding-refresh [campaign-dir] [until-chapter].
tools: Read, Edit, Write, Bash, Glob, Grep, AskUserQuestion, Skill, Artifact
---

# Grounding refresh (summary_native → managed promotion)

The four grounding documents are an **index** over the structured summaries in
`docs/summaries/`. This skill rebuilds them for a chapter range and publishes them as
one managed generation under `docs/grounding/`. It runs the CampaignGenerator CLIs;
it never hand-writes a grounding document, and generation never writes `docs/` —
only `promote` does.

The operator's manual is `~/src/CampaignGenerator/docs/cli/summary_native_howto.md`
(Steps 0–8), plus `grounding_bundle_migration.md` and `grounding_bundle_promotion.md`
in the same folder. **Read the relevant section before each phase**: flags change
between CampaignGenerator releases (for example, `--config` moved from
`config/grounding.yaml` to `config/config.yaml` in October 2026).

## Who decides what

| Step | Who decides | Notes |
|---|---|---|
| extract (Spark) | Model proposes notes; **code** drops any note whose citation does not resolve or whose quotation is not verbatim | Read `drops.md` |
| synth (claude-code) | Model renders prose from code-routed checked notes; **code** builds the tables, the timeline and `reference/` | Draft only |
| Thread ratification | **GM** | Without it Active Plots and the quest sections stay empty |
| Claims coverage (chunks or none) | **GM** | Explain the check first (below) |
| Reviewer name | **GM** | Ask; never infer it from git config |
| The four document sign-offs | **GM** | Each one binds the reviewer's name to exact draft bytes |
| Canon wording, patches | **GM** | Canon chain and inversion rules from the campaign CLAUDE.md apply |

An unanswered or ambiguous question is not a decision: re-ask it. A question the GM
answers with a question ("what is this check doing?") gets an explanation, then the
same question again.

## Phase 0 — preconditions

1. Confirm the campaign directory has `docs/summaries/` and `config/config.yaml`.
2. Run `/spark-status`. Use the IP endpoints from the file, never hostnames, and probe
   `/v1/models` on each box.
3. Make sure CampaignGenerator is current: `git -C ~/src/CampaignGenerator pull --ff-only`
   when its working tree is clean. Stale releases had promotion bugs (see the end of this file).
4. **Backend guard:** every `summary_native` command, even one that makes no model call,
   needs `CG_BACKEND=claude-code` in the environment or `--backend claude-code`. Any
   shell line that merely *contains* the word `campaign_state` trips the guard too, so
   prefix greps as well. Never set `CG_ALLOW_API=1` unless the GM asked for the API.
5. **Model choice:** pass the backend and model explicitly every time, and never let a
   call fall through to a default (Fable). **Sonnet reads and writes; Opus adjudicates.**
   - Writing (synth prose): `--backend claude-code --model claude-sonnet-5-5`.
   - Adjudicating (`audit`, one judgment per tracking claim):
     `--backend claude-code --model claude-opus-5-5`.
   - Reading: any subagent that reads drafts, summaries or rulings (Phase 5 review,
     comparing against `notes/`) runs on Sonnet and returns findings. Opus, in the main
     session or an Opus agent, rules on those findings before anything reaches the GM.
   - Extraction on the Spark uses `--backend dgx --model <live model id>` and both `--endpoints`.
   The GM can name other models; otherwise use these.

## Phase 1 — validate and build the corpus

```bash
summary_native validate --summaries-dir docs/summaries        # exit 0 required
summary_native build    --summaries-dir docs/summaries        # writes docs/summary_native/chSSS-UUU/
```

- Blocking findings (titles, duplicates) are GM edits to `docs/summaries/`; follow
  `summary_native_howto.md` Steps 1–4 and the campaign's canon chain for any spelling.
- If any summary, `canon.yaml` or the registry is newer than the range's `manifest.json`,
  run `build --force`. synth refuses a stale corpus, and promotion later binds every
  summary's sha256.

## Phase 2 — extract on the Spark

```bash
summary_native extract --summaries-dir docs/summaries --since 2 --until N \
  --backend dgx --model <id> --endpoints http://<spark1>:8001/v1 http://<spark2>:8001/v1
```

- Run it in the background. Chunks are cached by a key that covers the prompts, so after a
  CampaignGenerator upgrade expect **every** chunk to re-extract, not just the new chapter.
  On two boxes, about 61 chunks took roughly 15 minutes.
- **Read `state/notes/drops.md`.** An *outlier* chunk whose drops are mostly `uncited` means
  the model forgot the citations; ch015 once lost 52 of 52 notes this way. Fix: move that
  chunk's `*.checked.json` and `*.out.md` into the scratchpad (never delete them), then re-run
  the same command. The cache serves the rest and only those chunks re-extract. Report
  before and after counts.
- `malformed-row` and a handful of `quoted-span-not-found` drops are normal. Report them.

## Phase 3 — synth the four drafts

```bash
F="--since 2 --until N --summaries-dir docs/summaries --backend claude-code --model claude-sonnet-5-5"
summary_native synth world_state $F
summary_native audit ${F/claude-sonnet-5-5/claude-opus-5-5}   # adjudication: Opus; slow, one judgment per item
summary_native synth campaign_state $F       # renders the audit it finds
summary_native synth party $F
summary_native synth planning $F
```

- **An exit code of 0 does not mean it succeeded.** A model failure in a section prints
  `Error: model call failed in section …` and still exits 0. Read the tail of every run.
  Each draft must end with `Wrote draft: …`.
- **Usage limits:** claude-code calls draw on the GM's Claude plan. On "You've hit your
  session limit", stop, report what finished, and resume after the reset. Re-running
  `audit` judges only the failed items; re-run a document with `--force`.
- Word-budget overruns (`OVER`) are reported, never trimmed. Mention them.
- party and planning can run in parallel with the audit → campaign_state chain.

## Phase 4 — threads (GM)

Planning's **Active Plots** and campaign_state's thread sections render only threads the GM
has ratified in `docs/thread_registry.yaml`. With none ratified they say so, and every thread
note lands in `reference/threads_unratified.md`. Offer the GM a choice:

- **Ratify first:** `summary_native thread-propose`, then rule on each group (`/grounding/threads`,
  or `thread_registry rule/ratify`). Hundreds of notes means an Approve/Reject/Discuss
  artifact, per the campaign's long-review-queue rule. Then re-synth planning and
  campaign_state with `--force`.
- **Publish now, ratify later:** fine. The drafts state that plots are unratified.

## Phase 5 — review the drafts against the GM's rulings

Before anything is promoted:

- Run `summary_native compare <doc> --summaries-dir docs/summaries --live docs/<doc>.md` for each draft.
- Check the drafts against rulings made **outside** the summaries: the latest
  `notes/session_prep/*`, `notes/batch_rulings_*`, and recent commits. Summaries harden
  hedges, and they assert states the tape never showed. Worked example (OOTA, 2026-10-13):
  the ch067 summary said Sylvira was "still unaware" the party killed her son. The GM's
  ruling: *the party never told her; that does not mean she doesn't know*. "Has not been
  told" was right; "unaware" and "does not yet know" were wrong. Grep the drafts **and
  `reference/`** for the subject, because a wrong caption spreads into the reference notes
  and the tracking audit.
- Fix wrong text **at its source** (the summary line), then rebuild. If the GM does not want
  a rebuild now, promote and then patch (Phase 10). Never edit a draft by hand: drafts are
  regenerated.

## Phase 6 — one-time migration (first promotion only)

Check with `summary_native promotion status --config config/config.yaml --json` and
`ls docs/grounding`. If the campaign has never migrated:

```bash
summary_native authority init --campaign-dir "$PWD" --json      # only if docs/authority is missing
summary_native review init    --campaign-dir "$PWD" --json      # only if docs/reviews is missing
migrate_grounding_bundle --campaign-dir "$PWD" --dry-run --json
migrate_grounding_bundle --campaign-dir "$PWD" --plan-sha256 <plan_sha256> --json
migrate_grounding_bundle --campaign-dir "$PWD" --verify --json
```

- If the `migrate_grounding_bundle` entry point is not installed in the venv, run
  `~/.venv/bin/python -m server.migrate_grounding_bundle …`. The venv imports the source tree.
- `legacy … does not satisfy the generated outline` means a live doc is missing a heading
  the generator writes. Find it: run `load_outline(name)` from
  `pipelines.summary_native.outline` against `docs/<name>.md`. Explain *why* it differs
  before proposing a fix. Example: the classic pipeline's `## Tracked Items Status` versus
  summary_native's `## Audit: Tracking Claims`, which hold the same content under a
  different title. A heading-only rename to adopt the legacy baseline is the GM's call. The
  alternative is an absent baseline (moving the live files out of the way first).
- Show the GM the plan (aliases, members, the config change) before applying it. Afterwards
  `docs/<doc>.md` and `docs/reference` are symlinks into `docs/grounding/current/`, and
  `config/config.yaml` points there.

## Phase 7 — claims selection and check

```bash
C=config/config.yaml
summary_native claims select --config $C --since 2 --until N --json      # → data.selection
```

Before saving, **explain what the check does**:

- It compares **structured claims** (subject + predicate + value: actor, faction, posture,
  identity, certainty, obligation status and amount, location, status, temporal order)
  under six blocking rules: direct contradiction, stale superseded, suspicion-as-fact,
  resolved-as-active, incompatible state, and audience leak.
- Claims come from the authority ledger automatically. Draft prose is checked **only** if
  chunks are selected for model extraction, and then the GM must confirm every extracted
  meaning, which means hundreds of items and an artifact.
- **0 chunks** = ledger-only coverage. It never reads the drafts. The receipt records the
  limitation, and the GM's own reading plus sign-off is the real check.

Ask for the coverage choice and the reviewer name, then:

```bash
summary_native claims selection save --config $C --input <selection.json> --reviewer <name> --json
summary_native claims review --config $C --selection <saved path> --review <review-id> --json
summary_native claims check  --config $C --selection <saved path> --review <review-id> --json   # → report id
```

Use a **fresh review id** whenever any draft's bytes have changed since the last review.

## Phase 8 — the GM's four sign-offs

`claims check` creates the sign-off items (`document-world_state`, … plus `claims-coverage`)
in the review. A sign-off says "I, <reviewer>, approve these exact bytes". Sign only on the
GM's explicit instruction, after the drafts have been reviewed:

```bash
sha=$(sha256sum docs/summary_native/chSSS-UUU/state/drafts/<doc>.draft.md | cut -d' ' -f1)
summary_native review document sign <review-id> --item document-<doc> \
  --document-sha256 $sha --expected-decision-revision 0 --reviewer <name> --json
```

Any later change to a draft makes its sign-off stale; re-sign it.

## Phase 9 — preview and publish

```bash
A="--config $C --since 2 --until N --review <review-id> --check-report <report-id>"
summary_native promote $A --dry-run --json          # read every gate; eligible must be true
summary_native promote $A --preview-sha256 <fresh preview_sha256> --request-id <unique-id> --json
```

- Take the preview digest from a dry-run made **immediately before** the commit. Never reuse
  an old one.
- Keep the operation id. On `PROMOTION_COMMIT_UNKNOWN`, inspect `promotion status` and
  `promotion recover`; never retry with a new request id.
- Confirm afterwards: `docs/grounding/current` points at the new generation, and
  `migrate_grounding_bundle --verify` is valid.

## Phase 10 — patching a published line (between builds)

Until CampaignGenerator ships patch support (issue #578), a GM correction to one published
line is done by hand, **in this order**:

1. **Promote first.** Editing a summary before promoting stales the run records' corpus
   bindings, and promote refuses.
2. **Edit the live line** in `docs/grounding/current/…`, the sanctioned prose-edit location,
   and mark it inline: `*(patched <date>: was "<old>"; see docs/grounding_patches.md P-NNN)*`.
   Never replace the top-level symlinks.
3. **Fix the source** (the summary line, registry or dossier) so the next build regenerates
   the right text.
4. **Record the patch** in `docs/grounding_patches.md` at the campaign root (not inside
   `docs/grounding/`, where unknown files are refused): the id, the date, the GM ruling
   verbatim, the origin, a before/after table for every location, `open` status, and the
   note that the next build needs `build --force`.

`promotion status` will report the bundle as edited live; that is expected. Prep tools read
only the four configured documents, so the inline markers are what they see.

## Phase 11 — commit

- One campaign per commit, on a branch off the default branch.
- Stage **explicit paths**: `config/config.yaml`, `docs/{world_state,campaign_state,party,planning,canon_events_timeline}.md`,
  `docs/reference`, `docs/grounding`, `docs/grounding_patches.md`, `docs/thread_registry.yaml`,
  `docs/authority*`, `docs/reviews/<review-ids>`, any edited summaries, and
  `docs/summary_native/chSSS-UUU/state/` **without** the bulky `runs/*/` prompt dumps (keep each
  `runs/*/record.json`; the audit dumps run to about 40 MB each).
- Check `git diff --cached --name-only` for audio and video (`.mp3`, `.m4a`, `.mp4`) and for
  paths outside the campaign before committing.
- Ask before pushing or opening a PR.

## Report

At the end, report: the range and the generation id; extract kept and dropped counts and
any re-extracted chunks; synth word-budget overruns; the claims coverage choice and report
id; who signed; open patches; what was committed and what was left out; and anything
pending (thread ratification, patches waiting for the next build).

## Known CampaignGenerator failure modes

Fixed in PR #577 (merged 2026-10-13). If they reappear, the checkout is stale:

- `retained run record is incomplete` on every record: the gate compared synth's
  `check: {complete, problems}` to the string `"passed"`.
- `expected one reading-contract path record` on campaign_state: synth did not write
  campaign_state's reading contract.
- `run record has no valid thread registry digest`: synth recorded a null digest when no
  registry existed. A null digest now means "no registry", and becomes stale once one exists.

Fixed upstream in `b330cda`: promote and claims resolved `out_root` relative to the config
file's folder.
