# Current-toolkit bridge and proven run

Read this when no first-class incremental NPC-update command is installed.
Inspect the current code and help before adapting these APIs: this describes
the implementation used on 2026-10-19, not a permanent API guarantee.

## Example

A prior run extended a campaign's reviewed history through chapter 12, using
chapter 13 as the only new source. Four changed dossiers and four new ones
passed native verification, received saved GM approvals and were published by
the native writer. No old summary bodies were re-read or re-drafted.

That run's campaign-local implementation lives under
`<campaign>/notes/npc_delta/ch<NNN>/`. Find prior runs on this machine with
`ls -d ~/*/notes/npc_delta/*/ ~/*/*/notes/npc_delta/*/ 2>/dev/null`.

- `publication_manifest.json`: source and generated chapter hashes.
- `build_delta.py`: explicit selection, baseline carry-forward, contextual
  evidence links, native verification and composition.
- `delta_manifest.json`, `context_links.json`, `verification_context.json`:
  the sparse output, the link reasoning and the evidence dependencies.
- `create_review.py`: native verification adapter, custody and signoff items.
- `make_review.py`: prose diffs for existing dossiers and complete text for new
  ones.
- `apply_review.py`: the actual saved decisions, native signoffs and a guarded,
  selected publication; a dry run unless `--apply`.
- `application_manifest.json`: final receipts.

These scripts contain fixed chapter and NPC selections. They are examples to
adapt, not a generic updater to rerun blindly for another session.

## Isolated publication and linking

The repository publisher's `refactor(root, paths)` takes explicit paths, but
its numbering subprocess enumerates the root's flat summary directory. Use a
scratch root containing only the new chapter, then copy its generated artifact
to the real destination. Preserve the earlier corpus files.

Command shape, from the campaign root:

```bash
summary_native build --config <campaign-config> \
  --summaries-dir notes/npc_delta/<run>/input --since N --until N
summary_native npc-link --config <campaign-config> \
  --summaries-dir notes/npc_delta/<run>/input --since N --until N
```

Use real numeric values and the campaign's registry configuration. Check that
the config actually loads the registry (a config without one silently skips
it). The input contains only the new numbered chapter, and validation should
report one file scanned. Inspect the mention-without-heading and withheld-form
reports.

## Cached history and verification

Relevant modules: `pipelines/summary_native/{npc_link,npc_verify,npc_compose,
npc_publish}.py` and `review/verification.py`.

Read only the selected baseline evidence files. Avoid a convenience reader that
opens every NPC file and filters the result afterward. Combine each selected
cached evidence body with the exact new evidence. Keep old chapter blocks
byte-for-byte and recompute the header counts and chapters. Store separate
hashes for the baseline draft/evidence and the candidate draft/evidence.
Historical baselines are not rewritten.

The native verifier accepts a `CorpusIndex` and source text. A bounded bridge
can derive its index from the real chapter/scene targets in the selected cached
NPC evidence plus the new chapter. Record that basis honestly: do not claim a
full summary scan, invent summary files or manufacture verification results.
Each NPC's evidence must still contain every target it cites.

Use the native pure verification adapter and custody models for this context.
A whole-draft signoff binds actual bytes, not a description of a requested
change.

## Canonical review root

The review store binds campaign identity to a canonical root, so a git
worktree can raise `REVIEW_CAMPAIGN_MOVED`. Do not rewrite `campaign.json` or
disable the guard. Run native review operations at the matching canonical
checkout, staging only the specific new candidate and evidence files and
checking baseline hashes. Preserve user edits, sync receipts and output back to
the working branch, and do not overwrite unrelated files.

After the saved decisions validate, explicitly approved unchanged passages can
receive native `accept_no_change` advisory decisions. Use the native exact-draft
signoff operation for document approvals and the normal publication preflight.
If the CLI would select the wrong range or rescan old sources, the native
`npc_publish.plan_publish` / `npc_publish.publish` APIs can publish an explicit
sparse selection. Keep their authority and stale-signoff checks; never supply a
test-only signoff override.

The example used scoped assistant edits and no new backend model calls. If a
later run calls a model, pass the agreed model explicitly and send only the
necessary baseline and delta, not every earlier summary.

## Related feature work

- [#512](https://github.com/kostadis/CampaignGenerator/issues/512): cross-range
  cache reuse and carry-over for NPCs absent from added chapters.
- [#585](https://github.com/kostadis/CampaignGenerator/issues/585): proposed
  GM attestation for mentioned-but-unchanged dossiers.
- [#587](https://github.com/kostadis/CampaignGenerator/issues/587): the missing
  changed-NPC delta planner, updater, review and publication path, with the
  demonstrated flow and acceptance tests. Its proposed syntax is **not**
  implemented; do not call it.
