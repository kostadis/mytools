---
name: dossier-merge
description: Deduplicate NPC dossier files produced by CampaignGenerator's `planning.py --build-dossiers`. Auto-clusters filenames by similarity heuristics, surfaces unclustered files and garbage/compound filenames, reads and auto-classifies each cluster (strict subset / merge / different NPCs), confirms with the user in batches of 3–5 grouped by heuristic type, writes canonical files with aliases recorded in BOTH YAML frontmatter (for `planning.py --synthesize`) and the body Identity section (for human readers), tars up the originals as a safety net before any destructive operation, and persists state so restarts remember past "keep both" decisions. Use when the user asks to "dedupe dossiers", "merge NPCs", "clean up docs/npcs/", or has just run `--build-dossiers`. Invoke as /dossier-merge [dossier-dir].
tools: Read, Glob, Grep, Edit, Write, Bash, AskUserQuestion
---

# Dossier Merge Workflow

Deduplicate a directory of per-NPC dossier files. `planning.py --build-dossiers` splits extractions on exact `## <name>` section headers, so transcription typos, alias-as-filename, role-as-filename, compound filenames (LLM-concatenated spellings), and garbage filenames (LLM error responses saved as files) all produce duplicate dossiers. The skill's job is to collapse them into one canonical file per NPC while preserving every variant name as an alias.

## Companion: sidecar batch merge

`planning.py --build-dossiers` writes `<stem>.new_notes.NNN.md` sidecars whenever a canonical dossier already exists, to avoid clobbering curated content. These accumulate across runs. To fold them back in, use the companion script `sidecar_merge_batch.py` in this skill's directory — it submits one Anthropic Message Batch (50% off) and is fully resumable via state files written next to the dossier dir:

```bash
python ~/.claude/skills/dossier-merge/sidecar_merge_batch.py /path/to/docs/npcs/
python ~/.claude/skills/dossier-merge/sidecar_merge_batch.py /path/to/docs/npcs/ --resume
```

Successful merges archive sidecars to `<npc-dir>/merged_sidecars/` rather than deleting them.

After merging sidecars, run `backfill_source_extracts.py` to mark every dossier with the full extract range it now covers — this prevents future `--build-dossiers` runs from re-emitting sidecars for already-consumed extracts (once `planning.py` learns to read the field; see TODO.md):

```bash
python ~/.claude/skills/dossier-merge/backfill_source_extracts.py /path/to/docs/npcs/ /path/to/docs/planning_extractions/
```

## Core invariant

Every non-canonical file's `name:` value, every entry in every non-canonical file's `aliases:` list, and the filename-derived human-readable form of every non-canonical file must end up in the canonical file's `aliases:` frontmatter AND appear in the canonical's `## Identity` section as a parenthetical ("also known as: X, Y, Z"). Nothing is lost.

## Why this split (frontmatter + body)

- **YAML frontmatter `aliases:`** — consumed by `run_synthesize()` in `planning.py` to normalize raw session extracts (e.g. rewrite "Captain Tolubb" to "Tolubb" before the LLM sees them) and to populate an `# ENTITY RESOLUTION` block in the system prompt.
- **Body parenthetical** — for humans reading the dossier. Keeps the "also known as" information visible when the dossier is opened directly.

Write both. They serve different readers.

## Precision rule (CLAUDE.md global)

"Is this the same entity?" is a scope decision, not a rendering decision. The user confirms every cluster. The LLM renders merges (combining section content) inside the user-confirmed structure. Never auto-merge without confirmation.

## Required information

1. **Dossier directory** — usually `docs/npcs/`. From args, or detect from `ui_config.yaml` in CWD (`plan_dossier_dir` key), or glob for `docs/npcs/` under CWD, or ask the user. Resolve to an absolute path.

If `AskUserQuestion` is not loaded, run `ToolSearch` first with `query: "select:AskUserQuestion"` to load its schema. Note its validation gotcha: every question must have ≥2 options. Always include a "keep both — different NPCs" option even when you're sure they match; users need that escape hatch.

## Workflow

### Phase 0: Pre-flight

1. Resolve the dossier directory.
2. **Create the backup tarball** *before doing anything else*:
   ```bash
   TS=$(date +%Y%m%d-%H%M%S)
   PARENT=$(dirname <dossier-dir>)
   BASE=$(basename <dossier-dir>)
   tar -czf "$PARENT/$BASE.backup-$TS.tar.gz" -C "$PARENT" "$BASE"
   ```
   Verify the tarball is non-empty. If it fails, **abort** — no safety net, no run.
3. Print the backup path prominently so the user knows where the restore point lives:
   ```
   Backup: /path/to/npcs.backup-20260416-120000.tar.gz (X MB, N files)
   Restore with: tar -xzf <path> -C <parent>
   ```
4. **Load or create state file** at `<dossier-dir>/.dedup_state.json`:
   ```json
   {
     "backup_tarball": "/absolute/path/to/tarball",
     "started_at": "ISO-8601",
     "updated_at": "ISO-8601",
     "clusters_confirmed": [
       {"files": ["a.md", "b.md"], "canonical": "a.md", "aliases_recorded": ["Foo"]}
     ],
     "clusters_rejected": [
       {"files": ["dren.md", "dren_halveth.md"], "reason": "different NPCs — different factions"}
     ],
     "clusters_deferred": [
       {"files": ["x.md", "y.md"], "note": "user wasn't sure"}
     ]
   }
   ```
   If the file exists from a prior run, load it and use `clusters_rejected` to pin past "keep both" decisions (see Phase 2).

### Phase 1: Inventory

Glob `<dossier-dir>/*.md`. Read each file and parse YAML frontmatter:

```markdown
---
name: Tolubb
aliases: []
---

# Tolubb
[body]
```

Files without frontmatter are legal inputs (pre-existing dossiers). Treat `name` as the filename stem and `aliases` as empty.

Build an inventory table: `(filename, name_field, aliases, body_char_count)`. Report the count and a trimmed sample to the user. Keep the full table in memory for subsequent phases.

### Phase 2: Auto-cluster

Run the following heuristics. Each produces candidate clusters; a file can appear in at most one cluster (prefer the highest-confidence heuristic).

**Heuristic ordering (highest confidence first):**

1. **Existing aliases hint** — if any file's `aliases:` already contains another file's `name:`, those files form a cluster.
2. **Compound filename** — a filename matching `<name>_<name>.md` or `<name>_<stem>_<name>.md` where both inner tokens also appear as standalone filenames (e.g. `brother_eldin_brother_eldrin.md` with `brother_eldin.md` and `brother_eldrin.md`). Auto-treat the compound and both referenced files as a cluster.
3. **Substring match** (case-insensitive, punctuation-normalized) — shorter name fully contained in longer, both names ≥ 3 chars.
4. **Title/role-prefix stripping** — strip prefixes `captain_`, `lord_`, `lady_`, `sir_`, `ser_`, `sergeant_`, `master_`, `mistress_`, `brother_`, `sister_`, `father_`, `mother_`, `aunt_`, `uncle_`, `the_`, `dr_`, `professor_`, `prefect_`, `canon_`, `madame_`, `mister_`, `mr_`, `headgnome_`, and any `the_<word>` pattern. After stripping, match on the remainder.
5. **Levenshtein distance ≤ 2** on normalized lowercased names where the shorter name is ≥ 5 chars (avoids false positives on short common names like `dala`/`dalia`).

**Also surface separately (not as merge clusters):**

6. **Garbage filenames** — filenames matching patterns like `i_don_t_see_`, `apologies_`, `no_session_`, `notes_in_your_`, `error_`, or unusually long (> 50 chars) with sentence-like structure. Also files whose body is empty, just a heading, or an obvious LLM error response. Surface for deletion approval, not for merging.

7. **Unclustered** — files not in any proposed cluster and not flagged as garbage. Surface the list at the end of Phase 4 as "Are any of these duplicates I missed?" — safety net against silent misses.

**Apply state file on load:** if a cluster matches (by exact set of filenames) something in `clusters_rejected`, silently drop it — the user already said "keep both". If it matches something in `clusters_confirmed`, that means a prior run got interrupted mid-execution; warn the user and ask whether to re-run the merge or skip.

Group the surviving clusters by heuristic type for batched presentation in Phase 4.

### Phase 3: Read + auto-classify

For each cluster, read all files in parallel (single tool-call batch). Auto-classify:

- **Strict subset** — one file's normalized body text (whitespace + punctuation collapsed) is fully contained in another's. The contained file is redundant.
- **Overlapping with unique content** — each file has meaningful content not in the others. Requires body reconciliation on merge.
- **Uncertain — likely different NPCs** — files contain explicit contradictions: different factions, different races/species, different "Current Location" claims, different genders used consistently, different first appearances. Flag for user review with the specific contradiction cited.

Record the classification + a short evidence string (what tipped the decision) with each cluster.

### Phase 4: Confirm with user (batched)

Present clusters in batches of **3–5 clusters per turn, grouped by heuristic type** — all spelling-drifts together, all title-as-filename together, etc. Use `AskUserQuestion` with one question per cluster, each question having at least these options:

- **Confirm merge** (with shown canonical + shown aliases)
- **Confirm merge — different canonical** (user will name it)
- **Keep both — different NPCs** (goes into `clusters_rejected`)
- **Defer** (goes into `clusters_deferred`)

Per cluster in the question body, show:

```
Files (N):
  - tolubb.md          (name: Tolubb,         2400 chars)
  - captain_tolubb.md  (name: Captain Tolubb, 180 chars — thin stub)
  - cap_tolubb.md      (name: Cap. Tolubb,    95 chars)
Classification: strict subset (stubs contained in tolubb.md)
Proposed canonical: tolubb.md
Proposed aliases:   ["Captain Tolubb", "Cap. Tolubb"]
```

For **uncertain / likely-different-NPCs** clusters, lead with the contradiction: "Different factions — `dren.md` says Crimson Guard, `dren_halveth.md` says Broken Blades."

**Canonical filename proposal follows the rules from the process dump:**
- Book-canon spelling when the user has previously stated one (check state file notes)
- Short slug for well-known characters (`thorne.md` over `thorne_duke.md`)
- Proper name over role-prefixed (`alremm.md` over `the_prophet.md`)
- User-stated correct spelling always wins

After each batch, update the state file with confirmed/rejected/deferred entries before moving to the next batch.

**Garbage-filename batch (separate):** present all detected garbage files in one `AskUserQuestion` call, each with options `delete` / `keep — it's real` / `defer`.

**Unclustered list (final batch before execution):** present the list of files not in any cluster as free-form text and ask "Any duplicates I missed? Name the pairs if so." Cheap safety net.

### Phase 5: Execute merges

Process confirmed clusters one group at a time. For each:

**Step 1 — Collect aliases (union, deduped case-insensitively, preserve prettiest form):**
- Every non-canonical file's `name:` value
- Every entry in every non-canonical file's `aliases:` list
- Human-readable form of every non-canonical filename (e.g. `captain_tolubb.md` → `Captain Tolubb`) — only if not already collected
- Any "also known as" parenthetical forms appearing in the losers' `## Identity` body text

**Step 2 — Reconcile body by classification:**

- **Strict subset:** keep canonical's body unchanged. No LLM work needed.
- **Overlapping with unique content:** send all bodies to the LLM with this prompt:
  > "These are N dossiers describing the same NPC: {names}. Produce a single clean dossier that preserves every unique fact. Follow the standard section structure: `## Identity`, `## Personality & Motivations`, `## History with the Party`, `## Current Status`, `## Relationships`, `## Arc Score Events`. Section rules:
  > - **Identity**: most specific role; end with `*Also known as: X, Y, Z.*` listing all aliases.
  > - **Personality & Motivations**: union of bullets, deduplicate semantically.
  > - **History with the Party**: chronological by date; if two sources describe the same event with different detail, write a single richer bullet.
  > - **Current Status**: most recent state wins; if sources contradict and dates are unclear, flag with `[CONTRADICTION: source A says X; source B says Y]`.
  > - **Relationships**: union; prefer specific phrasing over generic.
  > - **Arc Score Events**: union; preserve every recorded event.
  > Output only the dossier body (without frontmatter). No preamble."

  Show the merged output to the user before writing. If there's a `[CONTRADICTION]` marker, stop and ask how to resolve.

**Step 3 — Write canonical file:**

```markdown
---
name: <canonical name>
aliases:
  - Alias One
  - Alias Two
---

# <canonical name>

## Identity
<role / title / faction>. *Also known as: Alias One, Alias Two.*

## Personality & Motivations
...
```

Aliases appear in **both** the frontmatter list AND the Identity-section parenthetical. If the canonical already has frontmatter, use `Edit` to update it; otherwise `Write` the whole file.

**Step 4 — Pre-delete safety checks for losers:**
- If a loser has > 200 chars of substantive content not carried into the canonical, warn the user before deleting.
- Run `grep -r <loser-basename> <project-root>` — if other files reference the loser's filename (hardcoded paths, imports), surface matches before deletion.

**Step 5 — Delete losers.** Collect all losers from the current batch and delete them in **one** `rm -v` command (easier to audit than per-file deletes; matches the process dump's execution order). Example:
```bash
rm -v docs/npcs/captain_tolubb.md docs/npcs/cap_tolubb.md
```

**Step 6 — Update state file** with the confirmed cluster's details (`files`, `canonical`, `aliases_recorded`).

**Step 7 — Per-batch summary** printed to the user:
```
Batch 1 (spelling drift, 4 clusters): merged 7 files → 4 canonicals.
  tolubb.md            ← captain_tolubb.md, cap_tolubb.md        aliases: [Captain Tolubb, Cap. Tolubb]
  hartsch.md           ← harch.md, harch_hartsch.md              aliases: [Harch]
  ...
```

### Phase 6: Final report

After all batches:
- Total: started with N files, ended with M (N - M merged away)
- Aliases recorded: count of canonical files with non-empty `aliases:`
- Clusters rejected as different NPCs (reminder): K
- Clusters deferred: J (list them — the user should revisit later)
- Backup location: `<tarball path>` — remind the user to `rm` it once they're satisfied
- Next step:
  ```
  python planning.py --npc <dossier-dir>/*.md --arc-scores ... \
      --summaries summaries.md --output docs/planning.md
  ```

## Key principles

- **Human decides scope; LLM renders inside.** Clustering is a proposal. Every merge waits for explicit user confirmation. Body reconciliation is rendering — safe for the LLM once the user has confirmed the files describe the same NPC.
- **Aliases flow uphill, nothing is lost.** Every variant name from every loser becomes an alias on the canonical, in both YAML and body form.
- **Always back up first.** The tarball exists before anything is deleted. If the tarball creation fails, abort — no safety net, no run.
- **State pins rejections.** A cluster the user has rejected as "different NPCs" must never be re-proposed in a future run.
- **Atomic per-batch.** Complete one batch fully (writes → deletes → state update → summary) before starting the next. Interruption leaves the dossier dir in a consistent state.
- **Filename similarity ≠ same NPC.** From the process dump: `dren` ≠ `dren_halveth`, `dala` ≠ `dalia`, `krell` ≠ `lieutenant_krell`, `rannos` / `ranos_davl` / `ranus_duval` are three NPCs, not one. Always surface contradictions before assuming a merge.
- **Garbage filenames are real.** LLM error responses saved as filenames happen. Detect them, confirm with the user, delete outright.
- **Compound filenames signal prior punts.** `brother_eldin_brother_eldrin.md` is the previous pass's unresolved ambiguity. Treat as a cluster.

## Output

- Dossier directory: merged in place with canonical files carrying YAML + body aliases
- `<parent>/<dossier-dir-name>.backup-<timestamp>.tar.gz`: restore point (user should `rm` when satisfied)
- `<dossier-dir>/.dedup_state.json`: persisted decisions for resumable runs
- Console summary per batch and final counts

The user should re-run `planning.py` synthesize after the skill completes to regenerate `planning.md` with aliases resolved.
