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

The shared implementations currently comprise 28 byte-identical files and
318,825 duplicated bytes. `skill-sync.txt` names that contract and
`check-skill-sync.sh` enforces it. `SKILL.md` files are intentionally outside
that contract because their tool names, question flows, backend selection, and
review UI differ by harness. The two review implementations are also
intentionally different: Claude uses `_shared/review-artifact`, while Codex uses
`_shared/review-page` plus local HTML handoff.

The audit that produced this document found two real drifts in files already
declared shared:

- `remove-recap/find_recap.py` lacked the newer serial-style recap openers in
  Codex.
- `vtt-spell-pass/find_unknowns.py` lacked session-start trim support in Codex.

Both implementations and their Codex workflow instructions were synchronized
on this branch.

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

Use repository-relative symbolic links for the 28 files already proven
byte-identical. Both installed skill directories are whole-directory links into
this repository, so the relative targets resolve from the checkout. Before
adopting this layout, verify that Claude and Codex skill discovery, packaging,
and any copy/export command preserve or follow symlinks. If either runtime does
not, keep the canonical files in `shared/skills` and have the link/install
scripts materialize copies; the generated copies should be checked in CI and
never edited directly.

Do not template whole `SKILL.md` files first. Their large shared prose makes
duplication visible, but line-oriented templates would make the operational
instructions harder to read and review. Start by extracting only stable domain
references used by both adapters, then link to them from each `SKILL.md`.

## Migration plan

1. Add a CI job that runs `dotfiles/check-skill-sync.sh`. This closes the
   current failure mode immediately.
2. Move one low-risk pair, such as `remove-recap/recap_unique.py`, into
   `dotfiles/shared/skills` and verify both live runtimes can execute it through
   a relative link.
3. Move the remaining 27 shared files in skill-sized commits. Preserve modes
   and run each affected helper's tests or smoke checks in both runtime paths.
4. Replace `skill-sync.txt` with a smaller manifest of shared links plus a list
   of intentional adapter-only files. The checker should fail on a copied
   platform-neutral file, because that reintroduces two authorities.
5. Review the 27 Claude-only skills by value and compatibility. Port a skill
   only when its workflow is useful in Codex and every Claude-specific tool has
   a deliberate Codex equivalent. Track that decision in a short manifest with
   `ported`, `claude-only`, or `candidate` status.
6. Add a Codex link/install checker analogous to `claude-links.sh`; today this
   repository documents how Claude files reach the live home directory but has
   no equivalent proof for Codex.

This removes duplicated executable logic first, where divergence changes
behavior, while leaving readable runtime instructions explicit.
