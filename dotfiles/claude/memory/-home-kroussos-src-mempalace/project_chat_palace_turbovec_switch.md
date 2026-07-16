---
name: project-chat-palace-turbovec-switch
description: Plan + findings for switching the chat palace from chroma to the turbovec backend
metadata: 
  node_type: memory
  type: project
  originSessionId: bc0ac169-8562-4710-baae-8a8128dfde5a
---

**STATUS: DONE (2026-05-31).** The **chat** palace (`~/.mempalace/palaces/chat`) now runs
on the **turbovec** backend. Migrated 37,434 drawers + 4,014 closets into
`<palace>/turbovec/` with exact id-parity vs chroma; live turbovec search verified. Read
path (campaigns MCP server) + write path (Stop/PreCompact hooks) both flipped to
`MEMPALACE_BACKEND=turbovec`. Old `chroma.sqlite3` (335 MB) left intact as frozen backup.
Config backups: `~/.claude.json.bak-turbovec-*`, `~/.claude/settings.json.bak-turbovec-*`.
Full effect after the `~/campaigns` MCP server restarts (new session / `/mcp reconnect`).
Footgun: a manual `mempalace mine` with no `MEMPALACE_BACKEND` set defaults to chroma →
writes the OLD frozen store; export `MEMPALACE_BACKEND=turbovec` for manual chat mines.
Below = the working record.

Goal (started 2026-05-31, branch `turbovec-backend`): switch the **chat** palace
(`~/.mempalace/palaces/chat`) from the chroma backend to the new **turbovec** backend.

**How backend selection works.** `palace.py` resolves `_DEFAULT_BACKEND` once from
`MEMPALACE_BACKEND` env var (via `registry.resolve_backend_for_palace`). Priority:
explicit > config > env > on-disk detect > default(`chroma`). turbovec stores under
`<palace>/turbovec/`; chroma stores in `<palace>/chroma.sqlite3` — **separate stores**.
So flipping the backend gives an EMPTY turbovec palace until data is migrated; the
chroma data is NOT deleted (reversible either way).

**Two paths must both switch backend** (else write/read disagree):
- WRITE: Stop/PreCompact hooks run `mempalace --palace $MEMPAL_CHAT_PALACE mine ...`
  (hook: `hooks/mempal_save_hook.sh`, line ~198; chat palace hard-pinned via
  `MEMPAL_CHAT_PALACE`). Needs `MEMPALACE_BACKEND=turbovec` in the hook env.
- READ: the mempalace MCP server. **Note:** the registered MCP server for the
  mempalace project points at `campaign-dev`, NOT chat. Config lives in `~/.claude.json`
  at `projects/<dir>/mcpServers/mempalace/env` (has MEMPALACE_EMBEDDING_*). Add
  `MEMPALACE_BACKEND=turbovec` there for whichever reader targets the chat palace.

**BLOCKER 1 — RESOLVED (2026-05-31).** Installed `turbovecdb` 0.1.0 (+ `turbovec`
0.7.0 engine) editable into BOTH `/home/kroussos/src/mempalace/venv` and
`/home/kroussos/worldanvil_pipeline/venv`. Both venvs' mempalace editable installs had
**stale entry-point metadata** (only `chroma`) — had to re-run `pip install -e
~/src/mempalace --no-deps` in each to regenerate `.dist-info` so the `turbovec` entry
point registers. Now `available_backends()` == `['chroma','turbovec']` in both. (Both
venvs share the same source tree `~/src/mempalace/mempalace`; worldanvil was on stale
mempalace 3.3.2, now 3.3.5.)

**BLOCKER 2 — hook write path already broken.** hook.log shows
`mempalace: command not found` at every save trigger — bare `mempalace` is not on the
hook's PATH. Chat auto-saves are currently failing regardless of backend. Fix the hook
to use an absolute binary (e.g. `$MEMPAL_PYTHON -m mempalace` or the venv's
`mempalace`).

**Existing data — migration can be LOSSLESS.** chat `chroma.sqlite3` (335 MB) has
41,396 embeddings, **dim 768**, in collections `mempalace_drawers` + `mempalace_closets`.
Embeddings live in chroma's `embeddings` table → a migrator can copy
id/document/metadata/vector straight into a turbovec collection with NO re-embedding.
**No chroma→turbovec migration tool exists yet** — would need writing (turbovec
`col.add(ids=, documents=, metadatas=, vectors=)`).

**Open decision for the user:** migrate the 41k existing drawers (honors the
"never forget / 100% recall / verbatim" mission) vs start the turbovec palace fresh
(chroma data stays on disk untouched, reversible, but invisible to the running system).
Recommend migrate — it can be lossless and fast (no re-embed).

**Exact switch points (verified 2026-05-31).** Backend is env-driven only (no
`--backend` CLI flag); `MEMPALACE_BACKEND` resolves `_DEFAULT_BACKEND` at import. Must
scope turbovec to exactly two processes — a global env var would wrongly force
`campaign-dev` (this project's MCP server, stays chroma) onto turbovec.
- READ path = the `/home/kroussos/campaigns` MCP server (no `--palace` → `default_palace:
  chat`; cmd `worldanvil_pipeline/venv/bin/python -m mempalace.mcp_server`). Flip: add
  `MEMPALACE_BACKEND: turbovec` to its `env` in `~/.claude.json`
  (`projects/<campaigns>/mcpServers/mempalace/env`).
- WRITE path = Stop + PreCompact hooks in `~/.claude/settings.json`. Both hooks call
  bare `mempalace --palace $MEMPAL_CHAT_PALACE mine` — which fails ("command not found")
  because the venv isn't on the hook's PATH. Fix at deployment layer: prefix BOTH hook
  commands with `MEMPALACE_BACKEND=turbovec PATH=/home/kroussos/worldanvil_pipeline/venv/bin:$PATH `
  (sets backend AND makes bare `mempalace` resolve). No committed-script edits needed.
  (Underlying script bug FIXED in repo on `turbovec-backend`: both hooks now resolve the
  CLI via a `MEMPAL_CLI` array — `"$MEMPAL_PYTHON_BIN" -m mempalace` when that interpreter
  has mempalace (find_spec probe, ~13ms), else bare `mempalace` on PATH — so they no longer
  depend on `mempalace` being on PATH. Verified end-to-end: mining a real transcript with
  `MEMPALACE_BACKEND=turbovec` writes a turbovec store and no chroma store. Uncommitted.)
- No SessionStart hook exists → no startup-injection reader to flip.

**Migration tool written:** `scripts/migrate_chroma_to_turbovec.py` (new, untracked).
Auto-picks per collection: copy vectors when chroma can read them (closets, 4014), else
re-embed verbatim docs (drawers, 37382, drawer vectors corrupt). Re-runnable; skips
collections already at parity. Run with the mempalace venv python.

Embedding stack: openai-compat, `nomic-ai/nomic-embed-text-v1.5`, endpoint
`http://192.168.1.147:8000` (the Spark). turbovec backend resolves mempalace's
embedding fn lazily as turbovecdb's `embedder`.

Related: [[project_campaign_dev_palace]], [[project_palace_isolation_feature]].
