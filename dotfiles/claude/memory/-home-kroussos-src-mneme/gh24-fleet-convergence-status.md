---
name: gh24-fleet-convergence-status
description: "Where the GH#24 fleet-convergence work stands and the content reconciliation blocking the toee migration"
metadata: 
  node_type: memory
  type: project
  originSessionId: 78a3e3ba-7062-4ba6-9c69-673d340a3c0d
---

GH #24: make toee's 6-wing mempalace layout the fleet standard, then converge every campaign onto it.
Plan at `~/.claude/plans/whimsical-greeting-thimble.md`.

**Thread 1 (tooling) — DONE & MERGED.** recipe **v2.0.0** (`mempalace.recipe.v2.yaml`, `standard`
6-wing scaffold; `notes/`+`summaries/` are wings; `choose_pattern` wire-what-exists;
`consolidate_config`; `mneme mp faces`; `mneme mp drop-legacy --confirm`). Commit `f3596cb`.

**Feature 005 (multi-root + membership) — DONE & MERGED (2026-06-30).** This ANSWERS the old
"why is mneme single-root" blocker — it isn't anymore. `data_roots.campaigns` is now one-or-more trees
(scalar still valid); `mneme` discovers campaigns across all trees; `find` refuses to silently resolve a
name ambiguous across trees. Each campaign self-declares its owning mneme in `.mneme/owner.yaml`
(host-independent uuid, minted lazily into hypostasis.yaml); `mneme integrate <campaign>` claims it,
`mneme up` integrates-first/refuses-foreign; `--dir` override also exists. Built via full spec-kit flow in
worktree `~/src/mneme-005-multi-root` (branch `005-multi-root-campaigns`), 160 tests green.
**`main` now = `003 (×3) → 004-T1 → 005 (×2)` linear at `e824a23`, pushed to origin.** 005 depends on
004-T1 (recipe v2), so they merged together; the still-*unfinished* part of 004 is Thread 2+.

**Thread 2 (toee = "do 4") — NOT a content reconciliation (earlier framing was WRONG).** Per user
(2026-06-30): **`~/toee/toee` is a SPARSE CHECKOUT of `~/campaigns/toee`** — same `kostadis/campaigns.git`
content, sparse view scoped to `toee/`, NOT a divergent fork. The "157 diffs" I saw were just the two
checkouts being at different commits + uncommitted working changes + the sparse view — nothing to merge.
This is exactly why 005 was built: mneme used to require every campaign under one monorepo root; 005
removes that so mneme can point at the dedicated `~/toee` sparse tree. **Goal: mneme manages toee from
`~/toee/toee`, not `~/campaigns/toee`.** (End-state vision: each campaign its own sparse tree.)

**DONE (2026-07-01):** `~/src/mneme` runtime moved to `main` (005 live in `~/.venvs/main` — editable,
no pip reinstall needed). Real `~/.config/hypostasis/hypostasis.yaml`: `data_roots.campaigns` =
`[~/campaigns, ~/toee]`; `mneme:` identity `64cf8b36-e823-4b8e-8353-d08fe707f9be` minted (append-only).
`mneme integrate toee --dir ~/toee/toee` → wrote `~/toee/toee/.mneme/owner.yaml`. Now `~/toee/toee` =
**owned**, `~/campaigns/toee` = **unintegrated** (double-listed, cosmetic). mneme uses `~/toee/toee`. ✓

**Chosen overlap handling = `--dir` (user, 2026-06-30):** `~/campaigns` left untouched (no sparse surgery),
so `toee` is in both trees → name-based `mneme up toee` / `mneme mp … toee` are AMBIGUOUS; toee ops must
pass `--dir ~/toee/toee`. Durable de-dup (sparse-exclude toee from ~/campaigns) deferred.

**toee palace REBUILT FROM SCRATCH — DONE (2026-07-01).** Old 74M store discarded (`rm -rf
~/.mempalace/palaces/toee`), regenerated fresh from `~/toee/toee` only. Authority `~/toee/toee/.mneme/
mempalace.yaml`: recipe v2, **5 wings** (chronicle=docs/distill_extractions, prep=notes/sessions,
notes=notes, summaries=summaries, **toee=. promoted to `authoritative`/canon**) — no narrative (no
docs/chapters); disposition `scaffold.nomatch`=deliberate recorded. Restored curated `extra_exclusions`
(temple/ 788 files, docs/*_extractions/, planning_extractions/, archive/, *.pdf, *.tar.gz) that bootstrap
had dropped (root wing 1182→123 files). New store 24M, embedded Ollama qwen3-embedding:0.6b 1024-dim;
search verified (Hedrack query → hedrack_strategy.md cosine 0.61). `mneme mp status toee` all-ok. Done via
scoped temp config (`data_roots.campaigns=[~/toee]`) because mp subcommands lack `--dir`.

**mempalace chroma-import bug FIXED (uncommitted in ~/src/mempalace).** turbovec-only path was dying on
eager chromadb import (broken opentelemetry deps). Made chroma lazy/optional in 3 spots:
`backends/__init__.py` (PEP-562 `__getattr__`), `registry.py` `_register_builtins` (try/except) +
`_discover_entry_points` (debug-log, no traceback). NEEDS COMMIT to mempalace (pin 46fcfc2 → bump after).

**Pending commits/cleanup:** (1) ~/src/mempalace chroma fix; (2) ~/toee campaign repo — new authority +
rendered faces (config.yaml/.mcp.json/mempalace.yaml/.mempalaceignore/wing files) uncommitted; (3) delete
superseded pushed proposal branch `mneme/bootstrap-toee` on campaigns.git origin [DONE].

**`--dir` on mp subcommands — DONE (branch `feat/mp-dir-option`, commit 9c96927, closes #27; not yet
merged to main).** Added `discover.resolve()`/`ref_for_dir()`; `--dir/-d` on status/refresh/render/faces/
regenerate/backup/restore/bringup/drop-legacy (working-copy cmds publish/adopt/bootstrap/migrate unchanged).
So toee ops now work WITHOUT the temp config: `mneme mp <cmd> toee --dir ~/toee/toee` (also faster — skips
the tree crawl). 164 tests. Runtime checkout ~/src/mneme is currently ON this branch.

**recipe baseline_exclusions bug — FIXED (#28, branch `fix/recipe-baseline-exclusions` off main, commit
ae196a0, not merged).** Recipe excluded `ui_config.yaml` (wrong name) not `ui_state.yaml`, and missed
`refs.yaml`/`refs.local.yaml`/`.mneme/`/`.mcp.json`/`.dedup_state.json` → these leaked into the `<campaign>`
wing and were TOP search hits (bm25=0.0 noise). Fixed in-place on v2.0.0 (correction, no version bump).
toee re-rendered + re-mined clean (search `hedrack` → real content top, no config junk). Kept recipe
baseline generous (user choice A — excluding an absent file is a harmless no-op). Filed **#29**: durable
follow-up = compose exclusions from tool-declared outputs instead of the hand-maintained recipe list.

**#27 + #28 MERGED to main (2026-07-01, origin/main=6a2a8ef, both auto-closed); runtime ~/src/mneme now on
main with both.** Remaining open: **#26** (embedding-dim guard, unbuilt), **#29** (tool-declared
exclusions, unbuilt), **mempalace#20** (chromadb-lazy fix — UNCOMMITTED in ~/src/mempalace working tree,
land on kostadis-dev). ~/toee re-rendered faces COMMITTED (35f84aa; ui_state.yaml + a .reviewed file left
uncommitted — not mneme-managed). Filed **#30**: policy — gitignore derived mempalace faces (they're caches;
check-in caused the #28 per-campaign churn) + guarantee render-on-setup; track only authority/owner/config.yaml.

**Room-keyword curation is LOW-STAKES (verified in mempalace src, 2026-07-01).** Per-room wing
`keywords` are consumed ONLY by `detect_room()` (`miner.py:397-436`) at mine time to stamp a room LABEL
(cascade: folder-path → filename → content-keyword-score → fallback `general`). Nothing is dropped; every
doc is embedded+indexed regardless. Search NEVER uses these keywords — default retrieval is whole-palace
vector+BM25 over raw chunk content; `room=` is an optional caller filter; hierarchical pruning uses a
content/entity-derived room index, not authored keywords. So generic/wrong keywords cost ZERO recall — only
room-label accuracy (the optional room filter + browse views). Folder-path is priority 1, so well-organized
dirs route themselves. ⇒ **Do NOT build an LLM room-keyword curation skill** (not worth it); ship
bootstrap's generic rooms; porting old curated keywords is optional polish only. (Distinct from
`hall_keywords` in config.json → `detect_hall`, a separate content-TYPE axis.)

**Embedding endpoint changed (2026-07-01):** now Ollama at `http://192.168.1.121:11434` serving
`qwen3-embedding:0.6b` via OpenAI-compat `/v1` (was `openai-compat Qwen/Qwen3-Embedding-0.6B @
192.168.1.121:8000`). Both are 1024-dim → existing palaces stay QUERY-COMPATIBLE (only the EF-identity
string `openai-compat:{model} @ {endpoint}` changed, not the dimension). Set in the GLOBAL
`~/.mempalace/config.json` (`embedding_provider` kept `openai-compat`, `embedding_model` →
`qwen3-embedding:0.6b`, `embedding_endpoint` → `…:11434`); mneme's global_alias render merges, won't clobber.
Resolution order is env `MEMPALACE_EMBEDDING_*` → config.json → default; no env override set.
NOTE: fleet-wide `discover()`/`mneme mp status` is SLOW on the big monorepo trees (rglob per campaign over
node_modules etc.) — pre-existing, now over 2 trees; potential future optimization.

**toee chroma legacy DROPPED — DONE (2026-07-04).** The toee store was already turbovec but still
carried dead chroma leftovers (`chroma.sqlite3` 184K + `.blob_seq_ids_migrated`) from the earlier
migration; nothing read them (`MEMPALACE_BACKEND=turbovec` ambient + in hypostasis.yaml). Removed via
`mneme mp drop-legacy toee --dir ~/toee/toee --confirm` (dropped 2 items). turbovec bindings
(`mempalace_drawers`/`_closets`) + `knowledge_graph.sqlite3` + `.collection_type_fixed` untouched;
search verified (`temple of elemental evil` → extract_002.md cosine 0.666). NO regenerate (user: "just
the drop"). Note: `mp status`/`drop-legacy` WITHOUT `--dir` still hang on the fleet-wide rglob — always
pass `--dir ~/toee/toee`. Also: collections have no recorded embedder identity (warning only) — optional
`mempalace palace set-embedder --model qwen3-embedding:0.6b`.

**Filed #46 (2026-07-04):** hypostasis declares `MEMPALACE_BACKEND` but mneme's provisioning subprocess
doesn't honor it — `mneme/mempalace/runner.py` inherits only `os.environ`, never injects `entity.env`,
unlike `lifecycle.py:155` (CG path). So `mp bringup`/`regenerate` create whatever ambient backend is set,
not the hypostasis-declared one. Fix: thread `entity.env` through runner/provision/bringup. NOT yet built.

**Runbook after reconciliation:** point `data_roots.campaigns` at the winning tree(s) → `mneme integrate
toee` → author+human-review the 6-wing `.mneme/mempalace.yaml` → `mneme mp faces` → `backup` →
`regenerate --confirm` → `drop-legacy --confirm` → verify `mneme mp status toee` green. Then abyss,
phandalin (add chronicle), Hillsfar (greenfield `bringup`). Closes #21.
