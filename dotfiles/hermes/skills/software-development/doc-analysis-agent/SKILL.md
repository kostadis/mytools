---
name: doc-analysis-agent
description: Build a local-LLM-driven agent that analyzes a collection of source documents, extracts structured items (questions/claims), retrieves grounding context from a sibling corpus, calls an OpenAI-compatible /chat/completions endpoint, and writes sidecar outputs without mutating the sources. Use for any "read these files, form opinions/extractions, don't edit the originals" batch task.
---

# Document Analysis Agent (local LLM + sidecars)

## When to use
- You must process many source documents (dossiers, chapters, notes) and produce structured analysis per document.
- The analysis should be grounded in OTHER files in the repo (authoritative corpus), not invented.
- The user wants the source files LEFT UNTOUCHED — outputs go to sidecar files.
- You have (or the user will provide) an OpenAI-compatible LLM endpoint (OpenAI, OpenRouter, Ollama, vLLM, LM Studio).

## Core architecture (5 stages)
1. **Parse** each source doc into typed blocks (e.g. frontmatter + body + an `## Uncertainty` section of bullet questions).
2. **Retrieve** grounding evidence for each item, scoped to a chapter/section range and ranked by keyword hits.
3. **LLM** forms an opinion/extraction per item (cite the corpus).
4. **Sidecar** write: `<stem>.answers.json` next to the source. Never write into the source.
5. **Orchestrate** the batch: concurrent, resumable, with a manifest.

## THE SIDECAR RULE (user preference — embed this)
Source documents are read-only. Emit a sidecar `<name>.answers.json` sitting next to each source
(`source_dir/foo.md` → `source_dir/foo.answers.json`). The sidecar is the canonical deliverable and
must be self-contained: `{meta, opinions:{qid:{question, evidence, opinion}}}`. A rendered `.md` is a
separate optional artifact built FROM the sidecar — never the store. Re-running must NEVER clobber a
filled sidecar (build-if-missing only; render reads the existing sidecar).

## Stage details

### LLM call — urllib, no SDK
Use the stdlib so there is zero dependency to install:
```python
import json, urllib.request
def llm(prompt, base_url, api_key, model, retries=3, timeout=90):
    body = json.dumps({"model": model, "messages": [{"role":"user","content":prompt}],
                       "temperature":0.2, "max_tokens":300}).encode()
    last=None
    for _ in range(retries):
        req = urllib.request.Request(base_url.rstrip("/")+"/chat/completions", data=body,
              headers={"Content-Type":"application/json", "Authorization":f"Bearer {api_key}"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())["choices"][0]["message"]["content"].strip()
        except Exception as e:
            last=e; time.sleep(2)
    return f"[LLM ERROR: {last}]"
```
Backend is configured via env (`OPENAI_BASE_URL`/`BASE_URL`, `OPENAI_API_KEY`/`API_KEY`, `MODEL`) or flags.
Local servers (vLLM/Ollama) often ignore the key — pass `"EMPTY"` safely.

### Retrieval — scope + rank
- Scope to the block's `chapters:` range AND to any explicit `(chNN)` refs in the question.
- Strong keywords = the entity name + Capitalized proper nouns; discard stopwords.
- Rank candidate lines by keyword-hit count; cap total chars; return `file [xN] | line`.
- If 0 hits → return "(no matching lines)" — do NOT fabricate.

### Parse robustness
Frontmatter is delimited by `---` fences that may also separate merged blocks. Split on `^---\s*$`,
track a pending `<!-- source: X -->` comment, and rebuild each block from its own `name:/type:/...`
frontmatter. Skip blocks with no questions. **A block with `## Uncertainty\nNone.` has ZERO
questions — treat as "no open items", not an error.**

## Orchestration (batch)
```python
def work(f):
    try:
        if not parse_dossier(f):          # 0-block doc -> skip, don't crash
            return (name, 0, 0, "no-questions")
        sc_path = sidecar_path(f)
        if not os.path.exists(sc_path):
            resolve_dossier(f, base_url=None)   # scaffold only
        if not os.path.exists(sc_path):
            return (name, 0, 0, "no-questions")
        sc = json.load(open(sc_path))
        pending = [q for q,v in sc["opinions"].items() if not v.get("opinion")]
        if not pending: return (name, len(sc["opinions"]), 0, "already-filled")
        for qid in pending:
            sc["opinions"][qid]["opinion"] = llm(...)
        json.dump(sc, open(sc_path,"w"))
        return (name, len(sc["opinions"]), len(pending), "ok")
    except Exception as e:                 # one bad file must not kill the batch
        return (name, 0, 0, f"error: {e}")
```
- **Resume:** `--skip-existing` skips sidecars already fully filled → safe to re-run after a crash.
- **Concurrency:** `ThreadPoolExecutor(max_workers=8)`; the LLM HTTP calls are I/O-bound.
- **Manifest:** write `batch_manifest.json` at end (`total/ok/errors[]`).

## PITFALLS (learned the hard way)
- **0-block dossiers crash the batch.** A "None." uncertainty doc has no sidecar; `json.load(missing_path)`
  raises `FileNotFoundError` and aborts the whole `ThreadPoolExecutor`. Guard with the `parse_dossier`
  short-circuit above. THIS IS THE #1 bug.
- **Re-render clobbers opinions.** If "render" rebuilds the scaffold and overwrites the sidecar, you
  lose all filled opinions. Render must READ the existing sidecar, never rebuild it.
- **Block-buffered stdout in background jobs.** When launched redirected (not a TTY), Python buffers
  stdout, so live `print` progress appears frozen at line ~29. Track real progress via a disk count
  (`glob sidecars; count fully-filled`), NOT the captured preview. Use `notify_on_complete=true` on
  background runs so you're pinged on finish instead of polling.
- **Manifest "errors" can be harmless.** Count "no-questions" skips separately from real errors.
- **Never** claim verification from a prior run after editing. Re-run a fresh ad-hoc /tmp check.

## Verification (before claiming done)
Write a throwaway `os-safe tempfile` `/tmp/hermes-verify-*.py` that asserts: parse counts, sidecar
shape, source-dossier SHA-256 unchanged before/after, and (for batch) 0 null opinions + 0 LLM
errors. Run it, then delete it. State explicitly it is ad-hoc, not a suite.

## References
- `references/sidecar_llm_batch.md` — concrete code skeleton (resolve + orchestrate) and the
  vLLM/Ollama endpoint pattern.
