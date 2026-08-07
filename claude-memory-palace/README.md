# claude-memory-palace

Mines Claude Code's auto-recall memories into a single MemPalace, backed by
[turbovecdb](https://github.com/kostadis/turbovecdb), so memories written in one
project are searchable from every other project.

## The problem

Claude Code keeps memories in one global directory plus one per project scope:

```
~/.claude/memory/                    # global
~/.claude/projects/<slug>/memory/    # per project
```

Only the *current* project's `MEMORY.md` index loads into a session. A memory
written while working in `CampaignGenerator` is invisible from `5etools-kostadis`.
There are 27 such directories on this machine holding 213 markdown files — one
palace over all of them turns siloed notes into cross-project recall.

## Setup (one time)

```bash
cd ~/src/mempalace          # branch: kostadis-dev
uv sync --extra turbovec    # installs the local editable ~/src/turbovecdb
```

`~/.mempalace/config.json` declares the palace and the backend:

```json
{
  "palaces": { "claude-memory": "/home/kroussos/.mempalace/palaces/claude-memory" },
  "backend": "turbovec"
}
```

`default_palace` is deliberately **absent**, so a command that forgets `--palace`
fails loudly with `PalaceNotDeclared` instead of silently reading or writing the
wrong palace.

## Usage

```bash
./mine-claude-memories.sh --dry-run   # preview
./mine-claude-memories.sh             # mine
```

Mining is append-only and idempotent, so re-running is how the palace is kept
fresh as new memories accumulate. Environment overrides: `MEMPALACE_REPO`,
`MEMPALACE_PALACE`, `MEMPALACE_BACKEND`, `CLAUDE_DIR`.

Search from the shell:

```bash
cd ~/src/mempalace
uv run mempalace --palace claude-memory --backend turbovec search "your query"
```

Or via MCP, registered at user scope so it is reachable from every project:

```bash
claude mcp add mempalace --scope user -- \
  /home/kroussos/src/mempalace/.venv/bin/mempalace-mcp \
  --palace claude-memory --backend turbovec
```

## Gotchas worth knowing

Each of these cost real debugging time; they are not hypothetical.

- **`--palace` and `--backend` are global flags** and must come *before* the
  subcommand: `mempalace --palace X mine DIR`, not `mempalace mine DIR --palace X`.
  The latter is an argparse error.

- **Use the project venv's absolute path for the MCP server.** A bare
  `mempalace-mcp` resolves via `$PATH` to `~/.venv/bin/mempalace-mcp`, which does
  **not** have `turbovecdb` installed. The registration above hardcodes
  `~/src/mempalace/.venv/bin/mempalace-mcp` for that reason. The MCP server does
  resolve palace *aliases* itself, so passing the bare alias `claude-memory` is
  safe and independent of the server's working directory.

- **The backend is a global setting, not a per-palace one.** A palace does not
  record which backend built it. Reading this palace without `--backend turbovec`
  falls through to chroma, finds an empty store, and returns **zero hits with no
  error**. The `backend` key in `config.json` is what makes the bare case safe.

- **Nothing is ever written into the source memory directories.** `~/src/claude-memory/sync.sh`
  rsyncs those dirs into a git repo and pushes on a cron, so a stray `mempalace.yaml`
  would be committed and propagated to the other machine. This is why setup skips
  `mempalace init` (the only command that writes into the *source* tree) and mines
  directly instead. Verify with `git -C ~/src/claude-memory status` after a run.

- **One memory dir is a symlink.** `~/.claude/projects/-home-kroussos-src-campaigns/memory`
  points into `~/src/mytools/dotfiles/claude/`. `os.walk` follows a symlinked top-level
  path, so it mines correctly — but plain `find` without `-L` will undercount it.

## Known upstream bugs (mempalace `kostadis-dev`)

Found while setting this up; both are in mempalace, not in this script.

1. **`palace set-embedder` ignores palace aliases.** `cmd_palace_set_embedder`
   (`mempalace/cli.py`) calls `os.path.abspath(os.path.expanduser(args.palace))`
   instead of `_resolve_cli_palace(args)` like every other command. Passing an
   alias creates a brand-new empty palace at `$CWD/<alias>` and writes there.
   `cmd_init` has the same defect. Workaround: pass an absolute path.

2. **The turbovec backend does not persist embedder identity.** `chroma.py`
   implements `get_stored_embedder_identity` / `set_embedder_identity`;
   `turbovec.py` implements neither, so it inherits the documented no-op default
   in `backends/base.py`. Consequences: every open of a turbovec palace warns
   `EmbedderIdentityUnknownWarning`, and `set-embedder` reports
   `✓ recorded embedder identity` for a write that never happened. Benign while
   only one embedding model is in use, but the guard that would catch a silent
   model swap is inert on this palace.
