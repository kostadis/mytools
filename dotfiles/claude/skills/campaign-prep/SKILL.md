---
name: campaign-prep
description: Load the current campaign's brief (the files the GM declared in mneme's corpus, normally docs/planning.md) plus a map of the rest of the corpus before session prep; everything else is searched, not loaded. Use when the user says "campaign prep", "prep mode", or invokes /campaign-prep.
tools: Read, Bash, Grep
---

# Campaign Prep Mode

Load the campaign's **brief** before any prep work (beats, encounters, NPC drafts, session arcs), and keep a map of where everything else lives.

The corpus plays three roles, and this skill treats each one differently:

| Role | Example | What this skill does |
|---|---|---|
| **The product** | `docs/planning.md` | Loaded in full at start (it is the brief) |
| **Navigation index** | `campaign_state`, `world_state`, `party` | Searched when needed, never loaded whole |
| **Evidence** | session summaries, NPC dossiers | Searched, then confirmed by reading the cited source |

Which files are the brief is the GM's declaration (`brief:` in `.mneme/corpus.yaml`), not this skill's. Out of the Abyss's grounding kind alone is ~786 KB (~200K tokens), which is why the rest is searched instead of loaded.

## Workflow

### 1. Get the brief from mneme

Run from inside the campaign workspace mneme owns (`~/obelisk/obelisk`, `~/toee/toee`, `~/out-of-the-abyss/out-of-the-abyss`, `~/phandalin/Phandalin`):

```bash
python3 ~/.claude/skills/_shared/corpus/corpus_files.py --brief
```

Output (tab-separated):

```
# campaign: NAME
BRIEF  KINDS  TRUST  BYTES  /absolute/path          ← load these, in this order
MAP    KIND   TRUST  FILES  BYTES  SEARCHABLE-FILES  standard|extra   ← where everything else is
```

**If the helper prints `REFUSE:` (exit 2), stop.** Show the GM mneme's message verbatim. Do not read `docs/planning.md` or any other file by name, do not glob `docs/`, and do not load a whole kind instead. Common causes:

- `declares no brief:`: the GM has not declared a brief. The remedy, the GM's to run, is `mneme corpus migrate-brief CAMPAIGN` (preview), then `--apply`.
- `campaign declares no corpus` / `campaign workspace not found`: this campaign is not managed by mneme. This skill does not work there.
- `store alias ... claimed by 2 campaigns`: you are in a second or stale checkout (e.g. `~/src/campaigns/<name>`). `cd` to the workspace mneme owns.
- `brief-unavailable` / `not on disk`: a brief file is outside this sparse checkout or missing. Report it; do not substitute.
- `invalid`: the corpus has findings. Point the GM to `mneme corpus check CAMPAIGN`.

### 2. Read every BRIEF file

In a single message, issue one Read call per BRIEF path. Read each in full unless it is enormous (>2000 lines); then read the head and tail and say the middle was skipped. These are the **only** files loaded up front.

### 3. Keep the MAP

Hold the MAP rows as the index of what else exists. Do not read those files now. When prep needs a fact the brief does not give:

1. **Search the palace.** Call the campaign's `mempalace_search` (the `mempalace` server in the campaign's `.mcp.json`) with keywords as `query` and `wing` set to the MAP kind (`grounding`, `summaries`, `npcs`, `party`, `prep`, …). A corpus-built palace mines each kind into the wing of the same name, **except** that a file declared in two kinds is mined only once, under one of them: `docs/party.md` is in both `party` and `grounding` and lives in the `grounding` wing, and toee's `arcs` files live in `prep`. So if a wing-filtered search comes back empty, repeat it with no `wing` before concluding the fact is absent.
2. **Confirm by reading the source.** A search hit is a pointer. Read the cited file, only the section you need (Grep for the heading or name, then Read with an offset), before stating the fact.
3. **Follow grounding citations to the evidence.** Grounding lines carry citations like `[ch 042 / …]` into the session summaries. Where a grounding document and a summary disagree, the summary wins.
4. **A kind with `SEARCHABLE-FILES` 0 is not in the palace** (PDFs, images, skip-named files). To find a file in it, list the kind with `python3 ~/.claude/skills/_shared/corpus/corpus_files.py KIND` and Grep or Read the specific file. Use the same command whenever you need a kind's exact file list; never glob.

### 4. Acknowledge readiness

After the reads complete, give a short status (3–6 lines):

- Campaign name (from `# campaign:`)
- The most recent session / chapter planning.md covers
- Open threads or near-term beats flagged in planning.md
- One line on the map: e.g. "Searchable: summaries (214), npcs (103), grounding (13), …"
- "Ready for prep — what are we working on?"

If planning.md does not say where the party is right now, say so rather than searching for it now. The user's next message is the prep task.

Do NOT summarize the docs in detail. The point is to load the brief, not to produce a written briefing.

### 5. Stay in prep mode

For the rest of the conversation:

- Cite specifics from the brief or from a source you read, never from memory
- If a fact is in neither, search (step 3) before saying it is unknown, and say so before fabricating
- Session summaries are the authority: where a grounding doc and a summary disagree, the summary wins. Voice files (`voice/`) are authoritative for how a character speaks
- Ignore `docs/chapters/`. The chapter splits were made to review the campaign bible and are not canon; never cite them

## Notes

- The brief and map come from `mneme corpus brief` on every run (mneme spec 009, mytools#87): never from `.mneme/corpus.toc.json`, a glob, or a remembered path. The helper follows mneme's consumer obligations 4–5 (`mneme/recipes/instructions/manage-mempalace.md`).
- This skill only reads. It never writes to the corpus, the brief, or the grounding docs, which are regenerated by CampaignGenerator pipelines.
- Managed campaigns today: obelisk, toee, out-of-the-abyss, Phandalin. Anything else refuses, by design.
