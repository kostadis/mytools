"""Drive the tagging loop with an LLM agent.

Supports four providers (DT_PROVIDER env var):
  cursor      — Cursor SDK agent (default; requires CURSOR_API_KEY)
  anthropic   — Anthropic API via ant auth login or ANTHROPIC_API_KEY
  openrouter  — OpenRouter OpenAI-compat endpoint (requires OPENROUTER_API_KEY)
  dgx         — Local DGX Spark vLLM endpoint (requires DT_DGX_ENDPOINT)

Each batch launches a fresh MCP server subprocess and runs an agent until the
worklist is drained (or no progress is made).  All durable state lives in
turbovecdb + the graph DB, so batches are independent and restartable.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

from . import extract
from .config import CONFIG, PROJECT_ROOT
from .prompts import DRIVING_PROMPT
from .store import Store


class RunnerError(RuntimeError):
    pass


def _worklist_ids(folder_id: Optional[str]) -> list[str]:
    if not CONFIG.scan_path.exists():
        raise RunnerError(
            f"no scan found at {CONFIG.scan_path}; run `drive-tagger scan` first"
        )
    return [r["id"] for r in extract.load_worklist(folder_id, CONFIG.scan_path)]


def _remaining_from_set(worklist: set[str]) -> int:
    if not worklist:
        return 0
    store = Store()
    try:
        processed = {d["id"] for d in store.all_documents() if d.get("processed")}
    finally:
        store.close()
    return len(worklist - processed)


def _remaining(folder_id: Optional[str]) -> int:
    return _remaining_from_set(set(_worklist_ids(folder_id)))


def _log_message(msg) -> None:
    """Best-effort streaming of assistant text and tool calls to stderr."""
    try:
        mtype = getattr(msg, "type", None)
        inner = getattr(msg, "message", None)
        content = getattr(inner, "content", None) if inner is not None else None
        if mtype == "assistant" and content:
            for block in content:
                btype = getattr(block, "type", None)
                if btype == "text":
                    text = getattr(block, "text", "")
                    if text.strip():
                        print(text, end="", file=sys.stderr, flush=True)
                elif btype in ("tool_call", "tool_use"):
                    name = getattr(block, "name", None) or getattr(block, "tool_name", "tool")
                    print(f"\n[tool] {name}", file=sys.stderr, flush=True)
    except Exception:  # noqa: BLE001 - logging must never break the run
        pass


def _run_cursor(
    *,
    execute: bool,
    folder_id: Optional[str],
    max_batches: int,
    run_id: str,
    total_start: int,
    worklist_ids: set[str],
) -> dict:
    api_key = os.environ.get("CURSOR_API_KEY")
    if not api_key:
        raise RunnerError(
            "CURSOR_API_KEY is not set. Get one at Cursor Dashboard -> Integrations "
            "and `export CURSOR_API_KEY=...`."
        )

    from cursor_sdk import Agent, AgentOptions, LocalAgentOptions, StdioMcpServerConfig

    batches_run = 0
    remaining = total_start
    for _ in range(max_batches):
        if remaining == 0:
            break

        env = {**os.environ, "DT_EXECUTE": "1" if execute else "0", "DT_RUN_ID": run_id}
        if folder_id:
            env["DT_FOLDER_ID"] = folder_id

        server = StdioMcpServerConfig(
            command=sys.executable,
            args=["-m", "drive_tagger.mcp_server"],
            env=env,
            cwd=str(PROJECT_ROOT),
        )

        print(
            f"\n=== batch {batches_run + 1} (remaining: {remaining}, "
            f"execute={execute}, provider=cursor) ===",
            file=sys.stderr,
            flush=True,
        )

        options = AgentOptions(
            model=CONFIG.model,
            api_key=api_key,
            local=LocalAgentOptions(cwd=str(PROJECT_ROOT)),
            mcp_servers={"drive-tagger": server},
        )
        with Agent.create(options) as agent:
            run_handle = agent.send(DRIVING_PROMPT)
            for message in run_handle.messages():
                _log_message(message)
            result = run_handle.wait()

        batches_run += 1
        status = getattr(result, "status", "unknown")
        print(f"\n[batch {batches_run} finished: {status}]", file=sys.stderr, flush=True)

        new_remaining = _remaining_from_set(worklist_ids)
        if new_remaining >= remaining:
            print("[no progress this batch; stopping]", file=sys.stderr, flush=True)
            remaining = new_remaining
            break
        remaining = new_remaining

    return {
        "status": "done" if remaining == 0 else "stopped",
        "batches": batches_run,
        "processed": total_start - remaining,
        "remaining": remaining,
        "execute": execute,
    }


def _run_custom(
    *,
    provider: str,
    model: str,
    execute: bool,
    folder_id: Optional[str],
    max_batches: int,
    run_id: str,
    total_start: int,
    worklist_ids: set[str],
) -> dict:
    from mcp.client.stdio import StdioServerParameters

    from ._custom_loop import run_batch

    base_url = ""
    api_key = ""
    disable_thinking = False
    if provider == "openrouter":
        base_url = CONFIG.openrouter_base_url
        api_key = CONFIG.openrouter_api_key
    elif provider == "dgx":
        base_url = CONFIG.dgx_endpoint
        api_key = "unused"
        disable_thinking = True  # Qwen3 thinking tokens make tool-calling loops unusably slow

    batches_run = 0
    remaining = total_start
    for _ in range(max_batches):
        if remaining == 0:
            break

        env = {**os.environ, "DT_EXECUTE": "1" if execute else "0", "DT_RUN_ID": run_id}
        if folder_id:
            env["DT_FOLDER_ID"] = folder_id

        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "drive_tagger.mcp_server"],
            env={k: str(v) for k, v in env.items()},
        )

        print(
            f"\n=== batch {batches_run + 1} (remaining: {remaining}, "
            f"execute={execute}, provider={provider}) ===",
            file=sys.stderr,
            flush=True,
        )

        run_batch(
            provider=provider,
            prompt=DRIVING_PROMPT,
            model=model,
            server_params=server_params,
            openai_base_url=base_url,
            openai_api_key=api_key,
            disable_thinking=disable_thinking,
        )

        batches_run += 1
        print(f"\n[batch {batches_run} finished]", file=sys.stderr, flush=True)

        new_remaining = _remaining_from_set(worklist_ids)
        if new_remaining >= remaining:
            print("[no progress this batch; stopping]", file=sys.stderr, flush=True)
            remaining = new_remaining
            break
        remaining = new_remaining

    return {
        "status": "done" if remaining == 0 else "stopped",
        "batches": batches_run,
        "processed": total_start - remaining,
        "remaining": remaining,
        "execute": execute,
    }


def run(*, execute: bool = False, folder_id: Optional[str] = None, max_batches: int = 100) -> dict:
    provider = CONFIG.provider

    CONFIG.ensure_dirs()
    run_id = __import__("time").strftime("%Y%m%dT%H%M%S")

    # Pre-flight: fail fast before spending time on the 75MB worklist load.
    from . import health as _health

    print("Checking endpoints...", file=sys.stderr, flush=True)
    failures = [r for r in _health.check_all() if not r.ok]
    if failures:
        for r in failures:
            print(f"  ✗  {r.name}: {r.detail}", file=sys.stderr)
        raise RunnerError("pre-flight checks failed — fix the above before running")
    print("  all checks passed.", file=sys.stderr, flush=True)

    # Build the worklist once — scan.jsonl is 75MB+, we don't re-read it per batch.
    print("Loading worklist...", file=sys.stderr, flush=True)
    worklist_ids = set(_worklist_ids(folder_id))
    total_start = _remaining_from_set(worklist_ids)
    if total_start == 0:
        return {"status": "nothing_to_do", "remaining": 0}
    print(f"Worklist: {len(worklist_ids)} processable files, {total_start} unprocessed.", file=sys.stderr, flush=True)

    if provider == "cursor":
        return _run_cursor(
            execute=execute,
            folder_id=folder_id,
            max_batches=max_batches,
            run_id=run_id,
            total_start=total_start,
            worklist_ids=worklist_ids,
        )

    if provider == "openrouter" and not CONFIG.openrouter_api_key:
        raise RunnerError(
            "OPENROUTER_API_KEY is not set; "
            "export it or switch DT_PROVIDER to cursor / anthropic / dgx"
        )

    if provider not in ("anthropic", "openrouter", "dgx"):
        raise RunnerError(
            f"Unknown DT_PROVIDER={provider!r}. "
            "Valid values: cursor, anthropic, openrouter, dgx"
        )

    model = CONFIG.dgx_model if provider == "dgx" else CONFIG.model

    return _run_custom(
        provider=provider,
        model=model,
        execute=execute,
        folder_id=folder_id,
        max_batches=max_batches,
        run_id=run_id,
        total_start=total_start,
        worklist_ids=worklist_ids,
    )
