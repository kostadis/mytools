"""Deterministic tagging pipeline: Python owns the loop, the LLM judges once per file.

Unlike the agentic runner (runner.py), the model never drives control flow.
For each file the harness extracts, embeds, and gathers context (similar
neighbors + the full category list), then makes ONE chat completion that
returns a JSON decision: categories to assign, new categories to create, and
links to record. The harness validates and applies it.

Workers are plain threads; each owns its own Store, Graph, and OpenAI client —
the same isolation as running multiple sharded processes, which turbovecdb's
FileLock and sqlite already handle.
"""

from __future__ import annotations

import concurrent.futures
import json
import queue
import sys
import threading
import time
from typing import Optional

from . import extract, gdrive
from .config import CONFIG
from .graph import Graph
from .prompts import JUDGE_PROMPT, build_judge_user_msg
from .store import Store

_EXTRACT_TIMEOUT = 90  # seconds; pypdf/docx/pptx can hang on malformed files
_JUDGE_RETRIES = 1  # re-asks after a JSON parse failure
_ALLOWED_RELATIONS = {"supersedes", "part-of", "duplicate-of", "references", "related-to"}


class PipelineError(RuntimeError):
    pass


class _Shared:
    """Cross-worker counters and the progress print lock."""

    def __init__(self, total: int) -> None:
        self.lock = threading.Lock()
        self.total = total
        self.done = 0  # files taken off the queue (any outcome)
        self.processed = 0
        self.skipped = 0
        self.judge_failed = 0
        self.errors = 0

    def log(self, name: str, outcome: str) -> None:
        with self.lock:
            self.done += 1
            print(f"[{self.done}/{self.total}] {name} — {outcome}", file=sys.stderr, flush=True)


def _extract_with_timeout(rec: dict) -> Optional[str]:
    """extract_text with a hard ceiling; the hung thread is abandoned on timeout."""
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = pool.submit(extract.extract_text, rec)
    try:
        return future.result(timeout=_EXTRACT_TIMEOUT)
    finally:
        pool.shutdown(wait=False)


def _parse_judge(content: str) -> dict:
    """Parse the judge's JSON reply, tolerating markdown fences and stray prose."""
    text = content.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("top-level JSON must be an object")
    return data


def _judge(client, rec: dict, snippet: str, neighbors: list[dict], categories: list[dict]) -> Optional[dict]:
    """One decision call (plus bounded parse-error retries). None = gave up."""
    messages = [
        {"role": "system", "content": "/no_think\n\n" + JUDGE_PROMPT},
        {
            "role": "user",
            "content": build_judge_user_msg(
                rec.get("name", ""), rec.get("mime_type", ""), snippet, neighbors, categories
            ),
        },
    ]
    for _attempt in range(_JUDGE_RETRIES + 1):
        response = client.chat.completions.create(
            model=CONFIG.dgx_model,
            messages=messages,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        content = response.choices[0].message.content or ""
        try:
            return _parse_judge(content)
        except (json.JSONDecodeError, ValueError) as exc:
            messages.append({"role": "assistant", "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": f"That was not valid JSON ({exc}). "
                    "Respond again with ONLY the JSON object.",
                }
            )
    return None


def _apply(
    store: Store, graph: Graph, fid: str, decision: dict, neighbor_ids: set[str]
) -> tuple[list[str], int, int]:
    """Validate and write the judge's decision. Returns (categories, links_added, links_dropped)."""
    new_names: list[str] = []
    for nc in decision.get("new_categories") or []:
        if not isinstance(nc, dict):
            continue
        cname = (nc.get("name") or "").strip()
        if not cname:
            continue
        store.create_category(cname, (nc.get("description") or "").strip())
        new_names.append(cname)

    cats = [c.strip() for c in (decision.get("categories") or []) if isinstance(c, str) and c.strip()]
    all_cats = sorted(set(cats) | set(new_names))
    if all_cats:
        store.assign_categories(fid, all_cats)

    links_added = 0
    links_dropped = 0
    for lnk in decision.get("links") or []:
        if not isinstance(lnk, dict):
            continue
        dst = (lnk.get("dst_id") or "").strip()
        # Only accept links to actual retrieved neighbors — hallucinated ids die here.
        if dst not in neighbor_ids or dst == fid:
            links_dropped += 1
            continue
        relation = (lnk.get("relation") or "").strip()
        if relation not in _ALLOWED_RELATIONS:
            relation = "related-to"
        try:
            if graph.add_link(fid, dst, relation, (lnk.get("note") or "").strip()):
                links_added += 1
        except ValueError:
            links_dropped += 1
    return all_cats, links_added, links_dropped


def _process_one(store: Store, graph: Graph, client, rec: dict, shared: _Shared, execute: bool, run_id: str) -> None:
    fid = rec["id"]
    name = rec.get("name", fid)

    # Text: reuse the stored body when the file is unchanged, else extract fresh.
    text: Optional[str] = None
    if store.has_unchanged(fid, rec.get("md5_checksum"), rec.get("modified_time")):
        doc = store.get_document(fid)
        if doc and doc.get("document"):
            text = doc["document"]
    if text is None:
        try:
            text = _extract_with_timeout(rec)
        except concurrent.futures.TimeoutError:
            graph.add_skipped(fid, "extract-timeout")
            with shared.lock:
                shared.skipped += 1
            shared.log(name, "skipped (extract-timeout)")
            return
        except Exception as exc:  # noqa: BLE001
            if "gdrive-cli" in str(exc):
                # transient (OAuth/network) — do NOT persist; retried next run
                with shared.lock:
                    shared.errors += 1
                shared.log(name, f"gdrive error (will retry next run): {exc}")
            else:
                graph.add_skipped(fid, "extract-error")
                with shared.lock:
                    shared.skipped += 1
                shared.log(name, f"skipped (extract-error): {exc}")
            return
        if not text:
            graph.add_skipped(fid, "no-text")
            with shared.lock:
                shared.skipped += 1
            shared.log(name, "skipped (no-text)")
            return
        store.add_document(rec, text)

    neighbors = store.find_similar(fid, CONFIG.similar_k)
    categories = store.list_categories()
    decision = _judge(client, rec, text[: CONFIG.judge_chars], neighbors, categories)
    if decision is None:
        with shared.lock:
            shared.judge_failed += 1
        shared.log(name, "judge failed (bad JSON after retries; will retry next run)")
        return

    all_cats, links_added, links_dropped = _apply(
        store, graph, fid, decision, {n["id"] for n in neighbors}
    )
    store.mark_processed(fid)

    drive_note = ""
    if execute and all_cats:
        props = {"dt_categories": ",".join(all_cats)}
        if run_id:
            props["dt_run"] = run_id
        try:
            gdrive.tag(fid, props, execute=True)
        except Exception as exc:  # noqa: BLE001
            drive_note = f" | DRIVE WRITE FAILED: {exc}"

    with shared.lock:
        shared.processed += 1
    outcome = f"{', '.join(all_cats) or '(no categories)'} | links: {links_added}"
    if links_dropped:
        outcome += f" (dropped {links_dropped} invalid)"
    shared.log(name, outcome + drive_note)


def _worker(work: "queue.Queue[dict]", shared: _Shared, execute: bool, run_id: str) -> None:
    """One worker thread: own Store/Graph/LLM client, pulls until the queue is dry."""
    from openai import OpenAI

    store = Store()
    graph = Graph()
    client = OpenAI(base_url=CONFIG.dgx_endpoint, api_key="unused", timeout=120.0)
    try:
        while True:
            try:
                rec = work.get_nowait()
            except queue.Empty:
                return
            try:
                _process_one(store, graph, client, rec, shared, execute, run_id)
            except Exception as exc:  # noqa: BLE001 — one bad file must not kill the worker
                with shared.lock:
                    shared.errors += 1
                shared.log(rec.get("name", rec["id"]), f"error: {exc}")
    finally:
        store.close()
        graph.close()


def run_pipeline(
    *,
    execute: bool = False,
    folder_id: Optional[str] = None,
    max_files: Optional[int] = None,
    workers: Optional[int] = None,
) -> dict:
    CONFIG.ensure_dirs()
    run_id = time.strftime("%Y%m%dT%H%M%S")
    n_workers = workers or CONFIG.pipeline_workers

    from . import health

    print("Checking endpoints...", file=sys.stderr, flush=True)
    failures = [r for r in health.check_all() if not r.ok]
    if failures:
        for r in failures:
            print(f"  ✗  {r.name}: {r.detail}", file=sys.stderr)
        raise PipelineError("pre-flight checks failed — fix the above before running")
    print("  all checks passed.", file=sys.stderr, flush=True)

    print("Loading worklist...", file=sys.stderr, flush=True)
    if not CONFIG.scan_path.exists():
        raise PipelineError(f"no scan found at {CONFIG.scan_path}; run `drive-tagger scan` first")
    records = extract.load_worklist(folder_id, CONFIG.scan_path)

    store = Store()
    graph = Graph()
    try:
        processed_ids = {d["id"] for d in store.all_documents() if d.get("processed")}
        skipped_ids = set(graph.all_skipped().keys())
    finally:
        store.close()
        graph.close()

    todo = [r for r in records if r["id"] not in processed_ids and r["id"] not in skipped_ids]
    remaining_start = len(todo)
    if remaining_start == 0:
        return {"status": "nothing_to_do", "remaining": 0}

    budget = max_files if max_files is not None else CONFIG.max_files_per_run
    todo = todo[:budget]
    print(
        f"Worklist: {len(records)} processable files, {remaining_start} unprocessed, "
        f"taking {len(todo)} this run with {n_workers} worker(s).",
        file=sys.stderr,
        flush=True,
    )

    work: "queue.Queue[dict]" = queue.Queue()
    for rec in todo:
        work.put(rec)
    shared = _Shared(total=len(todo))

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = [pool.submit(_worker, work, shared, execute, run_id) for _ in range(n_workers)]
        for f in futures:
            f.result()  # propagate unexpected worker crashes
    elapsed = time.time() - t0

    rate = shared.processed / (elapsed / 60) if elapsed > 0 else 0.0
    return {
        "status": "done",
        "processed": shared.processed,
        "skipped": shared.skipped,
        "judge_failed": shared.judge_failed,
        "errors": shared.errors,
        "remaining": remaining_start - shared.processed - shared.skipped,
        "elapsed_s": round(elapsed, 1),
        "files_per_min": round(rate, 2),
        "execute": execute,
    }
