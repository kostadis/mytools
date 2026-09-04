---
name: session-doc-run
description: Run the CampaignGenerator session_doc pipeline (enhance_summary → scene_extract → sd_narrate → assemble) with a human gate between stages, and build the two inputs it needs that nothing else produces — a display-name-labelled VTT, and a session-local players.yaml when one player covered an absent player's PC. Use when the user says "run the session_doc", "run the pipeline", or when /staged-consistency reports that stages 1-3 have no artifacts. Invoke as /session-doc-run [session-dir].
---

# session-doc-run

The pipeline itself is documented in `~/src/CampaignGenerator/docs/cli/session_doc_pipeline.md`
and that file is authoritative for flags. This skill owns the part that is not
written down anywhere: **what has to be true before Stage 1 will produce
anything worth reviewing**, and where the gates go.

## Where this sits

```
/speaker-attribution     → session_<date>.speakers.vtt   (player labels)
      ↓  [THIS SKILL — build the two inputs, then run with gates]
Stage 1  enhance_summary → session-summary.md      → HUMAN REVIEW
Stage 2  scene_extract   → scene_extractions/      → HUMAN REVIEW   (see /scene-extract)
Stage 3  sd_narrate      → narration/              → HUMAN REVIEW
Stage 4  assemble        → session_doc.md
      ↓
/staged-consistency      → checks each boundary
```

`/staged-consistency` is the *checker* at these boundaries; this skill is the
*runner*. If it told you stages 1-3 have no artifacts, you are here.

## The gate is not optional and it is not this skill's opinion

`session_doc_pipeline.md` states the boundaries, and `~/.claude/CLAUDE.md`'s LLM
Pipeline Design Rule is the reason: each stage is one LLM doing one thing a
human can verify before the next call inherits it. Running all four in sequence
is *"LLM extracts → LLM structures → LLM renders"* — the pattern that rule
prohibits by name. **Ask how far to run before running anything**, and offer
Stage 1 alone as the default.

## Before Stage 1 — the two inputs nothing else builds

### 1. A display-name VTT

`enhance_summary --party --party-config` runs a wrong-VTT pre-flight that aborts
unless some line starts with a recorded display name. The format it wants is
Zoom's:

```
Kostadis Roussos: ...
David Mendenhall: ...
```

`/speaker-attribution` emits short labels (`Dave:`, `Gary:`). Map them to the
`display_names` in `config/players.yaml` — check that file, do not guess the
form — and write a new VTT rather than editing the attributed one:

```bash
python3 - <<'PY'
import re
m={"Kostadis":"Kostadis Roussos","Wade":"Wade Brown","Dave":"David Mendenhall","Gary":"Gary Young"}
src=open("session_<date>.speakers.vtt").read()
out=re.sub(r"^(Kostadis|Wade|Dave|Gary)(?: \[\?\])?:", lambda mo:f"{m[mo.group(1)]}:", src, flags=re.M)
open("session_<date>.displaynames.vtt","w").write(out)
PY
grep -oE '^[A-Za-zÉé][A-Za-zÉé .]{2,30}:' session_<date>.displaynames.vtt | sort | uniq -c | sort -rn
```

Two things that bite:

- **Leave `UNKNOWN` alone.** Folding unattributed cues into the GM is tempting
  (it makes the tally look complete) and it is a **false attribution** — which
  `docs/cli/player_identity_howto.md` calls *"the most expensive failure this
  system produces."* 115 honest `UNKNOWN` cues beat 115 lines wrongly credited.
  Report the coverage instead: *"2117 cues, 94.6% attributed."*
- **Neutralise anything in a `NOTE` header that looks like a label.** A
  provenance block containing `Speakers: pyannote…` parses as a speaker called
  `Speakers`. Reword those lines; do not delete the provenance.

Running without a labelled VTT at all is a real option only if none exists — say
so explicitly, because the enhancement pass's documented failure mode is
attribution drift, and you are removing the only signal against it.

### 2. A session-local `players.yaml`, when cover happened

`config/players.yaml` records the *steady-state* table. When a player was absent
and someone else ran their PC, the steady-state file is wrong for this session,
and feeding it a correctly-labelled VTT produces a **silent** collapse: every
line the coverer spoke as the absent PC lands on their own PC's name.

Do not edit the campaign config. Write a throwaway beside the session and pass
`--players-config`:

```yaml
- id: gary
  display_names: [Gary Young]
  plays: [Valphine Sotorra, Brewbarry]   # covered for Stéphane this session
- id: stphane
  display_names: [Stéphane Bourdeaud]
  plays: [Brewbarry]
  active: false                          # absent; kept so old transcripts resolve
```

`plays: [A, B]` is the documented "one person plays two characters" form.
`active: false` is documented for a player who *left*; using it for a one-session
absence is safe **only because this file is session-local** — never make that
edit in `config/players.yaml`.

**Derive the cover arrangement from the tape, not from `CLAUDE.md`.** Both
directions have been seen in one campaign. If `/speaker-attribution` ran, its
manifest's `speaker_map` already has the answer. Head-comment the file with how
you know, because a bare override looks like a mistake to the next reader.

This is an identity decision, so it is a **human checkpoint** — present the
collapse that would otherwise happen and let the GM choose.

## Config resolution

Same trap as `/consistency-check` step 2, one layer worse for the pipeline
scripts: a workspace may have **no root `config.yaml`**, only `config/`. The
`--party-config` / `--players-config` / `session_doc.yaml` files live there:

```bash
ls <campaign>/config/          # party.yaml players.yaml session_doc.yaml
```

Pass absolute paths for everything. Read `config/session_doc.yaml` before
running — `paths.scene_extractions_dir` is the authority for where Stage 2
writes, and it does **not** always match what other skills grep for
(`scene_extractions` vs `scene_extractions_new`).

## Running a stage

**These calls exceed a 10-minute foreground timeout.** Stage 1 on a 98-minute
session took ~7 minutes; a long one will not fit. Launch detached, redirect to a
file, and poll — never pipe a long job through `tail`, which buffers to
completion and shows you nothing:

```bash
nohup python -m session_doc.enhance_summary <vtt> \
  --gmassist <abs>/gm-assist.md --output <abs>/session-summary.md \
  --party <abs>/docs/party.md --party-config <abs>/config/party.yaml \
  --players-config <abs>/<session>/players.session.yaml \
  --backend claude-code > stage1.log 2>&1 &
```

Poll on the **output file plus liveness**, so a crashed run is not mistaken for
a slow one:

```bash
for i in $(seq 1 18); do
  [ -f "$OUT" ] && { echo DONE; break; }
  pgrep -f session_doc.enhance_summary >/dev/null || { echo "PROCESS GONE"; break; }
  sleep 30
done
```

A harness task-completion notice for the *launch wrapper* is not the job
finishing. Check the file.

## After a stage — verify upstream fixes survived, before the review

The enhancement pass re-reads the tape, so a correction applied upstream can be
undone by the transcript that caused it. Grep for every fix the previous stage
applied:

```bash
grep -c "half-orc" session-summary.md      # 9
grep -oE "(^|[^-])\b(an|the) orc\b" session-summary.md | wc -l   # 3  ← drifted back
```

Report both numbers. Three regressions against nine correct is a review item;
silence about it is how a fixed error reaches narration.

**Run `sd_verify_quotes` at the gate — it is free and it is the point of the gate.** The pipeline diagram in `session_doc_pipeline.md` shows it hanging off Stage 1 and Stage 2 outputs for a reason: a quote is a span of the tape or it is not, and that question needs no model.

```bash
python -m session_doc.sd_verify_quotes --vtt <same VTT the stage used> \
  --summary <session>/session-summary.md --out <session>/quote_report_stage1.md --report-only
```

It checks only `> "…"` blockquotes and says nothing about **who** said them, so it does not replace the checks below — it removes the quote-fidelity question from them.

Then spot-check the **two failure modes this document class has** — do not
re-run the whole check, that is `/staged-consistency`'s job:

- **Invented precise dice values.** Grep the literal number in the VTT. Only
  timestamp hits ⇒ invented. Verify each individually: on ch08 the 25-damage
  Lightning Bolt was verbatim on tape (`"25 half damage is 12"`) while adjacent
  values were not checked at all — say which you checked.
- **Attribution drift toward the prominent character.**

**Corroboration is the good outcome, and worth saying out loud.** When the pass
independently reproduces an upstream ruling — pulling the exact exchange you
adjudicated by hand — that is the strongest evidence available that the fix was
right. On ch08 it also re-derived an event a reviewer had nearly deleted,
retroactively vindicating a mid-run self-correction.

## Notes

- **Do not run Stage 2 from here.** `/scene-extract` owns it — the voicing map,
  the `party.md` format gate, the attribution-strategy checkpoint and the output
  ceiling. It needs the same session-local `players.yaml`; hand it over.
- The backend comes from `config/session_doc.yaml` (`backends.active` and
  `active_profile`), and a stale `active_profile` pointing at another session's
  knobs is easy to miss. Check it, and say which backend actually ran.
- Stage 1's log lands in `<session>/logs/` — name it in the handoff.
- Never let "the pipeline ran" imply "the output is good." Every stage output is
  an LLM's unreviewed work until the gate closes.
