---
name: gmassist-precheck
description: Pre-extraction pass — run enhance_summary then consistency_check against a gm-assist + VTT, before any per-scene VTT extraction. Use when the user invokes /gmassist-precheck [session-dir]. Catches canon and scope problems on the human-authored scene structure before spending tokens on scene_extract.
tools: Bash, Read, Edit
---

# gm-assist precheck

Run the cheap pre-extraction pass: take a session's gm-assist + VTT, produce the enriched `session-summary.md` via `enhance_summary.py`, then run `check_consistency.py` against it. The point is to surface canon contradictions (NPCs that don't exist, world-state conflicts, named beats that don't fit) while the artifact is still a small structural document — *before* the expensive per-scene VTT batch in `scene_extract.py`.

This is an experimental pass. The user is trying it a few times to decide if it's worth keeping. Keep the workflow tight and don't over-elaborate.

## Workflow

### 1. Locate the session directory

If the user passed a path argument, use it. Otherwise:
- Run `pwd` to confirm CWD is a campaign workspace (contains `docs/`, `summaries/`, `config.yaml`).
- List recent session directories: `ls -t summaries/ | head -10`
- Ask: "Which session — pass the path under `summaries/` (e.g. `summaries/20260512`)?"

The session dir should contain `gm-assist.md` and a `.vtt` transcript. Confirm both exist before continuing.

### 2. Run enhance_summary (with built-in pre-flight)

```bash
python ~/src/CampaignGenerator-unified-pipeline/enhance_summary.py \
  <session-dir>/<vtt-file>.vtt \
  --gmassist <session-dir>/gm-assist.md \
  --output <session-dir>/session-summary.md \
  --party docs/party.md \
  --gm-player <gm-name> \
  --batch
```

Pass `--party docs/party.md` and `--gm-player <name>` whenever they're available — they enable the wrong-VTT pre-flight inside `enhance_summary.py` itself (aborts with exit 2 if no VTT line starts with any expected display name, before submitting). The GM display name is whatever they appear as in Zoom (e.g. `Kostadis`).

`--batch` is the default for cost reasons (50% off list price). Block-and-poll mode is fine — the call is one cached request, so it returns quickly. If the user explicitly wants the live streaming path, drop `--batch`.

If `session-summary.md` already exists, ask the user whether to overwrite or skip the enrichment step (and just re-run the consistency check on the existing file). Don't silently overwrite — the existing file may have human edits.

If the pre-flight aborts (exit 2 with `speaker-mismatch`), the VTT is almost certainly the wrong file. Stop and report it to the user — don't pass `--allow-speaker-mismatch` to "make it work."

### 3. Run the consistency check

Delegate to the existing `/consistency-check` skill rather than reimplementing. Tell the user:

> Enrichment done. Running `/consistency-check <session-dir>/session-summary.md` next.

Then invoke the consistency-check skill workflow on that file. That skill handles the session-prep step (REQUIRED — do not skip), the `--context docs/party.md` wiring, and the report presentation. Don't shortcut its session-prep prompt; the value of this pass collapses without prep.

### 4. Present findings and pause

After consistency-check returns:
- Surface the issue count and the report.
- Ask: "Apply any of these fixes to `session-summary.md` before scene_extract?"
- If yes, edit `session-summary.md` directly using the Edit tool, citing each **Suggested fix** from the report.

Do NOT auto-advance to `scene_extract.py`. The point of this pass is the human checkpoint between enrichment and extraction. End with:

> Ready for `scene_extract.py` when you are.

## Notes

- This skill exists to evaluate whether the gm-assist → enhance_summary → consistency_check chain is a worthwhile pre-extraction pass. Each run is also a data point — note (briefly, in the chat) anything that felt high-value or wasted in the run, so the user can decide whether to formalise it.
- The consistency check is operating on a Stage-1 artifact (enriched summary), not a Stage-2 artifact (per-scene extractions) or final narration. False positives are possible — flagged issues at this stage are scope/canon hints, not transcript errors. The skill should frame findings that way.
- If `enhance_summary.py` is unavailable in the unified-pipeline tree, fall back to `~/src/CampaignGenerator/enhance_summary.py`. Both checkouts are kept in sync; either is fine.
- Both `enhance_summary.py` and `scene_extract.py` share the same wrong-VTT pre-flight (`--party`, `--gm-player`, `--allow-speaker-mismatch`). They share the same root motivation: don't spend tokens enriching/extracting against the wrong recording. Always pass `--party` and `--gm-player` when running this skill — that's where the protection lives.
