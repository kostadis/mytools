---
name: spark-status
description: Load the current DGX Spark setup into context — models, endpoints, ports, and active containers. Invoke as /spark-status before any task that needs to hit a Spark endpoint. Also use proactively when the user asks about the Spark, mentions a model name, or proposes using a local endpoint.
tools: Read, Bash
---

# Spark Status

Read the authoritative DGX Spark inventory and load it into context so you don't
have to ask the user what's running.

## What to do

1. Read `~/src/dgx/current-setup.md` in full.
2. Extract and report, in a compact table:
   - Which model is live on which box and port
   - Context window length
   - Active parsers (tool-call, reasoning)
   - Embed endpoint (if up)
   - Any stability notes or caveats from the most recent LIVE banner
3. Note the snapshot date from the file header.
4. If any section of the file warns that a container is stopped or a box is down,
   call that out explicitly.

## What NOT to do

- Do not ask the user what's running — the file is the answer.
- Do not guess model names from memory — read the file every time, it changes.
- Do not summarize old PREV banners as current state — only the topmost LIVE banner
  counts.
- **Never use `spark`, `spark1`, or `spark2` as hostnames in commands or configs.**
  These names do not resolve in WSL2. Always use the IP addresses from the file
  (e.g. `192.168.1.147:8001` for chat, `192.168.1.121:8000` for embed).

## After loading

Resume whatever task prompted the /spark-status invocation, now with the correct
model id and endpoint in context. If the task involves writing a command or config
that references a Spark endpoint, use the IP addresses from the file, not the
hostnames.
