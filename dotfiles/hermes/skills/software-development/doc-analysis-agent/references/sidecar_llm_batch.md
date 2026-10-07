# Sidecar LLM Batch — concrete skeleton

## Endpoint pattern (OpenAI-compatible)
Any of these speak `/v1/chat/completions`:
- **vLLM**: `http://HOST:PORT/v1`  (model = exact served id, e.g. `Qwen/Qwen3-Next-80B-A3B-Instruct-FP8`; check via `GET /v1/models`)
- **Ollama**: `http://localhost:11434/v1`  (model = `llama3`, `qwen2`, ...)
- **OpenRouter**: `https://openrouter.ai/api/v1`  (model = `openai/gpt-4o-mini`, `anthropic/...`)
- **LM Studio**: `http://localhost:1234/v1`

Local servers usually ignore `api_key`; pass `"EMPTY"` — the header is harmless.

First check reachability before a big run:
```bash
curl -s --max-time 8 http://192.168.1.147:8001/v1/models | head -c 300
```

## resolve_dossier() — one file → sidecar
```python
def resolve_dossier(dossier, base_url=None, api_key="EMPTY", model="local-model",
                    chapters_dir=DEFAULT_CHAPTERS, render=True):
    blocks = parse_dossier(dossier)
    if not blocks:
        return (None, 0, 0)                       # 0-block doc
    sc_path = sidecar_path(dossier)               # dossier dir + stem + ".answers.json"
    if base_url:                                  # LLM mode: build + fill, overwrite
        sc = build_scaffold(blocks, chapters_dir)
        for qid, o in sc["opinions"].items():
            o["opinion"] = llm_opinion(o["question"], o["evidence"], base_url, api_key, model)
        sc["meta"]["resolved_with"] = f"llm:{model}"
        json.dump(sc, open(sc_path,"w"), indent=2, ensure_ascii=False)
    else:                                         # scaffold only if missing; never clobber
        if not os.path.exists(sc_path):
            json.dump(build_scaffold(blocks, chapters_dir), open(sc_path,"w"), indent=2, ensure_ascii=False)
        else:
            sc = json.load(open(sc_path))
    if render:
        render_from_sidecar(sc_path, RESOLVED_DIR / (stem + ".resolved.md"))
    return (sc_path, filled, total)
```

## build_scaffold() — self-contained sidecar
```python
def build_scaffold(blocks, chapters_dir):
    opinions = {}
    for bi, b in enumerate(blocks):
        for qi, q in enumerate(b["questions"]):
            opinions[f"{bi}.{qi}"] = {
                "block": f"{b['type']}: {b['name']}",
                "chapters": b["chapters"],
                "question": q,
                "evidence": retrieve(chapters_dir, b["chapters"], q, b["name"]),
                "opinion": None,
            }
    return {"meta": {"blocks": len(blocks), "questions": len(opinions)}, "opinions": opinions}
```

## none-pass (0-block "Uncertainty: None." docs)
These have no questions → no sidecar from the main flow. Emit a marker sidecar so the set is complete:
```python
def none_pass():
    for f in dossiers():
        sp = sidecar_path(f)
        if os.path.exists(sp): continue
        m = re.search(r"##\s*Uncertainty\s*\n(.*?)(?:\n##\s|\Z)", open(f).read(), re.S|re.I)
        if m and m.group(1).strip().lower().replace(".","").strip() == "none":
            json.dump({"meta":{"blocks":1,"questions":0,"resolved_with":"no-open-uncertainties"},
                       "entity": entity_meta(f), "opinions": {}}, open(sp,"w"), indent=2)
```

## Smoke test first
```bash
python orchestrate.py --scaffold --fill --limit 3 --workers 3   # 3 dossiers, then inspect
```
Then full run in background:
```bash
python orchestrate.py --scaffold --fill --workers 8   # notify_on_complete=true
python orchestrate.py --none-pass                      # after fill finishes
```

## Throughput realism
~8 workers against a single local vLLM on a LAN ≈ 7 dossiers/min for small docs.
300 docs ≈ 40 min. Don't poll every 60 s — rely on `notify_on_complete` and check a disk count
(`glob sidecars; sum fully-filled`) between long waits.
