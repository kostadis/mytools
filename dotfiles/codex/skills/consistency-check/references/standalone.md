---
name: consistency-check
description: Run a CampaignGenerator consistency check on one session document, then review and apply only approved fixes. Use when the user asks to check a recap, enhanced summary, scene extraction, or narration for campaign consistency, including when they type /consistency-check [document-path].
metadata:
  short-description: Check one session document for campaign consistency
---

# Consistency Check

Run `check_consistency.py` on one session document, judge the report against
campaign context and transcript evidence, then record the sources and rulings.

This is the Codex port of the Claude skill. Do not edit
`~/src/mytools/dotfiles/claude/skills/consistency-check/` when changing this
skill.

## Codex Compatibility

- Ask user questions in chat. Do not refer to Claude `AskUserQuestion`.
- Use `update_plan` for multi-step progress when useful.
- Use `apply_patch` for manual edits to tracked documents.
- There is no Codex `Artifact` review flow here.
- Use CampaignGenerator's `--backend codex-cli` for the audit. It uses the
  operator's saved ChatGPT subscription login and does not require or forward
  an OpenAI or Codex API key.
- If Codex reports a missing executable, missing login, incompatible model, or
  timeout, surface that failure and stop. Do not silently select another
  backend. Other script backends remain available only when the user explicitly
  requests one: `anthropic`, `dgx`, `openrouter`, or `claude-code`.

## Workflow

### 1. Identify the Document

If the user passed a path, use it. Otherwise ask for the document path.
Resolve it relative to the current working directory.

Common targets:
- `summaries/<date>/gm-assist.md`
- `summaries/<date>/session-summary.md`
- `summaries/<date>/scene_extractions_new/0N_*.md`
- `summaries/<date>/narration/*.md`

Read the document before running the check. Note the session directory, likely
document class, key names, and transcript files next to it.

Classify the document:
- `first-pass recap`: direct session recap or `gm-assist.md`
- `enhanced recap`: `enhance_summary` output, usually larger than its source
- `scene extraction`: per-scene extraction containing quote blocks
- `narration`: final prose output
- `backfill`: old session checked against newer grounding docs

### 2. Locate the Campaign Root and Config

Find the campaign root by walking upward from the document or CWD until you find
`docs/`, `summaries/`, and `config/`.

Current campaign layout is:

```text
<campaign>/
  config/config.yaml
  docs/
  summaries/
```

Pass `--config <campaign>/config/config.yaml` explicitly. Do not require a root
`config.yaml`.

After the run, inspect the command output. If it reports missing context files
because the config paths were resolved relative to `config/`, create a temporary
absolute-path config and rerun. The minimum useful config is:

```yaml
documents:
  - { label: campaign_state, path: /abs/campaign/docs/campaign_state.md }
  - { label: world_state, path: /abs/campaign/docs/world_state.md }
```

Record whichever config path was used in the manifest.

### 3. Choose Session Prep

Session prep is required unless the user confirms there is none. It catches VTT
transcription errors that grounding docs cannot.

Search the whole `notes/` tree, not just `notes/session_prep/`. Candidate
locations include:
- `notes/session_prep/`
- `notes/prep/`
- `notes/sessions/`
- `notes/sessions/handouts/`
- `notes/canon/`
- `notes/threads/`
- `notes/npcs/`
- location or arc files directly under `notes/`

Categorize candidates:
- `HIGH`: exact dated/session/location prep, handouts used in this session, NPC
  trackers, VTT glossary files.
- `MEDIUM`: arc background, evidence maps, planning, prior session recap.
- `LOW`: adjacent but off-session.

Ask the user to choose the prep set. Recommend a focused set:
the exact prep doc, relevant handouts, VTT glossary files, and `docs/party.md`.
If they answer `none`, continue but record that the run was prep-less.

### 4. Build Context

Always include these context files when present:
- `docs/party.md`
- `docs/entity_registry.yaml`
- `notes/vtt_transcription_corrections.md`
- `notes/vtt_known_additions.md`
- the selected prep and handout files
- the source recap when checking an enhanced recap

`check_consistency.py` auto-loads only the configured documents, usually
`campaign_state` and `world_state`. Everything else must go through one
`--context` flag followed by all context paths.

### 5. Run the Check

Locate the CampaignGenerator repo. Prefer `/home/kroussos/src/CampaignGenerator`;
fall back to `/home/kroussos/CampaignGenerator` if needed.

Run from the campaign root:

```bash
python3 /home/kroussos/src/CampaignGenerator/session_doc/check_consistency.py <document> \
  --config <campaign>/config/config.yaml \
  --backend codex-cli \
  --context <file1> <file2> ... \
  --output <session-dir>/consistency_report_<tag>.md
```

Validation after the run:
- Confirm the context count is plausible.
- Confirm there are no `context file not found` warnings.
- Do not trust a `No issues found` banner by itself; inspect the saved report.
- Count issues from report headings, not from the command banner.
- If `codex-cli` reports a setup, login, model, timeout, process, or empty-result
  error, stop and resolve that condition before continuing; do not treat partial
  output as a report.

### 6. Write the Sources Manifest

Create `<report-stem>.sources.yaml` in the session directory. Include:

```yaml
consistency_check:
  timestamp: "<ISO-8601>"
  campaign: "<campaign name or path>"
  document_checked: "<relative path>"
  document_class: "<class>"
  report: "<relative path>"
  config: "<config path used>"
  backend: "<backend>"
  issues_found: <count from report body>
  session_prep_used: true
  entity_registry_used: true
  session_date: "<session date>"
  sources:
    auto_loaded:
      - { label: campaign_state, path: docs/campaign_state.md }
      - { label: world_state, path: docs/world_state.md }
    context:
      - { path: docs/party.md, role: "PCs" }
      - { path: docs/entity_registry.yaml, role: "entity registry and aliases" }
      - { path: notes/vtt_transcription_corrections.md, role: "ASR glossary" }
      - { path: notes/<prep>.md, role: "session prep" }
  notes: |
    Caveats, config workaround, missing prep, transcript choice, or
    auto-continuation inspection.
```

### 7. Adjudicate Findings

Treat the report as advisory. It can find a real contradiction and still choose
the wrong fix direction.

For each finding, classify it:
- `clear-cut`: name spelling, title, internal contradiction settled by transcript,
  place-name inconsistency, chronology, simple attribution.
- `judgment`: campaign canon, prep-vs-play divergence, party knowledge, GM ruling.
- `minor`: style or normalization with no downstream risk.

Use the transcript for anything about attribution, exact wording, rolls,
equipment, kills, retracted GM slips, or facts absent from grounding docs. Prefer
a speaker-labelled Zoom `.md` for attribution, and the cleanest VTT for wording.

Important failure modes:
- A table ruling is not automatically a rules error.
- Backfilled chapters should not be edited to match the party's current state.
- Module truth is not automatically party knowledge.
- Module vocabulary and table vocabulary can both be valid.
- A glossary replacement can merge two PCs if speaker attribution was lost.
- Read the whole sequence before ruling on one grep hit.

Present findings in severity order and ask before editing. Batch only fixes that
are genuinely mechanical and unambiguous. Apply accepted edits with
`apply_patch`, then grep for residual bad forms.

### 8. Append the Resolution

Append a `resolution` block to the manifest:

```yaml
  resolution:
    reviewed_by: GM
    reviewed: "<date>"
    applied:
      - { finding: 1, fix: "<what changed>" }
    partially_applied: []
    rejected:
      - finding: 2
        ruling: "<decision>"
        rationale: "<evidence>"
  vtt_adjudicated: |
    Findings settled against transcript evidence, with transcript path and
    relevant quotes summarized.
  carry_forward:
    - status: OPEN
      item: "<follow-up with enough evidence to avoid rediscovery>"
```

Every `carry_forward` item must have a status:
`OPEN`, `DONE`, `CORRECTION`, `WONTFIX`, or `NOTE`.

Validate the manifest parses as YAML, show the relevant diff, and close with:
- fixes applied
- findings rejected or deferred
- what transcript review caught
- carry-forward items
