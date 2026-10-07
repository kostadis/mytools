# Claude and Codex dotfile convergence

## Current state

The Claude tree contains 40 authored skills. Codex currently ports 13 of them:

- consistency-check
- dialogue-edit
- enhance-summary
- no-mech
- remove-recap
- scene-extract
- session-summary-consistency
- speaker-attribution
- speaker-attribution-text
- staged-consistency
- voice-critic
- voice-smooth
- vtt-spell-pass

Those 13 are the campaign document pipeline where Codex support has been
deliberately implemented. The other 27 Claude skills are not silently missing
copies: some are Claude-specific infrastructure, some predate the Codex port,
and some may be useful future ports. Treat adding one as a product decision,
not as a directory sync operation.

The shared implementations comprise 28 canonical files under
`dotfiles/shared/skills/`. The Claude and Codex runtime trees expose those files
through repository-relative symbolic links, removing 318,825 duplicated bytes.
`skill-layout.json` names the shared skill directories and intentional runtime
adapters, while `check-skill-sync.sh` validates every canonical link and rejects
new byte-identical copies outside the shared tree. `SKILL.md` files are intentionally outside the
shared contract because their tool names, question flows, backend selection,
and review UI differ by harness. The two review implementations are also
intentionally different: Claude uses `_shared/review-artifact`, while Codex uses
`_shared/review-page` plus local HTML handoff.

The audit that produced this document found two real drifts in files already
declared shared:

- `remove-recap/find_recap.py` lacked the newer serial-style recap openers in
  Codex.
- `vtt-spell-pass/find_unknowns.py` lacked session-start trim support in Codex.

Both implementations and their Codex workflow instructions were synchronized
before the shared-file migration. The canonical tree now prevents the same
kind of implementation drift from recurring.

## What should remain separate

Keep these as harness adapters rather than forcing byte identity:

- Every `SKILL.md`. The shared domain workflow can converge, but invocation,
  available tools, approval UI, and error handling must stay explicit for each
  harness.
- Claude global instructions, settings, hooks, agents, plugins, and marketplace
  state. Codex has different configuration and plugin mechanisms; copying these
  files would create invalid or misleading configuration.
- Review UI adapters and `agents/openai.yaml`. They are runtime integration,
  not campaign logic.
- Claude-only batch orchestration until Codex has an equivalent reviewed flow.

## Recommended structure

Move platform-neutral code and references to one canonical tree, while keeping
small Claude and Codex adapters:

```text
dotfiles/
  shared/skills/
    remove-recap/
      find_recap.py
      recap_unique.py
    vtt-spell-pass/
      find_unknowns.py
      ...
  claude/skills/<name>/
    SKILL.md
    <links to shared files>
  codex/skills/<name>/
    SKILL.md
    <links to shared files>
```

The repository uses relative symbolic links for the 28 files proven
byte-identical. Both installed skill directories are whole-directory links into
this repository, so the relative targets resolve from the checkout. The pilot
and each skill migration executed helpers through both runtime paths before
merge.

Do not template whole `SKILL.md` files first. Their large shared prose makes
duplication visible, but line-oriented templates would make the operational
instructions harder to read and review. Start by extracting only stable domain
references used by both adapters, then link to them from each `SKILL.md`.

## Migration plan

1. **Complete:** CI runs `dotfiles/check-skill-sync.sh` for dotfile changes.
2. **Complete:** `remove-recap/recap_unique.py` proved the relative-link layout
   through both runtime paths.
3. **Complete:** the remaining 27 shared files moved in skill-sized PRs, with
   modes preserved and affected tests or smoke checks run before merge.
4. **Complete:** `skill-layout.json` declares shared skill directories and
   intentional adapters. The checker fails on copied platform-neutral files,
   broken links, wrong links, and undeclared shared directories.
5. Review the 27 Claude-only skills by value and compatibility. Port a skill
   only when its workflow is useful in Codex and every Claude-specific tool has
   a deliberate Codex equivalent. Track that decision in a short manifest with
   `ported`, `claude-only`, or `candidate` status.
6. Add a Codex link/install checker analogous to `claude-links.sh`; today this
   repository documents how Claude files reach the live home directory but has
   no equivalent proof for Codex.

This removes duplicated executable logic first, where divergence changes
behavior, while leaving readable runtime instructions explicit.
