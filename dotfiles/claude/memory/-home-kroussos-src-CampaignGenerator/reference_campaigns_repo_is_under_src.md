---
name: reference-campaigns-repo-is-under-src
description: "The campaigns repo is ~/src/campaigns. ~/campaigns is a stale second copy whose rosters still have pre-#291 paths — don't verify campaign facts against it."
metadata: 
  node_type: memory
  type: reference
  originSessionId: 50eac868-9279-4dc6-930b-c9a8ba0fc5e3
  modified: 2026-08-14T14:38:02.174Z
---

There are **two** campaign trees on this machine and only one is the repo:

- `~/src/campaigns` — the git repo (`github.com/kostadis/campaigns`). It is what
  `/home/kroussos/src/CLAUDE.md` lists and what `tests/conftest.py`'s live-corpus
  fixtures resolve to.
- `~/campaigns` — a **stale copy**. Same campaign names, same directory layout, older
  contents.

**Why it matters:** the two disagree on facts you might go there to check, and the stale
one looks completely plausible. Measured 2026-08-14 while implementing feature 008:

| | `~/src/campaigns/Phandalin` | `~/campaigns/Phandalin` |
|---|---|---|
| `config/party.yaml` `sheet:` | `docs/party/soma.md` (campaign-root-relative, post-#291) | `../docs/party/soma.md` (config-relative, pre-#291) |

Reading the stale one produced a confident, wrong conclusion — that research D1's claim
"#291 rewrote all three divergent rosters campaign-root-relative" was false on disk, and
that `dnd_sheet` had to cope with two path conventions. All five rosters under
`~/src/campaigns` (Hillsfar, Phandalin, out-of-the-abyss, stormgiants, toee) are
campaign-root-relative. A code review caught it.

Consistent with the already-recorded OOTA case: `~/campaigns/out-of-the-abyss` is stale
too (see [[reference_oota_live_corpus_path]]), which suggests the whole `~/campaigns`
tree is an abandoned earlier location rather than one drifted directory.

**How to apply:** when checking anything about live campaign data — roster contents,
sheet filenames, what a migration will hit — read `~/src/campaigns`. If a finding there
contradicts a spec or a doc, check whether you read `~/campaigns` by mistake before
writing the contradiction down. Campaign PRs go to the `~/src/campaigns` repo.
