# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Personal dotfiles for Claude Code. The `claude/` directory is the source of truth — individual paths under `~/.claude/` are symlinks pointing into `claude/` here, so every edit is automatically git-tracked. There is no build, test, or lint step; changes take effect the next time Claude Code loads the config or the skill is invoked.

**The symlinks are per-machine and are not created by anything in this repo.** A fresh checkout does nothing on its own — someone has to link the paths by hand. Verify with `ls -l ~/.claude` before assuming an edit here is live; a machine where `~/.claude/skills` is a real directory is silently running a different config from the one in git.

The current link set:

| Path under `~/.claude/` | Kind | Target |
|---|---|---|
| `CLAUDE.md` | symlink | `claude/CLAUDE.md` |
| `settings.json` | symlink | `claude/settings.json` |
| `skills/` | symlink (whole dir) | `claude/skills/` |
| `agents/` | symlink (whole dir) | `claude/agents/` |
| `plugins/blocklist.json` | symlink | `claude/plugins/blocklist.json` |
| `plugins/known_marketplaces.json` | symlink | `claude/plugins/known_marketplaces.json` |
| `plugins/marketplaces/` | **real dir, not linked** | — |
| `hooks/` | **real dir, not linked** | — |
| `memory/`, `projects/*/memory/` | **real dirs, not linked** | owned by `~/src/claude-memory` |

`skills/` and `agents/` are linked as whole directories, so a new skill written to `~/.claude/skills/<name>/` lands in this repo automatically.

## The authored content

- `claude/CLAUDE.md` — the user's **global** Claude Code instructions, loaded into every session's context. This is distinct from the repo-root `CLAUDE.md` you are reading right now, which describes the dotfiles repo itself. Its last line is `@RTK.md`, an import of a file that **does not exist** in this repo or in `~/.claude/` — a dangling import inherited from an older machine. Either add `claude/RTK.md` or drop the line.
- `claude/settings.json` — user-level settings: `model: sonnet`, `advisorModel: opus`, `effortLevel: xhigh`, `theme: dark`, `tui: fullscreen`, `permissions.defaultMode: auto`, the `frontend-design` plugin, and two independent hook families (below).
- `claude/skills/<name>/SKILL.md` — 24 user-invocable skills. See the catalogue below.
- `claude/agents/<name>.md` — custom subagent definitions (`kostadis-architect`, `ux-reviewer`).
- `claude/plugins/blocklist.json`, `claude/plugins/known_marketplaces.json` — plugin marketplace config. **Caveat**: Claude Code refreshes these files periodically. Because they are symlinked, those refreshes land in the repo and produce a dirty working tree. Either `git checkout --` them or fold the refresh into the next commit.

**Not authored, not touched:**
- `claude/plugins/marketplaces/claude-plugins-official/` is a **vendored mirror** of the upstream Anthropic plugin marketplace. Do not hand-edit. The live copy at `~/.claude/plugins/marketplaces/` is a separate real directory that Claude Code auto-updates — it is deliberately *not* symlinked to the repo, because auto-refresh churn would overwhelm git. The repo's snapshot will drift behind; refresh it as a separate chore if needed.
- Ephemeral runtime data (`backups/`, `cache/`, `history.jsonl`, `projects/`, `sessions/`, `plans/`, etc.) is listed in `claude/.gitignore` and stays in `~/.claude/` as real files, not symlinks.

### Hooks — a tracking gap

`settings.json` wires up two unrelated hook families:

- **`cbm-*`** (`PreToolUse` on `Grep|Glob`, `SessionStart`, `SubagentStart`) — the codebase-memory discovery gate and session reminders. The scripts live in `~/.claude/hooks/` and are **not tracked in this repo**. `settings.json` therefore references executables a fresh checkout will not have, and the hooks fail silently when they are missing. Track `claude/hooks/` if these matter.
- **`Stop` / `PreCompact`** — MemPalace diary checkpoints, at `$HOME/src/Mempalace/hooks/`. Note the capital `M`: an earlier version of this file pointed at `$HOME/src/mempalace/`, which does not exist on a case-sensitive filesystem, so both hooks silently no-op'd. Keep the capitalisation.

## Memory is NOT managed by this repo

Per-project auto-recall memory (`~/.claude/projects/<slug>/memory/`) and user-level memory (`~/.claude/memory/`) are owned by a **separate repo, `~/src/claude-memory`** ([github.com/kostadis/claude-memory](https://github.com/kostadis/claude-memory)), which syncs them across all machines via `~/.claude/bin/sync-memory.sh` on a 30-minute cron. Do not symlink memory into this repo — it would be tracked in two places at once.

How that repo works:

- Each machine owns exactly one namespace, `machines/$(hostname)/`, and writes only there — so no two machines can clobber each other.
- `bin/sync-memory.sh` pushes the local `~/.claude/memory/` and every `~/.claude/projects/*/memory/` into that namespace, then **union-merges** every *other* machine's namespace back into the live tree (`rsync --update`, never `--delete`; `MEMORY.md` is dedup-unioned line by line). `--pull-only` imports without touching origin.
- Deletion is a two-phase consensus protocol, not an rsync side effect: `--mark-delete <path>` records intent in `machines/<host>/deletions.wal` and removes the file locally; `bin/reap-deletions.sh` only truly removes it once **every** machine has marked it.
- `machines/<hostname>/slugmap` rewrites inbound project slugs. This matters here because the other machines (`MyDell2024`, `SiliconValley`) run as user `kroussos` while this one (`Linux-Alien`) runs as `kostadis`, and the campaign trees sit at different paths. Without the map, foreign memory lands under slugs this machine never opens. Unmapped slugs are dropped (`* skip`), so **adding a new project tree means adding a slugmap line** or its memory silently never loads.

`claude/memory/` used to be tracked here as well. That made mytools a second authority: the copies drifted, and the cron wrote foreign machines' files into this working tree through a symlink. Those files have been deleted and `memory/` is now listed in `claude/.gitignore` — **do not re-add it.** Memory belongs to `claude-memory`; this repo owns config, skills, and agents.

## Skills catalogue (`claude/skills/`)

29 skills. Most support the D&D campaign pipeline in the user's `CampaignGenerator` and `campaigns` projects; a few are infrastructure. They are independent of each other except where noted — there is no shared runner or layered pipeline.

**Session pipeline, in rough order of use** (gm-assist → session summary → scene extractions → narration, with a human gate between stages):

- `campaign-prep` — loads the four grounding docs (campaign_state, world_state, planning, party) before session prep.
- `gmassist-precheck` — pre-extraction pass over gm-assist + VTT, before any per-scene extraction.
- `scene-extract` — runs `scene_extract` over a session VTT when one person voices several PCs: builds the voicing map, picks an attribution strategy at a human checkpoint, then hands back a speaker-attribution review queue.
- `chapter-summarise` — the no-recording branch: builds `session-summary.md` straight from chapter *prose* (one Haiku subagent per chapter, Opus orchestrating), then gates every output on a deterministic verifier the GM reviews — never the model's self-report.
- `consistency-check` — checks one session document against the campaign's context files.
- `staged-consistency` — runs the check at *every* pipeline boundary with a human-review gate between stages.
- `session-summary-consistency` — quote-level check on `scene_extractions_new/`; flags VTT transcription errors in verbatim quotes.
- `voice-smooth` — renders verbatim quotes into readable in-voice prose (`scene_extractions_smoothed/`), guard-railed by each character's voice file.
- `voice-critic` — flags generic prose and voice drift in generated narration.
- `scrub` — propose→review→apply removal of mechanical residue (DC/AC/HP, table-speak) from finished narration. Deliberately human-gated: it replaced an autonomous LLM pass after that pass stripped spell names (CampaignGenerator issue #151).

**Narration inputs:**

- `voice-file` — per-character voice notes for `session_doc.py`.
- `voice-examples` — per-character style examples, so narrators sound distinct.
- `style-examples` — campaign-level style references.
- `fable-narration` — writes the whole POV-rotating `session-summary-fable-doc.md` in one pass from `scene_extractions_smoothed/`, with the recurring `voice-critic` findings baked in as up-front constraints instead of fixed afterwards.

**Entity and canon management:**

- `registry-cleanup` — audits and repairs a registry that has recorded transcription garblings as aliases. Enforces the rule that an alias is an approved canonical alternate name, never a misspelling; every removal, merge and rename is GM-confirmed.
- `entity-triage` — rules on the UNKNOWN-surface-form queue from `registry.py triage-candidates`; writes to `docs/entity_registry.yaml`.
- `ensemble-alias-review` — resolves undecided alias groups with campaign-lore context, one at a time.
- `ensemble-type-merge` — merges dossiers for one entity extracted under multiple `(type, subject)` keys.
- `dossier-merge` — dedupes NPC dossiers in `docs/npcs/`.
- `module-inventory` — extracts a proper-noun inventory from a module's source (prose bible or 5etools JSON).
- `mempalace-campaign` — sets up MemPalace semantic search over a campaign workspace.

**Transcripts:**

- `audio-to-vtt` — re-transcribes a session's Zoom `.m4a` into a more accurate VTT via faster-whisper on the DGX Spark, anchored on the campaign's proper-noun vocabulary.
- `vtt-spell-pass` — applies the known-misspellings glossary to Otter/Zoom VTTs and prompts on unrecognised proper nouns.

**Infrastructure:**

- `codebase-memory` — structural code queries against the codebase knowledge graph.
- `spark-status` — loads current DGX Spark models, endpoints, ports, containers into context.
- `spark-status-conform` — reconciles live Spark state against `current-setup.md` and resolves the drift.
- `cognee-quickstart` — Cognee project setup and troubleshooting.
- `drive-consolidate` — interactive merge of near-duplicate drive-tagger categories.
- `drive-consolidate-links` — the same treatment for drifted file-to-file *link relations*, one relation family at a time. Never auto-merges directional antonyms.

A recurring design principle across these: **the LLM proposes, the human rules, a deterministic step applies.** `scrub`, `entity-triage`, `ensemble-type-merge`, and `module-inventory` all separate a regex/deterministic candidate pass from an LLM description pass from a human confirmation gate. Preserve that separation when editing them — collapsing it is what caused issue #151.

## Agents (`claude/agents/`)

- `kostadis-architect.md` — forensic architectural review using the Kostadis Doctrine (Split-Brain, Optimistic Lies, Fragmented State, Infrastructure Proxy anti-patterns). Invoked via the `Agent` tool with `subagent_type: "kostadis-architect"`.
- `ux-reviewer.md` — UX analysis agent for web frontends. Reads Vue/React/HTML source and produces a structured report with dimension scores and prioritised findings.

Agent files use Claude Code's subagent frontmatter format (name, description, tools, model). Edit in place; they are picked up on the next session.

## Working on skills

- Skills are discovered by filename: `claude/skills/<skill-name>/SKILL.md`. The frontmatter `description` is what Claude Code shows to the model when deciding whether the skill is relevant — keep it specific and trigger-word-rich.
- `allowed-tools` / `tools` in frontmatter is an allowlist. Skills that gate on the user need `AskUserQuestion`; skills that shell out to their helper scripts need `Bash`.
- `argument-hint` is user-facing; `$ARGUMENTS` at the bottom of the skill body is where the user's invocation text gets substituted.
- Seven skills ship **helper Python scripts** next to `SKILL.md` — `vtt-spell-pass` (10), `scrub` (4), `dossier-merge`, `ensemble-type-merge`, `module-inventory`, `registry-cleanup` (2 each), and `chapter-summarise` (1). These are the deterministic halves of the propose/apply split; the SKILL.md invokes them by path. Keep script and prose in sync when changing either.
- There is nothing to "run" or "test" locally. Because `~/.claude/skills` is a directory symlink, an edit here is live in the next session — start a fresh Claude Code session and invoke the skill.
