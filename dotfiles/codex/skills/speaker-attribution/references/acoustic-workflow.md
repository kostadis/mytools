# Acoustic workflow

Read when generating or joining acoustic turns. The local join helpers use only
Python's standard library. New diarization uses the separately maintained
`~/src/mytools/audio-to-vtt/spark/diarize_remote.py`; inspect that repository's
applicable instructions and current CLI before deploying. If missing, report
the dependency. Existing valid turn files still support the local workflow.

## Spark execution

Use the configured host (historically `spark2`), not an inferred IP. Resolve its
home once with `ssh spark2 'printf "%s\n" "$HOME"'` and store it in a
task-specific variable. Never repurpose `HOME` or `CODEX_HOME`.

Create a unique remote working directory. Stage the current remote helper,
selected audio, and a manifest; check command exit codes and verify remote file
sizes/hashes. The helper is deployed as a flat file, so a local edit does not
update the remote copy. Re-stage it before each new run.

Use **absolute remote paths** in the manifest. JSON readers and `av.open()` do
not expand `~`. Example structure (replace paths and speaker count with the
actual session values):

```json
{
  "audio_path": "/home/kostadis/audio-to-vtt-work/session-run/audio.m4a",
  "hf_token_path": "/home/kostadis/.hf-token-diarize",
  "num_speakers": 2,
  "model": "pyannote/speaker-diarization-community-1",
  "device": "cuda"
}
```

Use the configured token **path**, never print or inline its contents. Use a
writable cache such as `HF_HOME=<remote-home>/.cache/diarize-hf`. Model access
must already be configured; distinguish permissions, gated-model access, and
GPU memory failures rather than treating all as authentication errors.

Run the configured environment, historically
`<remote-home>/.venvs/diarize/bin/python`, with:

```text
diarize_remote.py --manifest <absolute-manifest-path> --output <absolute-turns-path>
```

Use `community-1` and the known number of **people**. In the source workflow,
`3.1` collapsed a three-person mono recording into one cluster holding 84% of
speech; `community-1` separated it. Extra NPC voices do not add participants.
An unknown room voice can still be forced into one of the requested bins.

Check `free -g` and `nvidia-smi --query-compute-apps=pid,process_name,used_memory
--format=csv`. Truncated process-table memory is easy to misread. Do not shut
down another workload to make room. Historical four-minute runs with 11–12 GB
free show that a busy Spark need not prevent CUDA; check current conditions,
try a bounded run when appropriate, and inspect actual errors before falling
back to Descript or another already authorized backend.

Keep the job observable with a process/session ID and a log. Do not pipe the
job through `tail`, which may buffer until completion. Redirect output and read
progress separately; use short polls so the user receives updates. Quote remote
shell paths properly, and do not use `JSON.stringify` as shell escaping.

Retrieve and validate the turn envelope against the selected recording before
joining. Confirm times are finite, ordered, in range, and end after start, and
that the requested people did not collapse into a single voice.

## Join semantics and uncertainty

`diarize_label.py` assigns the cluster holding the greatest overlapping duration
of each cue. The preferred second source uses the same span-overlap join;
Markdown without ends uses the nearest preceding utterance, including silence
gaps. These methods have different boundary error rates.

The confusion matrix uses transcript word counts, not recognized word-by-word
speaker truth. A second-source cluster is mapped only when it contributes at
least 5% of compared words and one primary cluster owns at least 60% of its row.
Agreement is computed on words with a qualifying mapping. Report coverage and
unmapped fragments alongside the percentage; excluded words are not successes.
The tool's proposed mapping is statistical and does not establish player names.

Read suspicious fragment quotes. A small voice asking about coffee may be a
real housemate; a GM performing an NPC may split into another bin. Confirm with
the GM before applying `Room (not at table)` or merging an acoustic fragment.

For a confirmed voice isolated only by the second clustering, use an approved
JSON file with `--md-label`. Real start/end spans are required for overrides,
and `--md-label-coverage` must be at least 0.5. An override applies only where
that cluster dominates the cue. Keep provenance in the output header. It drops
`[?]` for those cues because the approved override resolves that disagreement;
do not bulk-clear unrelated flags.

Do not infer cross-validation merely from a second file's existence. Read the
join report. With no comparable spans or no qualifying mapping, agreement is
unavailable. With one acoustic source, retain that fact in every report/header.
