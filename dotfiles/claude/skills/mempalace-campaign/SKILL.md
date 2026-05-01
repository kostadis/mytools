---
name: mempalace-campaign
description: Set up MemPalace (semantic search palace) for a D&D campaign workspace. Detects the campaign's folder structure, identifies document layers (narrative bible, extractions, grounding docs, pipeline inputs), proposes a wing/room architecture, handles exclusions, mines the docs, registers the MCP server, and writes a usage guide. Supports single-wing (simple campaigns) and three-wing (CampaignGenerator pipelines) architectures. Use when the user wants to add mempalace to a new campaign or asks to "set up mempalace" for a campaign directory.
tools: Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion
---

# MemPalace Campaign Setup

Set up a per-campaign semantic search palace using mempalace v3+. The goal is
a searchable index of the campaign's **synthesized, curated content** — not
raw session transcripts. Output is MCP tools available in-session plus a
`MEMPALACE.md` guide in the campaign root.

## Prerequisites

Before starting, verify mempalace is installed:

```bash
pip show mempalace
# or check venv locations
ls /home/kroussos/worldanvil_pipeline/venv/bin/mempalace 2>/dev/null
```

If not installed, tell the user: `pip install mempalace` (needs Python 3.9+).
Stop and report if installation fails.

Find the mempalace binary path — it's usually one of:
- `$(which mempalace)`
- `/home/kroussos/worldanvil_pipeline/venv/bin/mempalace`

Store as `$MP` for the rest of the workflow. The matching Python for MCP
registration is the sibling `python` in the same `bin/` dir.

## Required Information

1. **Campaign directory** — from args, or detect from CWD, or ask. This must
   be the campaign root (the dir that contains `docs/`, `summaries/`, etc.).
2. **Campaign name** — derived from the directory basename. This becomes the
   primary mempalace "wing" name (lowercased, no spaces).

## Workflow

### Phase 1: Survey the campaign structure

Use Glob + Bash `ls` to inventory the campaign dir. Identify:

- **Top-level dirs**: `docs/`, `summaries/`, `characters/`, `voice/`,
  `examples/`, `logs/`, `planning_extractions/`, `adventures/`, etc.
- **docs/ subdirs**: `npcs/`, `tracking/`, `background/`, `adventures/`,
  `dead/`, `*_extractions/`, `gdriveMD/`, etc.
- **Loose top-level files**: Which markdown docs live at the root of `docs/`?
- **Tooling files**: `config.yaml`, `ui_config.yaml`, `*.sh`, `script_run`,
  `.mcp.json`, `CLAUDE.md`

Report the structure back to the user briefly. Name the dirs you recognize
as raw-session-data candidates (typically `summaries/`, `logs/`, any dir with
VTT transcripts or per-session subdirs named by date).

### Phase 2: Identify document layers

This determines whether to use single-wing or three-wing architecture.
Look for:

1. **A narrative bible** — a large (1000+ lines) source-of-truth document
   that the pipeline uses as input. Typically organized by chapters or
   sessions. Examples: `NeverwinterExpansionismAndTheNorth.md`,
   `campaign_chronicle.md`, or any very large markdown file with `# Chapter`
   headings.

2. **Distillation/extraction intermediates** — structured extracts of the
   bible, organized by topic (NPCs, Factions, World Events, Locations,
   Threads). Typically in `docs/distill_extractions/` or similar. These
   are pipeline-generated, not hand-edited.

3. **Grounding docs** — final synthesized outputs used by the pipeline:
   `campaign_state.md`, `world_state.md`, `party.md`, `planning.md`.

4. **Pipeline rendering inputs** — files used only for narrative rendering,
   not for DM reference: `voice/`, `examples/`.

5. **Pipeline intermediates** — files that exist only as inputs to the next
   pipeline stage: `state_extractions/`, `party_extractions/`,
   `planning_extractions/`, `synthesize_npc/`.

Use **AskUserQuestion** to confirm what you found:

**"I found [large doc] which looks like a narrative bible, and [extraction
dirs] which look like structured extractions of it. Is this a
CampaignGenerator pipeline campaign? If so, I'll set up a three-wing
architecture: chronicle (timeline facts), narrative (prose), and
[campaign_name] (current state). Otherwise I'll do a single-wing setup."**

### Phase 3: Decide wing architecture

**Three-wing** (recommended for CampaignGenerator campaigns):

| Wing | Purpose | Source |
|------|---------|--------|
| `chronicle` | Structured timeline facts | Distill extractions |
| `narrative` | Prose retrieval by chapter | Chapter-split bible |
| `<campaign>` | Current reference state | Grounding docs, NPCs, tracking, etc. |

**Single-wing** (simple campaigns without a pipeline):

| Wing | Purpose | Source |
|------|---------|--------|
| `<campaign>` | Everything | All curated docs |

If three-wing, proceed to Phase 3a (split the bible). Otherwise skip to
Phase 4.

### Phase 3a: Split the narrative bible (three-wing only)

Create `docs/chapters/` directory. Split the narrative bible on its top-level
headings (`# Chapter NN ...` or similar) into individual files.

Rules:
- Preserve original text verbatim — no editing, no summarizing
- Name files with chapter number and slugified title:
  `chapter_00_neverwinter_expansionism.md`
- Handle inconsistent heading styles (some may have colons, trailing periods)
- **Do NOT modify or delete the original file** — the pipeline still uses it
- Count chapters and report to user

### Phase 4: Ask about exclusions

Use **AskUserQuestion** to confirm:

**Question 1 — Raw session data:** Is there a directory holding raw
session content (VTT transcripts, per-session folders) that gets synthesized
elsewhere?

**Question 2 — Archived content:** If a `dead/` or `archive/` dir exists,
include as historical reference or exclude?

**Question 3 — Google Drive imports:** If `gdriveMD/` or similar exists,
exclude? (Default: yes)

Skip these questions for dirs that don't exist. Don't ask about `logs/` —
always exclude operational logs.

### Phase 5: Write the exclusion file

Create `.gitignore` in the campaign root (mempalace respects gitignore).

**Always exclude:**
- Raw-session-data dir (e.g. `summaries/`)
- `logs/`
- Tooling files: `config.yaml`, `ui_config.yaml`, `*.sh`, `script_run`,
  `entities.json`, `--output/`, `tracking.txt`
- `.claude/`, `MEMPALACE.md`

**Three-wing additional exclusions (from root .gitignore):**
- `voice/`, `examples/` (pipeline rendering inputs)
- `docs/distill_extractions/` (mined separately as `chronicle` wing)
- `docs/state_extractions/`, `docs/party_extractions/` (pipeline intermediates)
- `docs/synthesize_npc/`, `planning_extractions/` (pipeline intermediates)
- The narrative bible file (replaced by chapter splits in `narrative` wing)
- `docs/chapters/` (mined separately as `narrative` wing)

The subdirectories are excluded from root because they have their own
`mempalace.yaml` and are mined as separate wings.

**Important:** If a `.gitignore` already exists, read it first and merge.

### Phase 6: Run mempalace init

```bash
$MP init --yes <campaign_dir>
```

This generates a default `mempalace.yaml`. You'll overwrite it in the next
step. It also creates `entities.json` (informational) which is already in
`.gitignore`.

If init fails, stop and report.

### Phase 7: Write mempalace.yaml files

**Single-wing:** Write one `mempalace.yaml` at the campaign root.

**Three-wing:** Write three `mempalace.yaml` files:

**`docs/distill_extractions/mempalace.yaml`** (chronicle wing):
```yaml
wing: chronicle
rooms:
- name: npcs
  description: NPC state snapshots across the campaign timeline
  keywords: [npc, character, dossier, location, state, faction]
- name: world
  description: World events, locations, faction movements
  keywords: [world, event, location, faction, history, alliance]
- name: arcs
  description: Threads, mysteries, and unresolved plot points
  keywords: [thread, mystery, unresolved, quest, score]
- name: general
  description: Content that doesn't fit other rooms
  keywords: []
```

**`docs/chapters/mempalace.yaml`** (narrative wing):
```yaml
wing: narrative
rooms:
- name: chapters
  description: Narrative prose chapters from the campaign chronicle
  keywords: [chapter]
- name: general
  description: Fallback
  keywords: []
```

**Root `mempalace.yaml`** (campaign reference wing):
```yaml
wing: <campaign_name_lowercase>
rooms:
- name: npcs
  description: NPC dossiers, character profiles, relationships, motivations
  keywords: [npcs, npc, dossier]
- name: party
  description: Player characters — sheets, backstories
  keywords:
  - characters
  - party
  - player
  - backstory
  # Add PC names as keywords
- name: arcs
  description: Quest tracking, arc scores, threat trackers
  keywords: [tracking, arc, quest, score, threat, campaign_arc]
  # Add villain/faction names as keywords
- name: adventures
  description: Future and in-progress adventure hooks
  keywords: [adventures, adventure, encounter, hook]
- name: dead
  description: Archived content
  keywords: [dead, archived, finished]
- name: world
  description: World state, lore, background, regional geography, politics
  keywords: [world_state, world, background, lore, region, history, faction]
- name: general
  description: Top-level docs that don't fit a specific room
  keywords: []
```

**Tailoring rules:**

1. **Drop rooms that don't apply.** No `adventures/` dir → no room.
2. **Add PC names to `party` keywords.** Glob `characters/` for basenames.
3. **Add villain/faction names to `arcs` keywords.** Pull from tracking files.
4. **Shared room names create tunnels.** Use `npcs`, `world`, `arcs` in both
   `chronicle` and reference wings to enable cross-wing graph traversal.

### Phase 8: Dry-run the mine

Preview classification before committing:

```bash
$MP mine <campaign_dir> --dry-run 2>&1 | tail -40
```

For three-wing, also dry-run the subdirectories:
```bash
$MP mine <campaign_dir>/docs/distill_extractions --dry-run 2>&1 | tail -20
$MP mine <campaign_dir>/docs/chapters --dry-run 2>&1 | tail -20
```

Check:
- Room distribution looks balanced
- No files from excluded dirs appear
- Core docs route sensibly

### Phase 9: Mine

**Single-wing:**
```bash
$MP mine <campaign_dir>
```

**Three-wing** (subdirectories BEFORE root):
```bash
# Chronicle wing (structured timeline)
$MP mine <campaign_dir>/docs/distill_extractions

# Narrative wing (prose chapters)
$MP mine <campaign_dir>/docs/chapters

# Reference wing (current state)
$MP mine <campaign_dir>
```

Order matters: root's `.gitignore` excludes subdirs to prevent double-mining.
Mine subdirs first.

Report the final drawer counts per wing/room.

### Phase 10: Register the MCP server (project-scoped)

```bash
claude mcp add mempalace -- <venv_python> -m mempalace.mcp_server
```

Run this from inside the campaign directory. Uses the venv's Python.

### Phase 11: Verify

```bash
$MP status
```

For three-wing, test each wing:
```bash
$MP search "<campaign-specific term>" --wing chronicle    # timeline
$MP search "<campaign-specific term>" --wing narrative    # prose
$MP search "<campaign-specific term>" --wing <campaign>   # current state
```

Confirm drawer counts match and search returns relevant hits from each wing.

### Phase 12: Write MEMPALACE.md

Create `<campaign_dir>/MEMPALACE.md` as a usage guide. Document:

1. **Wing architecture** — which wings exist and what each answers
2. **Quick reference** — CLI commands with the actual mempalace binary path
3. **Wing/room taxonomy tables** — rooms + what's in them + drawer counts
4. **Search patterns** — when to use `--wing chronicle` vs `--wing narrative`
   vs `--wing <campaign>` vs no filter
5. **What's excluded** — with rationale
6. **Refresh workflow** — how to re-mine per wing, and full rebuild steps
7. **Tuning guide** — pointer to per-wing `mempalace.yaml` files
8. **MCP tools** — primary tools and their uses
9. **Tunnel documentation** — which rooms bridge wings
10. **Troubleshooting** — missing palace, MCP tools not showing, segfaults
11. **Known quirks** — any mis-routed files

Use `/home/kroussos/campaigns/Phandalin/MEMPALACE.md` as reference template.

### Phase 13: Report

Tell the user:
- Total drawers + per-wing/room breakdown
- Wing architecture summary
- MCP server location
- Path to `MEMPALACE.md`
- Any classification quirks to tune later
- How to do a full rebuild: `rm -rf ~/.mempalace/palace/` then re-mine

## Key Principles

- **Curated over raw.** The palace's value is fast semantic lookup over
  human-verified content. Mining raw transcripts pollutes it.
- **Three-wing for pipeline campaigns.** If the campaign uses
  CampaignGenerator (narrative bible + extractions + grounding docs), use
  three wings: `chronicle` (timeline facts from extractions), `narrative`
  (prose from chapter splits), `<campaign>` (current state).
- **Single-wing for simple campaigns.** If no pipeline, one wing is fine.
- **Shared room names create tunnels.** Use `npcs`, `world`, `arcs` across
  wings to enable graph traversal between timeline snapshots and current
  dossiers.
- **Don't mine pipeline artifacts into the reference wing.** `voice/`,
  `examples/`, `*_extractions/` are pipeline inputs/intermediates, not DM
  reference material. Exclude from root, mine extractions separately.
- **The narrative bible stays untouched.** Split it into chapters for the
  narrative wing, but never modify or delete the original.
- **Mine subdirs before root.** Root's `.gitignore` excludes subdirs to
  prevent double-mining. Mine chronicle and narrative wings first.
- **Project-scoped MCP.** Each campaign gets its own MCP server.
- **No hooks by default.** Use `mempalace_add_drawer` for manual filing.
- **Dry-run before committing.** Always preview classification.
- **Palace clearing:** `rm -rf ~/.mempalace/palace/` then re-mine all wings.
  No built-in reset command.

## Ongoing Usage: Session Prep Workflow

After initial setup, the mempalace is used during session design. The key
pattern is **mine now, chronicle later** — session prep produces two kinds
of content that go to different places at different times.

### Mine Immediately (canon lore)

Content that is true about the world regardless of what happens at the table:

- **New NPCs** — `mempalace_add_drawer` in `<campaign>/npcs` + KG entries
  for relationships and traits
- **Backstory corrections** — `mempalace_kg_add` entries that update facts
- **World-building canon** — drawers + KG for mythology, faction structure,
  campaign-wide principles
- **NPC mechanics** — KG entries for crack conditions, DCs, reachability
  (these are designed, not emergent)
- **Strategic positions** — KG entries for who's watching whom on the board

### Do NOT Mine (planning documents)

Content that describes what *might* happen stays as note files, never enters
the mempalace:

- Session shape, beat structure, outcome branches
- Momentum/encounter mechanics
- Read-aloud notecards, DM checklists
- Arc design documents (custom arcs, level-band designs)

These are planning tools accessed via file reads or campaign MCP tools.

### Mine After the Session (chronicle beats)

After the session runs, add a chronicle entry capturing:

- What actually happened (which branch was taken)
- How NPCs actually behaved
- What the party chose and what it costs them
- Any new facts that emerged from play

This goes in the `chronicle` wing as an adventure beat, sourced from the
session transcript. Do not add chronicle entries before the session runs —
this confuses retrieval between planned and actual events.

### KG Predicate Vocabulary for Campaigns

Standard predicates (`member_of`, `killed_by`, `allied_with`) work for
basic facts. Campaign design needs a richer vocabulary:

**Character design:**

| Predicate | Use |
|-----------|-----|
| `cracked_by` | What reaches a character emotionally |
| `blind_spot` | What the character cannot see about themselves |
| `reachable_by` | Who can get through, with mechanical conditions |
| `key_question` | The line an NPC will deliver |
| `characterized_by` | A specific personal detail that makes them real |

**Strategic:**

| Predicate | Use |
|-----------|-----|
| `watching` | Who is tracking whom on the board |
| `strategic_position` | Board-level awareness |
| `motive_for_recruiting` | Why one entity uses another |
| `would_discard` | Disposability in an alliance |
| `crack_moment` | Designed turning point for a character arc |

**World-building:**

| Predicate | Use |
|-----------|-----|
| `believe_themselves_to_be` | Shared species/group belief |
| `function_as` | Role in the world |
| `is_actually` | Trope inversion |
| `maps_onto` | Real-world analogue informing the design |

### NPC Drawer Best Practices

Write full character profiles, not summaries. A future session searching
for a character needs the complete picture. Include:

- Identity and faction (name, rank, role in the scene)
- Motivation (why they're doing what they're doing)
- The crack (what reaches them, mechanical conditions if any)
- What doesn't work (what the party will try that won't land)
- After the scene (what happens to them next, how they evolve)

### What Does NOT Go in the Mempalace

| Content | Where It Goes |
|---------|---------------|
| Session prep, DM checklists, beat structures | `notes/` directory |
| Arc design documents | `notes/arc_cleanup/` or `notes/epic_tier/` |
| Published module tracking | `docs/tracking*.txt` |
| Outcome branches (speculative) | `notes/` directory |
| Read-aloud notecards | `notes/` directory |

The mempalace is for retrieval of what IS true. Notes are for what MIGHT
happen. Tracking files are published ground truth that is never modified.

## Failure Modes

- **"No mempalace.yaml found"** — running mine from wrong dir or init
  didn't complete. Each wing's source directory needs its own yaml.
- **Everything routes to `general`** — keywords too weak. Add folder names.
- **Extraction files all route to one room** — file-level routing picks up
  the first topic section (e.g. `## NPCs`). Content is still searchable;
  room filtering just doesn't help within that wing.
- **`planning_extractions/` routes to `arcs`** — room order wrong. Move
  `extractions` above `arcs`.
- **MCP tools don't appear** — server registered at wrong scope or Claude
  Code wasn't restarted. Check `~/.claude.json`.
- **Segfault on search** — Run `$MP repair`.
- **Stale content after doc edits** — re-mine the affected wing.
