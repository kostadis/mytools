# Batch-run the uncertainty-resolution agent over all merged dossiers

Proven pattern (out-of-the-abyss, 300 dossiers, ~3,600 questions). The real
implementation lives at
`docs/ensemble/orchestrate_batch.py`; this is the condensed recipe.

## Two-phase, read-only design (never touches source dossiers)
- **Phase 1 — scaffold** (local, fast): for every dossier, parse into merged
  blocks, retrieve chapter evidence, write `<entity>.answers.json` sidecar
  with `opinion: null`. Skips dossiers that already have a filled sidecar.
- **Phase 2 — fill** (LLM): for every sidecar with empty opinions, call the
  LLM per question, fill `opinion`, refresh the `*.resolved.md` render.
  Concurrent (ThreadPoolExecutor), resumable (re-run skips filled).
- **Phase 3 — none-pass**: dossiers whose `## Uncertainty` is literally
  `None.` have no bullets, so the parser skips them. Emit a sidecar marked
  `resolved_with: "no-open-uncertainties"` for exactly those 28.

## Backend (OpenAI-compatible /chat/completions)
```
BACKEND_URL  = http://<host>:<port>/v1      # e.g. vLLM at 192.168.1.147:8001/v1
BACKEND_MODEL = Qwen/Qwen3-Next-80B-A3B-Instruct-FP8
BACKEND_KEY   = EMPTY                        # local servers ignore the key
```
- Verify reachability first: `curl -s <BACKEND_URL>/models | head`.
- Per-question call: model with `temperature: 0.2`, `max_tokens: 300`, a
  "cite chapter evidence, never invent" system/user prompt.
- Wrap in retry+backoff (3 tries, doubled sleep capped 8s) + ~90s timeout so a
  single dead call doesn't blank an opinion silently.

## Run
```
python3 orchestrate_batch.py --scaffold --fill --workers 8
python3 orchestrate_batch.py --none-pass          # after fill completes
```
Smoke test first: `--limit 3 --workers 3`, then check 3 sidecars filled.

## Progress tracking (stdout is block-buffered when piped)
Do NOT trust the log tail — it freezes at first flush. Track on disk:
```python
import json, glob
files = glob.glob('merged_dossiers/*.answers.json')
full  = sum(1 for f in files if all(v.get('opinion') for v in json.load(open(f))['opinions'].values()))
print(f'filled={full}/272  (28 dossiers are None.-pass)')
```

## Gotchas
- 272/300 get real sidecars; the other 28 are `None.` → handle with none-pass.
- Re-running fill is safe: it skips already-filled sidecars.
- Manifest: write `batch_manifest.json` at phase-2 end (total/ok/errors).
