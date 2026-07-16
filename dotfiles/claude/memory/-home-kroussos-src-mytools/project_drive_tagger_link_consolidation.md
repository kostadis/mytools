---
name: project_drive_tagger_link_consolidation
description: "drive-tagger has a /drive-consolidate-links skill (link-relation counterpart of /drive-consolidate); relation drift comes from the MCP path, and antonym relations must not be auto-merged"
metadata: 
  node_type: memory
  type: project
  originSessionId: 8ea9a23f-0cdc-4d22-bb8f-33b6b523c1d2
---

drive-tagger's typed file-to-file edges (`graph.sqlite`) had the same
vocabulary-drift problem as category names: the controlled set is 5
(`supersedes, part-of, duplicate-of, references, related-to`) but the live graph
held 33 relations — 28 rogue types / 466 edges. Built (2026-07-04) the link
counterpart of [[project_drive_tagger_pass2_faceting]]'s `/drive-consolidate`:

- **Tool:** `src/drive_tagger/link_consolidate.py` (`collect_relations` /
  `apply_relations`) + `graph.merge_relations` (rewrite relation, dedup on
  `UNIQUE(src,dst,relation)`, idempotent) + CLI `consolidate collect-links` /
  `apply-links` + a `## Relations` table in the report.
- **Skill:** `/drive-consolidate-links` (dotfiles/claude/skills/…). Mirrors the
  5-phase category flow over relation *families*; reviews singletons too (they're
  rogue, not clean); vocabulary may EXPAND (promote a high-signal rogue like
  `complements`/`series-member` to canonical — don't roll everything up to the 5).

**Two non-obvious things to remember:**
1. **The drift source is the MCP agent path**, not the pipeline. `pipeline._apply`
   coerces unknown relations → `related-to`; `mcp_server.link_files` passes the
   LLM's raw relation through with no coercion. So the "stop regeneration"
   follow-up (not yet done) is: coerce `link_files` + share one allow-set +
   update the prompt — the link analog of the category prompt fix
   ([[project_drive_tagger_prompt_vs_consolidation]]).
2. **Directional antonyms must never be auto-merged.** String grouping puts
   `sequel-to` + `prequel-to` in one `confidence:high` family, but folding them
   onto one canonical *reverses* edge direction. `collect_relations` detects
   antonym families and emits `suggested_canonical: null` + a `warning`; the skill
   forces split or remap-to-non-directional. General lesson: string tightness ≠
   semantic safety.

**How to apply:** run `/drive-consolidate-links` for the interactive cleanup;
`collect-links` needs no embed prefix (reads only the graph), `apply-links` does
(regenerates reports → opens the store). Back up `graph.sqlite` before apply.
