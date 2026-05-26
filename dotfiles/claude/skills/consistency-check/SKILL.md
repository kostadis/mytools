---
name: consistency-check
description: Run a consistency check on a session document (enhanced recap or final narration) against the campaign's context files. Use when the user invokes /consistency-check [document-path].
tools: Bash, Read
---

# Consistency Check

Run `check_consistency.py` on a specified document from the current campaign workspace.

## Workflow

### 1. Identify the document

If the user passed a path argument, use it. Otherwise ask: "Which document do you want to check — the enhanced sections, the final narration, or something else? (Provide the path.)"

Resolve the path relative to CWD. Common targets:
- `vtt_roleplay_extractions/enhanced_sections.md` — enhanced recap (post-Pass 2)
- `session-doc.md` (or whatever `--output` was set to) — final narration

### 2. Locate the campaign workspace

Run `pwd` to confirm CWD. `check_consistency.py` auto-detects config from CWD, so run it from the campaign workspace directory (the one that contains `config.yaml` or `docs/`).

If CWD is not the campaign workspace, ask the user which campaign directory to use.

### 2.5. Ask for session prep — REQUIRED, do not skip

Recaps are built from the VTT transcript, which is lossy. The DM's session prep is the authoritative record of what was intended at the table — names, exact quotes, sigils, place names, intel reveals. **Prep is the only source that catches transcription errors** (mishearings, dropped beats, swapped homophones like "manse" → "manticore" or "boar" → "bear"). Skipping this step means the check is blind to its highest-value finds.

Procedure:

1. Look for prep files in conventional locations:
   - `notes/session_prep/` (most common — Phandalin, OOTA)
   - `notes/prep/`, `notes/sessions/`, `notes/<date>/`
   - Any file under `notes/` named after a scene, location, or chapter the recap covers
2. Run `ls notes/session_prep/ 2>/dev/null; ls notes/prep/ 2>/dev/null` (or similar) to enumerate candidates.
3. Ask the user explicitly: **"Which session prep file(s) should I fact-check against? Found: [list]. Or pass `none` if there is no prep for this session."** Do this even if no candidates were found — the user may have prep elsewhere or under a non-obvious name.
4. If the user names one or more prep files, read them and include their content as `--context` arguments (one `--context` per file).
5. If the user says `none`, proceed without prep but **note in the final report** that the check was run without session prep and may miss transcription errors.

Do NOT proceed past this step without an explicit answer from the user. The "I'll just check against `docs/party.md`" default produced a report in a prior Phandalin run that flagged imaginary rules issues while missing real transcription errors that changed the meaning of intel reveals — that failure mode is exactly what this step exists to prevent.

### 3. Build the command

Base command:
```
python /path/to/CampaignGenerator/check_consistency.py <document>
```

- If the user's campaign workspace has a `docs/party.md`, append `--context docs/party.md`
- For each session prep file confirmed in step 2.5, append `--context <prep-file>`
- If the user specifies additional context files, append them to `--context`
- Use `--output consistency_report.md` if the user wants to save the report

Check for `docs/party.md` existence with a quick `ls docs/` or `test -f docs/party.md` before deciding.

### 4. Run the check

Execute the command. The script prints a summary line count to stderr and streams the full report. Wait for it to complete.

### 5. Present findings

After the run:
- Report the issue count (already printed by the script)
- If issues were found, show the full report inline so the user can act on it
- Ask: "Would you like to apply any of these fixes to the document?"

If the user says yes, edit the document directly using the Edit tool to apply each fix in turn, citing the **Suggested fix** from the report.

## Notes

- `check_consistency.py` loads `campaign_state` and `world_state` from config automatically. `party.md` is not in the default config and must be passed via `--context`.
- **Session prep is the highest-value context** — it catches transcription errors from the VTT that nothing else can catch. Always offer to include it (step 2.5). Skipping prep is the most common failure mode of this skill.
- The check is advisory — every suggested fix should be reviewed before applying. Don't bulk-apply without showing the user what will change.
- If the script errors on a missing config label, the campaign's `config.yaml` may not have that document configured. Fall back to `--context` with explicit paths.
