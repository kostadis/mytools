---
name: consistency-check
description: Run a consistency check on a session document (enhanced recap or final narration) against the campaign's context files. Use when the user invokes /consistency-check [document-path].
tools: Bash, Read, Write, Edit, Glob, AskUserQuestion
---

# Consistency Check

Run `check_consistency.py` on a specified document from the current campaign workspace, fact-checking it against grounding docs + the DM's session prep, then record exactly what content was used.

## Workflow

### 1. Identify the document

If the user passed a path argument, use it. Otherwise ask: "Which document do you want to check — the enhanced sections, the final narration, or something else? (Provide the path.)"

Resolve the path relative to CWD. Common targets:
- `summaries/<date>/session-summary.md` (or the enhance_summary `--output`) — enriched recap
- `vtt_roleplay_extractions/enhanced_sections.md` — enhanced recap (post-Pass 2)
- `session-doc.md` (or whatever the narration `--output` was set to) — final narration

**Read the document yourself before running.** It grounds the entity/beat list (who/what appears), tells you which prep is relevant, and lets you anticipate the likely findings.

### 2. Locate the campaign workspace + verify config resolves

Run `pwd`. `check_consistency.py` auto-detects config, so run it from the campaign workspace (the dir with `config.yaml` / `config/config.yaml` / `docs/`). If CWD is not the workspace, ask which campaign directory to use.

**Config-move gotcha (verify before running).** `check_consistency.py` resolves `documents[].path` against the **config file's own directory** (`base_dir = config_path.parent`). If the workspace moved `config.yaml` into a `config/` subdirectory, relative paths like `docs/campaign_state.md` resolve to `config/docs/...` and the run dies with `file not found: .../config/docs/campaign_state.md`. Fixes, in order of preference:
- Fix the config so its paths resolve from its own dir (e.g. `path: ../docs/campaign_state.md`), OR
- Pass `--config <path>` to a config whose `documents:` use absolute paths (a throwaway config in the scratchpad works — only `campaign_state` + `world_state` are auto-loaded).

Sanity check after the run: the header should read `Context  : N document(s)` with N = 2 (auto-loaded) + your `--context` count, and there should be **no** `Warning: context file not found` lines.

### 2.5. Discover + choose session prep — REQUIRED, do not skip

Recaps are built from the VTT transcript, which is lossy. The DM's session prep is the authoritative record of what was intended at the table — names, exact quotes, sigils, place names, intel reveals. **Prep is the only source that catches transcription errors** (mishearings, dropped beats, swapped homophones). Skipping it means the check is blind to its highest-value finds.

**Sweep the WHOLE `notes/` tree, not just `notes/session_prep/`.** Prep is scattered by campaign convention — in one campaign (OOTA/Candlekeep) `notes/session_prep/` held only 4 files while the bulk of the arc prep lived in `notes/sessions/` and its `handouts/` subdir. Enumerate every plausible location:

```bash
ls notes/session_prep/ notes/prep/ notes/sessions/ notes/sessions/handouts/ \
   notes/canon/ notes/threads/ notes/npcs/ docs/npcs/ 2>/dev/null
```

Then **categorize** candidates by relevance to *this* session (use the entities/beats you got from reading the document in step 1):
- **HIGH** — the dated/named prep doc for this exact session; in-world handouts (letters, petitions, papers) tied to its beats; the player NPC/name tracker.
- **MEDIUM** — arc background: locations, evidence maps, runsheets, day-by-day prep, superseded cuts.
- **LOW** — adjacent but off-session (other locations, party/companion handouts).

The campaign-standard sources (`docs/party.md` and `docs/entity_registry.yaml` — see step 3) are **always** included, so this choice is only about the *session prep*. Present a **tiered choice** and let the user pick (recommend the focused set — too many context files dilute/overload the check with off-page material):
- **Focused prep set (recommended):** the session's prep doc + `docs/party.md` + the relevant in-world handouts + the NPC tracker (~5–6 files).
- **Minimal:** the session prep doc + `docs/party.md`.
- **Broad:** focused + runsheets/evidence-maps/adjacent-session docs.
- **Let me pick:** enumerate the full tagged list.

Ask explicitly — e.g. via AskUserQuestion — and **do not proceed without an explicit answer.** The "I'll just check against `docs/party.md`" default once produced a report that flagged imaginary rules issues while missing real transcription errors — that failure mode is exactly what this step prevents. If the user says `none`, proceed but **note in the final report** that the check ran without prep and may miss transcription errors.

### 3. Build the command

```
python /path/to/CampaignGenerator/check_consistency.py <document> \
  [--config <config>] \
  --context <file1> <file2> ...            # NOTE: --context is nargs="+" — ONE flag, many files
  --output summaries/<date>/consistency_report_<tag>.md
```

- `--context` takes **multiple files after a single flag** (`nargs="+"`). Do **not** repeat the flag — a later `--context` overwrites the earlier one and silently drops files.
- **Always include two campaign-standard sources** (neither is in the config auto-load):
  - `docs/party.md` — the PCs.
  - **`docs/entity_registry.yaml`** — the canonical registry of every entity, with its **aliases** and notes. This is the highest-yield source for the most common finding class (misspelled / mis-titled / mis-attributed entity names): the alias lists let the check separate a legitimate alternate name from a transcription error — e.g. `Asha` / `Asha Vandry` are canonical aliases of **Asha Vandree**, whereas `Bookworm` is *not* an alias of **Bookwyrm**, so it's a real error. Feed the **`.yaml`** for alias-level checking. Its generated human-readable companion `docs/entity_inventory.md` (canonical names + notes, no aliases) is a lighter alternative only when the context budget is tight. If the campaign has no registry yet, skip it (it's an enhancement, not a hard dependency).
- Then add every prep/handout file the user confirmed in step 2.5.
- **Quote paths with spaces** (in-world handout filenames often have them, e.g. `"notes/sessions/Kalan to Janussi - Second Petition.md"`).
- Save the report with `--output` into the session's summary directory.

### 4. Run the check

Execute and wait. Confirm the `Context : N document(s)` count and the absence of `context file not found` warnings (see step 2). The script may print a `No issues found.` banner even when the report body lists issues — trust the report body, not the banner.

### 4.5. Record the sources used — REQUIRED (YAML manifest)

Write a manifest of exactly what content fed the check into the session's **summary directory** (the dir containing the checked document), named to pair with the report — `<report-stem>.sources.yaml` (e.g. `consistency_report_ch58.sources.yaml`); fall back to `<document-stem>.consistency_sources.yaml` if no report was saved. This is the provenance record — what the recap was judged against, so a later reader can reproduce or audit the check. Include both the config-auto-loaded grounding docs and the `--context` files:

```yaml
consistency_check:
  timestamp: "<ISO-8601, from `date -Iseconds` or the report/log name>"
  campaign: "<workspace dir or name>"
  document_checked: "<relative path>"
  report: "<relative path to saved report, or null>"
  config: "<config path used>"
  model: "<model the script reported>"
  issues_found: <int>
  session_prep_used: true            # false if the user said `none`
  entity_registry_used: true         # false if the campaign has no registry
  sources:
    auto_loaded:                     # from config _DEFAULT_CONFIG_DOCS
      - { label: campaign_state, path: docs/campaign_state.md }
      - { label: world_state,    path: docs/world_state.md }
    context:                         # every --context file, with why it was chosen
      - { path: docs/party.md,             role: "PCs (campaign-standard)" }
      - { path: docs/entity_registry.yaml, role: "canonical entity registry + aliases (campaign-standard)" }
      - { path: notes/session_prep/<...>.md,       role: "session prep (authoritative)" }
      - { path: notes/sessions/handouts/<...>.md,  role: "in-world handout / NPC tracker" }
  notes: |
    Caveats worth recording — e.g. the session diverged from prep (see step 5),
    a config workaround was used, or prep was `none`.
```

### 5. Present findings — triage, don't dump

Report the issue count, then show the report. **Triage the findings into three buckets** rather than treating them uniformly:

- **Clear-cut errors** (name/spelling/title, internal attribution, place-name inconsistencies, mechanics miscategorized) — recommend applying.
- **Canon judgment (needs the user's table knowledge)** — a "new fact" the recap asserts that no doc establishes (e.g. a claimed kinship), or a recap beat that contradicts prep because **play diverged**. Only the user knows what actually happened at the table; ask, don't guess.
- **Minor/optional** — mechanical nitpicks, phrasing.

**Play-divergence caveat.** When the session went off the prep's rails (players do), the check will flag large prep-vs-recap contradictions that are *legitimate divergence, not errors* — the recap reflects actual play. Flag these as informational; do not "fix" the recap to match superseded prep. The high-value catches are name/title/quote/**transcription** errors.

Ask which fixes to apply. Apply only approved ones, one at a time, via Edit, citing the report's **Suggested fix**. For canon-judgment items, take the user's ruling (keep as new canon / remove / soften).

## Notes

- `check_consistency.py` auto-loads `campaign_state` + `world_state` from config; `party.md` and `docs/entity_registry.yaml` are **not** in the default set and must be passed via `--context` (step 3 makes them standard).
- **`docs/entity_registry.yaml` is the canonical entity tracker** — every entity with its aliases and notes, generated alongside `docs/entity_inventory.md`. Because it encodes aliases, it is the best source for the highest-frequency finding class (name/title/attribution errors); include it on every run when it exists. Same registry the `entity-triage` and `vtt-spell-pass` skills build on.
- **Session prep is the highest-value context for *this session's* facts** — it catches VTT transcription errors nothing else can. Discovering it (step 2.5) across the whole `notes/` tree, and choosing a focused set, is the most important part of a good run.
- The check is **advisory** — review every suggested fix before applying; never bulk-apply.
- Config-move breakage (step 2) is a known `check_consistency.py` limitation (tracked upstream) — verify the config resolves before blaming the check.
- The YAML manifest (step 4.5) is not optional — it is how the campaign records what each recap was judged against.
