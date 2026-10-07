# Chapter 45 Run Notes — "Universal Basic Treasure"

Completed run: `~/phandalin-entity-scan/parts/ch45/` — 30 files written, verified on disk.

## Structure variance
- This chapter's body sections are `## <POV> — <Title>` (e.g. `## Brewbarry — Return to Phandalin`), NOT the `## NN.MM <POV> <date>` format seen elsewhere. No numeric sub-section IDs exist, so bullets carry no `(NN.MM)` citation prefixes — that convention only applies when the IDs exist.
- Lesson: read the chapter's actual heading format first; don't assume the documented one.

## Workflow that worked
1. Read full chapter (single read_file call, ~42KB fits).
2. Grep the registry directly (`grep -n "name: X" docs/entity_registry.yaml`) for each candidate entity name/alias instead of running the parser + matcher pipeline — fast and sufficient when authoring by hand from a single chapter.
3. Authored ALL entity bodies as Python string dict in ONE execute_code script looping file writes. Zero cleanup passes needed. This is now the preferred pattern for any per-chapter run, not just large ranges.

## Entities created with NO registry entry (naming judgment)
- `Brother Aldric Sunmantle.md` — registry has unrelated `Aldric Stone Path`; used full chapter name.
- `Perrin Alagondar.md` — registry mentions Perrin only inside Necklace of Fireballs note text.
- `Lord Neverember.md` — registry has Neverember-related entries but no person entry under this exact name.
- Registry has NO entries for: Elsa, Privy Council, UBT concept. Tuck appears (registry: `Tuck Stonehill`) but was left as a bullet inside Toblen Stonehill.md rather than a separate file (minor appearance only).
- Report these gaps/naming choices in the completion reply so merge/curation can reconcile.
