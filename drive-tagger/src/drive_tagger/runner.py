"""Drive the tagging loop with a Cursor SDK agent.

Each batch launches a fresh local agent with the drive-tagger MCP server attached
over stdio and sends the driving prompt. Because all durable state lives in
turbovecdb + the graph DB, batches are independent: we keep launching agents
until the worklist is drained (or no progress is made).
"""

from __future__ import annotations

import json
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
    ids: list[str] = []
    with open(CONFIG.scan_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not extract.is_processable(rec):
                continue
            if folder_id and folder_id not in (rec.get("parents") or []):
                continue
            ids.append(rec["id"])
    return ids


def _remaining(folder_id: Optional[str]) -> int:
    worklist = set(_worklist_ids(folder_id))
    if not worklist:
        return 0
    store = Store()
    try:
        processed = {d["id"] for d in store.all_documents() if d.get("processed")}
    finally:
        store.close()
    return len(worklist - processed)


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


def run(*, execute: bool = False, folder_id: Optional[str] = None, max_batches: int = 100) -> dict:
    api_key = os.environ.get("CURSOR_API_KEY")
    if not api_key:
        raise RunnerError(
            "CURSOR_API_KEY is not set. Get one at Cursor Dashboard -> Integrations "
            "and `export CURSOR_API_KEY=...`."
        )

    from cursor_sdk import Agent, AgentOptions, LocalAgentOptions, StdioMcpServerConfig

    CONFIG.ensure_dirs()
    run_id = __import__("time").strftime("%Y%m%dT%H%M%S")

    total_start = _remaining(folder_id)
    if total_start == 0:
        return {"status": "nothing_to_do", "remaining": 0}

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
            f"execute={execute}) ===",
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

        new_remaining = _remaining(folder_id)
        if new_remaining >= remaining:
            # No forward progress this batch; stop to avoid an infinite loop.
            print(
                "[no progress this batch; stopping]", file=sys.stderr, flush=True
            )
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
