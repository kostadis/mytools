# drive-tagger

An agentic, LLM-in-the-loop tagger for Google Drive.

A [Cursor SDK](https://cursor.com/docs/sdk/python) agent autonomously calls MCP
tools to process your Drive one file at a time: it pulls a file, embeds it
locally, retrieves the most similar already-seen files and the most relevant
existing categories from [turbovecdb](https://github.com/kostadis/turbovecdb),
then reasons about whether the file joins existing categories or needs new ones,
and records a rich set of connections - multiple categories per file plus typed
file-to-file links. All Google Drive I/O goes through the Rust
[`gdrive-cli`](https://github.com/kostadis/mytools/tree/main/gdrive-cli);
durable state lives in turbovecdb plus a small SQLite graph, so the agent can be
stopped and resumed without losing work.

## Architecture

```
LLM agent (cursor / anthropic / openrouter / dgx)
         |
         +--MCP stdio-->  drive-tagger MCP server  -->  gdrive-cli (Rust)  -->  Google Drive
                                   |
                                   +-->  turbovecdb (documents + categories)
                                   +-->  graph.sqlite (file-to-file links)
```

The agent loops over these tools:

1. `next_file` - pull the next unprocessed file (extract text, embed, store)
2. `find_similar` / `search_categories` / `list_categories` - retrieve context
3. `create_category` - add a new theme when nothing fits
4. `assign_categories` - attach the richest fitting set of categories
5. `link_files` - record typed relationships (supersedes, part-of, related-to, ...)

## Prerequisites

1. **gdrive-cli** built and authorized:
   - Clone and build: `cargo build --release` in `mytools/gdrive-cli`.
   - Put your Google OAuth Desktop client at `~/.config/gdrive-cli/credentials.json`.
   - Run `gdrive-cli google scan` once to mint `token.json` / `token-write.json` (browser consent).
   - drive-tagger looks for the binary at `../gdrive-cli/target/release/gdrive-cli` (sibling in mytools); override with `DT_GDRIVE_CLI`.
2. **LLM backend** — pick one:
   - **Cursor** (default): `export CURSOR_API_KEY=...` (Cursor Dashboard → Integrations).
   - **Anthropic/Claude subscription**: `ant auth login` once, then `export DT_PROVIDER=anthropic`. No API key env var needed.
   - **OpenRouter**: `export OPENROUTER_API_KEY=... DT_PROVIDER=openrouter DT_MODEL=anthropic/claude-haiku-4.5`.
   - **DGX Spark**: `export DT_PROVIDER=dgx` (uses `http://192.168.1.147:8001/v1` by default; override with `DT_DGX_ENDPOINT`).
3. **Optional local fast-path**: if Google Drive for Desktop is mounted, set `DT_USE_MOUNT=1` (and `DT_DRIVE_MOUNT`, default `/mnt/g`) to read synced binaries locally instead of downloading.

## Install

```bash
uv sync
```

This installs `cursor-sdk`, `mcp`, `fastembed` (local ONNX `all-MiniLM-L6-v2`
embeddings, no torch), the document parsers, and `turbovecdb` (editable, from
`../../turbovecdb`, a sibling of the mytools checkout).

## Usage

```bash
# 1. List your Drive into data/scan.jsonl
uv run drive-tagger scan            # add --all-drives for shared drives

# 2. Run the agent (dry-run: writes to turbovecdb + graph, NOT to Drive)
uv run drive-tagger run

# 3. Inspect progress and the taxonomy
uv run drive-tagger status
uv run drive-tagger report          # writes reports/DRIVE-TAGS.md, categories.json, graph.json

# 4. When happy, also write tags to Drive appProperties
uv run drive-tagger run --execute
```

Scope a first run cheaply with a folder and a small budget:

```bash
DT_FOLDER_ID=<drive-folder-id> DT_MAX_FILES=10 uv run drive-tagger run
```

### Tunables (environment variables)

| Var | Default | Meaning |
| --- | --- | --- |
| `DT_PROVIDER` | `cursor` | LLM backend: `cursor`, `anthropic`, `openrouter`, `dgx` |
| `DT_MODEL` | `claude-haiku-4-5` | Model id for cursor / anthropic / openrouter. For openrouter use the namespaced id, e.g. `anthropic/claude-haiku-4.5`. |
| `DT_DGX_MODEL` | `Qwen/Qwen3-Next-80B-A3B-Instruct-FP8` | Model id for the DGX backend (verify with `/spark-status`) |
| `DT_DGX_ENDPOINT` | `http://192.168.1.147:8001/v1` | OpenAI-compat base URL for the DGX Spark chat endpoint |
| `OPENROUTER_API_KEY` | (unset) | Required when `DT_PROVIDER=openrouter` |
| `DT_OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Override the OpenRouter endpoint |
| `DT_EMBED_PROVIDER` | `local` | Embedding backend: `local` (fastembed, 384-dim) or `dgx` (Ollama on spark2, 1024-dim). **Switching requires `drive-tagger reset`** and setting `DT_EMBED_DIM` to match. |
| `DT_DGX_EMBED_ENDPOINT` | `http://192.168.1.121:11434/v1` | Ollama OpenAI-compat base URL for DGX embeddings (spark2) |
| `DT_DGX_EMBED_MODEL` | `qwen3-embedding:0.6b` | Embedding model id served by Ollama on spark2 |
| `DT_EMBED_DIM` | `384` | Vector dimension — must match the embed model (384 for local MiniLM, 1024 for qwen3-embedding:0.6b) |
| `DT_SIMILAR_K` | `8` | neighbors / categories retrieved per file |
| `DT_MAX_FILES` | `50` | max files processed per `run` invocation |
| `DT_MAX_CHARS` | `12000` | max characters embedded per file |
| `DT_FOLDER_ID` | (unset) | restrict the worklist to direct children of this folder |
| `DT_ALL_DRIVES` | `0` | include shared drives in `scan` |
| `DT_USE_MOUNT` | `0` | read synced binaries from the local Drive mount |
| `DT_GDRIVE_CLI` | `../gdrive-cli/.../gdrive-cli` | path to the gdrive-cli binary |

## Notes

- `appProperties` written to Drive (`dt_categories`, `dt_run`) are app-private:
  searchable via the API but not shown in the Drive web UI. The human-readable
  artifact is `reports/DRIVE-TAGS.md`.
- Re-running only processes new or changed files (tracked by md5 / modified time
  in turbovecdb), so there is no full re-cluster pass.

## License

MIT.
