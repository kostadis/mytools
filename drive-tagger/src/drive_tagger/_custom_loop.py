"""Async agent loop for non-Cursor providers (Anthropic, OpenRouter, DGX).

Spawns the drive-tagger MCP server as a stdio subprocess, connects to it via
the mcp ClientSession, then runs a tool-calling loop using whichever LLM
backend was requested.  Called via asyncio.run() from the sync runner.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

_MAX_STEPS_DEFAULT = 500
_STEPS_AFTER_DONE = 15  # extra steps allowed after next_file returns done: true


def _mcp_result_text(result: Any) -> str:
    parts = [block.text for block in result.content if hasattr(block, "text")]
    return "\n".join(parts) if parts else ""


def _is_done(result_text: str) -> bool:
    try:
        return bool(json.loads(result_text).get("done"))
    except (json.JSONDecodeError, AttributeError, ValueError):
        return False


async def _run_anthropic(
    prompt: str,
    model: str,
    server_params: StdioServerParameters,
    max_steps: int = _MAX_STEPS_DEFAULT,
) -> None:
    from anthropic import AsyncAnthropic

    async with AsyncAnthropic() as client, stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_resp = await session.list_tools()
            tools = [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "input_schema": t.inputSchema,
                }
                for t in tools_resp.tools
            ]
            messages: list[dict] = [{"role": "user", "content": prompt}]
            steps = 0
            done_since: int | None = None

            while steps < max_steps:
                response = await client.messages.create(
                    model=model,
                    max_tokens=8192,
                    tools=tools,
                    messages=messages,
                )
                for block in response.content:
                    btype = getattr(block, "type", None)
                    if btype == "text" and block.text.strip():
                        print(block.text, end="", file=sys.stderr, flush=True)
                    elif btype == "tool_use":
                        print(f"\n[tool] {block.name}", file=sys.stderr, flush=True)

                if response.stop_reason != "tool_use":
                    break

                messages.append({"role": "assistant", "content": response.content})
                tool_results: list[dict] = []
                for block in response.content:
                    if getattr(block, "type", None) != "tool_use":
                        continue
                    steps += 1
                    result = await session.call_tool(block.name, block.input or {})
                    result_text = _mcp_result_text(result)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_text,
                        }
                    )
                    if block.name == "next_file" and _is_done(result_text):
                        if done_since is None:
                            done_since = steps

                messages.append({"role": "user", "content": tool_results})

                if done_since is not None and (steps - done_since) >= _STEPS_AFTER_DONE:
                    print(
                        "\n[batch done: worklist exhausted]", file=sys.stderr, flush=True
                    )
                    break


async def _run_openai_compat(
    prompt: str,
    model: str,
    base_url: str,
    api_key: str,
    server_params: StdioServerParameters,
    max_steps: int = _MAX_STEPS_DEFAULT,
    disable_thinking: bool = False,
    system_instructions: str = "",
) -> None:
    from openai import AsyncOpenAI

    # extra_body merged into every chat.completions.create call (newer vLLM)
    extra: dict = {}
    if disable_thinking:
        extra["chat_template_kwargs"] = {"enable_thinking": False}

    # Build system message.
    # - /no_think: Qwen3 thinking-token disable (honored by tokenizer).
    # - agent enforcement: prevents Qwen from roleplaying tool calls as prose.
    # - system_instructions: full workflow instructions when caller wants them
    #   in the system turn (more reliable than a long user message for Qwen).
    system_parts = []
    if disable_thinking:
        system_parts.append("/no_think")
    # Do NOT name other tools here, even to forbid them. Qwen exhibits negation
    # blindness: "calling link_files first is FORBIDDEN" reliably makes it call
    # link_files first (verified 0/5 vs 5/5 on both DGX boxes). Salience wins
    # over logic — only ever mention the tool we want called.
    system_parts.append(
        "You are an autonomous agent. You MUST use tool calls for ALL actions. "
        "NEVER describe, simulate, or narrate tool calls in text. "
        "Your very first response MUST be a call to the `next_file` tool — "
        "do not output any text before making that call."
    )
    if system_instructions:
        system_parts.append(system_instructions)
    seed_messages: list[dict] = [{"role": "system", "content": "\n\n".join(system_parts)}]
    async with (
        AsyncOpenAI(base_url=base_url, api_key=api_key or "unused", timeout=120.0) as client,
        stdio_client(server_params) as (read, write),
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_resp = await session.list_tools()
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description or "",
                        "parameters": t.inputSchema,
                    },
                }
                for t in tools_resp.tools
            ]
            messages: list[dict] = seed_messages + [{"role": "user", "content": prompt}]
            steps = 0
            done_since: int | None = None

            while steps < max_steps:
                try:
                    response = await client.chat.completions.create(
                        model=model,
                        messages=messages,  # type: ignore[arg-type]
                        tools=tools,  # type: ignore[arg-type]
                        extra_body=extra or None,
                    )
                except Exception as exc:
                    print(f"\n[batch aborted: LLM error — {exc}]", file=sys.stderr, flush=True)
                    break
                choice = response.choices[0]
                msg = choice.message

                if msg.content and msg.content.strip():
                    print(msg.content, end="", file=sys.stderr, flush=True)
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        print(f"\n[tool] {tc.function.name}", file=sys.stderr, flush=True)

                if choice.finish_reason != "tool_calls" or not msg.tool_calls:
                    break

                # Guard: if the very first tool call isn't next_file the model has
                # entered hallucination mode — abort rather than burn the batch.
                if steps == 0 and msg.tool_calls[0].function.name != "next_file":
                    print(
                        f"\n[batch aborted: first tool was "
                        f"{msg.tool_calls[0].function.name!r}, expected next_file]",
                        file=sys.stderr,
                        flush=True,
                    )
                    break

                # Rebuild as plain dict — avoids Pydantic serialisation surprises
                assistant_msg: dict = {
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                }
                messages.append(assistant_msg)

                for tc in msg.tool_calls:
                    steps += 1
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError as exc:
                        # Feed parse error back so the model can retry or recover.
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": f"[error] malformed tool arguments: {exc}",
                            }
                        )
                        continue
                    result = await session.call_tool(tc.function.name, args)
                    result_text = _mcp_result_text(result)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result_text,
                        }
                    )
                    if tc.function.name == "next_file" and _is_done(result_text):
                        if done_since is None:
                            done_since = steps

                if done_since is not None and (steps - done_since) >= _STEPS_AFTER_DONE:
                    print(
                        "\n[batch done: worklist exhausted]", file=sys.stderr, flush=True
                    )
                    break


def run_batch(
    *,
    provider: str,
    prompt: str,
    model: str,
    server_params: StdioServerParameters,
    openai_base_url: str = "",
    openai_api_key: str = "",
    max_steps: int = _MAX_STEPS_DEFAULT,
    disable_thinking: bool = False,
    system_instructions: str = "",
) -> None:
    """Run one agent batch synchronously. Called from the sync runner loop."""
    if provider == "anthropic":
        asyncio.run(_run_anthropic(prompt, model, server_params, max_steps=max_steps))
    else:
        asyncio.run(
            _run_openai_compat(
                prompt,
                model,
                openai_base_url,
                openai_api_key,
                server_params,
                max_steps=max_steps,
                disable_thinking=disable_thinking,
                system_instructions=system_instructions,
            )
        )
