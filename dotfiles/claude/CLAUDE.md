# Global Rules for Claude Code Sessions

## LLM Pipeline Design Rule

**Before planning any LLM call, state what decision you are removing from the human.**

If the answer is "none — the human reviews and corrects the output before it feeds anything downstream," the call is safe. The LLM is a fast first draft.

If the answer is "the LLM decides X and that output feeds the next step automatically," ask: *is X a precision decision?* Scope (what belongs where), ordering (what comes before what), attribution (who said/did what) — these are precision decisions. They require a human checkpoint before proceeding.

### Checklist for any planned LLM call

1. **What is the input?** Human-verified, or another LLM's unreviewed output?
2. **What decision is the LLM making?** Draft/render, or structure/scope?
3. **Who reviews the output before it feeds the next step?**
4. **What happens downstream if this output is 10% wrong?**

If the answer to (4) is "the next LLM call inherits the error and amplifies it" — a human checkpoint is required before that next call.

### The underlying principle

LLMs are renderers, not architects. They are exceptional at taking verified structure and making it feel alive. They are unreliable at scope decisions, temporal ordering, and respecting boundaries they can see past.

The rough extraction pass is the ceiling, not the floor. If a first-pass LLM output looks impressive, that is the best it can do — not a sign that it can handle the precision work downstream.

**Good pattern:** LLM extracts → human reviews and imposes structure → LLM renders inside that structure.

**Bad pattern:** LLM extracts → LLM structures → LLM renders. Errors compound silently.

## Local AI Hardware Exploration

The user owns a DGX Spark and is actively experimenting with local AI hardware to build intuition for the tradeoffs. **Suboptimal-by-design is the point, not an accident.**

For most tasks, calling the Anthropic API would be faster, smarter, and cheaper than running a local model on the Spark. The user knows this. The user does not care about Anthropic having their data. So "you'd be better off using Anthropic" is not useful pushback — it answers a question the user is not asking.

**What the user is actually trying to learn:** what it feels like to wire up local-LLM and local-GPU components, where the friction is, what breaks, what's surprisingly good, what's surprisingly bad. The exercise is calibration, not optimisation.

**How to engage:**

- When proposing or evaluating a "use the Spark for X" plan, lead with the *learning* tradeoffs (what this teaches, what its limits will reveal) before the *performance* tradeoffs.
- Don't hide that an Anthropic-API path would dominate on raw quality / speed — name it, then move on. Pretending the local path is optimal is dishonest; harping on the suboptimality is unhelpful.
- Honest engineering pushback is still welcome — verbatim violations, dimension mismatches, precision-decision risks, architecture failure modes. Those aren't "this is suboptimal," they're "this is broken." Keep flagging them.
- Treat exploratory implementations as legitimate work product even when they're a detour from the most efficient path.

## Codebase Semantic Search (codebase-memory-mcp)

1. For structural/relational code queries — definitions, references, call chains, cross-file or class relationships — use `codebase-memory-mcp` (`search_graph`, `trace_path`, `get_code_snippet`, `query_graph`) first, not Grep/Glob.
2. Grep/Glob/Bash grep remain free to use for: non-code files, config values, exact string/regex matches, and sanity-checking a `codebase-memory-mcp` result that looks stale or incomplete.
3. If a project isn't indexed yet, run `index_repository` before relying on graph queries for it.
4. `auto_index` is off by default, so the graph does not track edits automatically — if `codebase-memory-mcp` returns nothing, or a result looks stale (e.g. after recent edits), fall back to Grep/Glob rather than reporting an absence as fact.

## Search mempalace Before Answering From Memory

mempalace (`mcp__mempalace__*`) is the deep archive of past work. It is **read-only for you**: search it, never write to it. It is populated by a separate process — `mempalace_kg_add`, `mempalace_diary_write`, and `mempalace_add_drawer` are off-limits unless I explicitly ask.

The auto-loaded `MEMORY.md` files are an index, not the archive. They hold a handful of facts; mempalace holds the rest. MEMORY.md being silent on a topic is not evidence the topic is undocumented.

**Search it when either of these is true:**

1. **I appeal to history** — "remember when", "last time", "we decided", "didn't we already", "what did we do about X".
2. **The loaded context does not answer the question** — search mempalace *before* saying "I don't know", before guessing, and before asking me something I may have already told you.

**Entry point:** `mempalace_search` — semantic, returns verbatim drawer content. Use `mempalace_search_hierarchical` when a flat search returns noise, and `mempalace_kg_query` for relational or time-bound facts. Pass **keywords only** in `query`: that is the string that gets embedded and it is capped at 250 chars. Background goes in `context`, which is *not* embedded — putting a paragraph in `query` degrades the result.

Grep/Glob/Bash grep remain free for: exact string/regex matches, current on-disk state, config values, and sanity-checking a mempalace result that looks stale or incomplete.

A search that returns nothing is a real answer. Say so and move on; do not silently fall back to guessing. If a whole project looks absent, `mempalace_list_wings` will show whether it has been mined at all — but **do not mine it yourself**. Mining is my job, not yours: report that the wing is missing or stale and leave the re-mine to me. Ad-hoc `mempalace mine` runs are what polluted the chat palace with 19,120 junk drawers that had to be purged.

The deeper protocol — verbatim quoting, unhappy paths, corrupt-index recovery, anti-patterns — lives in the **`mempalace-recall` skill**, shipped by the mempalace plugin. This section only sets the standing search-first default; read that skill when a recall gets complicated.

## GitHub: Use the MCP Server, Not the `gh` CLI

For anything that touches GitHub itself — creating, reading, updating, commenting
on, or merging pull requests and issues; reading diffs, checks, and reviews — use
the `mcp__github__*` tools rather than shelling out to `gh` through Bash.

Local git work is unaffected: `git branch`, `git add`, `git commit`, `git push`,
`git log`, `git status` all stay on Bash as normal. The rule is about the GitHub
API surface, not about git.

Rationale: the MCP path avoids the Bash permission surface entirely. `gh pr merge`
is liable to be blocked by the auto-mode permission classifier mid-task, where
`mcp__github__merge_pull_request` goes through cleanly.

## An Unanswered Question Is Not a Decision

When a question to the user comes back without a clear, explicit answer — a default or "recommended" option appears selected, the response is ambiguous, the question timed out, or the user was simply taking time — do NOT proceed as if the user decided. Re-ask and wait for an explicit answer.

- Never fill in a recommended choice on the user's behalf. "The user was taking too long" is never a reason to decide for them.
- Treat only an explicit, affirmative response as a decision. If in doubt whether an answer was really given, ask again and say why.
- This is the human-checkpoint principle from the LLM Pipeline Design Rule applied to conversation: a timeout is not a checkpoint.

@RTK.md
# graphify
- **graphify** (`~/.claude/skills/graphify/SKILL.md`) - any input to knowledge graph. Trigger: `/graphify`
When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.
