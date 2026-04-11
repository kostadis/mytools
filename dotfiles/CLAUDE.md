# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Personal dotfiles for Claude Code. The `claude/` directory is the source of truth — individual paths under `~/.claude/` are symlinks pointing into `claude/` here, so every edit is automatically git-tracked. There is no build, test, or lint step; changes take effect the next time Claude Code loads the config or the skill is invoked.

The authored content (all symlinked live into `~/.claude/`):

- `claude/CLAUDE.md` — the user's **global** Claude Code instructions, loaded into every session's context. This is distinct from the repo-root `CLAUDE.md` you are reading right now, which describes the dotfiles repo itself.
- `claude/settings.json` — user-level Claude Code settings. Currently `{}` — the `model` field is intentionally absent so `/model` switches freely per session.
- `claude/skills/<name>/SKILL.md` — custom user-invocable skills (the Kostadis Engine plus the campaign helpers, see below).
- `claude/agents/<name>.md` — custom subagent definitions (`kostadis-architect`, `ux-reviewer`).
- `claude/plugins/blocklist.json`, `claude/plugins/known_marketplaces.json` — plugin marketplace config. **Caveat**: Claude Code refreshes these files periodically. Because they are symlinked, those refreshes land in the repo and produce a dirty working tree. Either `git checkout --` them or fold the refresh into the next commit.

**Not authored, not touched:**
- `claude/plugins/marketplaces/claude-plugins-official/` is a **vendored mirror** of the upstream Anthropic plugin marketplace. Do not hand-edit. The live copy at `~/.claude/plugins/marketplaces/` is a separate real directory that Claude Code auto-updates — it is deliberately *not* symlinked to the repo, because auto-refresh churn would overwhelm git. The repo's snapshot will drift behind; refresh it as a separate chore if needed.
- Ephemeral runtime data (`backups/`, `cache/`, `history.jsonl`, `projects/`, `sessions/`, `plans/`, etc.) is listed in `claude/.gitignore` and stays in `~/.claude/` as real files, not symlinks.

## The Kostadis Engine (skills architecture)

`claude/skills/` currently holds nine skill directories:

- **Kostadis Engine (7)**: `k-preprocess`, `k-parallel`, `k-sequential`, `tribunal`, `anti-gravity`, `lagrange`, `value-bridge`. Covered in detail below — they form one layered pipeline.
- **Campaign helpers (2)**: `voice-file` and `style-examples`. These are independent, unrelated to the Kostadis Engine. They produce narration-support artifacts (per-character voice files, style-reference passages) for `session_doc.py` in the user's `CampaignGenerator` project. Edit them on their own terms; they do not share the Kostadis runners' invariants.

The Kostadis Engine skills are not independent — they form one layered architectural-audit pipeline. Understanding the layering is essential before editing any one of them, because the runner skills (`k-sequential`, `k-parallel`) duplicate lens prompts inline and must stay in sync with the standalone lens skills.

**L0 — ground truth (no analysis):**
- `k-preprocess` — "expert System Architect" exhaustive technical summary. Verbose, no inference, no compression. Its output is the shared input for every downstream lens.

**L1–L4 — analytical lenses, each standalone and each duplicated inside the runners:**
- `tribunal` (L1) — Kostadis Tribunal v10. PASS/FAIL verdicts on Truth Audit, Silicon Check, Atomicity, IDM, Entity Integrity. Asks: is the author a Script Scribe or an Architecturalist?
- `anti-gravity` (L2) — Anti-Gravity Engine v10.1. PASS/FAIL on Sovereign Identity (MOID killer), Intrinsic State (snapshot portability), Orphan Reconciliation (Brick Test).
- `lagrange` (L3) — First-principles constraint transformation. Not a critique — finds the hidden assumption making a problem hard and proposes a coordinate shift that makes it trivial. Socratic, not adversarial.
- `value-bridge` (L4) — Strategic Value Translator for Nutanix. Turns technical findings into board-level business language (Automation Ceiling, False Green Dashboard, Weekend Outage, etc.) with executive summary, pain pillars, SE trap questions, and a Nutanix pivot.

**Runners — orchestrate the lenses via the Agent tool:**
- `k-sequential` — L0 → L1 → L2 → L3 → L4 in a chain. Each lens receives L0 plus the **previous** lens's output. Use when each lens should build on the last.
- `k-parallel` — L0 runs alone, then L1/L2/L3/L4 spawn simultaneously as independent Agent calls, each seeing only L0. Use for uncontaminated per-lens verdicts.

**Invariants the runners rely on — do not break these when editing skills:**
1. **Every lens runs in its own Agent context.** Never combine lenses into one Agent call. L1 must not see L2's output in `k-parallel`. In `k-sequential` the chain is strictly `L0→L1→L2→L3→L4`, where each step sees L0 plus the immediately previous lens only.
2. **L0 is the shared contract.** Lens prompts assume L0 is exhaustive and uncompressed. If you loosen `k-preprocess`, downstream lenses will silently degrade.
3. **Disk layout is load-bearing.** Every lens and every runner writes to `~/kostadis-output/<slug>/` with these exact filenames: `l0.md`, `l1-tribunal.md`, `l2-anti-gravity.md`, `l3-lagrange.md`, `l4-value-bridge.md`, and (for runners) an assembled `full-report.md`. The per-lens files must not be deleted after assembly — `full-report.md` is an additional artifact, not a replacement.
4. **Console silence.** All lenses and runners respond with file paths and one-line status only. They must not dump lens content to the console. When editing a skill, preserve the "do not display to console" instruction.
5. **Slug derivation.** Runners and lenses derive a lowercase hyphenated slug from the input topic (e.g. `vcf9-supervisor`). Keep this consistent so sequential and parallel runs over the same input land in the same directory.
6. **Lens prompts are duplicated in the runners.** `k-sequential/SKILL.md` and `k-parallel/SKILL.md` contain their own condensed copies of the L1–L4 prompts. When you change a lens's core questions (e.g. the five Tribunal verdicts, the three Anti-Gravity checks), update the standalone skill **and** both runners in the same change, or the sequential/parallel outputs will diverge from a direct lens invocation.

## Agents (`claude/agents/`)

- `kostadis-architect.md` — forensic architectural review using the Kostadis Doctrine (Split-Brain, Optimistic Lies, Fragmented State, Infrastructure Proxy anti-patterns). Invoked via the `Agent` tool with `subagent_type: "kostadis-architect"`. Complementary to the standalone lens skills: the agent is on-demand and conversational, the skills write structured reports to disk.
- `ux-reviewer.md` — UX analysis agent for web frontends. Reads Vue/React/HTML source and produces a structured report with dimension scores and prioritised findings.

Agent files use Claude Code's subagent frontmatter format (name, description, tools, model). Edit in place; they are picked up on the next session.

## Working on skills

- Skills are discovered by filename: `claude/skills/<skill-name>/SKILL.md`. The frontmatter `description` is what Claude Code shows to the model when deciding whether the skill is relevant — keep it specific and trigger-word-rich.
- `allowed-tools` in frontmatter is an allowlist. The Kostadis runners need `Agent` (to spawn isolated lens contexts) plus `Bash`/`Write` (to create the output directory and write per-lens files). Standalone lenses typically only need `Bash`/`Write`.
- `argument-hint` is user-facing; `$ARGUMENTS` at the bottom of the skill body is where the user's invocation text gets substituted.
- There is nothing to "run" or "test" locally. To validate a change: symlink `claude/` into `~/.claude/` (or edit in place there), start a fresh Claude Code session, invoke the skill, and inspect the files written under `~/kostadis-output/<slug>/`.
