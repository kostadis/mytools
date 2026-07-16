---
name: qwen-negation-blindness
description: "Never name forbidden tools in prompts for local Qwen models — negation makes the failure worse, not better"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: e75668f1-813f-4c38-be4a-5be6250b441d
---

Qwen3 (Qwen3-Next-80B on the DGX Sparks) exhibits negation blindness in tool selection: a system-prompt sentence like "calling link_files first is FORBIDDEN" made the model call `link_files` first 100% of the time (0/5 and 0/3 correct on both boxes). Removing the forbidden-tool list restored 100% correct `next_file`-first behavior. Salience wins over logic — naming a tool makes it more likely to be called regardless of the negation wrapping it.

**Why:** Local/smaller models pattern-match on salient tokens rather than parse instruction logic. The same applies to tool descriptions: imperative language in a description ("Call ONCE with ALL neighbors") gets executed as an immediate instruction, and stale tool references in the driving prompt (e.g. "call stats once" after the tool was removed) cause fallback loops on whatever tool is available.

**Follow-up finding (same session):** positive imperatives are just as literal as negations. "Your very first response MUST be a call to next_file" made the model re-call next_file even when the harness had already made that call for it (0/5 correct after seed priming; 5/5 once the sentence was removed). Any tool named in the prompt tends to get called, period.

**Structural fix that beats prompt fiddling:** when a specific first tool call is required, have the harness make it directly and inject a synthetic assistant tool-call turn + tool result (seed priming). The model resumes mid-loop where it behaves reliably. drive-tagger `_custom_loop.py` does this for `next_file`.

**How to apply:**
- In prompts for Qwen/local models, avoid naming tools at all when possible — negated OR required. Describe the goal; let tool descriptions carry the what.
- Keep MCP tool descriptions passive (what the tool does), never imperative (when/how to call it) — workflow belongs in the driving prompt only.
- When a prompt change misbehaves, test empirically: reproduce the exact request payload (system prompt + tool schemas from the real MCP server) and A/B prompt variants directly against the endpoint with N trials each. A 0/5 vs 5/5 split settles arguments that speculation can't. Probe script pattern lives in the drive-tagger session history (probe_first_tool.py).
- Cheap backstop: abort the batch if the model's first tool call isn't the expected entry-point tool ([[drive-tagger]] `_custom_loop.py` guard).
