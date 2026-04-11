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
